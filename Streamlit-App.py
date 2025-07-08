import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import datetime

OVERRIDE_FILE = "dividend_overrides.json"
DEFAULT_TICKERS = (
    "VOW3.DE, INGA.AS, LHA.DE, NEDAP.AS, VICI, KMI, O, ENB, "
    "ECMPA.AS, COLD, VEI.OL, ALV.DE, DG.PA, SCMN.SW, IMB.L, "
    "ITX.MC, NESN.SW, SAN.PA"
)

# ------------------------------------------------------------------ #
# Hilfsfunktionen
# ------------------------------------------------------------------ #
def load_overrides() -> dict:
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_overrides(overrides: dict) -> None:
    with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)


@st.cache_data(ttl=3600)
def fx_rate(src: str, dst: str = "EUR") -> float:
    if src == dst:
        return 1.0
    try:
        pair = f"{src}{dst}=X"
        rate = yf.Ticker(pair).history(period="1d")["Close"].iloc[-1]
        return float(rate)
    except Exception:
        return 1.0


def price_changes(stock: yf.Ticker) -> list[str]:
    """%-Änderungen für 1 Tag / 1 Woche / 1 Monat / 1 Jahr."""
    try:
        hist = stock.history(period="370d", interval="1d", auto_adjust=True)
        if hist.empty:
            return ["N/A"] * 4
        close = hist["Close"].dropna()
        latest = close.iloc[-1]
        spans = [1, 7, 30, 365]
        out = []
        for d in spans:
            target = close.index[-1] - pd.Timedelta(days=d)
            past = close.loc[close.index >= target]
            if past.empty:
                out.append("N/A")
                continue
            past_price = past.iloc[0]
            pct = (latest - past_price) / past_price * 100
            s = "0,0" if abs(pct) < 0.05 else f"{pct:.1f}".replace(".", ",").lstrip("+")
            out.append(s)
        return out
    except Exception:
        return ["N/A"] * 4


# ------------------------------------------------------------------ #
# Streamlit-App
# ------------------------------------------------------------------ #
st.set_page_config(page_title="Dividendenrendite Tracker", layout="wide")
st.title("Dividendenrendite Tracker (Streamlit)")

if "dividend_overrides" not in st.session_state:
    st.session_state["dividend_overrides"] = load_overrides()

if "results" not in st.session_state:
    st.session_state["results"] = None

# Eingabe
tickers_input = st.text_input(
    "Aktien-Ticker (kommagetrennt, z. B. SAP.DE, MSFT, O, IMB.L)",
    value=DEFAULT_TICKERS,
)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

# Buttons
col_run, col_override, col_del = st.columns([2, 2, 2])
run_clicked = col_run.button("Analyse starten", use_container_width=True)
ov_clicked = col_override.button("Dividende manuell erfassen", use_container_width=True)
del_clicked = col_del.button("Alle Overrides löschen", use_container_width=True)

# Overrides löschen
if del_clicked:
    st.session_state["dividend_overrides"] = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state["results"] = None
    st.experimental_rerun()

# Analyse
if run_clicked and tickers:
    overrides = st.session_state["dividend_overrides"]
    rows = []
    for tkr in tickers:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            stk = yf.Ticker(tkr)
            info = stk.info
            name = (
                info.get("longName")
                or info.get("shortName")
                or info.get("symbol")
                or tkr
            )
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            cur = info.get("currency", "USD")
            if tkr.endswith(".L") and cur == "GBp" and price:
                price /= 100
                cur = "GBP"
            price_eur = round(price * fx_rate(cur), 2) if price else None

            # Dividende
            div = overrides.get(tkr)
            if div is None:
                direct = info.get("trailingAnnualDividendRate")
                if direct and direct > 0:
                    div = direct
                else:
                    dy = info.get("dividendYield") or 0
                    if dy and price:
                        dy = dy / 100 if dy > 1 else dy
                        div = price * dy
                    else:
                        hist = stk.history(period="1y", actions=True, auto_adjust=True)
                        div = hist["Dividends"].sum() if "Dividends" in hist else 0
            div_eur = round(div * fx_rate(cur), 2) if div else None

            div_str = f"€ {div_eur:,.2f}" if price_eur and div_eur else "N/A"
            yld_str = (
                f"{div_eur / price_eur * 100:.2f}"
                if price_eur and div_eur
                else "N/A"
            )

            changes = price_changes(stk)
            change_str = "/".join(changes)

            rows.append(
                {
                    "Unternehmen": name,
                    "Ticker": tkr,
                    "Kurs (€)": f"€ {price_eur:,.2f}" if price_eur else "N/A",
                    "Jahresdividende (€)": div_str,
                    "Dividendenrendite (%)": yld_str,
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

    # Sortierung nach Tages-Veränderung (1. Wert vor dem ersten '/')
    def day_change(val: str) -> float:
        try:
            return float(val.split("/")[0].replace(",", "."))
        except Exception:
            return float("-inf")

    df["sort_key"] = df["Veränderung T/W/M/J"].apply(day_change)
    df = df.sort_values("sort_key", ascending=False).drop(columns="sort_key")
    st.session_state["results"] = df

# Tabelle anzeigen
if st.session_state["results"] is not None:
    st.dataframe(
        st.session_state["results"],
        use_container_width=True,
        column_config={
            "Kurs (€)": st.column_config.TextColumn(align="right"),
            "Jahresdividende (€)": st.column_config.TextColumn(align="right"),
            "Dividendenrendite (%)": st.column_config.TextColumn(align="right"),
            "Veränderung T/W/M/J": st.column_config.TextColumn(align="right"),
            "Stand": st.column_config.TextColumn(align="right"),
        },
    )

# Override-Dialog
if ov_clicked and st.session_state["results"] is not None:
    df = st.session_state["results"]
    comp_map = {row["Unternehmen"]: row["Ticker"] for _, row in df.iterrows()}

    with st.form("override_form", clear_on_submit=True):
        st.subheader("Dividende manuell erfassen")
        comp = st.selectbox("Unternehmen auswählen", list(comp_map.keys()))
        tkr = comp_map[comp]
        curr = st.session_state["dividend_overrides"].get(tkr, "")
        val = st.text_input("Dividende in Euro (leer = löschen)", value=str(curr))
        c1, c2 = st.columns(2)
        save_btn = c1.form_submit_button("Speichern")
        cancel_btn = c2.form_submit_button("Abbrechen")

        if save_btn:
            val = val.replace(",", ".").strip()
            if val == "":
                st.session_state["dividend_overrides"].pop(tkr, None)
            else:
                try:
                    st.session_state["dividend_overrides"][tkr] = float(val)
                except ValueError:
                    st.error(f"Ungültiger Wert: {val}")
                    st.stop()
            save_overrides(st.session_state["dividend_overrides"])
            st.success("Gespeichert")
            st.session_state["results"] = None
            st.experimental_rerun()

        if cancel_btn:
            st.experimental_rerun()
