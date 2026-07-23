"""
╔══════════════════════════════════════════════════════════════════╗
║  KomposIoT Dashboard v3 — PHP API Edition                       ║
║  Target  : PHP REST API (kompos_d1r32 server)                   ║
║  Fitur   : Live Monitor · Tren Sensor · Analisis SPRT           ║
║            Klasifikasi Fase (Decision Tree)                      ║
║            Regresi IKK (Decision Tree Regressor)                 ║
║            Agregasi · Konfigurasi                                ║
╚══════════════════════════════════════════════════════════════════╝
Jalankan: streamlit run dashboard_php.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import json
from datetime import datetime, timedelta
import time
import warnings
from io import StringIO

# ML imports
from sklearn.tree import (DecisionTreeClassifier, DecisionTreeRegressor,
                          export_text, plot_tree)
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (classification_report, confusion_matrix,
                              mean_absolute_error, mean_squared_error, r2_score)
from sklearn.pipeline import Pipeline
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════
# KONFIGURASI
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="KomposIoT Monitor",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Default server (PHP API) ──────────────────────────────────────
DEFAULT_SERVER = "https://wedashwara.com/kompos"
DEFAULT_APIKEY = "kompos2024iot"

FASE_DEF = {
    0: {"nama": "Mesophilik Awal",    "warna": "#52B788", "emoji": "🌱"},
    1: {"nama": "Termofilik Aktif",   "warna": "#E76F51", "emoji": "🔥"},
    2: {"nama": "Puncak Dekomposisi", "warna": "#9B2226", "emoji": "⚡"},
    3: {"nama": "Pendinginan",        "warna": "#219EBC", "emoji": "❄️"},
    4: {"nama": "Maturasi",           "warna": "#8B5E3C", "emoji": "🌾"},
    5: {"nama": "Kompos Matang",      "warna": "#6B7280", "emoji": "✅"},
}

SENSOR_OPTS = {
    "suhu":     {"label": "Suhu (°C)",       "color": "#FF8C42", "unit": "°C"},
    "moisture": {"label": "Kelembapan (%)",  "color": "#38BDF8", "unit": "%"},
    "gas":      {"label": "Gas (ppm)",        "color": "#86EFAC", "unit": "ppm"},
}

# ── Color helper: convert #RRGGBB hex + alpha to rgba() ──────────
def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert #RRGGBB string + alpha float to Plotly-compatible rgba() string."""
    h = hex_color.lstrip('#')
    if len(h) == 6:
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color  # fallback unchanged


