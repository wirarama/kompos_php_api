"""
============================================================
 SIMULASI KIRIM DATA KOMPOS IoT → PHP SERVER
 Mensimulasikan Wemos D1 R32 mengirim JSON via HTTP POST
 untuk setiap fase kompos (6 fase × N sampel per fase)
============================================================
 Target : PHP REST API (data.php)
 Author : Wirarama Wedashwara Wyrawan — Universitas Mataram
============================================================
 Jalankan  : python simulasi_php.py
 Prasyarat : pip install requests
============================================================
"""

import requests
import json
import random
import time
import sys
from datetime import datetime, timedelta
from collections import Counter

# ════════════════════════════════════════════════════════════
# KONFIGURASI
# ════════════════════════════════════════════════════════════
SERVER_BASE   = "http://localhost/kompos/api"  # Ganti dengan IP/domain server
API_KEY       = "kompos2024iot"                # Harus sama dengan config.php
DEVICE_ID     = "D1R32_SIM"                   # ID perangkat simulasi
DEVICE_LOC    = "Bak Kompos A"

SAMPEL_PER_FASE = 10     # Jumlah sampel per fase (min 5, rekomendasi 20–50)
DELAY_DETIK     = 0.3    # Jeda antar pengiriman (detik)

# ════════════════════════════════════════════════════════════
# PROFIL SENSOR PER FASE
# Nilai diambil dari paper KomposIoT v2 (SPRT hypothesis ranges)
# ════════════════════════════════════════════════════════════
FASE_PROFIL = {
    0: {
        "nama"    : "Mesophilik Awal",
        "emoji"   : "🌱",
        "hari"    : (0,  4),
        "suhu"    : (20.0, 38.0),
        "moisture": (62.0, 75.0),
        "gas"     : (40.0, 90.0),
        "deskripsi": "Aktivasi mikroba mesofilik, suhu mulai naik",
    },
    1: {
        "nama"    : "Termofilik Aktif",
        "emoji"   : "🔥",
        "hari"    : (4,  14),
        "suhu"    : (38.0, 65.0),
        "moisture": (48.0, 68.0),
        "gas"     : (90.0, 280.0),
        "deskripsi": "Mikroba termofilik dominan, suhu & gas naik pesat",
    },
    2: {
        "nama"    : "Puncak Dekomposisi",
        "emoji"   : "⚡",
        "hari"    : (14, 20),
        "suhu"    : (52.0, 70.0),
        "moisture": (36.0, 52.0),
        "gas"     : (280.0, 580.0),
        "deskripsi": "Suhu dan gas NH3/CO2 mencapai puncak tertinggi",
    },
    3: {
        "nama"    : "Pendinginan",
        "emoji"   : "❄️",
        "hari"    : (20, 28),
        "suhu"    : (28.0, 55.0),
        "moisture": (38.0, 54.0),
        "gas"     : (120.0, 480.0),
        "deskripsi": "Suhu turun eksponensial, biomassa mikroba berkurang",
    },
    4: {
        "nama"    : "Maturasi",
        "emoji"   : "🌾",
        "hari"    : (28, 36),
        "suhu"    : (24.0, 35.0),
        "moisture": (38.0, 52.0),
        "gas"     : (45.0, 160.0),
        "deskripsi": "Pembentukan humus, aktivitas mikroba rendah stabil",
    },
    5: {
        "nama"    : "Kompos Matang",
        "emoji"   : "✅",
        "hari"    : (36, 42),
        "suhu"    : (18.0, 28.0),
        "moisture": (34.0, 50.0),
        "gas"     : (20.0, 90.0),
        "deskripsi": "Kompos stabil, siap diaplikasikan ke lahan",
    },
}

# Warna ANSI untuk terminal
class Color:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    DIM    = "\033[2m"

FASE_COLORS = [
    Color.GREEN, Color.YELLOW, Color.RED,
    Color.CYAN,  Color.MAGENTA, Color.BLUE,
]

# ════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════
def sensor_value(lo: float, hi: float, noise: float = 0.05) -> float:
    """
    Generate nilai sensor realistis dalam range [lo, hi].
    Menambahkan Gaussian noise ±5% untuk menyimulasikan fluktuasi sensor.
    """
    base   = random.uniform(lo, hi)
    jitter = base * noise * random.gauss(0, 1)
    val    = base + jitter
    return round(max(lo * 0.88, min(hi * 1.12, val)), 2)


def spread_timestamp(fase_id: int, sample_idx: int,
                     base_date: datetime) -> datetime:
    """
    Distribusikan timestamp secara merata dalam rentang hari fase.
    """
    lo, hi = FASE_PROFIL[fase_id]["hari"]
    n      = max(SAMPEL_PER_FASE - 1, 1)
    frac   = sample_idx / n
    day_offset = lo + (hi - lo) * frac
    hour_offset = random.uniform(0, 23)
    return base_date + timedelta(days=day_offset, hours=hour_offset)


