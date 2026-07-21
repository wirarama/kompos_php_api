# KomposIoT — Wemos D1 R32 + PHP REST API Server

Sistem monitoring kompos IoT berbasis **ESP32 (Wemos D1 R32)** dengan
server **PHP REST API** berkeamanan tinggi dan skrip simulasi Python.

---

## 📁 Struktur File

```
kompos_d1r32/
├── firmware/
│   └── kompos_d1r32.ino       ← Upload ke Wemos D1 R32
├── server/
│   ├── api/
│   │   ├── index.php          ← Router utama (entry point)
│   │   ├── config.php         ← Konfigurasi global
│   │   ├── security.php       ← Middleware keamanan
│   │   ├── db.php             ← PDO SQLite helper
│   │   ├── sprt.php           ← SPRT-CUSUM engine
│   │   ├── ikk.php            ← Indeks Kesehatan Kompos
│   │   ├── data.php           ← POST /api/data.php
│   │   ├── latest.php         ← GET  /api/latest.php
│   │   ├── history.php        ← GET  /api/history.php
│   │   ├── aggregate.php      ← GET  /api/aggregate.php
│   │   ├── status.php         ← GET  /api/status.php
│   │   ├── health.php         ← GET  /api/health.php
│   │   ├── reset.php          ← DELETE /api/reset.php
│   │   └── .htaccess          ← Apache hardened config
│   └── data/                  ← Auto-created (writable!)
│       ├── kompos.sqlite
│       ├── sprt_state.json
│       └── security/
│           ├── audit.log
│           ├── blocked_ips.json
│           └── rate_limits.json
└── simulasi_php.py            ← Simulasi pengiriman Python
```

---

## 🚀 Deploy PHP Server

### Persyaratan
- PHP >= 7.4 dengan ekstensi: `pdo`, `pdo_sqlite`, `json`
- Apache 2.4+ dengan `mod_rewrite` aktif
- Folder `server/data/` harus writable oleh web server

### Langkah Deploy Apache

```bash
# 1. Copy ke web root
sudo cp -r server/ /var/www/html/kompos/

# 2. Buat folder data dan set permission
sudo mkdir -p /var/www/html/kompos/data/security
sudo chown -R www-data:www-data /var/www/html/kompos/data/
sudo chmod 750 /var/www/html/kompos/data/

# 3. Aktifkan mod_rewrite
sudo a2enmod rewrite headers
sudo systemctl restart apache2

# 4. Pastikan AllowOverride aktif di Apache config
# /etc/apache2/sites-available/000-default.conf:
#   <Directory /var/www/html>
#       AllowOverride All
#   </Directory>

# 5. Test
curl http://localhost/kompos/api/health.php
```

### Konfigurasi Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /var/www/html;

    location /kompos/api/ {
        # Blokir akses langsung ke folder data/
        location /kompos/api/../data/ { deny all; }

        try_files $uri $uri/ /kompos/api/index.php?$query_string;

        # Security headers
        add_header X-Content-Type-Options "nosniff";
        add_header X-Frame-Options "DENY";
        add_header X-XSS-Protection "1; mode=block";

        # Limit request size
        client_max_body_size 16k;
        client_body_timeout 10s;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/run/php/php8.1-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }
}
```

### Ganti API Key (WAJIB sebelum produksi!)

Edit `server/api/config.php`:
```php
define('API_KEY', 'GANTI_DENGAN_KEY_ACAK_MIN_32_KARAKTER');
```

Generate key acak:
```bash
php -r "echo bin2hex(random_bytes(24)) . PHP_EOL;"
# Contoh output: a3f8c2d1e9b4f7a2c5d8e1b4f7a2c5d8e1b4f7a2
```

---

## 📡 API Endpoints — Tutorial Lengkap

### Base URL
```
http://IP_SERVER/kompos/api
```

### Autentikasi
Semua endpoint kecuali `health.php` memerlukan API key.
Kirim melalui **header** (direkomendasikan) atau **field JSON body**:

```bash
# Via header (direkomendasikan untuk firmware)
-H "X-API-Key: kompos2024iot"

