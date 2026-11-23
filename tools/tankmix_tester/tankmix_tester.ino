/*
 * tankmix_tester.ino - Reads the receiver's PWM outputs and prints them on the
 * serial monitor, to check the tank mix without the robot.
 *
 * Board: ESP32-S3 (e.g. ESP32-S3 Zero), Arduino core.
 * Arduino IDE: Tools -> USB CDC On Boot -> Enabled (otherwise nothing is
 * printed over the USB port). Serial monitor at 115200.
 *
 * NOTE: on the ESP32-S3, GPIO 26-32 are used by the flash/PSRAM and GPIO 25
 * does not exist. Using those pins makes the chip reset in a loop
 * (TG1WDT_SYS_RST).
 *
 * WIRING (robot battery disconnected, ESCs unplugged from the receiver):
 *   ESP32 5V   -> + (middle pin) of any receiver output
 *   ESP32 GND  -> - of any receiver output
 *   Output 1 signal -> GPIO 2   (left motor)
 *   Output 2 signal -> GPIO 4   (right motor)
 *   Output 3 signal -> GPIO 6   (weapon)
 *
 * ELRS receivers use 3.3 V logic, so the signals can go straight to the ESP32.
 */

const int NUM_CH = 3;
const int PINS[NUM_CH] = {2, 4, 6};
const char *NAMES[NUM_CH] = {"LEFT", "RIGHT", "WEAPON"};

// Which pulse direction drives each wheel FORWARD on your robot.
// +1 = above 1500 us is forward, -1 = below 1500 us is forward.
// With mirrored motors (and the TANKMIX_INV_* options) one or both sides end
// up inverted: set these so that "stick forward" prints FORWARD.
const int LEFT_SIGN  = 1;
const int RIGHT_SIGN = 1;

volatile uint32_t riseTime[NUM_CH];
volatile uint16_t pulseWidth[NUM_CH];
volatile uint32_t lastPulse[NUM_CH];

void IRAM_ATTR isrChannel(int i)
{
    uint32_t now = micros();
    if (digitalRead(PINS[i]))
    {
        riseTime[i] = now;
    }
    else
    {
        uint32_t w = now - riseTime[i];
        if (w > 500 && w < 2600)   // ignore noise
        {
            pulseWidth[i] = w;
            lastPulse[i] = now;
        }
    }
}

void IRAM_ATTR isr0() { isrChannel(0); }
void IRAM_ATTR isr1() { isrChannel(1); }
void IRAM_ATTR isr2() { isrChannel(2); }

// -100% (1000 us) .. 0 (1500 us) .. +100% (2000 us)
int toPct(uint16_t us)
{
    long p = ((long)us - 1500) * 100 / 500;
    if (p > 100) p = 100;
    if (p < -100) p = -100;
    return (int)p;
}

// What a tank-drive robot would do with these outputs.
// left/right are already corrected by LEFT_SIGN/RIGHT_SIGN (positive = wheel forward).
const char *describe(int left, int right)
{
    const int DB = 5;  // deadband in %
    bool lStop = abs(left) < DB, rStop = abs(right) < DB;
    if (lStop && rStop) return "stopped";
    if (abs(left - right) < DB) return left > 0 ? "FORWARD" : "BACKWARD";
    if ((left > DB && right < -DB) || (left < -DB && right > DB))
        return left > right ? "SPIN RIGHT" : "SPIN LEFT";
    return left > right ? "turn right" : "turn left";
}

void setup()
{
    Serial.begin(115200);
    for (int i = 0; i < NUM_CH; i++)
    {
        pinMode(PINS[i], INPUT);
        pulseWidth[i] = 0;
        lastPulse[i] = 0;
    }
    attachInterrupt(digitalPinToInterrupt(PINS[0]), isr0, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PINS[1]), isr1, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PINS[2]), isr2, CHANGE);
    Serial.println();
    Serial.println("Tank mix tester");
    Serial.println("Mix OFF: LEFT = steering, RIGHT = throttle (pass-through)");
    Serial.println("Mix ON: stick forward should print FORWARD (adjust LEFT_SIGN/RIGHT_SIGN)");
}

void loop()
{
    static uint32_t lastPrint = 0;
    if (millis() - lastPrint < 100) return;   // 10 times per second
    lastPrint = millis();

    uint16_t us[NUM_CH];
    bool ok[NUM_CH];
    uint32_t now = micros();

    noInterrupts();
    for (int i = 0; i < NUM_CH; i++)
    {
        us[i] = pulseWidth[i];
        ok[i] = (now - lastPulse[i]) < 100000UL && lastPulse[i] != 0;  // pulse in the last 100 ms
    }
    interrupts();

    for (int i = 0; i < NUM_CH; i++)
    {
        if (ok[i])
            Serial.printf("%s:%4u us (%4d%%)  ", NAMES[i], us[i], toPct(us[i]));
        else
            Serial.printf("%s: NO PULSE        ", NAMES[i]);
    }

    if (ok[0] && ok[1])
        Serial.printf("| %s", describe(LEFT_SIGN * toPct(us[0]), RIGHT_SIGN * toPct(us[1])));
    else
        Serial.print("| no signal (receiver off or 'no pulses' failsafe)");
    Serial.println();
}
