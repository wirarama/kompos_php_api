# KomposIoT — Wemos D1 R32 + PHP Server

Sistem monitoring kompos IoT berbasis **ESP32 (Wemos D1 R32)** dengan
server **PHP REST API** dan skrip simulasi Python.

---

## 📁 Struktur File

```
kompos_d1r32/
├── firmware/
│   └── kompos_d1r32.ino     ← Upload ke Wemos D1 R32
├── server/
│   ├── api/
│   │   ├── index.php        ← Router utama
│   │   ├── config.php       ← Konfigurasi global
│   │   ├── db.php           ← PDO SQLite helper
│   │   ├── sprt.php         ← SPRT-CUSUM engine
│   │   ├── ikk.php          ← Indeks Kesehatan Kompos
│   │   ├── data.php         ← POST /api/data.php
│   │   ├── latest.php       ← GET  /api/latest.php
│   │   ├── history.php      ← GET  /api/history.php
│   │   ├── aggregate.php    ← GET  /api/aggregate.php
│   │   ├── status.php       ← GET  /api/status.php
│   │   ├── health.php       ← GET  /api/health.php
│   │   ├── reset.php        ← DELETE /api/reset.php
│   │   └── .htaccess        ← Apache rewrite rules
│   └── data/                ← Auto-created (writable)
│       ├── kompos.sqlite
│       └── sprt_state.json
└── simulasi_php.py          ← Simulasi pengiriman Python
```

---

## 🚀 Deployment Server PHP

### Persyaratan
- PHP >= 7.4 dengan ekstensi: `pdo`, `pdo_sqlite`, `json`
- Apache (dengan mod_rewrite) atau Nginx
- Folder `server/data/` harus writable

### Langkah Deploy

```bash
# 1. Copy folder server/ ke web root
cp -r server/ /var/www/html/kompos/

# 2. Buat dan set permission folder data
mkdir -p /var/www/html/kompos/data
chmod 775 /var/www/html/kompos/data
chown www-data:www-data /var/www/html/kompos/data

# 3. Aktifkan mod_rewrite Apache
a2enmod rewrite
systemctl restart apache2

# 4. Test health check
curl http://localhost/kompos/api/health.php
```

### Nginx Config
```nginx
location /kompos/api/ {
    try_files $uri $uri/ /kompos/api/index.php?$query_string;
}
```

---

## 📡 Firmware Wemos D1 R32

### Library yang Dibutuhkan (Arduino IDE)
- **esp32** by Espressif Systems (Board Support Package)
- **ArduinoJson** v6.x by Benoit Blanchon
- **OneWire** v2.3 by Paul Stoffregen
- **DallasTemperature** v3.9 by Miles Burton

### Konfigurasi Firmware
Edit bagian ① di `kompos_d1r32.ino`:
```cpp
const char* WIFI_SSID   = "NamaWiFi";
const char* WIFI_PASSWORD = "Password";
const char* SERVER_BASE = "http://192.168.1.100/kompos/api";
const char* API_KEY     = "kompos2024iot";
```

### Wiring D1 R32
| Sensor         | Pin D1 R32 | GPIO   | Catatan             |
|----------------|-----------|--------|---------------------|
| DS18B20 DATA   | D4        | GPIO4  | + 4.7kΩ ke 3.3V    |
| Soil Moisture  | A0        | GPIO36 | ADC 12-bit (VP)     |
| MQ-135 AOUT    | A1        | GPIO39 | Via voltage divider |
| LED Status     | D13       | GPIO13 | + 220Ω              |

---

## 🐍 Simulasi Python

```bash
# Install dependency
pip install requests

# Jalankan (pastikan PHP server berjalan dulu)
python simulasi_php.py
```

### Konfigurasi
Edit di `simulasi_php.py`:
```python
SERVER_BASE      = "http://localhost/kompos/api"
API_KEY          = "kompos2024iot"
SAMPEL_PER_FASE  = 10
DELAY_DETIK      = 0.3
```

---

## 🔌 API Endpoints

| Method   | Endpoint              | Keterangan                        |
|----------|-----------------------|-----------------------------------|
| `POST`   | `/api/data.php`       | Kirim data sensor                 |
| `GET`    | `/api/latest.php`     | Data terbaru                      |
| `GET`    | `/api/history.php`    | Riwayat (param: hours, limit)     |
| `GET`    | `/api/aggregate.php`  | Agregasi (param: level, days)     |
| `GET`    | `/api/status.php`     | Status server + SPRT state        |
| `GET`    | `/api/health.php`     | Health check (tanpa auth)         |
| `DELETE` | `/api/reset.php`      | Reset database (dev only)         |

### Contoh POST Request
```bash
curl -X POST http://localhost/kompos/api/data.php \
  -H "Content-Type: application/json" \
  -H "X-API-Key: kompos2024iot" \
  -d '{"device_id":"D1R32_01","timestamp":"2024-03-15T14:30:00",
       "suhu":54.3,"moisture":48.2,"gas":185.6}'
```

### Contoh Response 201
```json
{
  "id": 1,
  "status": "ok",
  "analysis": {
    "fase_pred": 1,
    "fase_nama": "Termofilik Aktif",
    "ikk": 72.4,
    "sprt": {"cusum_t": 1.23, "cusum_m": 0.45, "cusum_g": 2.11}
  },
  "alerts": [],
  "recommendation": "Semua parameter dalam kondisi normal."
}
```

---

*Universitas Mataram — Program Studi Teknik Informatika*
*Wirarama Wedashwara Wyrawan, 2024*