# Via JSON body (untuk simulasi/testing)
{"api_key": "kompos2024iot", ...}
```

---

### 1. `POST /api/data.php` — Kirim Data Sensor

Endpoint utama yang dipanggil firmware setiap interval.
Menjalankan pipeline: validasi → SPRT-CUSUM → IKK → simpan DB → agregasi.

**Request:**
```bash
curl -X POST http://localhost/kompos/api/data.php \
  -H "Content-Type: application/json" \
  -H "X-API-Key: kompos2024iot" \
  -d '{
    "device_id"  : "D1R32_01",
    "device_loc" : "Bak Kompos A",
    "timestamp"  : "2024-03-15T14:30:00",
    "suhu"       : 54.3,
    "moisture"   : 48.2,
    "gas"        : 185.6
  }'
```

**Field JSON:**

| Field       | Tipe   | Wajib | Keterangan                     |
|-------------|--------|-------|--------------------------------|
| device_id   | string | ✅    | ID unik perangkat              |
| timestamp   | string | ✅    | Format ISO 8601                |
| suhu        | float  | ✅    | Suhu °C (range 0–100)          |
| moisture    | float  | ✅    | Kelembapan % (range 0–100)     |
| gas         | float  | ✅    | Gas ppm (range 0–1000)         |
| device_loc  | string | ❌    | Lokasi fisik perangkat         |
| firmware    | string | ❌    | Versi firmware                 |
| uptime      | int    | ❌    | Uptime perangkat (detik)       |
| wifi_rssi   | int    | ❌    | Signal WiFi (dBm)              |

**Response 201 Created:**
```json
{
  "id": 42,
  "status": "ok",
  "timestamp": "2024-03-15T14:30:00",
  "device_id": "D1R32_01",
  "analysis": {
    "fase_pred": 1,
    "fase_nama": "Termofilik Aktif",
    "fase_emoji": "🔥",
    "fase_warna": "#E76F51",
    "ikk": 72.4,
    "ikk_label": "Baik",
    "sprt": {
      "cusum_t": 1.234,
      "cusum_m": 0.456,
      "cusum_g": 2.111,
      "A": 2.9444,
      "B": -1.9459
    }
  },
  "alerts": ["GAS_ACTIVE"],
  "recommendation": "Gas mulai aktif — monitor lebih sering."
}
```

**Error Responses:**

| Code | Keterangan                                  |
|------|---------------------------------------------|
| 400  | Field wajib hilang atau nilai di luar range |
| 401  | API key salah atau tidak ada                |
| 413  | Request body terlalu besar (>8 KB)          |
| 415  | Content-Type bukan application/json         |
| 429  | Rate limit: 10 POST/menit atau 200 req/jam  |

---

### 2. `GET /api/latest.php` — Data Terbaru

```bash
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/latest.php?device_id=D1R32_01"
```

**Query params:**

| Param     | Default    | Keterangan         |
|-----------|------------|--------------------|
| device_id | D1R32_01   | ID perangkat       |

**Response 200:**
```json
{
  "id": 42,
  "device_id": "D1R32_01",
  "timestamp": "2024-03-15T14:30:00",
  "suhu": 54.3,
  "moisture": 48.2,
  "gas": 185.6,
  "fase_pred": 1,
  "fase_nama": "Termofilik Aktif",
  "ikk": 72.4,
  "sprt_cusum_t": 1.234,
  "sprt_cusum_m": 0.456,
  "sprt_cusum_g": 2.111,
  "created_at": "2024-03-15 14:30:01"
}
```

---

### 3. `GET /api/history.php` — Riwayat Data

```bash
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/history.php?device_id=D1R32_01&hours=24&limit=200"
```

**Query params:**

| Param     | Default  | Max   | Keterangan              |
|-----------|----------|-------|-------------------------|
| device_id | D1R32_01 | —     | ID perangkat            |
| hours     | 24       | 720   | Ambil N jam terakhir    |
| limit     | 500      | 5000  | Maksimal baris          |

**Response 200:**
```json
{
  "device_id": "D1R32_01",
  "count": 48,
  "hours": 24,
  "data": [
    {
      "id": 1,
      "timestamp": "2024-03-15T00:00:00",
      "suhu": 25.1,
      "moisture": 70.4,
      "gas": 65.2,
      "fase_pred": 0,
      "fase_nama": "Mesophilik Awal",
      "ikk": 74.1
    }
  ]
}
```

---

### 4. `GET /api/aggregate.php` — Agregasi Data

Tiga mode agregasi dengan statistik μ/min/max/σ.

```bash
# Per jam (default)
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/aggregate.php?level=hourly&days=7"

