# Tank mixing in the TX module (RadioMaster T8L)

This fork of ExpressLRS **3.6.2** adds **tank (differential) mixing inside the transmitter's ELRS module**. The module takes throttle and steering from the radio, turns them into left and right motor commands, and only then sends them over the air. The receiver gets channels that are already mixed.

## Why this exists

Tank-drive robots (and boats, tracked vehicles, etc.) need a mix: pushing the stick forward must drive both motors forward, and pushing it sideways must drive them in opposite directions. Normally that mix is done in one of two places:

- **In the radio:** EdgeTX radios have a mixer menu. The **RadioMaster T8L has no screen and no mixer** — its Web UI only offers endpoints, reverse and channel mapping.
- **In the robot:** an external mixer board between the receiver and the ESCs. It works, but it is one more part to buy, wire, fit and break inside a robot that gets hit.

The **stock ELRS receiver firmware has no mixing either**, and a receiver-side mixer was proposed to ELRS and declined.

The T8L's internal RF module, however, runs regular open-source ExpressLRS. This fork puts the mix there, so a T8L can drive a tank-steer robot with **no external mixer** and a **stock receiver**.

## Tested setup

| Part | Model |
|---|---|
| Radio | RadioMaster T8L, internal ELRS module (ESP8285) |
| TX firmware | This fork (ExpressLRS 3.6.2 + tank mix), target `radiomaster.tx_2400.t8l` |
| Receiver | RadioMaster ER5C-i, stock ExpressLRS 3.6.2 |
| Robot | Beetleweight combat robot, 2 brushless drive motors + 1 weapon motor |

It should work with any ELRS 3.6.x receiver, since the receiver only sees normal channels.

## How it works

```
T8L sticks/switches ──CRSF──> ELRS TX module ──────────────── 2.4 GHz ───> receiver ──PWM──> ESCs
                              │                         │
                              │  ChannelData[16]        │  OTA packet
                              │        │                │
                              │  tankMixApply() ────────┘
                              │   (copy + mix Ch1/Ch2)
```

Every time the module builds an RC packet, `tankMixApply()`:

1. Copies all 16 channels (the original array is never modified, so a frame is never mixed twice)
2. Reads throttle `T` and steering `S` relative to center (CRSF 992)
3. If the mix is **off**, returns the copy unchanged (pure pass-through)
4. If the mix is **on**, computes:
   ```
   S'    = S * STEER_PCT / 100
   left  = T + S'
   right = T - S'
   ```
5. If either side goes past full travel, **scales both down by the same factor**, so the ratio between the sides (and the turn) is kept instead of being flattened by clipping
6. Applies a small output deadband and the configured reversals
7. Writes `left` and `right` to their output channels. **Every other channel, including the weapon, passes through untouched**

## Default channel layout

| What | Channel | Notes |
|---|---|---|
| Steering (input) | Ch1 | right stick horizontal |
| Throttle (input) | Ch2 | right stick vertical (self-centering) |
| Left motor (output) | Ch1 | → receiver output 1 |
| Right motor (output) | Ch2 | → receiver output 2 |
| Weapon | Ch3 | passes through, the mix can never write to it |
| ELRS arm | Ch5 | untouched |
| Mix on/off switch | Ch6 | on above ~1750 µs |

With these defaults, the whole drive is on the right stick and the weapon stays on its own channel.

## Configuration

All options are `#define`s at the top of `src/include/tankmix.h`. The simplest way to change them is to **edit the default values there** and rebuild.

| Define | Default | What it does |
|---|---|---|
| `TANKMIX_THR_IN` | `1` (Ch2) | Throttle input channel |
| `TANKMIX_STR_IN` | `0` (Ch1) | Steering input channel |
| `TANKMIX_LEFT_OUT` | `0` (Ch1) | Left motor output channel |
| `TANKMIX_RIGHT_OUT` | `1` (Ch2) | Right motor output channel |
| `TANKMIX_SW_CH` | `5` (Ch6) | Mix on/off switch channel |
| `TANKMIX_WEAPON_CH` | `2` (Ch3) | Weapon channel (protected) |
| `TANKMIX_STEER_PCT` | `70` | How strong steering is in the mix (0–100). Lower = gentler turns |
| `TANKMIX_INV_LEFT` | `0` | `1` reverses the left motor |
| `TANKMIX_INV_RIGHT` | `1` | `1` reverses the right motor (motors are usually mirrored in the chassis) |
| `TANKMIX_INV_THR` | `1` | `1` swaps forward and backward without changing turning |
| `TANKMIX_INV_STEER` | `0` | `1` swaps left and right turns without changing forward |
| `TANKMIX_OUT_DB` | `16` (~10 µs) | Output deadband: outputs this close to center are set exactly to neutral |
| `TANKMIX_CENTER_DB` | `40` (~5%) | How centered the sticks must be for the switch to toggle the mix |

