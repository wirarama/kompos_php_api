/*
 ╔══════════════════════════════════════════════════════════════╗
 ║  FIRMWARE KOMPOS IoT — Wemos D1 R32 (ESP32)                ║
 ║  Sensor : DS18B20 · Capacitive Soil Moisture · MQ-135      ║
 ║  Target : PHP REST API via HTTP POST JSON                   ║
 ╠══════════════════════════════════════════════════════════════╣
 ║  Board   : Wemos D1 R32 (ESP32 chipset)                    ║
 ║  Bedanya dengan ESP8266:                                    ║
 ║  - 2 core 240 MHz (vs 1 core 80 MHz)                       ║
 ║  - 2x ADC 12-bit (vs 1x ADC 10-bit)                        ║
 ║  - WiFi + Bluetooth                                         ║
 ║  - Pin layout kompatibel Arduino Uno                        ║
 ╠══════════════════════════════════════════════════════════════╣
 ║  WIRING D1 R32:                                             ║
 ║  DS18B20 DATA    → D4  (GPIO4)  + 4.7kΩ pull-up ke 3.3V   ║
 ║  Soil Moisture   → A0  (GPIO36 / VP) — ADC1_CH0            ║
 ║  MQ-135 AOUT     → A1  (GPIO39 / VN) — ADC1_CH3            ║
 ║  LED Status      → D13 (GPIO13) + 220Ω                     ║
 ║                                                             ║
 ║  CATATAN: D1 R32 memiliki 2 ADC terpisah sehingga          ║
 ║  Soil Moisture dan MQ-135 dapat dibaca BERSAMAAN            ║
 ║  tanpa relay/multiplexer!                                   ║
 ╠══════════════════════════════════════════════════════════════╣
 ║  Library (Arduino IDE Library Manager):                     ║
 ║  - esp32 by Espressif Systems (board support)               ║
 ║  - ArduinoJson  v6.x   by Benoit Blanchon                  ║
 ║  - OneWire      v2.3   by Paul Stoffregen                   ║
 ║  - DallasTemperature v3.9 by Miles Burton                   ║
 ╚══════════════════════════════════════════════════════════════╝
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Preferences.h>   // ESP32 NVS (pengganti EEPROM)
#include <time.h>          // ESP32 built-in NTP

// ════════════════════════════════════════════════════════════
// ①  KONFIGURASI — SESUAIKAN SEBELUM UPLOAD
// ════════════════════════════════════════════════════════════

// WiFi credentials
const char* WIFI_SSID     = "NamaWiFi_Anda";
const char* WIFI_PASSWORD = "PasswordWiFi_Anda";

// PHP Server URL — tanpa trailing slash
// Lokal  : "http://192.168.1.100/kompos/api"
// Hosting: "http://namadomain.com/kompos/api"
const char* SERVER_BASE   = "http://192.168.1.100/kompos/api";

// Identitas perangkat
const char* DEVICE_ID     = "D1R32_01";
const char* DEVICE_LOC    = "Bak Kompos A";
const char* API_KEY       = "kompos2024iot";

// Interval kirim data (ms)
const uint32_t SEND_INTERVAL_MS = 60000UL;   // 60 detik

// NTP Server
const char* NTP_SERVER1   = "pool.ntp.org";
const char* NTP_SERVER2   = "time.nist.gov";
const long  GMT_OFFSET_SEC = 28800;           // WIB = UTC+8
const int   DST_OFFSET_SEC = 0;

// Retry & watchdog
const int   MAX_WIFI_RETRY  = 30;
const int   MAX_HTTP_RETRY  = 3;
const int   HTTP_TIMEOUT_MS = 15000;
const int   MAX_ERROR_COUNT = 10;

// ════════════════════════════════════════════════════════════
// ②  PIN DEFINITIONS (Wemos D1 R32 pin mapping)
// ════════════════════════════════════════════════════════════
//
//  Wemos D1 R32 Label → ESP32 GPIO
//  D4   → GPIO4    (1-Wire DS18B20)
//  A0   → GPIO36   (ADC1_CH0, VP pin — Soil Moisture)
//  A1   → GPIO39   (ADC1_CH3, VN pin — MQ-135)
//  D13  → GPIO13   (LED onboard & status LED)
//  D12  → GPIO12   (opsional: buzzer alert)
//
// PENTING: GPIO34,35,36,39 adalah INPUT ONLY (tidak ada pull-up internal)
//          GPIO36 (VP) dan GPIO39 (VN) adalah ADC dedicated, sangat stabil

#define PIN_DS18B20     4    // D4  → GPIO4
#define PIN_MOISTURE    36   // A0  → GPIO36 (VP) — ADC1_CH0
#define PIN_MQ135       39   // A1  → GPIO39 (VN) — ADC1_CH3
#define PIN_LED_STATUS  13   // D13 → GPIO13

// ADC configuration
#define ADC_RESOLUTION  12   // 12-bit: 0–4095
#define ADC_VREF        3.3f // referensi tegangan ADC
#define ADC_SAMPLES     16   // oversampling per reading

// ════════════════════════════════════════════════════════════
// ③  KALIBRASI SENSOR
// ════════════════════════════════════════════════════════════

// Capacitive Soil Moisture — kalibrasi 2 titik
// Cara kalibrasi: baca nilai raw saat sensor di udara (dry)
//                 dan saat tercelup air penuh (wet)
const int   MOIST_DRY_RAW  = 3200;   // ADC 12-bit saat kering
const int   MOIST_WET_RAW  = 1200;   // ADC 12-bit saat basah

// MQ-135 gas sensor
// RO = resistance di udara bersih (dikalibrasi saat warmup)
// Kurva sensitifitas NH3: ppm = A * (RS/RO)^B
float       MQ135_RO       = 10.0f;  // kΩ — update via kalibrasi
const float MQ135_RL       = 10.0f;  // kΩ load resistor
const float MQ135_A        = 110.47f;
const float MQ135_B        = -2.862f;

// DS18B20 — tidak perlu kalibrasi (digital sensor)
// Resolusi: 9-bit(93ms), 10-bit(187ms), 11-bit(375ms), 12-bit(750ms)
const int   DS18B20_RES    = 11;     // 11-bit: ±0.125°C

// ════════════════════════════════════════════════════════════
// ④  MOVING AVERAGE FILTER
// ════════════════════════════════════════════════════════════
const int MA_WIN = 8;   // window lebih besar karena ADC 12-bit lebih noise-tolerant

struct MAFilter {
    float buf[MA_WIN] = {0};
    int   idx = 0;
    bool  full = false;

    float push(float v) {
        buf[idx % MA_WIN] = v;
        float s = 0;
        int n = full ? MA_WIN : (idx + 1);
        for (int i = 0; i < n; i++) s += buf[i];
        idx++;
        if (idx >= MA_WIN) { full = true; idx = 0; }
        return s / n;
    }
};

MAFilter maTemp, maMoist, maGas;

// ════════════════════════════════════════════════════════════
// ⑤  GLOBAL OBJECTS & STATE
// ════════════════════════════════════════════════════════════
OneWire            oneWire(PIN_DS18B20);
DallasTemperature  ds18b20(&oneWire);
Preferences        prefs;   // ESP32 NVS storage
WiFiClient         wifiClient;

uint32_t lastSendMs  = 0;
uint32_t bootMs      = 0;
int      sendCount   = 0;
int      errorCount  = 0;
float    lastTemp    = 25.0f;
float    lastMoist   = 50.0f;
float    lastGas     = 100.0f;
bool     mq135Ready  = false;
bool     ntpSynced   = false;

// ════════════════════════════════════════════════════════════
// ⑥  UTILITY FUNCTIONS
// ════════════════════════════════════════════════════════════
void ledOn()  { digitalWrite(PIN_LED_STATUS, HIGH); }
void ledOff() { digitalWrite(PIN_LED_STATUS, LOW);  }

void blinkLED(int n, int ms_on = 100, int ms_off = 100) {
    for (int i = 0; i < n; i++) {
        ledOn();  vTaskDelay(pdMS_TO_TICKS(ms_on));
        ledOff(); if (i < n-1) vTaskDelay(pdMS_TO_TICKS(ms_off));
    }
}

float softClip(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

// 12-bit ADC oversampling + averaging
float readADC(int pin) {
    uint32_t sum = 0;
    for (int i = 0; i < ADC_SAMPLES; i++) {
        sum += analogRead(pin);
        delayMicroseconds(200);
    }
    return (float)(sum / ADC_SAMPLES);
}

// ISO 8601 timestamp dari ESP32 SNTP
String getTimestamp() {
    struct tm ti;
    if (!getLocalTime(&ti, 3000)) {
        // Fallback: millis-based offset dari boot
        uint32_t s = (millis() - bootMs) / 1000;
        char buf[32];
        snprintf(buf, sizeof(buf), "1970-01-01T%02lu:%02lu:%02lu",
                 (s/3600)%24, (s/60)%60, s%60);
        return String(buf);
    }
    char buf[24];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &ti);
    return String(buf);
}

uint32_t uptimeSec() { return (millis() - bootMs) / 1000UL; }

// ════════════════════════════════════════════════════════════
// ⑦  WIFI CONNECTION
// ════════════════════════════════════════════════════════════
bool connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return true;

    Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    for (int i = 0; i < MAX_WIFI_RETRY && WiFi.status() != WL_CONNECTED; i++) {
        delay(500);
        Serial.print(".");
        digitalWrite(PIN_LED_STATUS, !digitalRead(PIN_LED_STATUS));
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] OK — IP: %s  RSSI: %d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        blinkLED(3, 200, 100);

        // Sync NTP (ESP32 built-in SNTP)
        if (!ntpSynced) {
            configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC,
                       NTP_SERVER1, NTP_SERVER2);
            Serial.print("[NTP] Syncing");
            struct tm ti;
            for (int i = 0; i < 20 && !getLocalTime(&ti); i++) {
                Serial.print(".");
                delay(500);
            }
            if (getLocalTime(&ti)) {
                ntpSynced = true;
                char buf[24];
                strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &ti);
                Serial.printf(" → %s\n", buf);
            } else {
                Serial.println(" timeout — using millis fallback");
            }
        }
        return true;
    }

    Serial.println("[WiFi] FAILED");
    blinkLED(8, 50, 50);
    return false;
}

// ════════════════════════════════════════════════════════════
// ⑧  SENSOR READ FUNCTIONS
// ════════════════════════════════════════════════════════════

// ── DS18B20 Temperature ───────────────────────────────────
float readTemperature() {
    ds18b20.requestTemperatures();
    // ESP32 lebih cepat, delay cukup 200ms untuk resolusi 11-bit
    delay(200);
    float t = ds18b20.getTempCByIndex(0);

    if (t == DEVICE_DISCONNECTED_C || t < -10.0f || t > 85.0f) {
        Serial.println("[DS18B20] Error — using last value");
        return lastTemp;
    }
    return t;
}

// ── Capacitive Soil Moisture (GPIO36/VP, ADC 12-bit) ─────
float readMoisture() {
    float raw = readADC(PIN_MOISTURE);

    // ADC 12-bit: range 0–4095
    // Map: DRY_RAW(3200)→0%  WET_RAW(1200)→100%
    // ESP32 ADC non-linearity correction (simple two-point)
    float pct = ((float)MOIST_DRY_RAW - raw)
              / ((float)MOIST_DRY_RAW - (float)MOIST_WET_RAW)
              * 100.0f;

    // ADC ESP32 memiliki non-linearity di ujung range — kompensasi sederhana
    if (pct < 5.0f)  pct = pct * 0.85f;
    if (pct > 90.0f) pct = 90.0f + (pct - 90.0f) * 0.7f;

    return softClip(pct, 0.0f, 100.0f);
}

// ── MQ-135 Gas Sensor (GPIO39/VN, ADC 12-bit) ────────────
float readGas() {
    float raw = readADC(PIN_MQ135);

    // Konversi ADC → tegangan
    float vSensor = (raw / 4095.0f) * ADC_VREF;
    if (vSensor >= ADC_VREF - 0.05f || vSensor <= 0.05f) return lastGas;

    // RS = resistance sensor saat ini (kΩ)
    float RS    = ((ADC_VREF - vSensor) / vSensor) * MQ135_RL;
    float ratio = RS / MQ135_RO;
    if (ratio <= 0.0f) return lastGas;

    // Konversi ke ppm (kurva NH3 dari datasheet MQ-135)
    float ppm = MQ135_A * pow(ratio, MQ135_B);
    return softClip(ppm, 0.0f, 1000.0f);
}

// ── MQ-135 Warmup & Calibration ──────────────────────────
void calibrateMQ135() {
    Serial.println("[MQ135] Warming up 30 seconds in clean air...");
    ledOn();
    delay(30000);   // warmup time

    float sum = 0;
    const int N = 60;
    for (int i = 0; i < N; i++) {
        float raw  = readADC(PIN_MQ135);
        float v    = (raw / 4095.0f) * ADC_VREF;
        if (v > 0.05f && v < ADC_VREF - 0.05f)
            sum += ((ADC_VREF - v) / v) * MQ135_RL;
        delay(300);
    }

    // RO = RS_in_clean_air / 3.6 (dari datasheet MQ-135)
    MQ135_RO   = softClip((sum / N) / 3.6f, 0.5f, 150.0f);
    mq135Ready = true;

    // Simpan ke NVS (Preferences) — bertahan setelah power cycle
    prefs.begin("mq135", false);
    prefs.putFloat("ro", MQ135_RO);
    prefs.end();

    Serial.printf("[MQ135] Calibrated — RO = %.4f kOhm (saved to NVS)\n", MQ135_RO);
    ledOff();
}

void loadCalibration() {
    prefs.begin("mq135", true);
    float stored = prefs.getFloat("ro", -1.0f);
    prefs.end();

    if (stored > 0.5f && stored < 150.0f) {
        MQ135_RO   = stored;
        mq135Ready = true;
        Serial.printf("[MQ135] RO loaded from NVS: %.4f kOhm\n", MQ135_RO);
    } else {
        Serial.println("[MQ135] No calibration — using default RO=10.0");
        Serial.println("[MQ135] Uncomment calibrateMQ135() in setup() to calibrate");
    }
}

// ════════════════════════════════════════════════════════════
// ⑨  HTTP POST TO PHP SERVER
// ════════════════════════════════════════════════════════════
struct PostResult {
    int    httpCode;
    bool   success;
    String fase_nama;
    float  ikk;
    String message;
    String alerts;
};

PostResult sendToServer(float temp, float moist, float gas,
                        const String& ts) {
    PostResult res = { 0, false, "", 0.0f, "not_sent", "" };

    if (!connectWiFi()) {
        res.message = "wifi_offline";
        return res;
    }

    // ── Build JSON payload ────────────────────────────────
    // Format identik dengan server.py dan simulasi_kirim.py
    StaticJsonDocument<384> doc;
    doc["device_id"]   = DEVICE_ID;
    doc["device_loc"]  = DEVICE_LOC;
    doc["timestamp"]   = ts;
    doc["suhu"]        = round(temp  * 100.0f) / 100.0f;
    doc["moisture"]    = round(moist * 100.0f) / 100.0f;
    doc["gas"]         = round(gas   * 10.0f)  / 10.0f;
    doc["firmware"]    = "D1R32_v2.0";
    doc["chip"]        = "ESP32";
    doc["uptime"]      = uptimeSec();
    doc["wifi_rssi"]   = WiFi.RSSI();
    doc["free_heap"]   = ESP.getFreeHeap();
    doc["api_key"]     = API_KEY;

    String payload;
    serializeJson(doc, payload);

    // ── HTTP POST ─────────────────────────────────────────
    String url = String(SERVER_BASE) + "/data.php";
    Serial.printf("\n[HTTP] POST → %s\n", url.c_str());
    Serial.printf("[HTTP] %s\n", payload.c_str());

    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Accept",       "application/json");
    http.addHeader("X-API-Key",    API_KEY);
    http.setTimeout(HTTP_TIMEOUT_MS);

    int code = http.POST(payload);
    res.httpCode = code;

    if (code == 201 || code == 200) {
        String body = http.getString();
        Serial.printf("[HTTP] %d: %s\n", code, body.c_str());

        StaticJsonDocument<768> resp;
        DeserializationError err = deserializeJson(resp, body);

        if (!err) {
            res.success   = true;
            res.fase_nama = resp["analysis"]["fase_nama"] | String("?");
            res.ikk       = resp["analysis"]["ikk"]       | 0.0f;
            res.message   = "ok";

            // Build alerts string
            String alertStr = "";
            JsonArray arr = resp["alerts"].as<JsonArray>();
            for (const auto& a : arr) {
                if (alertStr.length()) alertStr += ", ";
                alertStr += a.as<String>();
            }
            res.alerts = alertStr;

            // LED feedback
            if (arr.size() > 0) blinkLED(5, 60, 60);
            else                blinkLED(1, 250, 0);

        } else {
            res.message = String("json_err:") + err.c_str();
        }

    } else {
        res.message = http.errorToString(code);
        Serial.printf("[HTTP] Error %d: %s\n", code, res.message.c_str());
        errorCount++;
        blinkLED(3, 50, 50);
    }

    http.end();
    return res;
}

// ════════════════════════════════════════════════════════════
// ⑩  SETUP
// ════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n╔════════════════════════════════════════╗");
    Serial.println("║  KomposIoT Firmware v2.0               ║");
    Serial.println("║  Board  : Wemos D1 R32 (ESP32)         ║");
    Serial.println("║  Target : PHP REST API Server           ║");
    Serial.println("╚════════════════════════════════════════╝");

    // Pin setup
    pinMode(PIN_LED_STATUS, OUTPUT);
    ledOff();
    // GPIO36 (VP) dan GPIO39 (VN) tidak perlu pinMode — ADC only

    // DS18B20 init
    ds18b20.begin();
    ds18b20.setResolution(DS18B20_RES);
    Serial.printf("[DS18B20] Sensors found: %d\n",
                  ds18b20.getDeviceCount());

    // ESP32 ADC config
    analogReadResolution(ADC_RESOLUTION);   // 12-bit
    analogSetAttenuation(ADC_11db);         // 0–3.3V range
    Serial.printf("[ADC] Resolution: %d-bit  Vref: %.1fV\n",
                  ADC_RESOLUTION, ADC_VREF);

    // Load MQ-135 calibration from NVS
    loadCalibration();
    // ↓ Uncomment untuk paksa kalibrasi ulang:
    // calibrateMQ135();

    // WiFi + NTP
    bootMs = millis();
    connectWiFi();

    // Pre-fill MA filters
    Serial.println("[INIT] Pre-filling sensor buffers...");
    for (int i = 0; i < MA_WIN; i++) {
        float t = readTemperature();
        float m = readMoisture();
        float g = mq135Ready ? readGas() : 100.0f;
        lastTemp  = maTemp.push(t);
        lastMoist = maMoist.push(m);
        lastGas   = maGas.push(g);
        delay(300);
    }

    Serial.println("\n[CONFIG] ─────────────────────────────");
    Serial.printf("[CONFIG] Server  : %s\n", SERVER_BASE);
    Serial.printf("[CONFIG] Device  : %s  @ %s\n", DEVICE_ID, DEVICE_LOC);
    Serial.printf("[CONFIG] Interval: %u sec\n", SEND_INTERVAL_MS / 1000);
    Serial.printf("[CONFIG] MQ135 RO: %.3f kΩ\n", MQ135_RO);
    Serial.println("[CONFIG] ─────────────────────────────");

    blinkLED(5, 80, 80);
    lastSendMs = millis() - SEND_INTERVAL_MS;  // send immediately on first loop
}

// ════════════════════════════════════════════════════════════
// ⑪  LOOP
// ════════════════════════════════════════════════════════════
void loop() {
    uint32_t now = millis();

    // WiFi watchdog
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Connection lost — reconnecting...");
        if (!connectWiFi()) { delay(15000); return; }
    }

    // Read sensors → push to MA filter
    lastTemp  = maTemp.push(readTemperature());
    lastMoist = maMoist.push(readMoisture());
    lastGas   = maGas.push(mq135Ready ? readGas() : lastGas);

    // Send at interval
    if (now - lastSendMs >= SEND_INTERVAL_MS) {
        lastSendMs = now;
        sendCount++;

        String ts = getTimestamp();

        Serial.println("\n┌─────── SENSOR READING ───────────────");
        Serial.printf( "│ Timestamp : %s\n", ts.c_str());
        Serial.printf( "│ Suhu      : %.2f °C\n",  lastTemp);
        Serial.printf( "│ Moisture  : %.2f %%\n",  lastMoist);
        Serial.printf( "│ Gas       : %.1f ppm\n", lastGas);
        Serial.printf( "│ Send #    : %d\n",       sendCount);
        Serial.printf( "│ Uptime    : %u sec\n",   uptimeSec());
        Serial.printf( "│ Free Heap : %u bytes\n", ESP.getFreeHeap());
        Serial.println("└──────────────────────────────────────");

        // Retry loop with exponential backoff
        PostResult result;
        bool sent = false;
        for (int attempt = 1; attempt <= MAX_HTTP_RETRY && !sent; attempt++) {
            if (attempt > 1) {
                uint32_t wait = 2000UL * attempt;
                Serial.printf("[HTTP] Retry %d/%d in %u ms...\n",
                              attempt, MAX_HTTP_RETRY, wait);
                delay(wait);
            }
            result = sendToServer(lastTemp, lastMoist, lastGas, ts);
            sent   = result.success;
        }

        if (result.success) {
            errorCount = 0;
            Serial.println("┌─────── SERVER RESPONSE ──────────────");
            Serial.printf( "│ Fase  : %s\n", result.fase_nama.c_str());
            Serial.printf( "│ IKK   : %.1f / 100\n", result.ikk);
            if (result.alerts.length())
                Serial.printf("│ Alerts: %s\n", result.alerts.c_str());
            Serial.println("└──────────────────────────────────────");
        } else {
            Serial.printf("[FAIL] HTTP %d — %s\n",
                          result.httpCode, result.message.c_str());
        }
    }

    // Watchdog: terlalu banyak error → restart
    if (errorCount > MAX_ERROR_COUNT) {
        Serial.println("[WATCHDOG] Too many errors — restarting ESP32...");
        delay(2000);
        ESP.restart();
    }

    delay(500);  // 500ms loop tick
}

/*
 ╔══════════════════════════════════════════════════════════╗
 ║  WIRING LENGKAP — Wemos D1 R32                          ║
 ╠══════════════════════════════════════════════════════════╣
 ║                                                          ║
 ║  DS18B20 (3-pin TO-92, flat side menghadap Anda):        ║
 ║    Pin kiri  (GND)  → GND Wemos                         ║
 ║    Pin tengah(DATA) → D4 (GPIO4)                        ║
 ║    Pin kanan (VCC)  → 3.3V Wemos                        ║
 ║    Pasang 4.7kΩ antara DATA dan 3.3V                    ║
 ║                                                          ║
 ║  Capacitive Soil Moisture Sensor (5-pin module):         ║
 ║    VCC  → 3.3V  (atau 5V jika modul mensupport)         ║
 ║    GND  → GND                                           ║
 ║    AOUT → A0 (GPIO36 / VP)                              ║
 ║    Note : GPIO36 INPUT ONLY, tidak ada internal pull-up  ║
 ║    Kalibrasi: baca nilai raw di udara dan air bersih     ║
 ║    Update MOIST_DRY_RAW dan MOIST_WET_RAW               ║
 ║                                                          ║
 ║  MQ-135 (4-pin module):                                  ║
 ║    VCC  → 5V (pin VIN / 5V Wemos D1 R32)               ║
 ║    GND  → GND                                           ║
 ║    AOUT → A1 (GPIO39 / VN)                              ║
 ║    DOUT → tidak digunakan                               ║
 ║    Note : MQ-135 butuh 5V untuk heater element          ║
 ║    AOUT output 0-5V → pasang voltage divider ke 3.3V:   ║
 ║      AOUT → R1(10kΩ) → [node] → R2(20kΩ) → GND        ║
 ║      [node] → A1 (GPIO39)                               ║
 ║    Vout = 5V × 20/(10+20) = 3.33V ✓                    ║
 ║                                                          ║
 ║  LED Status (opsional):                                  ║
 ║    D13 (GPIO13) → 220Ω → LED → GND                      ║
 ║    Atau: gunakan LED onboard GPIO2 (active LOW)          ║
 ║                                                          ║
 ║  KEUNGGULAN D1 R32 vs ESP8266 untuk project ini:        ║
 ║  ✅ Dua ADC channel terpisah — tidak perlu relay         ║
 ║  ✅ ADC 12-bit (4096 level vs 1024 level)               ║
 ║  ✅ SNTP built-in — tidak perlu library NTPClient        ║
 ║  ✅ NVS Preferences — lebih aman dari EEPROM             ║
 ║  ✅ FreeRTOS — task scheduling built-in                  ║
 ║  ✅ Heap 320KB — JSON dokumen lebih besar                ║
 ║  ✅ Dual core — WiFi tidak mengganggu sensor read        ║
 ╚══════════════════════════════════════════════════════════╝

 TROUBLESHOOTING:
 1. DS18B20 baca -127°C atau DISCONNECTED
    → Cek resistor 4.7kΩ pull-up ke 3.3V (BUKAN 5V!)
    → Cek polaritas sensor (lihat tulisan flat-side)
    → Coba oneWire.reset() sebelum request

 2. Moisture selalu 0% atau 100%
    → Kalibrasi ulang MOIST_DRY_RAW dan MOIST_WET_RAW
    → Buka Serial Monitor, baca nilai raw: Serial.println(analogRead(36))
    → ESP32 ADC bisa tidak akurat di range 0-150 dan 3900-4095

 3. MQ-135 nilai tidak stabil / selalu tinggi
    → Warmup minimal 30-60 detik setelah power on
    → Cek voltage divider (AOUT tidak boleh lebih dari 3.3V ke GPIO39)
    → Uncomment calibrateMQ135() untuk kalibrasi ulang

 4. HTTP 0 atau Connection refused
    → Pastikan SERVER_BASE benar (IP, port, path)
    → Test manual: curl -X POST http://IP/kompos/api/data.php -H ...
    → Cek firewall server, port 80 harus terbuka

 5. HTTP 401 Unauthorized
    → API_KEY di firmware harus sama persis dengan di config.php

 6. WiFi terus disconnect
    → Cek SSID/password (case-sensitive, max 32 karakter)
    → ESP32 mendukung 2.4GHz dan 5GHz (berbeda dengan ESP8266)
    → Coba ubah WiFi channel di router ke channel 1, 6, atau 11
*/
