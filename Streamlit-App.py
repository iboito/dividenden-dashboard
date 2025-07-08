import streamlit as st
st.write("⚙️ laufende Streamlit-Version:", st.__version__)
# ───────────────────────────────────────────────────────────────
# Dividendenrendite Tracker   –   Streamlit-Version
# ───────────────────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import json, os, datetime

# ---------- Konstante Dateien ------------------------------------------------
OVERRIDE_FILE   = "dividend_overrides.json"
DEFAULT_TICKERS = ("VOW3.DE, INGA.AS, LHA.DE, NEDAP.AS, VICI, KMI, O, ENB, "
                   "ECMPA.AS, COLD, VEI.OL, ALV.DE, DG.PA, SCMN.SW, IMB.L, "
                   "ITX.MC, NESN.SW, SAN.PA")

# ---------- Ticker-Mapping (bei Bedarf ergänzen) -----------------------------
TICKER_MAP = {
    "WCH":  "WCH.DE",   # Wacker Chemie AG
    "LVMH": "MC.PA",    # LVMH Moët Hennessy Louis Vuitton
}

def normalize(tkr: str) -> str:
    return TICKER_MAP.get(tkr.upper(), tkr.upper())

# ---------- Helpers ----------------------------------------------------------
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
def fx_rate(src: str, dst: str = "EUR") -> float:
    if src == dst:
        return 1.0
    try:
        pair = f"{src}{dst}=X"
        return float(yf.Ticker(pair).history(period="1d")["Close"].iloc[-1])
    except Exception:
        return 1.0

def price_changes(stock: yf.Ticker) -> list[str]:
    """%-Änderungen Tag/Woche/Monat/Jahr (Fallback N/A)."""
    try:
        hist = stock.history(period="400d", interval="1d", auto_adjust=True)
        if hist.empty:
            return ["N/A"] * 4
        close  = hist["Close"].dropna()
        latest = close.iloc[-1]
        spans  = [1, 7, 30, 365]
        res    = []
        for d in spans:
            target = close.index[-1] - pd.Timedelta(days=d)
            past   = close.loc[close.index >= target]
            if past.empty:
                res.append("N/A"); continue
            pct = (latest - past.iloc[0]) / past.iloc[0] * 100
            txt = "0,0" if abs(pct) < 0.05 else f"{pct:.1f}".replace(".", ",").lstrip("+")
            res.append(txt)
        return res
    except Exception:
        return ["N/A"] * 4

# ============================================================================ #
#                               Streamlit App                                  #
# ============================================================================ #
st.set_page_config("Dividendenrendite Tracker", layout="wide")
st.title("📊 Dividendenrendite Tracker")

if "overrides" not in st.session_state:
    st.session_state.overrides = load_overrides()
if "results" not in st.session_state:
    st.session_state.results = None

# ---------- Eingabe ----------------------------------------------------------
t_in = st.text_input(
    "Aktien-Ticker (Komma getrennt, z. B. SAP.DE, MSFT, O, IMB.L)",
    value=DEFAULT_TICKERS
)
ticker_list = [normalize(x) for x in t_in.split(",") if x.strip()]

# ---------- Buttons ----------------------------------------------------------
c_run, c_ovr, c_del = st.columns(3)
do_run = c_run.button("Analyse starten", use_container_width=True)
do_ovr = c_ovr.button("Dividende manuell erfassen", use_container_width=True)
do_del = c_del.button("Alle Overrides löschen", use_container_width=True)

# ---------- Overrides löschen ------------------------------------------------
if do_del:
    st.session_state.overrides = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state.results = None
    st.experimental_rerun()