Channel indices are **0-based** (Ch1 = 0, Ch2 = 1, ...).

### Getting the directions right

The defaults match the tested robot. On a different chassis, test with the wheels in the air and adjust:

| Symptom | Fix |
|---|---|
| Stick forward makes the robot **spin**, stick sideways makes it **drive** | One motor is mirrored: toggle `TANKMIX_INV_LEFT` or `TANKMIX_INV_RIGHT` |
| Forward and backward are swapped, turning is correct | Toggle `TANKMIX_INV_THR` |
| Turning is swapped, forward is correct | Toggle `TANKMIX_INV_STEER` |
| Everything is backwards | Toggle `TANKMIX_INV_THR` and `TANKMIX_INV_STEER` |
| A motor creeps with the sticks centered | Recalibrate the ESC neutral, or raise `TANKMIX_OUT_DB` (e.g. `30`) |
| Turning is too twitchy | Lower `TANKMIX_STEER_PCT` (e.g. `50`) |

## Safety

Combat robots carry dangerous weapons, so the mix is deliberately conservative:

- **The weapon channel is protected at compile time.** The build fails if a mix output is set to the weapon channel, to Ch5 (ELRS arm) or to the same channel as the other output
- **The mix starts off** every time the module powers up
- **The switch must be seen low at least once** before the mix can turn on. An unassigned or stuck-high switch channel can't enable the mix by itself
- **The mix only toggles with both sticks centered**, so flipping the switch while driving can't make the robot jump. This is also why both input sticks must be self-centering: on a ratcheted throttle stick the switch would never toggle
- **The receiver failsafe is unchanged.** Set it to **set position at center** or **no pulses**, never **last position**. With "last position", losing the link mid-turn would leave both motors spinning in opposite directions

## Build and flash

You need the [ExpressLRS Configurator](https://github.com/ExpressLRS/ExpressLRS-Configurator/releases) and this repository cloned locally.

1. Configurator → Settings → enable **Advanced mode**
2. Firmware source → **Local**, pointing to this repository's `src` folder
3. Device category **RadioMaster 2.4 GHz** → device **RadioMaster T8L Internal 2.4GHz TX**
4. Flashing method **WiFi**
5. Set the **same regulatory domain and binding phrase** as your receiver, otherwise they won't bind
6. On the T8L Web UI, enable the module's WiFi. Connect the PC to the module's network
7. Click **Flash** with **Force flash unchecked**: the module rejects firmware for the wrong target

To go back to stock, flash the official ExpressLRS release of the same version the same way.

> Updating the T8L's ELRS module from the RadioMaster Web UI replaces it with stock firmware and **removes the mix**.

## Bench test

Always test with the **wheels off the ground** and the **weapon disconnected**:

1. **Mix off** (switch low): Ch1 and Ch2 behave exactly as without the mod
2. **Mix on** (sticks centered, switch high): stick forward → robot drives forward; stick right → robot turns right
3. **Sticks centered:** no motor moves
4. **Failsafe:** drive in a turn and switch the radio off mid-turn. Both motors must stop and the weapon must shut off

### Checking the outputs without the robot

`tools/tankmix_tester/tankmix_tester.ino` is an ESP32-S3 sketch that reads receiver outputs 1–3 and prints the pulse widths and what the robot would do ("FORWARD", "SPIN RIGHT", ...) on the serial monitor. The ESP powers the receiver over USB, so no robot battery is needed. Wiring and usage are in the sketch header.

The sketch can't know how your motors are mounted, so set `LEFT_SIGN` / `RIGHT_SIGN` at the top until "stick forward" prints FORWARD. The raw pulse widths are always shown, and the weapon line must not change when you move the drive stick.

## Limitations

- Only tested on **ExpressLRS 3.6.2** with the T8L. Other versions need the same two-line change in `tx_main.cpp` (the `OtaPackChannelData` call)
- The configuration is compiled in. Changing an option means rebuilding and reflashing
- Using the T8L for something else (a drone, a simulator) with the mix switch on will send mixed channels. Keep the switch low, or flash stock firmware