# Per hari
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/aggregate.php?level=daily&days=30"

# Per fase
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/aggregate.php?level=fase&days=42"
```

**Query params:**

| Param     | Default  | Pilihan               | Keterangan               |
|-----------|----------|-----------------------|--------------------------|
| device_id | D1R32_01 | —                     | ID perangkat             |
| level     | hourly   | hourly, daily, fase   | Level agregasi           |
| days      | 7        | 1–90                  | Rentang hari             |

**Response `level=hourly`:**
```json
{
  "level": "hourly",
  "days": 7,
  "count": 168,
  "data": [
    {
      "hour_bucket": "2024-03-15 14",
      "suhu_mean": 54.32, "suhu_min": 52.1, "suhu_max": 56.8, "suhu_std": 1.2,
      "moisture_mean": 48.10, "moisture_min": 46.2, "moisture_max": 50.1,
      "gas_mean": 188.50, "gas_min": 175.0, "gas_max": 205.3,
      "ikk_mean": 72.1, "ikk_min": 68.4, "ikk_max": 75.9,
      "fase_mode": 1,
      "sample_count": 6
    }
  ]
}
```

---

### 5. `GET /api/status.php` — Status Server

```bash
curl -H "X-API-Key: kompos2024iot" \
  "http://localhost/kompos/api/status.php"
```

**Response 200:**
```json
{
  "server": "KomposIoT PHP API v2.0",
  "php_version": "8.2.0",
  "total_records": 360,
  "devices": ["D1R32_01", "D1R32_SIM"],
  "latest": {
    "device_id": "D1R32_01",
    "timestamp": "2024-03-15T14:30:00",
    "suhu": 54.3,
    "fase_nama": "Termofilik Aktif",
    "ikk": 72.4
  },
  "sprt_params": { "A": 2.9444, "B": -1.9459, "alpha": 0.05, "beta": 0.10 },
  "sprt_state": {
    "suhu_f0": { "cusum": 0.123, "detections": 2 },
    "gas_f2":  { "cusum": 1.456, "detections": 1 }
  }
}
```

---

### 6. `GET /api/health.php` — Health Check

Tidak memerlukan autentikasi. Cocok untuk monitoring server.

```bash
curl http://localhost/kompos/api/health.php
```

**Response 200:**
```json
{
  "status": "ok",
  "server": "KomposIoT PHP API v2.0",
  "php": "8.2.0",
  "time": "2024-03-15T14:30:00",
  "db_path": "exists"
}
```

---

### 7. `DELETE /api/reset.php` — Reset Database

**Hanya untuk development.** Menghapus semua data dan mereset SPRT state.

```bash
curl -X DELETE -H "X-API-Key: kompos2024iot" \
  http://localhost/kompos/api/reset.php
```

**Response 200:**
```json
{
  "status": "ok",
  "message": "Database cleared and SPRT state reset",
  "records_deleted": 360
}
```

---

## 🔒 Sistem Keamanan (`security.php`)

Server ini dilengkapi **7 layer keamanan** terintegrasi:

### 1. Rate Limiting

Setiap IP dibatasi jumlah requestnya:

| Limit          | Default | Keterangan                   |
|----------------|---------|------------------------------|
| Request/menit  | 30      | Semua method                 |
| POST/menit     | 10      | Lebih ketat untuk POST data  |
| Request/jam    | 200     | Batas akumulatif per jam     |

Jika limit terlampaui, server mengembalikan **HTTP 429** beserta header:
```
Retry-After: 60
X-RateLimit-Limit-Minute: 30
X-RateLimit-Limit-Hour: 200
```

IP yang melebihi 3× limit menit akan otomatis **diblokir 30 menit**.

### 2. IP Whitelist & Blacklist

Konfigurasi di `config.php`:
```php
// Hanya izinkan IP/subnet tertentu (kosong = semua IP)
define('IP_WHITELIST', [
    '192.168.1.0/24',   // subnet lokal
    '203.0.113.42',     // IP publik statis
]);

