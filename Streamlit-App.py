# ───────────────────────────────────────────────────────────────
# Dividenden-Dashboard – Streamlit-App
# Batch-Abruf · stabile Kursveränderungen · Safe-Info gegen Rate-Limit
# ───────────────────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import datetime
import time
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

OVERRIDE_FILE = "dividend_overrides.json"
DEFAULT_TICKERS = (
    "VOW3.DE, INGA.AS, LHA.DE, VICI, KMI, O, ENB, ALV.DE, MC.PA"
)

# Kurzformen → vollständige Yahoo-Ticker
TICKER_MAP = {
    "WCH":  "WCH.DE",
    "LVMH": "MC.PA",
}

# ────────── Hilfsfunktionen ────────────────────────────────────
def norm(ticker: str) -> str:
    """Ticker ggf. auf Yahoo-Konvention abbilden."""
    return TICKER_MAP.get(ticker.upper(), ticker.upper())


def load_overrides() -> dict:
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_overrides(data: dict) -> None:
    with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@st.cache_data(ttl=3600)
def fx(src: str, dst: str = "EUR") -> float:
    """Live-Wechselkurs via Yahoo Finance (1-h Cache)."""
    if src == dst:
        return 1.0
    pair = f"{src}{dst}=X"
    try:
        return float(yf.Ticker(pair).history("1d")["Close"].iloc[-1])
    except Exception:
        return 1.0


def safe_info(ticker_obj: yf.Ticker, pause: float = 1.2, tries: int = 3) -> dict:
    """Schonender Abruf der .info-Daten – vermeidet Rate-Limit."""
    for _ in range(tries):
        data = ticker_obj.get_info()
        if data:  # Yahoo hat geliefert
            return data
        time.sleep(pause)
    return {}


def pct_from_history(series: pd.Series) -> list[str]:
    """%-Änderung Tag/Woche/Monat/Jahr aus einer Close-Serie."""
    if series.empty or len(series) < 2:
        return ["N/A"] * 4

    latest = series.iloc[-1]
    spans = [1, 7, 30, 365]
    out = []

    for days in spans:
        tgt = series.index[-1] - pd.Timedelta(days=days)
        idx = series.index.get_indexer([tgt], method="bfill")[0]
        past = series.iloc[idx]

        if past <= 0:
            out.append("N/A")
            continue

        pct = (latest - past) / past * 100
        out.append("0,0" if abs(pct) < 0.05 else f"{pct:.1f}".replace(".", ",").lstrip("+"))
    return out

# ────────── Streamlit-App ───────────────────────────────────────
st.set_page_config("Dividenden-Dashboard", layout="wide")
st.title("📊 Dividenden-Dashboard")

if "ovr" not in st.session_state:
    st.session_state.ovr = load_overrides()
if "res" not in st.session_state:
    st.session_state.res = None

raw = st.text_input("Ticker (Komma getrennt)", DEFAULT_TICKERS)
tickers = [norm(t) for t in raw.split(",") if t.strip()]

c_run, c_edit, c_del = st.columns(3)
do_run = c_run.button("Analyse starten", use_container_width=True)
do_edit = c_edit.button("Dividende manuell", use_container_width=True)
do_del = c_del.button("Overrides löschen", use_container_width=True)

# Overrides löschen
if do_del:
    st.session_state.ovr = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state.res = None
    st.experimental_rerun()

