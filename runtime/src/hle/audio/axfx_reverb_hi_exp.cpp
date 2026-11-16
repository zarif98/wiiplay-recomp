// WII PLAY: native AXFXReverbHiExpCallback (0x80107550), the SDK's high-quality reverb.
//
// The game runs it every 5 ms audio frame on 3 channels x 96 samples. Translated, every float op
// went through PowerPC single-rounding helpers and every delay-line access through guest memory
// checks: ~0.65 ms per video frame, the single most expensive guest function in Tanks!. This is a
// line-by-line transcription of the PowerPC (see the offsets below), in the same operation order
// and with FMA contraction off, so it computes what the console computes.
//
// AXFX_REVERBHI_EXP fields used (offsets into the struct, big-endian guest memory):
//   0x00 earlyLine[3]      0x0C earlyPos[3]       0x18 earlyLength       0x20 earlyCoef[3]
//   0x2C preDelayLine[3]   0x38 preDelayPos       0x3C preDelayLength (0 = no pre-delay)
//   0x44 combLine[3][3]    0x68 combPos[3]        0x74 combLength[3]     0x8C combCoef[3]
//   0x98 allpassLine[3][2] 0xB0 allpassPos[2]     0xB8 allpassLength[2]
//   0xC8 lastAllpassLine[3] 0xD4 lastAllpassPos[3] 0xE0 lastAllpassLength[3]
//   0xF8 allpassCoef       0xFC lastLpfOut[3]     0x108 lpfCoef          0x10C tempDisableFX
//   0x12C crosstalk        0x134 fusedGain        0x138 busIn            0x13C busOut
//   0x140 outGain          0x144 sendGain
#include "hle_stubs.h"
#include "memory.h"

#include <cmath>
#include <cstdint>
#include <cstring>

#pragma clang fp contract(off)

namespace {

constexpr uint32_t kSamples = 96;  // one AX frame

inline uint32_t Be32(const uint8_t* p) {
    uint32_t v;
    std::memcpy(&v, p, 4);
    return __builtin_bswap32(v);
}
inline void PutBe32(uint8_t* p, uint32_t v) {
    v = __builtin_bswap32(v);
    std::memcpy(p, &v, 4);
}
inline float BeF(const uint8_t* p) {
    const uint32_t bits = Be32(p);
    float f;
    std::memcpy(&f, &bits, 4);
    return f;
}
inline void PutBeF(uint8_t* p, float f) {
    uint32_t bits;
    std::memcpy(&bits, &f, 4);
    PutBe32(p, bits);
}

// fctiwz: truncate toward zero, saturating; NaN gives INT_MIN like the hardware.
inline int32_t Fctiwz(float f) {
    if (std::isnan(f)) return INT32_MIN;
    if (f >= 2147483648.0f) return INT32_MAX;
    if (f < -2147483648.0f) return INT32_MIN;
    return static_cast<int32_t>(f);
}

// A guest float array as host memory, `count` elements (bounds-checked once per call).
struct Line {
    uint8_t* p = nullptr;
    float at(uint32_t i) const { return BeF(p + i * 4); }
    void set(uint32_t i, float v) const { PutBeF(p + i * 4, v); }
};

bool Resolve(uint32_t addr, uint32_t count, Line& out) {
    if (addr == 0 || count == 0) return false;
    out.p = Memory::GetPointer(addr, static_cast<size_t>(count) * 4);
    return out.p != nullptr;
}

}  // namespace