# ══════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.stApp { background-color: #0B1120; color: #D8E4F0; }
section[data-testid="stSidebar"] { background: #131E30; }
section[data-testid="stSidebar"] * { color: #D8E4F0 !important; }

.metric-card {
    background: #162232; border-radius: 10px;
    padding: 14px 18px; border-left: 4px solid;
    margin-bottom: 8px;
}
.metric-value { font-size: 2.1rem; font-weight: 700; line-height: 1.1; }
.metric-label { font-size: 0.78rem; opacity: 0.65; margin-top: 2px; }
.metric-sub   { font-size: 0.82rem; margin-top: 5px; }

.fase-badge {
    display: inline-block; padding: 5px 16px;
    border-radius: 20px; font-weight: 700;
    font-size: 0.9rem; color: white; margin: 4px 0;
}
.sec-title {
    font-size: 1.0rem; font-weight: 700; color: #38BDF8;
    border-bottom: 1px solid #1E3048;
    padding-bottom: 5px; margin: 14px 0 9px 0;
}
.alert-critical { background:#7F1D1D; border-left:4px solid #EF4444;
                  padding:8px 12px; border-radius:6px; margin:3px 0; font-size:0.85rem; }
.alert-warning  { background:#451A03; border-left:4px solid #F59E0B;
                  padding:8px 12px; border-radius:6px; margin:3px 0; font-size:0.85rem; }
.alert-ok       { background:#14532D; border-left:4px solid #22C55E;
                  padding:8px 12px; border-radius:6px; margin:3px 0; font-size:0.85rem; }
.ml-card {
    background: #162232; border-radius: 10px;
    padding: 16px; margin-bottom: 10px;
    border: 1px solid #1E3048;
}
.ml-metric { text-align:center; padding:10px; background:#1A2840;
             border-radius:8px; margin:4px; }
.ml-metric-val { font-size:1.5rem; font-weight:700; }
.ml-metric-lbl { font-size:0.75rem; color:#94A3B8; margin-top:2px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# API HELPER
# ══════════════════════════════════════════════════════════════════
def get_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-Key": api_key,
    }


@st.cache_data(ttl=5)
def api_latest(base: str, key: str, device_id: str):
    try:
        r = requests.get(f"{base}/latest.php",
                         headers=get_headers(key),
                         params={"device_id": device_id}, timeout=4)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=10)
def api_history(base: str, key: str, device_id: str, hours: int = 24,
                limit: int = 500) -> pd.DataFrame:
    try:
        r = requests.get(f"{base}/history.php",
                         headers=get_headers(key),
                         params={"device_id": device_id,
                                 "hours": hours, "limit": limit},
                         timeout=8)
        if r.status_code == 200:
            df = pd.DataFrame(r.json().get("data", []))
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                for c in ["suhu", "moisture", "gas", "ikk",
                           "sprt_cusum_t", "sprt_cusum_m", "sprt_cusum_g"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                if "fase_pred" in df.columns:
                    df["fase_pred"] = df["fase_pred"].astype(int)
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def api_aggregate(base: str, key: str, device_id: str,
                  level: str = "hourly", days: int = 7) -> pd.DataFrame:
    try:
        r = requests.get(f"{base}/aggregate.php",
                         headers=get_headers(key),
                         params={"device_id": device_id,
                                 "level": level, "days": days},
                         timeout=8)
        if r.status_code == 200:
            return pd.DataFrame(r.json().get("data", []))
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=15)
def api_status(base: str, key: str):
    try:
        r = requests.get(f"{base}/status.php",
                         headers=get_headers(key), timeout=4)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def api_health(base: str) -> bool:
    try:
        r = requests.get(f"{base}/health.php", timeout=3)
        return r.status_code == 200
    except Exception:
        return False



# ══════════════════════════════════════════════════════════════════
# DB HEALTH CHECK
# ══════════════════════════════════════════════════════════════════
def check_db_health(base: str, key: str) -> dict:
    """Cek apakah database PHP sudah terbentuk dan bisa ditulis."""
    result = {
        "server_online": False,
        "db_exists": False,
        "db_writable": False,
        "total_records": 0,
        "last_record": None,
        "error": None,
    }
    try:
        # 1. server online?
        r = requests.get(f"{base}/health.php", timeout=4)
        if r.status_code != 200:
            result["error"] = f"Server HTTP {r.status_code}"
            return result
        result["server_online"] = True
        health = r.json()
        result["db_exists"] = health.get("db_path") == "exists"

        # 2. status (total records)
        r2 = requests.get(f"{base}/status.php",
                          headers=get_headers(key), timeout=4)
        if r2.status_code == 200:
            st_data = r2.json()
            result["total_records"] = st_data.get("total_records", 0)
            result["last_record"]   = st_data.get("latest")

        # 3. write test — kirim satu data dummy & cek id bertambah
        test_payload = {
            "device_id": "__db_test__",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "suhu": 25.0, "moisture": 50.0, "gas": 100.0,
            "api_key": key,
        }
        r3 = requests.post(f"{base}/data.php",
                           headers=get_headers(key),
                           json=test_payload, timeout=6)
        if r3.status_code in (200, 201):
            resp3 = r3.json()
            if resp3.get("id"):
                result["db_writable"] = True
                result["test_id"]     = resp3["id"]
        elif r3.status_code == 401:
            result["error"] = "Auth gagal — cek API key"
        else:
            result["error"] = f"Write test HTTP {r3.status_code}"

    except requests.exceptions.ConnectionError:
        result["error"] = "Connection refused — pastikan server.py / PHP berjalan"
    except requests.exceptions.Timeout:
        result["error"] = "Timeout — server lambat merespons"
    except Exception as e:
        result["error"] = str(e)

    return result


# ══════════════════════════════════════════════════════════════════
# UI SIMULATION HELPERS
# ══════════════════════════════════════════════════════════════════
FASE_PROFIL_SIM = {
    0: {"nama":"Mesophilik Awal",    "suhu":(20,38),  "moisture":(62,75), "gas":(40,90)},
    1: {"nama":"Termofilik Aktif",   "suhu":(38,65),  "moisture":(48,68), "gas":(90,280)},
    2: {"nama":"Puncak Dekomposisi", "suhu":(52,70),  "moisture":(36,52), "gas":(280,580)},
    3: {"nama":"Pendinginan",        "suhu":(28,55),  "moisture":(38,54), "gas":(120,480)},
    4: {"nama":"Maturasi",           "suhu":(24,35),  "moisture":(38,52), "gas":(45,160)},
    5: {"nama":"Kompos Matang",      "suhu":(18,28),  "moisture":(34,50), "gas":(20,90)},
}

def sim_sensor(lo, hi, noise=0.05):
    import random
    base   = random.uniform(lo, hi)
    jitter = base * noise * random.gauss(0, 1)
    return round(max(lo*0.9, min(hi*1.1, base+jitter)), 2)

def run_ui_simulation(base: str, key: str, device_id: str,
                      fase_ids: list, n_per_fase: int,
                      delay_ms: int, progress_placeholder,
                      log_placeholder) -> list:
    """Kirim data simulasi dari UI dan kembalikan log hasil."""
    import random, time as _time
    random.seed()
    results = []
    logs    = []
    total   = len(fase_ids) * n_per_fase
    done    = 0
    base_dt = datetime.now() - timedelta(days=42)

    for fase_id in fase_ids:
        p = FASE_PROFIL_SIM[fase_id]
        emoji = FASE_DEF[fase_id]["emoji"]
        for s in range(n_per_fase):
            suhu    = sim_sensor(*p["suhu"])
            moisture= sim_sensor(*p["moisture"])
            gas     = sim_sensor(*p["gas"])
            ts      = (base_dt + timedelta(
                        days=fase_id*6 + s*(6/max(n_per_fase-1,1)),
                        hours=random.uniform(0,23))
                      ).strftime("%Y-%m-%dT%H:%M:%S")

            payload = {
                "device_id": device_id,
                "timestamp": ts,
                "suhu": suhu, "moisture": moisture, "gas": gas,
                "api_key": key,
            }
            try:
                r   = requests.post(f"{base}/data.php",
                                    headers=get_headers(key),
                                    json=payload, timeout=6)
                ok  = r.status_code in (200, 201)
                an  = r.json().get("analysis", {}) if ok else {}
                ikk = an.get("ikk", 0)
                fname = an.get("fase_nama", "?")
                log   = (f"{emoji} F{fase_id} #{s+1:02d}  "
                         f"T={suhu:.1f}°C M={moisture:.1f}% G={gas:.0f}ppm  "
                         f"→ {'✅' if ok else '❌'}  "
                         f"IKK={ikk:.1f}  [{fname}]")
            except Exception as e:
                ok  = False
                log = f"❌ F{fase_id} #{s+1:02d} ERROR: {e}"

            logs.append(log)
            results.append({"fase": fase_id, "ok": ok})
            done += 1
            progress_placeholder.progress(done / total,
                text=f"Mengirim {done}/{total} sampel...")
            log_placeholder.code("\n".join(logs[-20:]))   # tampilkan 20 baris terakhir
            if delay_ms > 0:
                _time.sleep(delay_ms / 1000)

    return results


def send_manual(base: str, key: str, payload: dict):
    try:
        r = requests.post(f"{base}/data.php",
                          headers=get_headers(key),
                          json=payload, timeout=6)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


# ══════════════════════════════════════════════════════════════════
# ML HELPERS — Decision Tree
# ══════════════════════════════════════════════════════════════════
FEATURES = ["suhu", "moisture", "gas"]
FEATURE_LABELS = ["Suhu (°C)", "Kelembapan (%)", "Gas (ppm)"]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah derived features untuk model ML."""
    df = df.copy()
    # Rate-of-change (per row)
    df["d_suhu"]    = df["suhu"].diff().fillna(0)
    df["d_moisture"]= df["moisture"].diff().fillna(0)
    df["d_gas"]     = df["gas"].diff().fillna(0)
    # Rolling stats (window 3)
    for c in ["suhu", "moisture", "gas"]:
        df[f"{c}_roll_mean"] = df[c].rolling(3, min_periods=1).mean()
        df[f"{c}_roll_std"]  = df[c].rolling(3, min_periods=1).std().fillna(0)
    # Sensor ratios
    df["suhu_gas_ratio"] = df["suhu"] / (df["gas"].replace(0, 1))
    df["cn_proxy"]       = (df["suhu"] * df["moisture"]) / (df["gas"].replace(0, 1))
    return df


ALL_FEATURES = (FEATURES +
                ["d_suhu", "d_moisture", "d_gas",
                 "suhu_roll_mean", "moisture_roll_mean", "gas_roll_mean",
                 "suhu_roll_std",  "moisture_roll_std",  "gas_roll_std",
                 "suhu_gas_ratio", "cn_proxy"])


@st.cache_data(ttl=60, show_spinner=False)
def train_classifier(df_json: str, max_depth: int, min_samples: int,
                     use_all_features: bool):
    """
    Latih Decision Tree Classifier untuk prediksi fase kompos.
    df_json: JSON string dari DataFrame (untuk cache compatibility)
    """
    df = pd.read_json(StringIO(df_json))
    if "fase_pred" not in df.columns or len(df) < 20:
        return None, None, None, None

    df = add_features(df)
    feat_cols = ALL_FEATURES if use_all_features else FEATURES
    feat_cols = [c for c in feat_cols if c in df.columns]

    X = df[feat_cols].fillna(0)
    y = df["fase_pred"].astype(int)

    if y.nunique() < 2:
        return None, None, None, None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_samples,
        criterion="gini",
        random_state=42,
        class_weight="balanced",
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    report = classification_report(y_test, y_pred, output_dict=True,
                                   zero_division=0)
    cm     = confusion_matrix(y_test, y_pred,
                               labels=sorted(y.unique()))
    cv_scores = cross_val_score(clf, X, y, cv=5, scoring="f1_macro")

    meta = {
        "features"   : feat_cols,
        "n_train"    : len(X_train),
        "n_test"     : len(X_test),
        "accuracy"   : round(float((y_pred == y_test).mean()) * 100, 2),
        "macro_f1"   : round(float(cv_scores.mean()) * 100, 2),
        "cv_std"     : round(float(cv_scores.std()) * 100, 2),
        "classes"    : sorted(y.unique().tolist()),
        "report"     : report,
        "cm"         : cm.tolist(),
        "importances": list(zip(feat_cols,
                                clf.feature_importances_.tolist())),
    }
    return clf, X_test, y_test, meta


@st.cache_data(ttl=60, show_spinner=False)
def train_regressor(df_json: str, max_depth: int, min_samples: int,
                    use_all_features: bool):
    """
    Latih Decision Tree Regressor untuk prediksi nilai IKK.
    """
    df = pd.read_json(StringIO(df_json))
    if "ikk" not in df.columns or len(df) < 20:
        return None, None, None, None

    df = add_features(df)
    feat_cols = ALL_FEATURES if use_all_features else FEATURES
    feat_cols = [c for c in feat_cols if c in df.columns]

    X = df[feat_cols].fillna(0)
    y = df["ikk"].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42
    )

    reg = DecisionTreeRegressor(
        max_depth=max_depth,
        min_samples_leaf=min_samples,
        criterion="squared_error",
        random_state=42,
    )
    reg.fit(X_train, y_train)
    y_pred = reg.predict(X_test)

    cv_mse = -cross_val_score(reg, X, y, cv=5, scoring="neg_mean_squared_error")

    meta = {
        "features"   : feat_cols,
        "n_train"    : len(X_train),
        "n_test"     : len(X_test),
        "mae"        : round(float(mean_absolute_error(y_test, y_pred)), 3),
        "rmse"       : round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 3),
        "r2"         : round(float(r2_score(y_test, y_pred)), 4),
        "cv_rmse"    : round(float(np.sqrt(cv_mse.mean())), 3),
        "cv_std"     : round(float(cv_mse.std() ** 0.5), 3),
        "importances": list(zip(feat_cols,
                                reg.feature_importances_.tolist())),
        "y_test"     : y_test.tolist(),
        "y_pred"     : y_pred.tolist(),
    }
    return reg, X_test, y_test, meta


def predict_single(model, feat_cols: list,
                   suhu: float, moisture: float, gas: float) -> float:
    """Prediksi satu baris data baru."""
    row = {"suhu": suhu, "moisture": moisture, "gas": gas,
           "d_suhu": 0, "d_moisture": 0, "d_gas": 0,
           "suhu_roll_mean": suhu, "moisture_roll_mean": moisture,
           "gas_roll_mean": gas,
           "suhu_roll_std": 0, "moisture_roll_std": 0, "gas_roll_std": 0,
           "suhu_gas_ratio": suhu / max(gas, 1),
           "cn_proxy": (suhu * moisture) / max(gas, 1)}
    X = pd.DataFrame([{c: row.get(c, 0) for c in feat_cols}])
    return model.predict(X)[0]


# ══════════════════════════════════════════════════════════════════
# CHART HELPERS
# ══════════════════════════════════════════════════════════════════
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#162232",
    font=dict(color="#D8E4F0", size=10),
    margin=dict(l=0, r=0, t=28, b=0),
    hovermode="x unified",
)


def phase_shading(fig, df: pd.DataFrame, rows=None):
    """Tambah shading warna per fase ke figure."""
    if "fase_pred" not in df.columns or df.empty:
        return
    prev, start = None, None
    for _, row in df.iterrows():
        f = int(row["fase_pred"])
        if f != prev:
            if prev is not None:
                kwargs = dict(x0=start, x1=row["timestamp"],
                              fillcolor=hex_to_rgba(FASE_DEF[prev]["warna"], 0.08),
                              opacity=1.0, layer="below", line_width=0)
                if rows:
                    for r in rows:
                        fig.add_vrect(row=r, col=1, **kwargs)
                else:
                    fig.add_vrect(**kwargs)
            start, prev = row["timestamp"], f


def ikk_color(v: float) -> str:
    if v >= 80: return "#22C55E"
    if v >= 60: return "#F59E0B"
    if v >= 40: return "#EF4444"
    return "#7F1D1D"


def ikk_label(v: float) -> str:
    if v >= 80: return "Optimal 🟢"
    if v >= 60: return "Baik 🟡"
    if v >= 40: return "Perhatian 🟠"
    return "Kritis 🔴"


# ══════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🌿 KomposIoT v3")
    st.markdown("PHP API · Decision Tree ML")
    st.divider()

    st.markdown("### ⚙️ Koneksi Server")
    server_base = st.text_input("PHP API Base URL", value=DEFAULT_SERVER)
    api_key     = st.text_input("API Key", value=DEFAULT_APIKEY, type="password")
    device_id   = st.text_input("Device ID", value="D1R32_01")

    # Server health indicator
    col_h1, col_h2 = st.columns([1, 2])
    with col_h1:
        if st.button("🔌 Ping", use_container_width=True):
            st.cache_data.clear()
    with col_h2:
        online = api_health(server_base)
        st.markdown(
            f"{'🟢 Online' if online else '🔴 Offline'}"
        )

    st.divider()

    st.markdown("### 📤 Kirim Data Manual")
    with st.form("manual_form"):
        ms = st.number_input("Suhu (°C)",       5.0,  80.0, 35.0, 0.1)
        mm = st.number_input("Kelembapan (%)",   0.0, 100.0, 55.0, 0.5)
        mg = st.number_input("Gas (ppm)",        0.0, 700.0,120.0, 1.0)
        send_btn = st.form_submit_button("📤 Kirim", use_container_width=True)

    if send_btn:
        payload = {
            "device_id": device_id,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "suhu": ms, "moisture": mm, "gas": mg,
            "api_key": api_key,
        }
        code, resp = send_manual(server_base, api_key, payload)
        if code in (200, 201):
            an = resp.get("analysis", {})
            st.success(
                f"✅ OK — Fase: {an.get('fase_nama','?')} | "
                f"IKK: {an.get('ikk', 0):.1f}"
            )
            alr = resp.get("alerts", [])
            for a in alr:
                st.warning(f"⚠️ {a}")
            st.cache_data.clear()
        else:
            st.error(f"❌ Error {code}: {resp.get('error','?')}")

    st.divider()

    auto_refresh = st.toggle("🔄 Auto Refresh", value=False)
    if auto_refresh:
        refresh_sec = st.slider("Interval (detik)", 5, 60, 15, 5)
        time.sleep(refresh_sec)
        st.cache_data.clear()
        st.rerun()

    if st.button("🗑 Clear Cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:linear-gradient(90deg,#131E30,#1A2840);
            border-radius:12px;padding:16px 24px;margin-bottom:16px;
            border-left:4px solid #38BDF8;">
  <h1 style="margin:0;color:#D8E4F0;font-size:1.5rem;">
    🌿 KomposIoT Dashboard — PHP API + Decision Tree ML
  </h1>
  <p style="margin:4px 0 0 0;color:#64748B;font-size:0.88rem;">
    SPRT-CUSUM Phase Detection · Decision Tree Classifier · IKK Regressor · PHP REST API
  </p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Live Monitor",
    "📈 Tren Sensor",
    "🔬 Analisis SPRT",
    "🤖 Klasifikasi DT",
    "📉 Agregasi",
    "⚙️ Konfigurasi",
])

# ══════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ══════════════════════════════════════════════════════════════════
with tab1:
    latest = api_latest(server_base, api_key, device_id)
    df_2h  = api_history(server_base, api_key, device_id, hours=2, limit=120)

    if latest is None:
        st.info("⏳ Belum ada data. Kirim data via form sidebar atau jalankan `simulasi_php.py`.")
        st.stop()

    # ── Metric cards ─────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    suhu_v  = float(latest.get("suhu", 0))
    moist_v = float(latest.get("moisture", 0))
    gas_v   = float(latest.get("gas", 0))
    ikk_v   = float(latest.get("ikk", 0))

    mc = lambda v, lo, hi: "#22C55E" if lo <= v <= hi else "#EF4444"

    with c1:
        st.markdown(f"""
        <div class="metric-card" style="border-color:#FF8C42">
          <div class="metric-label">🌡️ Suhu DS18B20</div>
          <div class="metric-value" style="color:#FF8C42">{suhu_v:.1f}°C</div>
          <div class="metric-sub">Normal 20–70°C</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        mc_color = mc(moist_v, 38, 72)
        st.markdown(f"""
        <div class="metric-card" style="border-color:#38BDF8">
          <div class="metric-label">💧 Kelembapan</div>
          <div class="metric-value" style="color:#38BDF8">{moist_v:.1f}%</div>
          <div class="metric-sub" style="color:{mc_color}">
            {'✅ Optimal 38–72%' if 38<=moist_v<=72 else '⚠️ Di luar rentang'}
          </div>
        </div>""", unsafe_allow_html=True)

    with c3:
        g_color = "#EF4444" if gas_v > 400 else "#F59E0B" if gas_v > 200 else "#22C55E"
        st.markdown(f"""
        <div class="metric-card" style="border-color:#86EFAC">
          <div class="metric-label">🌫️ Gas MQ-135</div>
          <div class="metric-value" style="color:#86EFAC">{gas_v:.0f} ppm</div>
          <div class="metric-sub" style="color:{g_color}">
            {'🔴 Kritis' if gas_v>400 else '🟡 Aktif' if gas_v>200 else '🟢 Normal'}
          </div>
        </div>""", unsafe_allow_html=True)

    with c4:
        ikk_c = ikk_color(ikk_v)
        st.markdown(f"""
        <div class="metric-card" style="border-color:{ikk_c}">
          <div class="metric-label">💚 IKK</div>
          <div class="metric-value" style="color:{ikk_c}">{ikk_v:.1f}</div>
          <div class="metric-sub">{ikk_label(ikk_v)}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── Fase + Gauge + Alerts ─────────────────────────────────────
    col_f, col_g, col_a = st.columns([2, 2, 2])

    with col_f:
        st.markdown('<div class="sec-title">🔍 Fase Terdeteksi</div>',
                    unsafe_allow_html=True)
        fid   = int(latest.get("fase_pred", 0))
        finfo = FASE_DEF.get(fid, FASE_DEF[0])
        st.markdown(f"""
        <div style="background:{finfo['warna']}22;border:2px solid {finfo['warna']};
                    border-radius:12px;padding:16px;text-align:center;margin:8px 0;">
          <div style="font-size:2.5rem;">{finfo['emoji']}</div>
          <div style="font-size:1.2rem;font-weight:700;color:{finfo['warna']};margin-top:4px;">
            {finfo['nama']}
          </div>
          <div style="font-size:0.78rem;color:#94A3B8;margin-top:3px;">
            Fase {fid} dari 6 · {latest.get('timestamp','')[:19]}
          </div>
        </div>""", unsafe_allow_html=True)

    with col_g:
        st.markdown('<div class="sec-title">📊 IKK Gauge</div>',
                    unsafe_allow_html=True)
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=ikk_v,
            number={"font": {"color": ikk_color(ikk_v), "size": 34}},
            gauge={
                "axis": {"range": [0, 100], "tickfont": {"color": "#94A3B8"}},
                "bar":  {"color": ikk_color(ikk_v), "thickness": 0.25},
                "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
                "steps": [
                    {"range": [0,  40], "color": "rgba(127,29,29,0.2)"},
                    {"range": [40, 60], "color": "rgba(120,53,15,0.2)"},
                    {"range": [60, 80], "color": "rgba(20,83,45,0.2)"},
                    {"range": [80,100], "color": "rgba(21,128,61,0.2)"},
                ],
            },
        ))
        PLOTLY_LAYOUT = {
            "template": "plotly_white",
            "font": dict(size=12)
        }

        fig_g.update_layout(
            **PLOTLY_LAYOUT,
            height=200,
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig_g, use_container_width=True,
                        config={"displayModeBar": False})

    with col_a:
        st.markdown('<div class="sec-title">⚠️ Rekomendasi</div>',
                    unsafe_allow_html=True)
        alerts = []
        if moist_v < 38:  alerts.append(("critical","💧 Kelembapan sangat rendah — Segera siram!"))
        elif moist_v < 45: alerts.append(("warning","💧 Kelembapan rendah — Monitor lebih sering"))
        elif moist_v > 72: alerts.append(("warning","💧 Kelembapan tinggi — Kurangi penyiraman"))
        if gas_v > 500:   alerts.append(("critical","🌫️ Gas >500ppm — Aerasi darurat!"))
        elif gas_v > 350: alerts.append(("warning","🌫️ Gas tinggi — Lakukan pembalikan"))
        if suhu_v > 70:   alerts.append(("critical","🌡️ Suhu kritis >70°C — Overheating!"))
        if ikk_v < 40:    alerts.append(("critical","⚠️ IKK kritis — Intervensi segera!"))
        if not alerts:    alerts.append(("ok","✅ Semua parameter dalam kondisi normal"))
        for lvl, msg in alerts:
            st.markdown(f'<div class="alert-{lvl}">{msg}</div>',
                        unsafe_allow_html=True)

    # ── Mini trend charts ─────────────────────────────────────────
    st.markdown('<div class="sec-title">📉 Tren 2 Jam Terakhir</div>',
                unsafe_allow_html=True)
    if not df_2h.empty:
        fig_mini = make_subplots(rows=1, cols=3,
                                  subplot_titles=["Suhu (°C)","Kelembapan (%)","Gas (ppm)"])
        for ci, (col, color) in enumerate(
            [("suhu","#FF8C42"),("moisture","#38BDF8"),("gas","#86EFAC")], 1
        ):
            if col in df_2h.columns:
                fig_mini.add_trace(go.Scatter(
                    x=df_2h["timestamp"], y=df_2h[col],
                    mode="lines", line=dict(color=color, width=2),
                    fill="tozeroy", fillcolor=hex_to_rgba(color, 0.13),
                    showlegend=False,
                ), row=1, col=ci)
        fig_mini.update_layout(**PLOTLY_LAYOUT, height=200)
        fig_mini.update_xaxes(gridcolor="#1E3048", tickfont=dict(size=8))
        fig_mini.update_yaxes(gridcolor="#1E3048", tickfont=dict(size=8))
        st.plotly_chart(fig_mini, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.info("Data 2 jam terakhir belum tersedia.")


# ══════════════════════════════════════════════════════════════════
# TAB 2 — TREN SENSOR
# ══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 📈 Tren Sensor")
    c_t1, c_t2 = st.columns(2)
    with c_t1:
        hours_sel = st.selectbox("Rentang Waktu",
            [1,6,12,24,48,72,168],
            format_func=lambda x: f"{x} jam" if x<24 else f"{x//24} hari",
            index=3)
    with c_t2:
        show_phase = st.toggle("Highlight Fase", value=True)

    df_tr = api_history(server_base, api_key, device_id,
                        hours=hours_sel, limit=2000)

    if df_tr.empty:
        st.info("Belum ada data riwayat.")
    else:
        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True,
            row_heights=[0.3,0.25,0.25,0.2],
            vertical_spacing=0.04,
            subplot_titles=["🌡️ Suhu (°C)","💧 Kelembapan (%)","🌫️ Gas (ppm)","💚 IKK"],
        )
        if show_phase:
            phase_shading(fig, df_tr, rows=[1,2,3,4])

        sensors = [("suhu","#FF8C42",1),("moisture","#38BDF8",2),("gas","#86EFAC",3)]
        for col, color, ri in sensors:
            if col in df_tr.columns:
                fig.add_trace(go.Scatter(
                    x=df_tr["timestamp"], y=df_tr[col],
                    mode="lines", line=dict(color=color,width=1.8),
                    fill="tozeroy", fillcolor=hex_to_rgba(color, 0.09),
                    name=SENSOR_OPTS[col]["label"],
                ), row=ri, col=1)

        if "ikk" in df_tr.columns:
            fig.add_trace(go.Scatter(
                x=df_tr["timestamp"], y=df_tr["ikk"],
                mode="lines", line=dict(color="#FCD34D",width=2),
                fill="tozeroy", fillcolor="rgba(252,211,77,0.09)",
                name="IKK",
            ), row=4, col=1)
            for thr, tc in [(80,"#22C55E"),(60,"#F59E0B"),(40,"#EF4444")]:
                fig.add_hline(y=thr, line_dash="dash",
                              line_color=tc, line_width=0.8, row=4, col=1)

        fig.update_layout(**PLOTLY_LAYOUT, height=600,
                          legend=dict(orientation="h", y=-0.04,
                                      bgcolor="rgba(0,0,0,0)"))
        fig.update_xaxes(gridcolor="#1E3048")
        fig.update_yaxes(gridcolor="#1E3048")
        st.plotly_chart(fig, use_container_width=True)

        # Violin per fase
        if "fase_pred" in df_tr.columns and len(df_tr) >= 10:
            st.markdown("#### Distribusi per Fase")
            df_tr["fase_nama"] = df_tr["fase_pred"].map(
                lambda x: f"{FASE_DEF.get(int(x),FASE_DEF[0])['emoji']} "
                          f"{FASE_DEF.get(int(x),FASE_DEF[0])['nama']}"
            )
            v1, v2, v3 = st.columns(3)
            for col_w, (sensor, color) in zip([v1,v2,v3],
                [("suhu","#FF8C42"),("moisture","#38BDF8"),("gas","#86EFAC")]):
                with col_w:
                    fig_v = px.violin(
                        df_tr, y=sensor, x="fase_nama",
                        color="fase_nama",
                        color_discrete_sequence=[FASE_DEF[i]["warna"] for i in range(6)],
                        box=True, points="outliers",
                        title=SENSOR_OPTS[sensor]["label"],
                    )
                    fig_v.update_layout(**PLOTLY_LAYOUT, height=280,
                                        showlegend=False, margin=dict(l=0,r=0,t=30,b=60))
                    fig_v.update_xaxes(tickangle=-30, tickfont=dict(size=7))
                    st.plotly_chart(fig_v, use_container_width=True,
                                    config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════
# TAB 3 — ANALISIS SPRT
# ══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 🔬 Analisis SPRT-CUSUM")
    df_sp = api_history(server_base, api_key, device_id, hours=72, limit=2000)

    if df_sp.empty or not all(c in df_sp.columns for c in
                               ["sprt_cusum_t","sprt_cusum_m","sprt_cusum_g"]):
        st.info("Data SPRT belum tersedia. Kirim minimal 5 data terlebih dahulu.")
    else:
        with st.expander("📐 Parameter SPRT", expanded=False):
            p1,p2,p3,p4 = st.columns(4)
            p1.metric("α (False Positive)","0.05")
            p2.metric("β (False Negative)","0.10")
            p3.metric("Batas A (H₁)","+2.944")
            p4.metric("Batas B (H₀)","-1.946")
            st.info("Λₙ ≥ A → Transisi fase terdeteksi (H₁) · "
                    "Λₙ ≤ B → Fase stabil (H₀) · "
                    "CUSUM di-reset setelah setiap deteksi")

        fig_s = make_subplots(rows=3, cols=1, shared_xaxes=True,
                               subplot_titles=[
                                   "SPRT Suhu — Λₙ (Deteksi Termofilik)",
                                   "SPRT Moisture — Λₙ (Deteksi Evaporasi)",
                                   "SPRT Gas — Λₙ (Deteksi Puncak)",
                               ], vertical_spacing=0.08)

        for ri, (col, color) in enumerate(
            [("sprt_cusum_t","#FF8C42"),
             ("sprt_cusum_m","#38BDF8"),
             ("sprt_cusum_g","#86EFAC")], 1
        ):
            cs = df_sp[col]
            fig_s.add_trace(go.Scatter(
                x=df_sp["timestamp"], y=cs.clip(lower=0),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.09)",
                line=dict(width=0), showlegend=False,
            ), row=ri, col=1)
            fig_s.add_trace(go.Scatter(
                x=df_sp["timestamp"], y=cs.clip(upper=0),
                fill="tozeroy", fillcolor="rgba(239,68,68,0.09)",
                line=dict(width=0), showlegend=False,
            ), row=ri, col=1)
            fig_s.add_trace(go.Scatter(
                x=df_sp["timestamp"], y=cs,
                mode="lines", line=dict(color=color, width=1.8),
                name=f"Λₙ {col.split('_')[-1].upper()}",
            ), row=ri, col=1)
            fig_s.add_hline(y=2.944, line_dash="dash",
                            line_color="#22C55E", line_width=1.2, row=ri, col=1)
            fig_s.add_hline(y=-1.946, line_dash="dash",
                            line_color="#EF4444", line_width=1.2, row=ri, col=1)

        fig_s.update_layout(**PLOTLY_LAYOUT, height=520,
                            legend=dict(orientation="h", y=-0.04,
                                        bgcolor="rgba(0,0,0,0)"))
        fig_s.update_xaxes(gridcolor="#1E3048")
        fig_s.update_yaxes(gridcolor="#1E3048", zeroline=True, zerolinecolor="#1E3048")
        st.plotly_chart(fig_s, use_container_width=True)

        # Phase timeline
        if "fase_pred" in df_sp.columns:
            st.markdown("#### 🗓️ Timeline Fase")
            fig_ph = go.Figure()
            for fid, finfo in FASE_DEF.items():
                mask = df_sp["fase_pred"] == fid
                if mask.any():
                    fig_ph.add_trace(go.Scatter(
                        x=df_sp.loc[mask,"timestamp"],
                        y=df_sp.loc[mask,"fase_pred"],
                        mode="markers", name=f"{finfo['emoji']} {finfo['nama']}",
                        marker=dict(color=finfo["warna"], size=5, opacity=0.8),
                    ))
            fig_ph.update_layout(**PLOTLY_LAYOUT, height=220,
                                  yaxis=dict(
                                      tickvals=list(range(6)),
                                      ticktext=[f"{FASE_DEF[i]['emoji']} {FASE_DEF[i]['nama']}"
                                                for i in range(6)],
                                      gridcolor="#1E3048"),
                                  xaxis=dict(gridcolor="#1E3048"),
                                  legend=dict(orientation="h", y=-0.3,
                                              bgcolor="rgba(0,0,0,0)",
                                              font=dict(size=9)))
            st.plotly_chart(fig_ph, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
# TAB 4 — KLASIFIKASI & REGRESI DECISION TREE
# ══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 🤖 Machine Learning — Decision Tree")
    st.caption("Model dilatih dari data historis yang diambil dari PHP API")

    # ── Hyperparameter controls ───────────────────────────────────
    with st.expander("⚙️ Konfigurasi Model", expanded=True):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            dt_hours = st.slider("Data training (jam terakhir)", 12, 720, 168, 12)
            dt_limit = st.slider("Maks. baris data", 100, 5000, 1000, 100)
        with mc2:
            dt_depth = st.slider("Max Depth", 2, 20, 5)
            dt_min_s = st.slider("Min Samples Leaf", 1, 30, 3)
        with mc3:
            dt_all_feat = st.toggle("Gunakan semua fitur (+ derived)", value=True)
            dt_model    = st.radio("Mode", ["Klasifikasi Fase", "Regresi IKK",
                                            "Keduanya"], index=2)

    # ── Load data ────────────────────────────────────────────────
    df_ml = api_history(server_base, api_key, device_id,
                        hours=dt_hours, limit=dt_limit)

    if df_ml.empty or len(df_ml) < 20:
        st.warning(f"⚠️ Data tidak cukup ({len(df_ml)} baris). "
                   f"Perlu minimal 20 baris. Jalankan `simulasi_php.py` terlebih dahulu.")
        st.stop()

    df_ml_json = df_ml.to_json()
    n_data = len(df_ml)
    st.caption(f"📊 Dataset: **{n_data} baris** dari {dt_hours} jam terakhir")

    # ═══════════════════════════════════════════════════════════════
    # KLASIFIKASI FASE
    # ═══════════════════════════════════════════════════════════════
    if dt_model in ("Klasifikasi Fase", "Keduanya"):
        st.markdown("---")
        st.markdown("#### 🌿 Decision Tree Classifier — Prediksi Fase Kompos")

        with st.spinner("Melatih Decision Tree Classifier..."):
            clf, X_test_c, y_test_c, meta_c = train_classifier(
                df_ml_json, dt_depth, dt_min_s, dt_all_feat
            )

        if clf is None:
            st.error("Gagal melatih classifier. Periksa data (perlu minimal 2 kelas fase).")
        else:
            # ── Metric summary ────────────────────────────────────
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#22C55E">
                      {meta_c['accuracy']:.1f}%
                    </div>
                    <div class="ml-metric-lbl">Accuracy (Test Set)</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with m2:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#38BDF8">
                      {meta_c['macro_f1']:.1f}%
                    </div>
                    <div class="ml-metric-lbl">Macro F1 (5-fold CV)</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with m3:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#FCD34D">
                      {meta_c['cv_std']:.1f}%
                    </div>
                    <div class="ml-metric-lbl">CV Std Dev</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with m4:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#86EFAC">
                      {len(meta_c['features'])}
                    </div>
                    <div class="ml-metric-lbl">Fitur Digunakan</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            col_cm, col_imp = st.columns(2)

            # ── Confusion matrix ──────────────────────────────────
            with col_cm:
                st.markdown("**Confusion Matrix**")
                cm_arr = np.array(meta_c["cm"])
                classes = meta_c["classes"]
                labels  = [f"{FASE_DEF.get(c, {'emoji':'?'})['emoji']} "
                           f"{FASE_DEF.get(c, {'nama':'?'})['nama'].split()[0]}"
                           for c in classes]

                fig_cm = go.Figure(go.Heatmap(
                    z=cm_arr,
                    x=labels, y=labels,
                    colorscale=[[0,"#0B1120"],[0.5,"#1A5276"],[1,"#E76F51"]],
                    text=cm_arr.astype(str), texttemplate="%{text}",
                    textfont=dict(size=12, color="white"),
                    showscale=True,
                ))
                fig_cm.update_layout(
                    **PLOTLY_LAYOUT, height=320,
                    xaxis=dict(title="Prediksi", tickfont=dict(size=9)),
                    yaxis=dict(title="Aktual", tickfont=dict(size=9),
                               autorange="reversed"),
                )
                st.plotly_chart(fig_cm, use_container_width=True,
                                config={"displayModeBar": False})

            # ── Feature importance ────────────────────────────────
            with col_imp:
                st.markdown("**Feature Importance**")
                imp_df = pd.DataFrame(meta_c["importances"],
                                      columns=["Feature","Importance"])
                imp_df = imp_df.sort_values("Importance", ascending=True).tail(12)
                fig_imp = go.Figure(go.Bar(
                    x=imp_df["Importance"],
                    y=imp_df["Feature"],
                    orientation="h",
                    marker_color="#38BDF8",
                    text=[f"{v:.3f}" for v in imp_df["Importance"]],
                    textposition="outside",
                    textfont=dict(color="#D8E4F0", size=9),
                ))
                fig_imp.update_layout(
                    **PLOTLY_LAYOUT, height=320,
                    xaxis=dict(title="Importance", gridcolor="#1E3048"),
                    yaxis=dict(tickfont=dict(size=9)),
                    margin=dict(l=0,r=40,t=10,b=0),
                )
                st.plotly_chart(fig_imp, use_container_width=True,
                                config={"displayModeBar": False})

            # ── Per-class metrics ────────────────────────────────
            st.markdown("**Metrik per Fase**")
            report = meta_c["report"]
            rows_r = []
            for c in classes:
                key   = str(c)
                finfo = FASE_DEF.get(c, {"emoji":"?","nama":"Unknown","warna":"#999"})
                r     = report.get(key, {})
                rows_r.append({
                    "Fase": f"{finfo['emoji']} {finfo['nama']}",
                    "Precision (%)": round(r.get("precision", 0) * 100, 1),
                    "Recall (%)":    round(r.get("recall", 0) * 100, 1),
                    "F1-Score (%)":  round(r.get("f1-score", 0) * 100, 1),
                    "Support":       int(r.get("support", 0)),
                })
            df_rep = pd.DataFrame(rows_r)

            fig_rep = go.Figure()
            for metric, color in [("Precision (%)","#38BDF8"),
                                   ("Recall (%)",   "#86EFAC"),
                                   ("F1-Score (%)","#FCD34D")]:
                fig_rep.add_trace(go.Bar(
                    name=metric,
                    x=df_rep["Fase"],
                    y=df_rep[metric],
                    marker_color=color, opacity=0.85,
                    text=[f"{v:.0f}" for v in df_rep[metric]],
                    textposition="outside",
                    textfont=dict(size=9, color="#D8E4F0"),
                ))
            fig_rep.add_hline(y=80, line_dash="dash",
                              line_color="#22C55E", line_width=1,
                              annotation_text="Target 80%")
            fig_rep.update_layout(
                **PLOTLY_LAYOUT, barmode="group", height=320,
                yaxis=dict(range=[0,115], gridcolor="#1E3048"),
                xaxis=dict(tickfont=dict(size=8), gridcolor="#1E3048"),
                legend=dict(orientation="h", y=-0.2, bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_rep, use_container_width=True)

            # ── Decision Tree text rules ─────────────────────────
            with st.expander("📋 Aturan Decision Tree (Text)"):
                tree_text = export_text(
                    clf, feature_names=meta_c["features"],
                    max_depth=min(dt_depth, 4),
                )
                st.code(tree_text, language="text")

            # ── Live prediction ───────────────────────────────────
            st.markdown("**🎯 Prediksi Langsung**")
            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1: p_suhu  = st.number_input("Suhu (°C)",    5.0,  80.0, suhu_v,  0.1, key="p_s_c")
            with pc2: p_moist = st.number_input("Moisture (%)", 0.0, 100.0, moist_v, 0.5, key="p_m_c")
            with pc3: p_gas   = st.number_input("Gas (ppm)",    0.0, 700.0, gas_v,   1.0, key="p_g_c")
            with pc4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔮 Prediksi Fase", use_container_width=True):
                    pred_fase = int(predict_single(
                        clf, meta_c["features"], p_suhu, p_moist, p_gas))
                    finfo = FASE_DEF.get(pred_fase, FASE_DEF[0])
                    st.success(
                        f"{finfo['emoji']} **{finfo['nama']}** (Fase {pred_fase})"
                    )

    # ═══════════════════════════════════════════════════════════════
    # REGRESI IKK
    # ═══════════════════════════════════════════════════════════════
    if dt_model in ("Regresi IKK", "Keduanya"):
        st.markdown("---")
        st.markdown("#### 📉 Decision Tree Regressor — Prediksi Nilai IKK")

        with st.spinner("Melatih Decision Tree Regressor..."):
            reg, X_test_r, y_test_r, meta_r = train_regressor(
                df_ml_json, dt_depth, dt_min_s, dt_all_feat
            )

        if reg is None:
            st.error("Gagal melatih regressor. Periksa kolom IKK di data.")
        else:
            # ── Metrics ───────────────────────────────────────────
            rm1, rm2, rm3, rm4 = st.columns(4)
            with rm1:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#22C55E">
                      {meta_r['r2']:.4f}
                    </div>
                    <div class="ml-metric-lbl">R² Score</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with rm2:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#38BDF8">
                      {meta_r['mae']:.2f}
                    </div>
                    <div class="ml-metric-lbl">MAE (IKK poin)</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with rm3:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#FCD34D">
                      {meta_r['rmse']:.2f}
                    </div>
                    <div class="ml-metric-lbl">RMSE</div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with rm4:
                st.markdown(f"""
                <div class="ml-card">
                  <div class="ml-metric">
                    <div class="ml-metric-val" style="color:#86EFAC">
                      {meta_r['cv_rmse']:.2f}
                    </div>
                    <div class="ml-metric-lbl">CV RMSE (5-fold)</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            col_sc, col_ri = st.columns(2)

            # ── Scatter: actual vs predicted ──────────────────────
            with col_sc:
                st.markdown("**Aktual vs Prediksi IKK**")
                y_t = meta_r["y_test"]
                y_p = meta_r["y_pred"]
                fig_sc = go.Figure()
                fig_sc.add_trace(go.Scatter(
                    x=y_t, y=y_p, mode="markers",
                    marker=dict(color="#38BDF8", size=5, opacity=0.7),
                    name="Prediksi",
                ))
                mn_v = min(min(y_t), min(y_p)) - 2
                mx_v = max(max(y_t), max(y_p)) + 2
                fig_sc.add_trace(go.Scatter(
                    x=[mn_v, mx_v], y=[mn_v, mx_v],
                    mode="lines", line=dict(color="#22C55E", dash="dash", width=1.5),
                    name="Ideal (y=x)",
                ))
                fig_sc.update_layout(
                    **PLOTLY_LAYOUT, height=320,
                    xaxis=dict(title="Aktual IKK", gridcolor="#1E3048"),
                    yaxis=dict(title="Prediksi IKK", gridcolor="#1E3048"),
                )
                st.plotly_chart(fig_sc, use_container_width=True,
                                config={"displayModeBar": False})

            # ── Feature importance regressor ──────────────────────
            with col_ri:
                st.markdown("**Feature Importance (Regressor)**")
                rimp_df = pd.DataFrame(meta_r["importances"],
                                        columns=["Feature","Importance"])
                rimp_df = rimp_df.sort_values("Importance", ascending=True).tail(12)
                fig_ri = go.Figure(go.Bar(
                    x=rimp_df["Importance"],
                    y=rimp_df["Feature"],
                    orientation="h",
                    marker_color="#FCD34D",
                    text=[f"{v:.3f}" for v in rimp_df["Importance"]],
                    textposition="outside",
                    textfont=dict(color="#D8E4F0", size=9),
                ))
                fig_ri.update_layout(
                    **PLOTLY_LAYOUT, height=320,
                    xaxis=dict(title="Importance", gridcolor="#1E3048"),
                    yaxis=dict(tickfont=dict(size=9)),
                    margin=dict(l=0,r=40,t=10,b=0),
                )
                st.plotly_chart(fig_ri, use_container_width=True,
                                config={"displayModeBar": False})

            # ── Residual plot ─────────────────────────────────────
            st.markdown("**Residual (Error = Aktual − Prediksi)**")
            residuals = [a - p for a, p in zip(y_t, y_p)]
            fig_res = go.Figure()
            fig_res.add_trace(go.Scatter(
                x=y_p, y=residuals, mode="markers",
                marker=dict(color="#FF8C42", size=4, opacity=0.6),
                name="Residual",
            ))
            fig_res.add_hline(y=0, line_color="#22C55E",
                              line_dash="dash", line_width=1.5)
            fig_res.update_layout(
                **PLOTLY_LAYOUT, height=240,
                xaxis=dict(title="Prediksi IKK", gridcolor="#1E3048"),
                yaxis=dict(title="Residual", gridcolor="#1E3048",
                           zeroline=True, zerolinecolor="#1E3048"),
            )
            st.plotly_chart(fig_res, use_container_width=True)

            # ── Live IKK prediction ───────────────────────────────
            st.markdown("**🎯 Prediksi IKK Langsung**")
            rp1, rp2, rp3, rp4 = st.columns(4)
            with rp1: rp_s = st.number_input("Suhu (°C)",    5.0,  80.0, suhu_v,  0.1, key="rp_s")
            with rp2: rp_m = st.number_input("Moisture (%)", 0.0, 100.0, moist_v, 0.5, key="rp_m")
            with rp3: rp_g = st.number_input("Gas (ppm)",    0.0, 700.0, gas_v,   1.0, key="rp_g")
            with rp4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔮 Prediksi IKK", use_container_width=True):
                    pred_ikk = float(predict_single(
                        reg, meta_r["features"], rp_s, rp_m, rp_g))
                    pred_ikk = max(0.0, min(100.0, pred_ikk))
                    st.success(
                        f"IKK Prediksi: **{pred_ikk:.1f} / 100** — "
                        f"{ikk_label(pred_ikk)}"
                    )

            # ── Decision Tree rules ───────────────────────────────
            with st.expander("📋 Aturan Regresi Decision Tree"):
                reg_text = export_text(
                    reg, feature_names=meta_r["features"],
                    max_depth=min(dt_depth, 4),
                )
                st.code(reg_text, language="text")


# ══════════════════════════════════════════════════════════════════
# TAB 5 — AGREGASI
# ══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 📉 Agregasi Data")
    a1, a2 = st.columns(2)
    with a1:
        agg_level = st.selectbox("Level Agregasi",
            ["hourly","daily","fase"],
            format_func={"hourly":"Per Jam","daily":"Per Hari","fase":"Per Fase"}.__getitem__)
    with a2:
        agg_days = st.slider("Rentang (hari)", 1, 90, 7)

    df_agg = api_aggregate(server_base, api_key, device_id, agg_level, agg_days)

    if df_agg.empty:
        st.info("Data agregasi belum tersedia.")
    else:
        if agg_level == "hourly" and "hour_bucket" in df_agg.columns:
            df_agg["hour_bucket"] = pd.to_datetime(df_agg["hour_bucket"])
            fig_agg = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                     subplot_titles=["Suhu μ±σ (°C)",
                                                     "Kelembapan μ±σ (%)",
                                                     "Gas μ±σ (ppm)"],
                                     vertical_spacing=0.08)
            for ri, (p, color) in enumerate(
                [("suhu","#FF8C42"),("moisture","#38BDF8"),("gas","#86EFAC")], 1
            ):
                x   = df_agg["hour_bucket"]
                mu  = pd.to_numeric(df_agg.get(f"{p}_mean", pd.Series()), errors="coerce")
                std = pd.to_numeric(df_agg.get(f"{p}_std",  pd.Series()), errors="coerce").fillna(0)
                mn  = pd.to_numeric(df_agg.get(f"{p}_min",  pd.Series()), errors="coerce")
                mx  = pd.to_numeric(df_agg.get(f"{p}_max",  pd.Series()), errors="coerce")
                # μ±σ band
                fig_agg.add_trace(go.Scatter(
                    x=pd.concat([x, x[::-1]]),
                    y=pd.concat([mu+std, (mu-std)[::-1]]),
                    fill="toself", fillcolor=hex_to_rgba(color, 0.15),
                    line=dict(width=0), name="μ±σ", showlegend=(ri==1),
                ), row=ri, col=1)
                # min-max band
                fig_agg.add_trace(go.Scatter(
                    x=pd.concat([x, x[::-1]]),
                    y=pd.concat([mx, mn[::-1]]),
                    fill="toself", fillcolor=hex_to_rgba(color, 0.06),
                    line=dict(width=0), name="min-max", showlegend=(ri==1),
                ), row=ri, col=1)
                fig_agg.add_trace(go.Scatter(
                    x=x, y=mu, mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=3),
                    name=f"{p} μ", showlegend=(ri==1),
                ), row=ri, col=1)

            fig_agg.update_layout(**PLOTLY_LAYOUT, height=540,
                                   legend=dict(orientation="h", y=-0.05,
                                               bgcolor="rgba(0,0,0,0)"))
            fig_agg.update_xaxes(gridcolor="#1E3048")
            fig_agg.update_yaxes(gridcolor="#1E3048")
            st.plotly_chart(fig_agg, use_container_width=True)

        elif agg_level == "daily" and "day" in df_agg.columns:
            df_agg["day"] = pd.to_datetime(df_agg["day"])
            fig_d = go.Figure()
            for col, color in [("suhu_mean","#FF8C42"),
                                ("moisture_mean","#38BDF8"),
                                ("gas_mean","#86EFAC")]:
                if col in df_agg.columns:
                    fig_d.add_trace(go.Bar(
                        x=df_agg["day"],
                        y=pd.to_numeric(df_agg[col], errors="coerce"),
                        name=col.replace("_mean","").capitalize(),
                        marker_color=color, opacity=0.85,
                    ))
            fig_d.update_layout(**PLOTLY_LAYOUT, barmode="group", height=380,
                                xaxis=dict(gridcolor="#1E3048"),
                                yaxis=dict(gridcolor="#1E3048"))
            st.plotly_chart(fig_d, use_container_width=True)

        elif agg_level == "fase" and "fase_pred" in df_agg.columns:
            df_agg["fase_pred"] = pd.to_numeric(df_agg["fase_pred"], errors="coerce").astype(int)
            df_agg["fase_label"] = df_agg["fase_pred"].map(
                lambda x: f"{FASE_DEF.get(x,FASE_DEF[0])['emoji']} "
                          f"{FASE_DEF.get(x,FASE_DEF[0])['nama']}"
            )
            fcolors = [FASE_DEF.get(int(x), FASE_DEF[0])["warna"]
                       for x in df_agg["fase_pred"]]

            fig_fa = make_subplots(rows=1, cols=3,
                                    subplot_titles=["Suhu (°C)","Kelembapan (%)","Gas (ppm)"])
            for ci, (col, mx_col) in enumerate(
                [("suhu_mean","suhu_max"),("moisture_mean","moisture_max"),
                 ("gas_mean","gas_max")], 1
            ):
                mu_v = pd.to_numeric(df_agg.get(col, pd.Series()), errors="coerce")
                mx_v = pd.to_numeric(df_agg.get(mx_col, pd.Series()), errors="coerce")
                fig_fa.add_trace(go.Bar(
                    x=df_agg["fase_label"], y=mu_v,
                    marker_color=fcolors,
                    error_y=dict(type="data", array=(mx_v - mu_v).tolist(),
                                 visible=True, color="#94A3B8"),
                    showlegend=False,
                ), row=1, col=ci)
            fig_fa.update_layout(**PLOTLY_LAYOUT, height=360,
                                  margin=dict(l=0,r=0,t=30,b=60))
            fig_fa.update_xaxes(tickangle=-25, tickfont=dict(size=8),
                                 gridcolor="#1E3048")
            fig_fa.update_yaxes(gridcolor="#1E3048")
            st.plotly_chart(fig_fa, use_container_width=True)

            # IKK per fase bar
            if "ikk_mean" in df_agg.columns:
                ikk_vals = pd.to_numeric(df_agg["ikk_mean"], errors="coerce")
                fig_ikk = go.Figure(go.Bar(
                    x=df_agg["fase_label"], y=ikk_vals,
                    marker_color=[ikk_color(v) for v in ikk_vals],
                    text=[f"{v:.1f}" for v in ikk_vals],
                    textposition="outside",
                ))
                fig_ikk.add_hline(y=80, line_dash="dash", line_color="#22C55E",
                                   annotation_text="Optimal")
                fig_ikk.add_hline(y=60, line_dash="dash", line_color="#F59E0B",
                                   annotation_text="Baik")
                fig_ikk.update_layout(**PLOTLY_LAYOUT, height=300,
                                       yaxis=dict(range=[0,110], gridcolor="#1E3048",
                                                  title="IKK"),
                                       xaxis=dict(gridcolor="#1E3048",
                                                  tickfont=dict(size=9)))
                st.plotly_chart(fig_ikk, use_container_width=True,
                                config={"displayModeBar": False})

        # Table + download
        st.markdown("#### 📋 Tabel Agregasi")
        num_cols = df_agg.select_dtypes("number").columns
        df_display = df_agg.copy()
        for c in num_cols:
            df_display[c] = pd.to_numeric(df_display[c], errors="coerce")
        st.dataframe(
            df_display.style.format({c: "{:.2f}" for c in num_cols}),
            use_container_width=True
        )
        csv = df_agg.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            csv,
            f"agregasi_{agg_level}_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv",
        )