# ────────── Analyse ────────────────────────────────────────────
if do_run and tickers:
    # 1) Sammel-Download: Kurse & Historien (1 HTTP-Request)
    bulk = yf.download(
        tickers,
        period="400d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=False,
    )

    rows = []
    for tkr in tickers:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            ticker_obj = yf.Ticker(tkr)
            info = safe_info(ticker_obj)  # Rate-Limit-sicher
            # Preis & Währung
            if info:
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                cur = info.get("currency", "USD")
                name = info.get("longName") or info.get("shortName") or tkr
            else:
                # Fallback aus Bulk-Daten
                name = tkr
                series_fallback = (
                    bulk[tkr]["Close"].dropna()
                    if isinstance(bulk.columns, pd.MultiIndex)
                    else bulk["Close"].dropna()
                )
                price = series_fallback.iloc[-1] if not series_fallback.empty else None
                cur = "EUR"

            if tkr.endswith(".L") and cur == "GBp" and price:
                price /= 100
                cur = "GBP"
            price_eur = round(price * fx(cur), 2) if price else None

            # Dividende
            div = st.session_state.ovr.get(tkr)
            if div is None:
                div = info.get("trailingAnnualDividendRate") if info else 0
                if not div:
                    dy = info.get("dividendYield") if info else 0
                    if dy and price:
                        div = price * (dy / 100 if dy > 1 else dy)
                if not div:
                    div_series = (
                        bulk[tkr]["Dividends"]
                        if isinstance(bulk.columns, pd.MultiIndex) and (tkr, "Dividends") in bulk
                        else bulk.get("Dividends", pd.Series())
                    )
                    div = div_series.tail(252).sum() if not div_series.empty else 0
            div_eur = round(div * fx(cur), 2) if div else None

            # Close-Serie (Multi- oder Single-Index)
            series = (
                bulk[tkr]["Close"].dropna()
                if isinstance(bulk.columns, pd.MultiIndex)
                else bulk["Close"].dropna()
            )
            change_str = "/".join(pct_from_history(series))

            rows.append(
                {
                    "Unternehmen": name,
                    "Ticker": tkr,
                    "Kurs (€)": f"€ {price_eur:,.2f}" if price_eur else "N/A",
                    "Jahresdividende (€)": f"€ {div_eur:,.2f}" if div_eur else "N/A",
                    "Dividendenrendite (%)": f"{div_eur / price_eur * 100:.2f}"
                    if div_eur and price_eur
                    else "N/A",
                    "Veränderung T/W/M/J": change_str,
                    "Stand": ts,
                }
            )
        except Exception:
            rows.append(
                {
                    "Unternehmen": f"Fehler bei '{tkr}'",
                    "Ticker": tkr,
                    "Kurs (€)": "N/A",
                    "Jahresdividende (€)": "N/A",
                    "Dividendenrendite (%)": "N/A",
                    "Veränderung T/W/M/J": "N/A",
                    "Stand": ts,
                }
            )

    df = pd.DataFrame(rows)

    # Sortieren nach Tages-Veränderung
    df["__"] = df["Veränderung T/W/M/J"].apply(
        lambda x: float(x.split("/")[0].replace(",", ".")) if "/" in x else -9e9
    )
    df.sort_values("__", ascending=False, inplace=True)
    df.drop(columns="__", inplace=True)

    st.session_state.res = df

# ────────── Tabelle ───────────────────────────────────────────
if st.session_state.res is not None:
    st.dataframe(st.session_state.res, use_container_width=True)

# ────────── Override-Dialog ───────────────────────────────────
if do_ovr and st.session_state.res is not None:
    cmap = {row["Unternehmen"]: row["Ticker"] for _, row in st.session_state.res.iterrows()}
    with st.form("ov_form", clear_on_submit=True):
        st.subheader("Dividende manuell")
        comp = st.selectbox("Unternehmen", list(cmap.keys()))
        tkr = cmap[comp]
        cur = st.session_state.ovr.get(tkr, "")
        val = st.text_input("Dividende in € (leer = löschen)", value=str(cur))
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Speichern"):
            v = val.replace(",", ".").strip()
            if v == "":
                st.session_state.ovr.pop(tkr, None)
            else:
                try:
                    st.session_state.ovr[tkr] = float(v)
                except ValueError:
                    st.error("Ungültiger Wert")
                    st.stop()
            save_overrides(st.session_state.ovr)
            st.session_state.res = None
            st.experimental_rerun()
        if c2.form_submit_button("Abbrechen"):
            st.experimental_rerun()