extern "C" void AXFXReverbHiExpCallback_HLE(uint32_t bufferUpdate, uint32_t reverb) {
    uint8_t* r = Memory::GetPointer(reverb, 0x148);
    if (r == nullptr) return;
    const auto u32 = [&](uint32_t off) { return Be32(r + off); };
    const auto f32 = [&](uint32_t off) { return BeF(r + off); };

    // tempDisableFX: skip this frame and clear bit 1 (rlwinm r0,r0,0,31,29).
    if (const uint32_t disable = u32(0x10C); disable != 0) {
        PutBe32(r + 0x10C, disable & ~2u);
        return;
    }

    // Channel buffers (int32, 96 each): the update's three, plus the optional buses.
    uint8_t* update = Memory::GetPointer(bufferUpdate, 12);
    if (update == nullptr) return;
    uint8_t* data[3];
    for (int ch = 0; ch < 3; ++ch) {
        data[ch] = Memory::GetPointer(Be32(update + ch * 4), kSamples * 4);
        if (data[ch] == nullptr) return;
    }
    const uint32_t busInAddr = u32(0x138), busOutAddr = u32(0x13C);
    uint8_t* busIn[3] = {};
    uint8_t* busOut[3] = {};
    for (int ch = 0; ch < 3; ++ch) {
        if (busInAddr != 0) {
            uint8_t* bus = Memory::GetPointer(busInAddr, 12);
            if (bus == nullptr || !(busIn[ch] = Memory::GetPointer(Be32(bus + ch * 4), kSamples * 4))) return;
        }
        if (busOutAddr != 0) {
            uint8_t* bus = Memory::GetPointer(busOutAddr, 12);
            if (bus == nullptr || !(busOut[ch] = Memory::GetPointer(Be32(bus + ch * 4), kSamples * 4))) return;
        }
    }

    // Positions and lengths.
    uint32_t earlyPos[3] = {u32(0x0C), u32(0x10), u32(0x14)};
    const uint32_t earlyLength = u32(0x18);
    uint32_t preDelayPos = u32(0x38);
    const uint32_t preDelayLength = u32(0x3C);
    uint32_t combPos[3] = {u32(0x68), u32(0x6C), u32(0x70)};
    const uint32_t combLength[3] = {u32(0x74), u32(0x78), u32(0x7C)};
    uint32_t allpassPos[2] = {u32(0xB0), u32(0xB4)};
    const uint32_t allpassLength[2] = {u32(0xB8), u32(0xBC)};
    uint32_t lastAllpassPos[3] = {u32(0xD4), u32(0xD8), u32(0xDC)};
    const uint32_t lastAllpassLength[3] = {u32(0xE0), u32(0xE4), u32(0xE8)};
    if (earlyLength == 0) return;

    // Delay lines, each resolved over its whole length (positions stay below the lengths).
    Line early[3], preDelay[3], comb[3][3], allpass[3][2], lastAllpass[3];
    for (int ch = 0; ch < 3; ++ch) {
        if (!Resolve(u32(0x00 + ch * 4), earlyLength, early[ch])) return;
        if (preDelayLength != 0 && !Resolve(u32(0x2C + ch * 4), preDelayLength, preDelay[ch])) return;
        for (int k = 0; k < 3; ++k)
            if (!Resolve(u32(0x44 + ch * 12 + k * 4), combLength[k], comb[ch][k])) return;
        for (int k = 0; k < 2; ++k)
            if (!Resolve(u32(0x98 + ch * 8 + k * 4), allpassLength[k], allpass[ch][k])) return;
        if (!Resolve(u32(0xC8 + ch * 4), lastAllpassLength[ch], lastAllpass[ch])) return;
    }

    const float earlyCoef[3] = {f32(0x20), f32(0x24), f32(0x28)};
    const float combCoef[3] = {f32(0x8C), f32(0x90), f32(0x94)};
    const float ap = f32(0xF8);
    const float lpf = f32(0x108);
    const float lpfInv = 1.0f - lpf;
    const float fused = 0.6f * f32(0x134);
    const float crosstalk = 0.5f * f32(0x12C);
    const float outGain = f32(0x140), sendGain = f32(0x144);
    float lastLpfOut[3] = {f32(0xFC), f32(0x100), f32(0x104)};

    for (uint32_t i = 0; i < kSamples; ++i) {
        float mixed[3];
        for (int ch = 0; ch < 3; ++ch) {
            int32_t sample = static_cast<int32_t>(Be32(data[ch] + i * 4));
            if (busIn[ch] != nullptr) sample += static_cast<int32_t>(Be32(busIn[ch] + i * 4));
            const float in = static_cast<float>(sample);

            // Early reflections: (c0*e0 + c1*e1) + c2*e2, summed as the PowerPC does.
            const float e0 = earlyCoef[0] * early[ch].at(earlyPos[0]);
            const float e1 = earlyCoef[1] * early[ch].at(earlyPos[1]);
            const float e2 = earlyCoef[2] * early[ch].at(earlyPos[2]);
            const float earlyOut = e2 + (e0 + e1);

            float delayed = in;
            if (preDelayLength != 0) {
                delayed = preDelay[ch].at(preDelayPos);
                preDelay[ch].set(preDelayPos, in);
            }

            float combSum = 0.0f;
            for (int k = 0; k < 3; ++k) {
                const float x = comb[ch][k].at(combPos[k]);
                const float fb = x * combCoef[k];
                combSum = combSum + x;
                comb[ch][k].set(combPos[k], delayed + fb);
            }

            const float a0 = allpass[ch][0].at(allpassPos[0]);
            float w = combSum + a0 * ap;
            allpass[ch][0].set(allpassPos[0], w);
            const float out0 = a0 - w * ap;

            const float a1 = allpass[ch][1].at(allpassPos[1]);
            w = out0 + a1 * ap;
            const float wAp = w * ap;
            allpass[ch][1].set(allpassPos[1], w);
            const float out1 = a1 - wAp;

            const float lpOut = lpfInv * out1 + lpf * lastLpfOut[ch];
            lastLpfOut[ch] = lpOut;

            const float l = lastAllpass[ch].at(lastAllpassPos[ch]);
            w = lpOut + l * ap;
            lastAllpass[ch].set(lastAllpassPos[ch], w);
            const float tail = l - w * ap;
            if (++lastAllpassPos[ch] >= lastAllpassLength[ch]) lastAllpassPos[ch] = 0;

            mixed[ch] = tail * fused + earlyOut;
        }

        // Crosstalk: each channel plus the other two, scaled.
        const float o0 = mixed[0] + (mixed[1] + mixed[2]) * crosstalk;
        const float o1 = mixed[1] + (mixed[0] + mixed[2]) * crosstalk;
        const float o2 = mixed[2] + (mixed[0] + mixed[1]) * crosstalk;
        const float out[3] = {o0, o1, o2};
        for (int ch = 0; ch < 3; ++ch) {
            PutBe32(data[ch] + i * 4, static_cast<uint32_t>(Fctiwz(out[ch] * outGain)));
            if (busOut[ch] != nullptr) PutBe32(busOut[ch] + i * 4, static_cast<uint32_t>(Fctiwz(out[ch] * sendGain)));
        }

        for (uint32_t& p : earlyPos)
            if (++p >= earlyLength) p = 0;
        if (preDelayLength != 0 && ++preDelayPos >= preDelayLength) preDelayPos = 0;
        for (int k = 0; k < 3; ++k)
            if (++combPos[k] >= combLength[k]) combPos[k] = 0;
        for (int k = 0; k < 2; ++k)
            if (++allpassPos[k] >= allpassLength[k]) allpassPos[k] = 0;
    }

    for (int k = 0; k < 3; ++k) {
        PutBe32(r + 0x0C + k * 4, earlyPos[k]);
        PutBe32(r + 0x68 + k * 4, combPos[k]);
        PutBe32(r + 0xD4 + k * 4, lastAllpassPos[k]);
        PutBeF(r + 0xFC + k * 4, lastLpfOut[k]);
    }
    PutBe32(r + 0x38, preDelayPos);
    PutBe32(r + 0xB0, allpassPos[0]);
    PutBe32(r + 0xB4, allpassPos[1]);
}
PPC_NATIVE_OVERRIDE_VOID(80107550, AXFXReverbHiExpCallback_HLE, (uint32_t bufferUpdate, uint32_t reverb),
                         (bufferUpdate, reverb));