# ══════════════════════════════════════════════════════════════════
# TAB 6 — KONFIGURASI + DB CHECK + UI SIMULATION
# ══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### ⚙️ Konfigurasi, Database Health & Simulasi UI")

    sub1, sub2, sub3 = st.tabs(["🗄️ Database & Server", "🎮 Simulasi UI", "📋 Referensi API"])

    # ── SUB-TAB 1: DB Health + Server Status ──────────────────────
    with sub1:
        st.markdown("#### 🗄️ Database Health Check")
        st.caption("Cek apakah database PHP sudah terbentuk, bisa dibaca, dan bisa ditulis.")

        col_db1, col_db2 = st.columns([1, 2])
        with col_db1:
            run_check = st.button("🔍 Jalankan Health Check", use_container_width=True,
                                  type="primary")
        with col_db2:
            st.info("Health check akan mengirim **1 data dummy** ke `/api/data.php` "
                    "untuk memverifikasi database writable.")

        if run_check:
            with st.spinner("Mengecek server dan database..."):
                health = check_db_health(server_base, api_key)

            # Result cards
            r1, r2, r3 = st.columns(3)
            with r1:
                icon = "🟢" if health["server_online"] else "🔴"
                color = "#22C55E" if health["server_online"] else "#EF4444"
                st.markdown(f"""
                <div class="metric-card" style="border-color:{color}">
                  <div class="metric-value" style="color:{color};font-size:1.8rem">
                    {icon} {"Online" if health["server_online"] else "Offline"}
                  </div>
                  <div class="metric-label">Server PHP API</div>
                  <div class="metric-sub">{server_base}</div>
                </div>""", unsafe_allow_html=True)

            with r2:
                icon2 = "🟢" if health["db_exists"] else "🔴"
                color2 = "#22C55E" if health["db_exists"] else "#EF4444"
                st.markdown(f"""
                <div class="metric-card" style="border-color:{color2}">
                  <div class="metric-value" style="color:{color2};font-size:1.8rem">
                    {icon2} {"Exists" if health["db_exists"] else "Not Found"}
                  </div>
                  <div class="metric-label">Database SQLite</div>
                  <div class="metric-sub">kompos.sqlite</div>
                </div>""", unsafe_allow_html=True)

            with r3:
                icon3 = "🟢" if health["db_writable"] else "🔴"
                color3 = "#22C55E" if health["db_writable"] else "#EF4444"
                st.markdown(f"""
                <div class="metric-card" style="border-color:{color3}">
                  <div class="metric-value" style="color:{color3};font-size:1.8rem">
                    {icon3} {"Writable" if health["db_writable"] else "Not Writable"}
                  </div>
                  <div class="metric-label">DB Write Test</div>
                  <div class="metric-sub">
                    {"ID: " + str(health.get("test_id","?")) if health["db_writable"]
                     else "Gagal menulis data"}
                  </div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            # Detail panel
            if health["error"]:
                st.error(f"❌ **Error:** {health['error']}")
                with st.expander("💡 Solusi"):
                    st.markdown("""
**Server offline / Connection refused:**
```bash
# Jalankan PHP server (XAMPP/Laragon) atau:
php -S localhost:8080 -t /path/to/kompos/
```

**DB tidak exists / not writable:**
```bash
# Pastikan folder data/ writable
mkdir -p /var/www/html/kompos/data/
chmod 775 /var/www/html/kompos/data/
chown www-data:www-data /var/www/html/kompos/data/
```

**Auth gagal (401):**
```python
# Samakan API_KEY di config.php dan di sidebar dashboard
define('API_KEY', 'kompos2024iot');
```
""")
            else:
                col_det1, col_det2 = st.columns(2)
                with col_det1:
                    st.success(f"✅ Total rekaman: **{health['total_records']}** baris")
                with col_det2:
                    if health.get("last_record"):
                        lr = health["last_record"]
                        st.info(f"📌 Data terakhir: **{lr.get('device_id','?')}** "
                                f"@ {lr.get('timestamp','?')[:19]}")

                if health["db_writable"] and health.get("test_id"):
                    st.success(
                        f"✅ Database sehat — write test berhasil (record ID: {health['test_id']})"
                    )

        st.divider()
        st.markdown("#### 📊 Status Server Detail")
        col_s1, col_s2 = st.columns([1, 3])
        with col_s1:
            if st.button("🔄 Refresh Status", use_container_width=True):
                st.cache_data.clear()
        status = api_status(server_base, api_key)
        if status:
            # Ringkasan
            rs1, rs2, rs3 = st.columns(3)
            rs1.metric("Total Records", status.get("total_records", "?"))
            rs2.metric("PHP Version",   status.get("php_version", "?"))
            rs3.metric("Devices",       len(status.get("devices", [])))
            with st.expander("📋 Full JSON Status"):
                st.json(status)
        else:
            st.error("Server tidak dapat dijangkau.")

        st.divider()
        with st.expander("⚠️ Reset Database (Development Only)", expanded=False):
            st.warning("Menghapus **SEMUA** data sensor dan mereset SPRT state!")
            if st.button("🗑️ Reset Database", type="primary",
                         use_container_width=True):
                try:
                    r = requests.delete(f"{server_base}/reset.php",
                                        headers=get_headers(api_key), timeout=5)
                    if r.status_code == 200:
                        st.cache_data.clear()
                        st.success(f"✅ {r.json().get('message','Reset OK')}")
                        st.rerun()
                    else:
                        st.error(f"Error {r.status_code}: {r.text}")
                except Exception as e:
                    st.error(f"❌ {e}")

    # ── SUB-TAB 2: UI SIMULATION ───────────────────────────────────
    with sub2:
        st.markdown("#### 🎮 Simulasi Pengiriman Data dari UI")
        st.caption(
            "Kirim data sintetis langsung dari browser ke PHP server — "
            "tanpa menjalankan `simulasi_php.py` di terminal."
        )

        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**Konfigurasi Simulasi**")
            sim_device  = st.text_input("Device ID Simulasi", value="D1R32_UI_SIM")
            sim_n       = st.slider("Sampel per fase", 2, 30, 5)
            sim_delay   = st.slider("Delay antar kirim (ms)", 0, 2000, 200, 50)

            # Pilih fase yang akan disimulasikan
            sim_fases   = st.multiselect(
                "Fase yang disimulasikan",
                options=list(range(6)),
                default=list(range(6)),
                format_func=lambda x: f"{FASE_DEF[x]['emoji']} {FASE_DEF[x]['nama']}",
            )

        with sc2:
            st.markdown("**Preview Nilai Sensor per Fase**")
            for fid in (sim_fases if sim_fases else list(range(6))):
                p     = FASE_PROFIL_SIM[fid]
                finfo = FASE_DEF[fid]
                st.markdown(
                    f"<div style='background:{finfo['warna']}15;"
                    f"border-left:3px solid {finfo['warna']};"
                    f"padding:5px 10px;border-radius:4px;margin:3px 0;"
                    f"font-size:0.82rem;color:#D8E4F0;'>"
                    f"{finfo['emoji']} <b>{finfo['nama']}</b> — "
                    f"🌡 {p['suhu'][0]}–{p['suhu'][1]}°C &nbsp;"
                    f"💧 {p['moisture'][0]}–{p['moisture'][1]}% &nbsp;"
                    f"🌫 {p['gas'][0]}–{p['gas'][1]} ppm"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        total_sim = len(sim_fases) * sim_n if sim_fases else 0
        st.markdown(
            f"**Total yang akan dikirim: "
            f"<span style='color:#22C55E;font-size:1.2rem'>{total_sim}</span> sampel**",
            unsafe_allow_html=True,
        )

        if not sim_fases:
            st.warning("Pilih minimal 1 fase untuk disimulasikan.")
        else:
            start_sim = st.button(
                f"▶️ Mulai Simulasi — {total_sim} sampel",
                type="primary", use_container_width=True,
            )

            if start_sim:
                # First check server
                if not api_health(server_base):
                    st.error("❌ Server tidak online. Nyalakan server PHP terlebih dahulu.")
                else:
                    st.markdown("---")
                    st.markdown("**📡 Log Pengiriman**")
                    progress_ph = st.empty()
                    log_ph      = st.empty()
                    result_ph   = st.empty()

                    with st.spinner("Simulasi berjalan..."):
                        results = run_ui_simulation(
                            server_base, api_key, sim_device,
                            sim_fases, sim_n, sim_delay,
                            progress_ph, log_ph,
                        )

                    progress_ph.progress(1.0, text="✅ Selesai!")

                    n_ok   = sum(1 for r in results if r["ok"])
                    n_fail = len(results) - n_ok

                    if n_ok == len(results):
                        result_ph.success(
                            f"✅ Simulasi selesai — {n_ok}/{len(results)} berhasil dikirim. "
                            f"Refresh tab **Live Monitor** atau **Tren Sensor** untuk melihat data."
                        )
                    elif n_ok > 0:
                        result_ph.warning(
                            f"⚠️ Sebagian berhasil: {n_ok} sukses, {n_fail} gagal."
                        )
                    else:
                        result_ph.error("❌ Semua pengiriman gagal. Cek koneksi server.")

                    # Per-fase summary
                    from collections import Counter
                    fase_counts = Counter(r["fase"] for r in results if r["ok"])
                    if fase_counts:
                        st.markdown("**Rekap per Fase:**")
                        cols_sum = st.columns(len(sim_fases))
                        for i, fid in enumerate(sim_fases):
                            cnt   = fase_counts.get(fid, 0)
                            finfo = FASE_DEF[fid]
                            with cols_sum[i]:
                                st.markdown(
                                    f"<div style='text-align:center;"
                                    f"background:{finfo['warna']}20;"
                                    f"border:1px solid {finfo['warna']};"
                                    f"border-radius:8px;padding:8px;'>"
                                    f"<div style='font-size:1.3rem'>{finfo['emoji']}</div>"
                                    f"<div style='font-size:0.9rem;font-weight:700;"
                                    f"color:{finfo['warna']}'>{cnt}/{sim_n}</div>"
                                    f"<div style='font-size:0.7rem;color:#94A3B8'>"
                                    f"{finfo['nama'].split()[0]}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                    st.cache_data.clear()  # refresh all cached API data

    # ── SUB-TAB 3: API Reference ───────────────────────────────────
    with sub3:
        st.markdown("#### 🔌 Endpoint Referensi")
        st.code(
            f"# PHP REST API Base URL\n"
            f"BASE = {server_base}\n\n"
            f"# Endpoints\n"
            f"POST   {server_base}/data.php       # Kirim data sensor\n"
            f"GET    {server_base}/latest.php     # Data terbaru\n"
            f"GET    {server_base}/history.php    # Riwayat (hours, limit)\n"
            f"GET    {server_base}/aggregate.php  # Agregasi (level, days)\n"
            f"GET    {server_base}/status.php     # Status + SPRT state\n"
            f"GET    {server_base}/health.php     # Health check\n"
            f"DELETE {server_base}/reset.php      # Reset DB (dev only)\n",
            language="bash",
        )

        st.markdown("#### 📦 Format JSON Request")
        st.code(json.dumps({
            "device_id" : device_id,
            "timestamp" : datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "suhu"      : 54.3,
            "moisture"  : 48.2,
            "gas"       : 185.6,
            "api_key"   : api_key,
        }, indent=2), language="json")

        st.markdown("#### ✅ Format Response 201")
        st.code(json.dumps({
            "id": 42, "status": "ok",
            "analysis": {
                "fase_pred": 1,
                "fase_nama": "Termofilik Aktif",
                "ikk": 72.4,
                "sprt": {"cusum_t": 1.23, "cusum_m": 0.45, "cusum_g": 2.11},
            },
            "alerts": [],
            "recommendation": "Semua parameter dalam kondisi normal.",
        }, indent=2), language="json")

        st.markdown("#### 🛡️ Autentikasi")
        st.code(
            "# Via Header (direkomendasikan untuk firmware)\n"
            "curl -H \"X-API-Key: kompos2024iot\" ...\n\n"
            "# Via JSON body field\n"
            '{"api_key": "kompos2024iot", "suhu": 54.3, ...}',
            language="bash",
        )

        st.markdown("#### 📡 Test dengan curl")
        st.code(
            f"curl -X POST {server_base}/data.php \\\n"
            f"  -H \"Content-Type: application/json\" \\\n"
            f"  -H \"X-API-Key: {api_key}\" \\\n"
            f"  -d '{{\"device_id\":\"{device_id}\"," 
            f"\"timestamp\":\"$(date -Iseconds)\"," 
            f"\"suhu\":54.3,\"moisture\":48.2,\"gas\":185.6}}'",
            language="bash",
        )