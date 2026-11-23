# Tank mixing in the TX module (RadioMaster T8L)

A fork of ExpressLRS **3.6.2** that does tank (differential) mixing **inside the transmitter's ELRS module**, right before transmitting. Built for the RadioMaster T8L, which has no screen or mixer menu, driving a beetleweight combat robot with an ER5C-i receiver.

The receiver keeps running stock ELRS. Its failsafe is unchanged.

## What changes

- `src/include/tankmix.h`: the `tankMixApply()` function, which takes the handset channels and returns a **copy** with the mix applied
- `src/src/tx_main.cpp`: includes the header and passes `tankMixApply(ChannelData)` to `OtaPackChannelData()`

## Default configuration

| What | Channel | Define |
|---|---|---|
| Throttle (input) | Ch2 – right stick vertical | `TANKMIX_THR_IN=1` |
| Steering (input) | Ch1 – right stick horizontal | `TANKMIX_STR_IN=0` |
| Left motor (output) | Ch1 | `TANKMIX_LEFT_OUT=0` |
| Right motor (output) | Ch2 | `TANKMIX_RIGHT_OUT=1` |
| On/off switch | Ch6 (above ~1750 µs) | `TANKMIX_SW_CH=5` |
| Weapon (protected) | Ch3 | `TANKMIX_WEAPON_CH=2` |
| Steering weight | 70% | `TANKMIX_STEER_PCT=70` |
| Reverse left/right motor | right reversed | `TANKMIX_INV_LEFT=0`, `TANKMIX_INV_RIGHT=1` |
| Reverse forward/backward | on | `TANKMIX_INV_THR=1` |
| Reverse turning | off | `TANKMIX_INV_STEER=0` |
| Output deadband | 16 (~10 µs) | `TANKMIX_OUT_DB=16` |

Channel indices are 0-based (Ch1 = 0). Channels that are not mix outputs pass through unchanged.

## Safety

- The build **fails** if a mix output lands on the weapon channel, on Ch5 (the ELRS arm channel) or on the same channel as the other output
- The switch only changes the mix state with both input sticks centered, so the robot doesn't jerk. Both sticks must be self-centering
- The mix can only turn on after the switch has been seen low at least once. This protects against a channel stuck high
- The mix starts off when the module powers up
- Set the receiver failsafe to **set position at center** or **no pulses**, never "last position"

## Build and flash

1. ExpressLRS Configurator → Settings → **Advanced mode**
2. Firmware → **Local**, pointing to this repository's `src` folder
3. Device: RadioMaster 2.4 GHz → **RadioMaster T8L Internal 2.4GHz TX**
4. Method: **WiFi**. Use the same regulatory domain and binding phrase as the receiver
5. Enable the module's WiFi from the T8L Web UI, connect the PC to its network and click **Flash** (with "Force flash" unchecked)

Updating the T8L's ELRS from the Web UI erases the mod.

## Bench test

Do this with the wheels off the ground and the weapon disconnected:

1. Mix off: Ch1 and Ch2 pass straight through
2. Mix on: stick forward → robot moves forward; stick right → robot turns right
3. Sticks centered: no motor moves
4. Turn and switch the radio off mid-turn: the motors stop and the weapon shuts off
