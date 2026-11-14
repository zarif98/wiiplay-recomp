#include <cstdio>
#include "hle_stubs.h"
#include <cstdlib>
#include <algorithm>
#include "gx_internal.h"
#include "runtime_log.h"

extern "C" void __GXSetSUTexRegs();

// ============================================================================
// FIFO Write Helpers
// ============================================================================

extern "C" void GX_HLE_FIFO_WriteFloat(float val) {
    u32 raw; std::memcpy(&raw, &val, 4);
    try { HleFifoWrite(raw, 4); } catch (...) { RT_LOGF(RT_TAG_GX, "FIFO write float failed\n"); }
}

extern "C" void GX_HLE_FIFO_Write32(uint32_t val) { HleFifoWrite(val, 4); }
extern "C" void GX_HLE_FIFO_Write16(uint16_t val) { HleFifoWrite(static_cast<u32>(val), 2); }
extern "C" void GX_HLE_FIFO_Write8(uint8_t val) { HleFifoWrite(static_cast<u32>(val), 1); }

extern "C" void GX__SetDrawSync_8016ed08(uint32_t token) {
    (void)token;
    try { uint32_t gd = Memory::Read32(kGXDataPtrAddr); if (gd) {
        if (Memory::Read32(gd + 0x5FCu)) GX__SetDirtyState_8016ee78();
        Memory::Write16(gd + 2, 0);
    } } catch (...) {}
}

extern "C" void GX__SetDrawSync_8016e9fc(uint32_t token) { GX__SetDrawSync_8016ed08(token); }

// WII PLAY: takes the CpuContext so the guest stack pointer is current. The draw-sync callback runs
// right away (the HLE consumes draws in order, so the token is reached at once); with a plain-argument
// signature the shared context's r1 can be stale, and the callback's frame then overwrote live frames
// (saved r31 in the caller came back as 1).
extern "C" void GAME_GXSetDrawSync(CpuContext* ctx) {
    const uint32_t token = ctx ? (ctx->gpr[3] & 0xFFFFu) : 0u;
    constexpr uint32_t kGamePeRegPtrAddr = 0x8043BDF0u;  // Wii Play __peReg (r13-0x6CD0, GXTokenInterruptHandler)
    constexpr uint32_t kGamePeRegBlock = 0x80002F00u;    // low-memory debugger area; no exception vectors are installed
    try {
        Memory::Write32(kGamePeRegPtrAddr, kGamePeRegBlock);
        Memory::Write16(kGamePeRegBlock + 0xEu, static_cast<uint16_t>(token));
    } catch (const ::Memory::AccessViolation&) {}
    if (!ctx) return;
    uint32_t cb = 0;
    if (Memory::TryRead32(ctx->gpr[13] - 0x6C80u, cb) && cb != 0) {  // Wii Play TokenCB (r13-0x6C80)
        CpuContext tmp = *ctx;
        tmp.gpr[1] = (ctx->gpr[1] - 0x400u) & ~0xFu;  // fresh frame area below the caller's stack
        tmp.gpr[3] = token;
        // Interrupt context: the callback may wake threads, but must not switch away mid-call.
        OS_HLE_BeginDeferredGuestCallbacks();
        InvokeIndirectCpu(cb, &tmp);
        OS_HLE_EndDeferredGuestCallbacks();
    }
}
PPC_NATIVE_OVERRIDE_VOID(800DE9A8, GAME_GXSetDrawSync, (CpuContext* ctx), (ctx));

extern "C" void GX__FinishInterruptHandler_8016ed94() {
    try {
        uint32_t gd = Memory::Read32(kGXDataPtrAddr);
        if (gd) Memory::Write16(gd + 0x0Au, static_cast<uint16_t>(Memory::Read16(gd + 0x0Au) | 0x0008u));
        Memory::Write8(kGxDrawDoneFlagAddr, 1);
    } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800DED40, GX__FinishInterruptHandler_8016ed94, (), ());

