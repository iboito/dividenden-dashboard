# ───────────────────────────────────────────────────────────────
# Dividenden-Dashboard – Streamlit-App (ohne TextColumn-align)
# ───────────────────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import json, os, datetime

OVERRIDE_FILE   = "dividend_overrides.json"
DEFAULT_TICKERS = (
    "VOW3.DE, INGA.AS, LHA.DE, NEDAP.AS, VICI, KMI, O, ENB, "
    "ECMPA.AS, COLD, VEI.OL, ALV.DE, DG.PA, SCMN.SW, IMB.L, "
    "ITX.MC, NESN.SW, SAN.PA"
)

# ───────────────────────────────────────────────────────────────
# 1. Basis-Funktionen
# ───────────────────────────────────────────────────────────────
TICKER_MAP = {"WCH": "WCH.DE", "LVMH": "MC.PA"}          # optional erweitern

def norm(t: str) -> str:            # Ticker normalisieren
    return TICKER_MAP.get(t.upper(), t.upper())

def load_overrides() -> dict:       # JSON lesen
    if os.path.exists(OVERRIDE_FILE):
        try:
            return json.load(open(OVERRIDE_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_overrides(d: dict) -> None:  # JSON speichern
    json.dump(d, open(OVERRIDE_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

@st.cache_data(ttl=3600, show_spinner=False)
def fx(src: str, dst: str = "EUR") -> float:
    if src == dst:
        return 1.0
    try:
        pair = f"{src}{dst}=X"
        return float(yf.Ticker(pair).history("1d")["Close"].iloc[-1])
    except Exception:
        return 1.0

def pct_changes(tkr: yf.Ticker) -> list[str]:
    """%-Änderungen Tag/Woche/Monat/Jahr → ['0,6', '3,1', …] / 'N/A'."""
    try:
        hist = tkr.history("400d", "1d", auto_adjust=True)
        if hist.empty:
            return ["N/A"] * 4
        close, last = hist["Close"].dropna(), hist["Close"].dropna().iloc[-1]
        spans, out = [1, 7, 30, 365], []
        for d in spans:
            tgt = close.index[-1] - pd.Timedelta(days=d)
            past = close.loc[close.index >= tgt]
            if past.empty:
                out.append("N/A")
                continue
            pct = (last - past.iloc[0]) / past.iloc[0] * 100
            out.append("0,0" if abs(pct) < .05
                       else f"{pct:.1f}".replace(".", ",").lstrip("+"))
        return out
    except Exception:
        return ["N/A"] * 4

# ───────────────────────────────────────────────────────────────
# 2. Streamlit-App
# ───────────────────────────────────────────────────────────────
st.set_page_config("Dividenden-Dashboard", layout="wide")
st.title("📊 Dividenden-Dashboard")

if "overrides" not in st.session_state:
    st.session_state.overrides = load_overrides()
if "results" not in st.session_state:
    st.session_state.results = None

# Eingabe
tick_raw = st.text_input(
    "Aktien-Ticker (Komma getrennt)", value=DEFAULT_TICKERS)
tickers   = [norm(x) for x in tick_raw.split(",") if x.strip()]

# Buttons
c1, c2, c3 = st.columns(3)
run  = c1.button("Analyse starten", use_container_width=True)
edit = c2.button("Dividende manuell erfassen", use_container_width=True)
wipe = c3.button("Overrides löschen", use_container_width=True)

# Overrides löschen
if wipe:
    st.session_state.overrides = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state.results = None
    st.experimental_rerun()

# Analyse starten
if run and tickers:
    rows = []
    for t in tickers:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            stk   = yf.Ticker(t)
            info  = stk.info
            name  = info.get("longName") or info.get("shortName") or info.get("symbol") or t
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            cur   = info.get("currency", "USD")
            if t.endswith(".L") and cur == "GBp" and price:
                price /= 100; cur = "GBP"
            peur  = round(price * fx(cur), 2) if price else None  # €-Preis

            # Dividende (Override > Yahoo > Yield > Historie)
            div = st.session_state.overrides.get(t)
            if div is None:
                direct = info.get("trailingAnnualDividendRate")
                if direct and direct > 0:
                    div = direct
                else:
                    dy = info.get("dividendYield") or 0
                    if dy and price:
                        div = price * (dy/100 if dy > 1 else dy)
                    else:
                        hist = stk.history("1y", actions=True, auto_adjust=True)
                        div = hist["Dividends"].sum() if "Dividends" in hist else 0
            deur = round(div * fx(cur), 2) if div else None

            div_str = f"€ {deur:,.2f}" if deur and peur else "N/A"
            yld_str = f"{deur/peur*100:.2f}" if deur and peur else "N/A"
            chg_str = "/".join(pct_changes(stk))

            rows.append({
                "Unternehmen":            name,
                "Ticker":                 t,
                "Kurs (€)":               f"€ {peur:,.2f}" if peur else "N/A",
                "Jahresdividende (€)":    div_str,
                "Dividendenrendite (%)":  yld_str,
                "Veränderung T/W/M/J":    chg_str,
                "Stand":                  now,
            })
        except Exception:
            rows.append({
                "Unternehmen": f"Fehler bei '{t}'", "Ticker": t,
                "Kurs (€)": "N/A", "Jahresdividende (€)": "N/A",
                "Dividendenrendite (%)": "N/A", "Veränderung T/W/M/J": "N/A",
                "Stand": now,
            })

    df = pd.DataFrame(rows)

    # Sortierung nach Tages-Veränderung
    def _day(x: str) -> float:
        try:
            return float(x.split("/")[0].replace(",", "."))
        except Exception:
            return -9e9
    df["__s"] = df["Veränderung T/W/M/J"].apply(_day)
    df.sort_values("__s", ascending=False, inplace=True)
    df.drop(columns="__s", inplace=True)
    st.session_state.results = df

# Tabelle
if st.session_state.results is not None:
    st.dataframe(st.session_state.results, use_container_width=True)

# Override-Dialog
if edit and st.session_state.results is not None:
    df = st.session_state.results
    cmap = {r["Unternehmen"]: r["Ticker"] for _, r in df.iterrows()}
    with st.form("ov_form", clear_on_submit=True):
        st.subheader("Dividende manuell erfassen")
        comp = st.selectbox("Unternehmen", list(cmap.keys()))
        tkr  = cmap[comp]
        cur  = st.session_state.overrides.get(tkr, "")
        val  = st.text_input("Dividende in Euro (leer = löschen)", value=str(cur))
        a, b = st.columns(2)
        ok   = a.form_submit_button("Speichern")
        cancel = b.form_submit_button("Abbrechen")
        if ok:
            v = val.replace(",", ".").strip()
            if v == "":
                st.session_state.overrides.pop(tkr, None)
            else:
                try:
                    st.session_state.overrides[tkr] = float(v)
                except ValueError:
                    st.error("Ungültiger Wert."); st.stop()
            save_overrides(st.session_state.overrides)
            st.success("Gespeichert – Analyse wird neu geladen …")
            st.session_state.results = None
            st.experimental_rerun()
        if cancel:
            st.experimental_rerun()
