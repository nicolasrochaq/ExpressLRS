#pragma once
/*
 * tankmix.h - Tank (differential) mixing in the ExpressLRS TX module (T8L)
 *
 * Mixes throttle + steering into left/right BEFORE transmitting.
 * The receiver keeps running stock ELRS (failsafe untouched).
 *
 * Usage in src/src/tx_main.cpp:
 *   #include "tankmix.h"
 *   ...
 *   OtaPackChannelData(&otaPkt, tankMixApply(ChannelData), ...);
 *
 * Channel indices are 0-based: Ch1 = 0, Ch2 = 1, Ch3 = 2 ...
 * Everything can be overridden in user_defines.txt, e.g. -DTANKMIX_THR_IN=2
 *
 * NOTE: the state lives in `static` variables in this header. Include it in
 * ONE .cpp only (tx_main.cpp). Each extra translation unit would get its own
 * independent copy of the state and buffer.
 */

#include <stdint.h>

#ifndef ICACHE_RAM_ATTR
#define ICACHE_RAM_ATTR
#endif

// CRSF_NUM_CHANNELS comes from ELRS common.h: include this file AFTER it.

// ---------- Configuration ----------
#ifndef TANKMIX_THR_IN
#define TANKMIX_THR_IN   1   // throttle input channel (Ch2)
#endif
#ifndef TANKMIX_STR_IN
#define TANKMIX_STR_IN   0   // steering input channel (Ch1)
#endif
#ifndef TANKMIX_LEFT_OUT
#define TANKMIX_LEFT_OUT 0   // left motor output (Ch1 -> receiver output 1)
#endif
#ifndef TANKMIX_RIGHT_OUT
#define TANKMIX_RIGHT_OUT 1  // right motor output (Ch2 -> receiver output 2)
#endif
#ifndef TANKMIX_SW_CH
#define TANKMIX_SW_CH    5   // mix on/off switch (Ch6)
#endif
#ifndef TANKMIX_STEER_PCT
#define TANKMIX_STEER_PCT 70 // steering weight in the mix (0-100)
#endif
#ifndef TANKMIX_INV_LEFT
#define TANKMIX_INV_LEFT  0  // 1 = reverse left motor
#endif
#ifndef TANKMIX_INV_RIGHT
#define TANKMIX_INV_RIGHT 1  // 1 = reverse right motor (mirrored motors in the chassis)
#endif
#ifndef TANKMIX_INV_THR
#define TANKMIX_INV_THR   1  // 1 = reverse forward/backward (turning unchanged)
#endif
#ifndef TANKMIX_INV_STEER
#define TANKMIX_INV_STEER 0  // 1 = reverse turning direction
#endif
#ifndef TANKMIX_OUT_DB
// Output deadband (CRSF units; 16 ~= 10 us). Below this the output is set
// exactly to neutral, so the ESC doesn't creep near center.
#define TANKMIX_OUT_DB 16
#endif
#ifndef TANKMIX_WEAPON_CH
#define TANKMIX_WEAPON_CH 2  // weapon channel (Ch3) - the mix must never write to it
#endif
#ifndef TANKMIX_CENTER_DB
// Deadband (CRSF units, ~4.9% of travel) for toggling the switch state.
// Toggling only happens with BOTH input sticks centered, so both must be
// self-centering. If throttle is moved to a ratcheted stick (e.g. left
// vertical in mode 2), the switch silently stops working.
#define TANKMIX_CENTER_DB 40
#endif
// -----------------------------------

// ELRS arm channel (Ch5) - never use as output or switch
#define TANKMIX_ARM_CH 4

// ---------- Compile-time checks ----------
static_assert(TANKMIX_THR_IN >= 0 && TANKMIX_THR_IN < 16, "TANKMIX_THR_IN out of range");
static_assert(TANKMIX_STR_IN >= 0 && TANKMIX_STR_IN < 16, "TANKMIX_STR_IN out of range");
static_assert(TANKMIX_LEFT_OUT >= 0 && TANKMIX_LEFT_OUT < 16, "TANKMIX_LEFT_OUT out of range");
static_assert(TANKMIX_RIGHT_OUT >= 0 && TANKMIX_RIGHT_OUT < 16, "TANKMIX_RIGHT_OUT out of range");
static_assert(TANKMIX_SW_CH >= 0 && TANKMIX_SW_CH < 16, "TANKMIX_SW_CH out of range");
static_assert(TANKMIX_THR_IN != TANKMIX_STR_IN, "throttle and steering on the same channel");
static_assert(TANKMIX_LEFT_OUT != TANKMIX_RIGHT_OUT, "both outputs on the same channel");
static_assert(TANKMIX_LEFT_OUT != TANKMIX_WEAPON_CH && TANKMIX_RIGHT_OUT != TANKMIX_WEAPON_CH,
              "mix output on the WEAPON channel");