def progress_bar(current: int, total: int, width: int = 22) -> str:
    """Render progress bar ASCII."""
    filled = int(current / total * width)
    return "█" * filled + "░" * (width - filled)


def ikk_label(ikk: float) -> str:
    if ikk >= 80: return f"{Color.GREEN}Optimal 🟢{Color.RESET}"
    if ikk >= 60: return f"{Color.YELLOW}Baik 🟡{Color.RESET}"
    if ikk >= 40: return f"{Color.YELLOW}Perhatian 🟠{Color.RESET}"
    return f"{Color.RED}Kritis 🔴{Color.RESET}"


def alert_color(a: str) -> str:
    if "CRITICAL" in a: return f"{Color.RED}{a}{Color.RESET}"
    return f"{Color.YELLOW}{a}{Color.RESET}"


# ════════════════════════════════════════════════════════════
# HTTP FUNCTIONS
# ════════════════════════════════════════════════════════════
HEADERS = {
    "Content-Type": "application/json",
    "Accept"       : "application/json",
    "X-API-Key"    : API_KEY,
}


def check_server() -> bool:
    """Cek koneksi ke PHP server via health endpoint."""
    url = f"{SERVER_BASE}/health.php"
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"{Color.GREEN}✅ Server online{Color.RESET}  "
                  f"PHP {data.get('php','?')}  "
                  f"— {data.get('server','?')}")
            return True
        else:
            print(f"{Color.RED}❌ Server HTTP {r.status_code}{Color.RESET}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"{Color.RED}❌ Tidak bisa terhubung ke {url}{Color.RESET}")
        print(f"   Pastikan PHP server berjalan dan SERVER_BASE benar.")
        return False
    except Exception as e:
        print(f"{Color.RED}❌ Error: {e}{Color.RESET}")
        return False


def kirim_data(fase_id: int, sample_idx: int,
               timestamp: datetime) -> tuple[bool, dict, dict]:
    """
    Kirim satu sampel ke POST /api/data.php.
    Returns (sukses, payload, response_dict)
    """
    p = FASE_PROFIL[fase_id]
    payload = {
        "device_id" : DEVICE_ID,
        "device_loc": DEVICE_LOC,
        "timestamp" : timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "suhu"      : sensor_value(*p["suhu"]),
        "moisture"  : sensor_value(*p["moisture"]),
        "gas"       : sensor_value(*p["gas"]),
        "api_key"   : API_KEY,
    }

    url = f"{SERVER_BASE}/data.php"
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=8)
        if r.status_code in (200, 201):
            return True, payload, r.json()
        else:
            return False, payload, {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
    except requests.exceptions.ConnectionError:
        return False, payload, {"error": "Connection refused"}
    except requests.exceptions.Timeout:
        return False, payload, {"error": "Timeout"}
    except Exception as e:
        return False, payload, {"error": str(e)}


def get_status() -> dict:
    """Ambil status server setelah simulasi selesai."""
    try:
        r = requests.get(
            f"{SERVER_BASE}/status.php",
            headers=HEADERS, timeout=5)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ════════════════════════════════════════════════════════════
# MAIN SIMULASI
# ════════════════════════════════════════════════════════════
def main():
    random.seed(42)

    total_fase  = len(FASE_PROFIL)
    total_kirim = total_fase * SAMPEL_PER_FASE
    base_date   = datetime.now() - timedelta(days=42)

    # ── Header ──────────────────────────────────────────────
    print(f"\n{Color.BOLD}{'═'*62}{Color.RESET}")
    print(f"{Color.BOLD}  SIMULASI KIRIM DATA KOMPOS IoT → PHP SERVER{Color.RESET}")
    print(f"{'═'*62}")
    print(f"  Server       : {Color.CYAN}{SERVER_BASE}{Color.RESET}")
    print(f"  Device ID    : {DEVICE_ID}")
    print(f"  Fase         : {total_fase}")
    print(f"  Sampel/fase  : {SAMPEL_PER_FASE}")
    print(f"  Total kirim  : {Color.BOLD}{total_kirim}{Color.RESET}")
    print(f"  Delay        : {DELAY_DETIK} detik")
    print(f"{'═'*62}\n")

    # ── Cek server ──────────────────────────────────────────
    print("🔌 Mengecek koneksi server... ", end="", flush=True)
    if not check_server():
        sys.exit(1)
    print()

    rekap          = []
    total_sukses   = 0
    total_gagal    = 0

    # ── Loop 6 fase ─────────────────────────────────────────
    for fase_id in range(total_fase):
        p     = FASE_PROFIL[fase_id]
        fc    = FASE_COLORS[fase_id]

        print(f"{'─'*62}")
        print(f"{fc}{Color.BOLD}  {p['emoji']}  Fase {fase_id}: {p['nama']}"
              f"  (Hari {p['hari'][0]}–{p['hari'][1]}){Color.RESET}")
        print(f"{Color.DIM}  {p['deskripsi']}{Color.RESET}")
        print(f"  🌡  {p['suhu'][0]}–{p['suhu'][1]}°C  "
              f"💧 {p['moisture'][0]}–{p['moisture'][1]}%  "
              f"🌫  {p['gas'][0]}–{p['gas'][1]} ppm")
        print()

        n_ok        = 0
        n_fail      = 0
        ikk_list    = []
        fase_det    = []

        for s in range(SAMPEL_PER_FASE):
            ts       = spread_timestamp(fase_id, s, base_date)
            ok, pld, resp = kirim_data(fase_id, s, ts)

            bar = progress_bar(s + 1, SAMPEL_PER_FASE)
            pct = (s + 1) / SAMPEL_PER_FASE * 100

            if ok:
                n_ok += 1
                total_sukses += 1
                analysis  = resp.get("analysis", {})
                ikk_val   = analysis.get("ikk", 0)
                fase_name = analysis.get("fase_nama", "?")
                alerts    = resp.get("alerts", [])
                ikk_list.append(ikk_val)
                fase_det.append(fase_name)

                alert_str = ""
                if alerts:
                    alert_str = " ⚠ " + " ".join(
                        alert_color(a) for a in alerts)

                print(
                    f"  [{fc}{bar}{Color.RESET}] "
                    f"#{s+1:02d} "
                    f"{Color.YELLOW}T={pld['suhu']:5.1f}°C{Color.RESET}  "
                    f"{Color.CYAN}M={pld['moisture']:4.1f}%{Color.RESET}  "
                    f"{Color.GREEN}G={pld['gas']:6.1f}ppm{Color.RESET}  "
                    f"→ IKK={ikk_val:5.1f}  "
                    f"{Color.DIM}[{fase_name}]{Color.RESET}"
                    f"{alert_str}"
                )
            else:
                n_fail += 1
                total_gagal += 1
                err = resp.get("error", "unknown")
                print(f"  [{bar}] #{s+1:02d}  "
                      f"{Color.RED}❌ GAGAL: {err}{Color.RESET}")

            time.sleep(DELAY_DETIK)

        # ── Ringkasan per fase ──────────────────────────────
        ikk_avg     = sum(ikk_list) / len(ikk_list) if ikk_list else 0
        fase_dominan = Counter(fase_det).most_common(1)[0][0] \
                       if fase_det else "-"

        print(f"\n  {Color.BOLD}Ringkasan Fase {fase_id}:{Color.RESET}  "
              f"Sukses {Color.GREEN}{n_ok}/{SAMPEL_PER_FASE}{Color.RESET}  │  "
              f"IKK rata {Color.BOLD}{ikk_avg:.1f}{Color.RESET}  {ikk_label(ikk_avg)}  │  "
              f"Fase terdeteksi: {Color.CYAN}{fase_dominan}{Color.RESET}\n")

        rekap.append({
            "fase_id"     : fase_id,
            "nama"        : p["nama"],
            "sukses"      : n_ok,
            "gagal"       : n_fail,
            "ikk_avg"     : round(ikk_avg, 2),
            "fase_dominan": fase_dominan,
        })

    # ── Rekap akhir ─────────────────────────────────────────
    print(f"\n{Color.BOLD}{'═'*62}{Color.RESET}")
    print(f"{Color.BOLD}  REKAP AKHIR SIMULASI{Color.RESET}")
    print(f"{'═'*62}")
    print(f"  Total dikirim : {total_sukses + total_gagal}")
    print(f"  Sukses        : {Color.GREEN}{total_sukses}{Color.RESET}")
    print(f"  Gagal         : "
          f"{Color.RED if total_gagal else Color.GREEN}{total_gagal}{Color.RESET}")
    print()

    # Tabel rekap
    print(f"  {'Fase':<25} {'Sukses':>7} {'IKK':>7}  {'Terdeteksi'}")
    print(f"  {'─'*56}")
    for row in rekap:
        fc  = FASE_COLORS[row["fase_id"]]
        ikk = row["ikk_avg"]
        print(
            f"  {fc}{FASE_PROFIL[row['fase_id']]['emoji']}"
            f" {row['nama']:<23}{Color.RESET}"
            f"  {row['sukses']:>4}/{SAMPEL_PER_FASE:<2}"
            f"  {ikk:>6.1f}"
            f"  {Color.DIM}{row['fase_dominan']}{Color.RESET}"
        )

    # Status server
    print()
    st = get_status()
    if st:
        total_db = st.get("total_records", "?")
        print(f"  Total rekaman di database : {Color.BOLD}{total_db}{Color.RESET}")

    print(f"{'═'*62}")
    print(f"  {Color.GREEN}✅ Simulasi selesai!{Color.RESET}")
    print(f"  Lihat hasilnya di dashboard Streamlit atau")
    print(f"  query langsung: GET {SERVER_BASE}/history.php")
    print(f"{'═'*62}\n")


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}⚠  Simulasi dihentikan oleh pengguna.{Color.RESET}\n")
        sys.exit(0)