// WII PLAY: GXDrawDone = GXSetDrawDone + wait. Draws are consumed in order, so the finish point is
// reached at once; do what Wii Play's GXFinishInterruptHandler (0x800DED40) does: set DrawDone, call the
// draw-done callback (r13-0x6C84; EGG's AsyncDisplay hands the copied XFB to VI from it) and wake
// FinishQueue. Takes the CpuContext so the callback runs on a current stack, in interrupt scope.
extern "C" void OSWakeupThread_HLE_801aaaa4(CpuContext* ctx);

extern "C" void GX__DrawDone_8016eab0() {
    try { Memory::Write8(kGxDrawDoneFlagAddr, 0); } catch (...) {}
    GXDrawDone(); GX__FinishInterruptHandler_8016ed94();
}

extern "C" void GX__DrawDone_WiiPlay(CpuContext* ctx) {
    try { Memory::Write8(kGxDrawDoneFlagAddr, 0); } catch (...) {}
    GXDrawDone();
    GX__FinishInterruptHandler_8016ed94();
    if (!ctx) return;
    uint32_t cb = 0;
    if (Memory::TryRead32(ctx->gpr[13] - 0x6C84u, cb) && cb != 0) {  // Wii Play DrawDoneCB
        CpuContext tmp = *ctx;
        tmp.gpr[1] = (ctx->gpr[1] - 0x400u) & ~0xFu;
        OS_HLE_BeginDeferredGuestCallbacks();
        InvokeIndirectCpu(cb, &tmp);
        OS_HLE_EndDeferredGuestCallbacks();
    }
    ctx->gpr[3] = ctx->gpr[13] - 0x6C90u;  // FinishQueue (0x8043BE30)
    OSWakeupThread_HLE_801aaaa4(ctx);
}
PPC_NATIVE_OVERRIDE_VOID(800DEA5C, GX__DrawDone_WiiPlay, (CpuContext* ctx), (ctx));

extern "C" void GX__PixModeSync_8016eb70() {
    try { uint32_t gd = Memory::Read32(kGXDataPtrAddr); if (gd) Memory::Write16(gd + 2, 0); } catch (...) {}
    GXPixModeSync();
}
/* WII PLAY: re-enabled (resolved by retarget_runtime.py) */
PPC_NATIVE_OVERRIDE_VOID(800DEB1C, GX__PixModeSync_8016eb70, (), ());

// ============================================================================
// Hardware Revision / Thread Query - No-ops
// ============================================================================

extern "C" void __GX__InitRevisionBits_8016b720() {}
PPC_NATIVE_OVERRIDE_VOID(800DB6CC, __GX__InitRevisionBits_8016b720, (), ());

// ============================================================================
// Texture State Management - Aurora handles internally
// ============================================================================

extern "C" void __GX__SetSUTexRegs_801712f0() {
    __GXSetSUTexRegs();
    try { uint32_t gd = Memory::Read32(kGXDataPtrAddr); if (gd) Memory::Write16(gd + 2, 0); } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800E1244, __GX__SetSUTexRegs_801712f0, (), ());

extern "C" void __GX__SetTmemConfig_80171458(uint32_t mode) {
    // TMEM layout configuration - Aurora manages internally
    (void)mode;
}
PPC_NATIVE_OVERRIDE_VOID(800E13AC, __GX__SetTmemConfig_80171458, (uint32_t mode), (mode));

extern "C" void __GX__FlushTextureState_80171c28() {
    // BP texture state flush - Aurora handles via API
    try { uint32_t gd = Memory::Read32(kGXDataPtrAddr); if (gd) Memory::Write16(gd + 2, 0); } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800E1B28, __GX__FlushTextureState_80171c28, (), ());

// ============================================================================
// Copy Configuration - No-ops for features Aurora doesn't use
// ============================================================================

