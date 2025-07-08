# ───────────────────────────────────────────────────────────────
# Dividenden-Dashboard – Streamlit-App
# Batch-Abruf | robust gegen Yahoo-Limits | saubere Multi-Index-Behandlung
# ───────────────────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import json, os, datetime, time, warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

OVERRIDE_FILE   = "dividend_overrides.json"
DEFAULT_TICKERS = (
    "VOW3.DE, INGA.AS, LHA.DE, VICI, KMI, O, ENB, ALV.DE, MC.PA"
)

# optionale Kurzformen
TICKER_MAP = {"WCH": "WCH.DE", "LVMH": "MC.PA"}

norm = lambda t: TICKER_MAP.get(t.upper(), t.upper())

# ───────── Datei-Helfer ────────────────────────────────────────
def load_overrides():
    if os.path.exists(OVERRIDE_FILE):
        try:
            return json.load(open(OVERRIDE_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_overrides(d):
    json.dump(d, open(OVERRIDE_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

# ───────── Yahoo-Helfer ───────────────────────────────────────
@st.cache_data(ttl=3600)
def fx(src, dst="EUR"):
    if src == dst:
        return 1.0
    pair = f"{src}{dst}=X"
    try:
        return float(yf.Ticker(pair).history("1d")["Close"].iloc[-1])
    except Exception:
        return 1.0

def safe_info(tkr_obj, pause=1.2, tries=3):
    for _ in range(tries):
        data = tkr_obj.get_info()
        if data:
            return data
        time.sleep(pause)
    return {}

# ───────── Prozent-Berechnung ─────────────────────────────────
def pct_from_series(series: pd.Series) -> list[str]:
    if series.empty or len(series) < 2:
        return ["N/A"] * 4
    latest = series.iloc[-1]
    spans  = [1, 7, 30, 365]
    out    = []
    for d in spans:
        tgt  = series.index[-1] - pd.Timedelta(days=d)
        idx  = series.index.get_indexer([tgt], method="bfill")[0]
        past = series.iloc[idx]
        if past <= 0:
            out.append("N/A"); continue
        pct = (latest - past) / past * 100
        out.append("0,0" if abs(pct) < .05
                   else f"{pct:.1f}".replace('.', ',').lstrip('+'))
    return out

def day_change(val):
    if isinstance(val, str) and "/" in val:
        try:
            return float(val.split("/")[0].replace(",", "."))
        except ValueError:
            pass
    return float("-inf")

# ───────── Streamlit-UI ───────────────────────────────────────
st.set_page_config("Dividenden-Dashboard", layout="wide")
st.title("📊 Dividenden-Dashboard")

if "ovr" not in st.session_state:
    st.session_state.ovr = load_overrides()
if "res" not in st.session_state:
    st.session_state.res = None

raw  = st.text_input("Ticker (Komma getrennt)", DEFAULT_TICKERS)
tick = [norm(t) for t in raw.split(",") if t.strip()]

c_run, c_edit, c_del = st.columns(3)
do_run  = c_run.button("Analyse starten",    use_container_width=True)
do_edit = c_edit.button("Dividende manuell", use_container_width=True)
do_del  = c_del.button("Overrides löschen",  use_container_width=True)

if do_del:
    st.session_state.ovr = {}
    if os.path.exists(OVERRIDE_FILE): os.remove(OVERRIDE_FILE)
    st.session_state.res = None
    st.experimental_rerun()

# ───────── Analyse ────────────────────────────────────────────
if do_run and tick:
    bulk = yf.download(
        tick, period="400d", interval="1d",
        group_by="ticker", auto_adjust=False, threads=False
    )

    # Close- und Dividenden-DFs robust erzeugen
    if isinstance(bulk.columns, pd.MultiIndex):
        close_df = bulk.xs("Close", level=1, axis=1)
        div_df   = bulk.xs("Dividends", level=1, axis=1) \
                   if "Dividends" in bulk.columns.get_level_values(1) else pd.DataFrame()
    else:  # nur 1 Ticker
        close_df = bulk[["Close"]].rename(columns={"Close": tick[0]})
        div_df   = bulk[["Dividends"]] if "Dividends" in bulk else pd.DataFrame()

    # Hilfs-Suche nach Serie (Ticker in Spalten könnte ohne Suffix stehen)
    def find_close(df: pd.DataFrame, tkr: str) -> pd.Series:
        if tkr in df:
            return df[tkr].dropna()
        uc = {c.upper(): c for c in df.columns}
        real = uc.get(tkr.upper())
        return df[real].dropna() if real else pd.Series()

    rows = []
    for t in tick:
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        info = safe_info(yf.Ticker(t))

        # Name / Kurs / Währung
        if info:
            name  = info.get("longName") or info.get("shortName") or t
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            cur   = info.get("currency", "USD")
        else:
            name  = t
            price = find_close(close_df, t).iloc[-1] if not find_close(close_df, t).empty else None
            cur   = "EUR"

        if t.endswith(".L") and cur == "GBp" and price:
            price /= 100; cur = "GBP"
        price_eur = round(price * fx(cur), 2) if price else None

        # Dividende
        div = st.session_state.ovr.get(t)
        if div is None:
            div = info.get("trailingAnnualDividendRate") if info else 0
            if not div:
                dy = info.get("dividendYield") if info else 0
                if dy and price:
                    div = price * (dy / 100 if dy > 1 else dy)
            if not div and (not div_df.empty and t in div_df):
                div = div_df[t].tail(252).sum()
        div_eur = round(div * fx(cur), 2) if div else None

        # Veränderungen
        series     = find_close(close_df, t)
        change_str = "/".join(pct_from_series(series))

        rows.append({
            "Unternehmen":            name,
            "Ticker":                 t,
            "Kurs (€)":               f"€ {price_eur:,.2f}" if price_eur else "N/A",
            "Jahresdividende (€)":    f"€ {div_eur:,.2f}"   if div_eur else "N/A",
            "Dividendenrendite (%)":  f"{div_eur/price_eur*100:.2f}"
                                       if div_eur and price_eur else "N/A",
            "Veränderung T/W/M/J":    change_str,
            "Stand":                  ts,
        })

    df = pd.DataFrame(rows)
    df["__sort"] = df["Veränderung T/W/M/J"].apply(day_change)
    df.sort_values("__sort", ascending=False, inplace=True)
    df.drop(columns="__sort", inplace=True)
    st.session_state.res = df

# ───────── Tabelle ────────────────────────────────────────────
if st.session_state.res is not None:
    st.dataframe(st.session_state.res, use_container_width=True)

# ───────── Override-Dialog ────────────────────────────────────
if do_edit and st.session_state.res is not None:
    cmap = {r["Unternehmen"]: r["Ticker"] for _, r in st.session_state.res.iterrows()}
    with st.form("ovr", clear_on_submit=True):
        st.subheader("Dividende manuell erfassen")
        comp = st.selectbox("Unternehmen", list(cmap.keys()))
        tkr  = cmap[comp]
        cur  = st.session_state.ovr.get(tkr, "")
        val  = st.text_input("Dividende in € (leer = löschen)", value=str(cur))
        a, b = st.columns(2)
        if a.form_submit_button("Speichern"):
            v = val.replace(",", ".").strip()
            if v == "":
                st.session_state.ovr.pop(tkr, None)
            else:
                try:
                    st.session_state.ovr[tkr] = float(v)
                except ValueError:
                    st.error("Ungültige Zahl"); st.stop()
            save_overrides(st.session_state.ovr)
            st.session_state.res = None
            st.experimental_rerun()
        if b.form_submit_button("Abbrechen"):
            st.experimental_rerun()
