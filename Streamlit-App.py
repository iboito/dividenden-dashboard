import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

OVERRIDE_FILE = "dividend_overrides.json"
DEFAULT_TICKERS = "VOW3.DE, INGA.AS, LHA.DE, NEDAP.AS, VICI, KMI, O, ENB, ECMPA.AS, NCCB.ST, SAN, COLD, VEI.OL, ALV.DE, DG.PA, SCMN.SW, IMB.L, ITX.MC, NESN.SW, SAN.PA"

def load_overrides():
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_overrides(overrides):
    with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)

def get_fx_rate_yahoo(src="USD", dst="EUR"):
    if src == dst:
        return 1.0
    try:
        pair = f"{src}{dst}=X"
        fx = yf.Ticker(pair)
        fxdata = fx.history(period="1d")
        rate = fxdata["Close"].iloc[-1]
        return float(rate)
    except Exception:
        return 1.0

st.set_page_config(page_title="Dividendenrendite Tracker", layout="wide")
st.title("Dividendenrendite Tracker (Streamlit-Version)")

# Session State für Overrides und Formularsteuerung
if "dividend_overrides" not in st.session_state:
    st.session_state["dividend_overrides"] = load_overrides()
if "show_override_form" not in st.session_state:
    st.session_state["show_override_form"] = False

# Eingabe der Ticker
tickers_input = st.text_input(
    "Aktien-Ticker (kommagetrennt, z.B. SAP.DE, MSFT, O, IMB.L)",
    value=DEFAULT_TICKERS
)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

# Button-Leiste: Analyse ganz links, dann rechts Override und ganz rechts Löschen
col_left, col_spacer, col_override, col_delete = st.columns([2, 10, 2, 2])

with col_left:
    analyse_clicked = st.button("Analyse starten", use_container_width=True)

with col_override:
    override_clicked = st.button("Dividende manuell erfassen", use_container_width=True)

with col_delete:
    delete_clicked = st.button("Alle manuellen Dividenden löschen", use_container_width=True)

if delete_clicked:
    st.session_state["dividend_overrides"] = {}
    if os.path.exists(OVERRIDE_FILE):
        os.remove(OVERRIDE_FILE)
    st.session_state["show_override_form"] = False
    st.experimental_rerun()

if override_clicked:
    st.session_state["show_override_form"] = True