extern "C" void GX__SetDispCopyFrame2Field_8016f5f8(uint32_t f) {
    GXSetDispCopyFrame2Field(f);
    try {
        const uint32_t gd = Memory::Read32(kGXDataPtrAddr);
        if (gd) {
            Memory::Write32(gd + 0x23Cu, (Memory::Read32(gd + 0x23Cu) & 0xFFFFCFFFu) | ((f & 3u) << 12));
            Memory::Write32(gd + 0x24Cu, Memory::Read32(gd + 0x24Cu) & 0xFFFFCFFFu);
        }
    } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800DF59C, GX__SetDispCopyFrame2Field_8016f5f8, (uint32_t f), (f));

extern "C" void GX__SetCopyClamp_8016f618(uint32_t c) {
    GXSetCopyClamp(static_cast<GXFBClamp>(c));
    try {
        const uint32_t gd = Memory::Read32(kGXDataPtrAddr);
        if (gd) {
            const uint32_t clamp = c & 3u;
            Memory::Write32(gd + 0x23Cu, (Memory::Read32(gd + 0x23Cu) & 0xFFFFFFFCu) | clamp);
            Memory::Write32(gd + 0x24Cu, (Memory::Read32(gd + 0x24Cu) & 0xFFFFFFFCu) | clamp);
        }
    } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800DF5BC, GX__SetCopyClamp_8016f618, (uint32_t c), (c));

extern "C" void GX__ClearBoundingBox_8016fecc() {
    GameBBoxClear();
    GXClearBoundingBox();
    try {
        const uint32_t gd = Memory::Read32(kGXDataPtrAddr);
        if (gd) Memory::Write16(gd + 2, 0);
    } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800DFE70, GX__ClearBoundingBox_8016fecc, (), ());

extern "C" void GX__ReadBoundingBox_GAME(uint32_t leftPtr, uint32_t topPtr, uint32_t rightPtr, uint32_t bottomPtr) {
    uint16_t l = 0, t = 0, r = 0, b = 0;
    GameBBoxRead(l, t, r, b);
    {   // union with Aurora's CPU-projected box, which also sees display-list and FIFO draws
        u16 al = 1023, ar = 0, at = 1023, ab = 0;
        ::GXReadBoundingBox(&al, &ar, &at, &ab);
        if (al <= ar && at <= ab) {
            if (l > r || t > b) { l = al; r = ar; t = at; b = ab; }
            else { l = std::min<uint16_t>(l, al); r = std::max<uint16_t>(r, ar); t = std::min<uint16_t>(t, at); b = std::max<uint16_t>(b, ab); }
        }
    }
    { static int n = 0; if (n++ < 40) RT_LOGF(RT_TAG_GX, "[bbox] read l=%u t=%u r=%u b=%u\n", l, t, r, b); }
    try {
        if (leftPtr) Memory::Write16(leftPtr, l);
        if (topPtr) Memory::Write16(topPtr, t);
        if (rightPtr) Memory::Write16(rightPtr, r);
        if (bottomPtr) Memory::Write16(bottomPtr, b);
    } catch (const Memory::AccessViolation&) {
    }
}
#if 0 /* WARIO-TODO: falta la direccion de GXReadBoundingBox (base 8028E26C) */
PPC_NATIVE_OVERRIDE_VOID(817F0050, GX__ReadBoundingBox_GAME,
                         (uint32_t leftPtr, uint32_t topPtr, uint32_t rightPtr, uint32_t bottomPtr),
                         (leftPtr, topPtr, rightPtr, bottomPtr));
#endif

// ============================================================================
// FIFO/State Management - No-ops
// ============================================================================

extern "C" void GX__SetDirtyState_8016ee78() {
    try { uint32_t gd = Memory::Read32(kGXDataPtrAddr); if (gd) Memory::Write32(gd + 0x5FCu, 0); } catch (...) {}
}
PPC_NATIVE_OVERRIDE_VOID(800DEE24, GX__SetDirtyState_8016ee78, (), ());

extern "C" void GX__ResetWriteGatherPipe_8016e6b0() {
    // WPAR reset - not needed on host
}
#if 0 /* WARIO-TODO: falta la direccion de GXResetWriteGatherPipe (base 8028C944) */
PPC_NATIVE_OVERRIDE_VOID(817F0054, GX__ResetWriteGatherPipe_8016e6b0, (), ());
#endif