// Blokir IP/subnet secara permanen
define('IP_BLACKLIST', [
    '185.220.101.0/24',
]);
```

### 3. Brute-Force Protection

Setelah **5 kali gagal autentikasi**, IP diblokir otomatis selama **30 menit**.
Counter direset setelah autentikasi berhasil.

### 4. Honeypot Path Detection

Jika ada request ke path mencurigakan berikut, IP langsung diblokir **24 jam**:
```
/wp-admin, /wp-login, /.env, /.git, /phpMyAdmin,
/backup, /shell, /cmd, /xmlrpc.php
```
Bot dan scanner biasanya mencari path ini secara otomatis.

### 5. Request Validation

- Content-Type wajib `application/json` untuk POST
- Body maksimal **8 KB** (lebih dari itu → HTTP 413)
- Blokir User-Agent berbahaya: `nikto`, `sqlmap`, `nmap`, `masscan`, dll.
- Method selain GET/POST/DELETE/OPTIONS → HTTP 405

### 6. Input Sanitization

Semua field JSON dibersihkan sebelum diproses:
```php
// Di security.php — sanitizeJsonBody()
strip_tags($v)          // hapus HTML tag
str_replace("\0", ...)  // hapus null bytes
substr($v, 0, 256)      // batasi panjang string
filter_var(VALIDATE_IP) // validasi format IP
```

### 7. Security Response Headers

Setiap response menyertakan header:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'
Cache-Control: no-store, no-cache
X-Powered-By: KomposIoT   ← menyembunyikan versi PHP
```

### Audit Log

Semua request dicatat di `data/security/audit.log`:
```
2024-03-15 14:30:01 | REQUEST                | IP=192.168.1.100 | {"method":"POST","route":"data","ua":"D1R32_v2.0"}
2024-03-15 14:30:05 | AUTH_FAIL              | IP=185.220.101.5 | {"count":1}
2024-03-15 14:30:10 | BRUTE_FORCE_BLOCKED    | IP=185.220.101.5 | {}
2024-03-15 14:31:00 | HONEYPOT_HIT           | IP=45.33.32.156  | {"uri":"/wp-admin/"}
2024-03-15 14:35:00 | RATE_LIMIT_MIN         | IP=10.0.0.99     | {"cnt":32}
```

### Konfigurasi Keamanan di `config.php`

```php
// Aktifkan/nonaktifkan autentikasi
define('AUTH_ENABLED', true);

// Rate limits (sesuaikan dengan kebutuhan)
define('RATE_LIMIT_PER_MIN',  30);
define('RATE_LIMIT_PER_HOUR', 200);
define('RATE_POST_PER_MIN',   10);

// Brute-force settings
define('BRUTE_MAX_FAILS',     5);
define('BRUTE_BLOCK_MINUTES', 30);

// Body size limit
define('MAX_BODY_BYTES', 8192);   // 8 KB
```

---

## 📡 Firmware Wemos D1 R32

### Library Arduino IDE (Tools → Manage Libraries)

| Library               | Versi | Author              |
|-----------------------|-------|---------------------|
| esp32 (board support) | 2.x+  | Espressif Systems   |
| ArduinoJson           | 6.x   | Benoit Blanchon     |
| OneWire               | 2.3   | Paul Stoffregen     |
| DallasTemperature     | 3.9   | Miles Burton        |

### Board Settings Arduino IDE

```
Board      : ESP32 Dev Module  (atau "WEMOS D1 R32")
Upload Speed: 921600
CPU Frequency: 240MHz
Flash Size : 4MB
Partition Scheme: Default 4MB
```

### Konfigurasi Firmware `kompos_d1r32.ino`

Edit bagian **① KONFIGURASI** di awal file:
```cpp
const char* WIFI_SSID     = "NamaWiFi_Anda";
const char* WIFI_PASSWORD = "PasswordWiFi_Anda";
const char* SERVER_BASE   = "http://192.168.1.100/kompos/api";
const char* API_KEY       = "kompos2024iot";  // harus sama config.php
const char* DEVICE_ID     = "D1R32_01";
const uint32_t SEND_INTERVAL_MS = 60000UL;    // 60 detik
```

### Wiring D1 R32