# ---------- Analyse ----------------------------------------------------------
if do_run and ticker_list:
    rows = []
    for tkr in ticker_list:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            stck  = yf.Ticker(tkr)
            info  = stck.info
            name  = info.get("longName") or info.get("shortName") or info.get("symbol") or tkr
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            cur   = info.get("currency", "USD")
            if tkr.endswith(".L") and cur == "GBp" and price:
                price /= 100; cur = "GBP"
            price_eur = round(price * fx_rate(cur), 2) if price else None

            # ---------- Dividende -----------------------------------------
            div = st.session_state.overrides.get(tkr)
            if div is None:
                direct = info.get("trailingAnnualDividendRate")
                if direct and direct > 0:
                    div = direct
                else:
                    dy = info.get("dividendYield") or 0
                    if dy and price:
                        dy  = dy/100 if dy > 1 else dy
                        div = price * dy
                    else:
                        hist = stck.history(period="1y", actions=True, auto_adjust=True)
                        div  = hist["Dividends"].sum() if "Dividends" in hist else 0
            div_eur  = round(div * fx_rate(cur), 2) if div else None
            div_str  = f"€ {div_eur:,.2f}" if div_eur and price_eur else "N/A"
            yld_str  = f"{div_eur/price_eur*100:.2f}" if div_eur and price_eur else "N/A"

            # ---------- Kursveränderungen ---------------------------------
            chg_str = "/".join(price_changes(stck))

            rows.append({
                "Unternehmen":            name,
                "Ticker":                 tkr,
                "Kurs (€)":               f"€ {price_eur:,.2f}" if price_eur else "N/A",
                "Jahresdividende (€)":    div_str,
                "Dividendenrendite (%)":  yld_str,
                "Veränderung T/W/M/J":    chg_str,
                "Stand":                  ts,
            })
        except Exception:
            rows.append({
                "Unternehmen": f"Fehler bei '{tkr}'",
                "Ticker": tkr,
                "Kurs (€)": "N/A",
                "Jahresdividende (€)": "N/A",
                "Dividendenrendite (%)": "N/A",
                "Veränderung T/W/M/J": "N/A",
                "Stand": ts,
            })

    df = pd.DataFrame(rows)

    # ---------- Sortierung nach Tages-Veränderung -------------------------
    def _day(val: str) -> float:
        try:
            return float(val.split("/")[0].replace(",", "."))
        except Exception:
            return -9999
    df["__sort"] = df["Veränderung T/W/M/J"].apply(_day)
    df.sort_values("__sort", ascending=False, inplace=True)
    df.drop(columns="__sort", inplace=True)

    st.session_state.results = df

# ---------- Tabelle ----------------------------------------------------------
if st.session_state.results is not None:
    st.dataframe(
        st.session_state.results,
        use_container_width=True,
        column_config={
            "Kurs (€)":               st.column_config.TextColumn(align="right"),
            "Jahresdividende (€)":    st.column_config.TextColumn(align="right"),
            "Dividendenrendite (%)":  st.column_config.TextColumn(align="right"),
            "Veränderung T/W/M/J":    st.column_config.TextColumn(align="right"),
            "Stand":                  st.column_config.TextColumn(align="right"),
        },
    )

# ---------- Override-Dialog --------------------------------------------------
if do_ovr and st.session_state.results is not None:
    df = st.session_state.results
    comp_map = {row["Unternehmen"]: row["Ticker"] for _, row in df.iterrows()}
    with st.form("ov_form", clear_on_submit=True):
        st.subheader("Dividende manuell erfassen")
        comp = st.selectbox("Unternehmen wählen", list(comp_map.keys()))
        tkr  = comp_map[comp]
        cur  = st.session_state.overrides.get(tkr, "")
        val  = st.text_input("Dividende in Euro (leer = löschen)", value=str(cur))
        c1, c2 = st.columns(2)
        ok  = c1.form_submit_button("Speichern")
        cancel = c2.form_submit_button("Abbrechen")
        if ok:
            val = val.replace(",", ".").strip()
            if val == "":
                st.session_state.overrides.pop(tkr, None)
            else:
                try:
                    st.session_state.overrides[tkr] = float(val)
                except ValueError:
                    st.error("Ungültige Zahl."); st.stop()
            save_overrides(st.session_state.overrides)
            st.success("Gespeichert – starte Analyse neu …")
            st.session_state.results = None
            st.experimental_rerun()
        if cancel:
            st.experimental_rerun()
