# ───────────────────────────────────────────────────────────────
# Dividenden-Dashboard – Streamlit-App
# Batch-Abruf, stabile Kursveränderungen, Multi-/Single-Index-Fix
# ───────────────────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import json, os, datetime

OVERRIDE_FILE   = "dividend_overrides.json"
DEFAULT_TICKERS = (
    "VOW3.DE, INGA.AS, LHA.DE, VICI, KMI, O, ENB, ALV.DE, MC.PA"
)

# Kurzformen ➜ vollständige Yahoo-Ticker
TICKER_MAP = {
    "WCH":  "WCH.DE",
    "LVMH": "MC.PA",
}

# ───────────── Hilfsfunktionen ─────────────────────────────────
def norm(t):
    return TICKER_MAP.get(t.upper(), t.upper())

def load_overrides():
    if os.path.exists(OVERRIDE_FILE):
        try:
            return json.load(open(OVERRIDE_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_overrides(data):
    json.dump(data, open(OVERRIDE_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

@st.cache_data(ttl=3600)
def fx(src, dst="EUR"):
    if src == dst:
        return 1.0
    pair = f"{src}{dst}=X"
    try:
        return float(yf.Ticker(pair).history("1d")["Close"].iloc[-1])
    except Exception:
        return 1.0

def pct_from_history(series):
    """%-Änderung Tag/Woche/Monat/Jahr aus einer Close-Serie."""
    if series.empty or len(series) < 2:
        return ["N/A"] * 4
    latest = series.iloc[-1]
    spans  = [1, 7, 30, 365]
    out    = []
    for d in spans:
        tgt = series.index[-1] - pd.Timedelta(days=d)
        idx = series.index.get_indexer([tgt], method="bfill")[0]
        past = series.iloc[idx]
        if past <= 0:
            out.append("N/A")
            continue
        pct = (latest - past) / past * 100
        out.append("0,0" if abs(pct) < .05
                   else f"{pct:.1f}".replace('.', ',').lstrip('+'))
    return out

# ───────────── Streamlit-App ───────────────────────────────────
st.set_page_config("Dividenden-Dashboard", layout="wide")
st.title("📊 Dividenden-Dashboard")

if "ovr" not in st.session_state:
    st.session_state.ovr = load_overrides()
if "res" not in st.session_state:
    st.session_state.res = None

raw  = st.text_input("Ticker (Komma getrennt)", DEFAULT_TICKERS)
tick = [norm(t) for t in raw.split(",") if t.strip()]

c_run, c_ovr, c_del = st.columns(3)
do_run  = c_run.button("Analyse starten", use_container_width=True)
do_ovr  = c_ovr.button("Dividende manuell", use_container_width=True)
do_del  = c_del.button("Overrides löschen", use_container_width=True)

# Overrides löschen
if do_del:
    st.session_state.ovr = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state.res = None
    st.experimental_rerun()

# ─ Analyse ─
if do_run and tick:
    # 1) Sammel-Download: Kurse & Historien
    bulk = yf.download(
        tick, period="400d", interval="1d",
        group_by="ticker", auto_adjust=False, threads=False
    )

    # 2) Sammel-Infos (Name, Währung, Live-Preis)
    info_map = yf.Tickers(" ".join(tick)).tickers
    rows = []

    for t in tick:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            info = info_map[t].info
            name = info.get("longName") or info.get("shortName") or t
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            cur   = info.get("currency", "USD")
            if t.endswith(".L") and cur == "GBp" and price:
                price /= 100; cur = "GBP"
            price_eur = round(price * fx(cur), 2) if price else None

            # Dividende
            div = st.session_state.ovr.get(t)
            if div is None:
                div = info.get("trailingAnnualDividendRate") or 0
                if not div:
                    dy = info.get("dividendYield") or 0
                    div = price * (dy / 100 if dy > 1 else dy) if dy and price else 0
                if not div and (t, "Dividends") in bulk:
                    div = bulk[t]["Dividends"].tail(252).sum()
            div_eur = round(div * fx(cur), 2) if div else None

            # Close-Serie finden (Multi- oder Single-Index)
            if isinstance(bulk.columns, pd.MultiIndex):
                series = bulk[t]["Close"].dropna()
            else:                                          # nur 1 Ticker
                series = bulk["Close"].dropna()

            changes = "/".join(pct_from_history(series))

            rows.append({
                "Unternehmen":            name,
                "Ticker":                 t,
                "Kurs (€)":               f"€ {price_eur:,.2f}" if price_eur else "N/A",
                "Jahresdividende (€)":    f"€ {div_eur:,.2f}"   if div_eur   else "N/A",
                "Dividendenrendite (%)":  f"{div_eur/price_eur*100:.2f}"
                                           if div_eur and price_eur else "N/A",
                "Veränderung T/W/M/J":    changes,
                "Stand":                  ts,
            })
        except Exception:
            rows.append({
                "Unternehmen": f"Fehler bei '{t}'", "Ticker": t,
                "Kurs (€)": "N/A", "Jahresdividende (€)": "N/A",
                "Dividendenrendite (%)": "N/A", "Veränderung T/W/M/J": "N/A",
                "Stand": ts,
            })

    df = pd.DataFrame(rows)

    # Sortieren nach Tages-Veränderung
    def _day(x):
        try:
            return float(x.split("/")[0].replace(",", "."))
        except Exception:
            return -9e9

    df["__"] = df["Veränderung T/W/M/J"].apply(_day)
    df.sort_values("__", ascending=False, inplace=True)
    df.drop(columns="__", inplace=True)

    st.session_state.res = df

# ─ Tabelle ─
if st.session_state.res is not None:
    st.dataframe(st.session_state.res, use_container_width=True)

# ─ Override-Dialog ─
if do_ovr and st.session_state.res is not None:
    cmap = {r["Unternehmen"]: r["Ticker"]
            for _, r in st.session_state.res.iterrows()}
    with st.form("ov", clear_on_submit=True):
        st.subheader("Dividende manuell")
        comp = st.selectbox("Unternehmen", list(cmap.keys()))
        tkr  = cmap[comp]
        cur  = st.session_state.ovr.get(tkr, "")
        val  = st.text_input("Dividende in € (leer = löschen)", value=str(cur))
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Speichern"):
            v = val.replace(",", ".").strip()
            if v == "":
                st.session_state.ovr.pop(tkr, None)
            else:
                try:
                    st.session_state.ovr[tkr] = float(v)
                except ValueError:
                    st.error("Ungültiger Wert"); st.stop()
            save_overrides(st.session_state.ovr)
            st.session_state.res = None
            st.experimental_rerun()
        if c2.form_submit_button("Abbrechen"):
            st.experimental_rerun()