```
┌─────────────────────────────────────────────────────┐
│               Wemos D1 R32 (ESP32)                  │
│                                                     │
│  DS18B20  DATA ──────── D4  (GPIO4)                 │
│           VCC  ──────── 3.3V                        │
│           GND  ──────── GND                         │
│           [4.7kΩ antara DATA dan 3.3V]              │
│                                                     │
│  Soil     AOUT ──────── A0  (GPIO36/VP) ADC 12-bit  │
│  Moisture VCC  ──────── 3.3V                        │
│           GND  ──────── GND                         │
│                                                     │
│  MQ-135   AOUT → [R1 10kΩ → node → R2 20kΩ → GND] │
│                  node ─── A1 (GPIO39/VN) ADC 12-bit │
│           VCC  ──────── 5V (VIN)                    │
│           GND  ──────── GND                         │
│                                                     │
│  LED      (+) ─ 220Ω ── D13 (GPIO13)               │
│           (−) ──────── GND                          │
└─────────────────────────────────────────────────────┘

Voltage divider MQ-135 (5V → 3.3V):
  AOUT → R1(10kΩ) → [node] → R2(20kΩ) → GND
  [node] → A1 (GPIO39)
  Vout = 5V × 20/(10+20) = 3.33V ✓
```

### Perbedaan D1 R32 vs ESP8266

| Fitur               | Wemos D1 R32 (ESP32) | ESP8266         |
|---------------------|----------------------|-----------------|
| ADC channels        | 2 independen (12-bit) | 1 (10-bit)     |
| Perlu relay MQ-135  | ❌ Tidak perlu        | ✅ Perlu relay |
| NTP                 | Built-in SNTP        | Library external|
| Kalibrasi storage   | NVS Preferences      | EEPROM          |
| Clock               | Dual-core 240 MHz    | 80 MHz          |
| RAM heap            | ~320 KB              | ~80 KB          |

---

## 🐍 Simulasi Python

```bash
# Install dependency
pip install requests

# Edit SERVER_BASE dan API_KEY di simulasi_php.py, lalu:
python simulasi_php.py
```

**Konfigurasi `simulasi_php.py`:**
```python
SERVER_BASE     = "http://localhost/kompos/api"
API_KEY         = "kompos2024iot"
DEVICE_ID       = "D1R32_SIM"
SAMPEL_PER_FASE = 10      # 10 × 6 fase = 60 total record
DELAY_DETIK     = 0.3     # jeda antar kirim
```

---

## 🔧 Maintenance

### Lihat IP yang diblokir
```bash
# Via CLI PHP
php -r "
  require '/var/www/html/kompos/api/config.php';
  require '/var/www/html/kompos/api/security.php';
  print_r(listBlockedIps());
"
```

### Hapus semua blokir
```bash
php -r "
  require '/var/www/html/kompos/api/config.php';
  require '/var/www/html/kompos/api/security.php';
  clearAllBlocks();
"
```

### Hapus log lama
```bash
# Hapus audit log lebih dari 30 hari
find /var/www/html/kompos/data/security/ -name "audit.log.*" \
     -mtime +30 -delete
```

### Rotasi SQLite database
```bash
# Backup database
cp /var/www/html/kompos/data/kompos.sqlite \
   /backup/kompos_$(date +%Y%m%d).sqlite

# Hapus data lebih dari 60 hari
sqlite3 /var/www/html/kompos/data/kompos.sqlite \
  "DELETE FROM sensor_data WHERE timestamp < datetime('now', '-60 days');"
sqlite3 /var/www/html/kompos/data/kompos.sqlite "VACUUM;"
```

---

## ⚠️ Checklist Sebelum Produksi

- [ ] Ganti `API_KEY` dengan string acak minimal 32 karakter
- [ ] Isi `IP_WHITELIST` dengan IP perangkat IoT Anda
- [ ] Aktifkan HTTPS (Let's Encrypt / Certbot)
- [ ] Uncomment `Strict-Transport-Security` di `security.php`
- [ ] Set `AUTH_ENABLED = true` di `config.php`
- [ ] Pastikan folder `data/` tidak dapat diakses dari web
- [ ] Aktifkan `mod_headers` Apache: `sudo a2enmod headers`
- [ ] Kalibrasi MQ-135 (`calibrateMQ135()`) di lingkungan bersih
- [ ] Test semua endpoint dengan `simulasi_php.py`

---

*Universitas Mataram — Program Studi Teknik Informatika*
*Wirarama Wedashwara Wyrawan, 2024*