static_assert(TANKMIX_LEFT_OUT != TANKMIX_ARM_CH && TANKMIX_RIGHT_OUT != TANKMIX_ARM_CH,
              "mix output on the ELRS arm channel (Ch5)");
static_assert(TANKMIX_SW_CH != TANKMIX_ARM_CH && TANKMIX_SW_CH != TANKMIX_WEAPON_CH,
              "mix switch on the arm or weapon channel");
static_assert(TANKMIX_SW_CH != TANKMIX_LEFT_OUT && TANKMIX_SW_CH != TANKMIX_RIGHT_OUT &&
              TANKMIX_SW_CH != TANKMIX_THR_IN && TANKMIX_SW_CH != TANKMIX_STR_IN,
              "mix switch on a drive channel");
static_assert(TANKMIX_OUT_DB >= 0 && TANKMIX_OUT_DB < 200, "TANKMIX_OUT_DB out of range");
static_assert(TANKMIX_STEER_PCT >= 0 && TANKMIX_STEER_PCT <= 100, "TANKMIX_STEER_PCT must be 0-100");

// 11-bit CRSF range: 172..1811, center 992
#define TANKMIX_MID   992
#define TANKMIX_HALF  819
#define TANKMIX_MIN   (TANKMIX_MID - TANKMIX_HALF)
#define TANKMIX_MAX   (TANKMIX_MID + TANKMIX_HALF)
#define TANKMIX_SW_ON 1400   // switch above this = mix on

static uint32_t tankMixBuf[CRSF_NUM_CHANNELS];
static bool tankMixActive = false;
// Only allow turning on after the switch has been seen LOW at least once.
// Protects against an unassigned/stuck-high channel enabling the mix by itself.
static bool tankMixSwSeenLow = false;

static inline ICACHE_RAM_ATTR int32_t tankMixClamp(int32_t v)
{
    if (v < TANKMIX_MIN) return TANKMIX_MIN;
    if (v > TANKMIX_MAX) return TANKMIX_MAX;
    return v;
}

// Takes the raw channels from the handset and returns a COPY with the mix applied.
// Never modifies the original array (avoids mixing the same frame twice).
static ICACHE_RAM_ATTR uint32_t *tankMixApply(const uint32_t *in)
{
    for (int i = 0; i < CRSF_NUM_CHANNELS; i++)
        tankMixBuf[i] = in[i];

    int32_t thr = (int32_t)in[TANKMIX_THR_IN] - TANKMIX_MID;
    int32_t str = (int32_t)in[TANKMIX_STR_IN] - TANKMIX_MID;

    // Only toggle on/off with the sticks centered,
    // so the robot doesn't jerk when the switch is flipped.
    bool swHigh = in[TANKMIX_SW_CH] > TANKMIX_SW_ON;
    if (!swHigh)
        tankMixSwSeenLow = true;
    bool wantOn = swHigh && tankMixSwSeenLow;
    if (wantOn != tankMixActive)
    {
        bool centered = (thr > -TANKMIX_CENTER_DB && thr < TANKMIX_CENTER_DB) &&
                        (str > -TANKMIX_CENTER_DB && str < TANKMIX_CENTER_DB);
        if (centered)
            tankMixActive = wantOn;
    }

    if (!tankMixActive)
        return tankMixBuf;   // pass everything through

    if (TANKMIX_INV_THR)   thr = -thr;
    if (TANKMIX_INV_STEER) str = -str;
    str = str * TANKMIX_STEER_PCT / 100;

    int32_t left  = thr + str;
    int32_t right = thr - str;

    // Proportional saturation: keeps the ratio between both sides
    int32_t aL = left  < 0 ? -left  : left;
    int32_t aR = right < 0 ? -right : right;
    int32_t peak = aL > aR ? aL : aR;
    if (peak > TANKMIX_HALF)
    {
        left  = left  * TANKMIX_HALF / peak;
        right = right * TANKMIX_HALF / peak;
    }

    if (left  > -TANKMIX_OUT_DB && left  < TANKMIX_OUT_DB) left  = 0;
    if (right > -TANKMIX_OUT_DB && right < TANKMIX_OUT_DB) right = 0;

    if (TANKMIX_INV_LEFT)  left  = -left;
    if (TANKMIX_INV_RIGHT) right = -right;

    tankMixBuf[TANKMIX_LEFT_OUT]  = (uint32_t)tankMixClamp(TANKMIX_MID + left);
    tankMixBuf[TANKMIX_RIGHT_OUT] = (uint32_t)tankMixClamp(TANKMIX_MID + right);
    return tankMixBuf;
}