if analyse_clicked or "results" not in st.session_state:
    results = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            company_name = info.get('longName') or info.get('shortName') or info.get('symbol') or ticker
            resolved_ticker = info.get('symbol', ticker)
            current_price = info.get('regularMarketPrice', info.get('currentPrice', 0))
            currency_code = info.get('currency', 'USD')
            # UK-Fix: Kurs und Dividende in Pence → Pfund
            if ticker.endswith('.L') and currency_code == "GBp":
                if current_price:
                    current_price = current_price / 100
                currency_code = "GBP"
            fx_rate = get_fx_rate_yahoo(currency_code, "EUR") if currency_code != "EUR" else 1.0
            price_eur = round(current_price * fx_rate, 2) if current_price else None

            # Dividende: Erst Override (in Euro, direkt verwenden!), dann Yahoo, dann Historie
            overrides = st.session_state["dividend_overrides"]
            annual_dividend = overrides.get(ticker)
            if annual_dividend is not None:
                dividend_eur = annual_dividend
            else:
                annual_dividend = None
                direct_dividend = info.get('trailingAnnualDividendRate')
                if direct_dividend is not None and direct_dividend > 0:
                    annual_dividend = direct_dividend
                if ticker.endswith('.L') and info.get('currency', '') == "GBp" and annual_dividend:
                    annual_dividend = annual_dividend / 100
                if annual_dividend is None or annual_dividend == 0:
                    dividend_yield = info.get('dividendYield')
                    if dividend_yield is not None and dividend_yield > 0 and current_price and current_price > 0:
                        if dividend_yield > 1:
                            dividend_yield = dividend_yield / 100
                        annual_dividend = current_price * dividend_yield
                if (annual_dividend is None or annual_dividend == 0):
                    try:
                        history = stock.history(period="1y", actions=True, auto_adjust=True)
                        if not history.empty and 'Dividends' in history.columns:
                            dividends_last_year = history['Dividends'].sum()
                            if ticker.endswith('.L') and info.get('currency', '') == "GBp":
                                dividends_last_year = dividends_last_year / 100
                            if dividends_last_year > 0:
                                annual_dividend = dividends_last_year
                    except Exception:
                        pass
                dividend_eur = round(annual_dividend * fx_rate, 2) if annual_dividend else None

            dividend_found = dividend_eur is not None and dividend_eur > 0
            if dividend_found and price_eur and price_eur > 0:
                yield_percent = (dividend_eur / price_eur) * 100
                dividend_str = f"€ {dividend_eur:,.2f}"
                yield_str = f"{yield_percent:.2f}"
            else:
                dividend_str = "N/A"
                yield_str = "N/A"
            price_str = f"€ {price_eur:,.2f}" if price_eur else "N/A"
            results.append({
                "Unternehmen": company_name,
                "Ticker": resolved_ticker,
                "Kurs (€)": price_str,
                "Jahresdividende (€)": dividend_str,
                "Dividendenrendite (%)": yield_str,
            })
        except Exception as e:
            results.append({
                "Unternehmen": f"Fehler bei '{ticker}'",
                "Ticker": ticker,
                "Kurs (€)": "N/A",
                "Jahresdividende (€)": "N/A",
                "Dividendenrendite (%)": "N/A"
            })
    st.session_state["results"] = pd.DataFrame(results)

# Ergebnisse anzeigen
if "results" in st.session_state and st.session_state["results"] is not None:
    df = st.session_state["results"].copy()
    # Markiere überschrieben Werte
    overrides = st.session_state["dividend_overrides"]
    override_tickers = set(overrides.keys())
    highlight = []
    for idx, row in df.iterrows():
        if row["Ticker"] in override_tickers:
            highlight.append(True)
        else:
            highlight.append(False)
    def highlight_overrides(val, is_override):
        return 'background-color: #2A3B4D; color: #F9F9F9' if is_override else ''
    st.dataframe(
        df.style.apply(lambda x: [highlight_overrides(v, override) for v, override in zip(x, highlight)], axis=1),
        use_container_width=True
    )

    # Manuelle Dividenden-Overrides: Dialog per Button, bleibt offen bis Speichern/Abbruch
    if st.session_state["show_override_form"]:
        company_ticker_map = {row["Unternehmen"]: row["Ticker"] for _, row in df.iterrows()}
        company_names = sorted(company_ticker_map.keys())
        with st.form("override_form", clear_on_submit=True):
            selected_company = st.selectbox("Unternehmen auswählen", company_names)
            ticker = company_ticker_map[selected_company]
            curr_override = overrides.get(ticker, "")
            value = st.text_input("Dividende in Euro (leer = Override löschen)", value=str(curr_override) if curr_override != "" else "")
            col_save, col_cancel = st.columns([1,1])
            submitted = col_save.form_submit_button("Speichern")
            cancelled = col_cancel.form_submit_button("Abbrechen")
            if submitted:
                value = value.replace(",", ".").strip()
                if value == "":
                    if ticker in overrides:
                        del overrides[ticker]
                else:
                    try:
                        overrides[ticker] = float(value)
                    except Exception:
                        st.error(f"Ungültiger Wert für {selected_company}: {value}")
                        st.stop()
                save_overrides(overrides)
                st.session_state["dividend_overrides"] = overrides
                st.session_state["show_override_form"] = False
                st.experimental_rerun()
            if cancelled:
                st.session_state["show_override_form"] = False
                st.experimental_rerun()
