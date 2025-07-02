import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

st.set_page_config(page_title="Dividendenrendite Dashboard", layout="wide")
st.title("Dividendenrendite Dashboard")

# Eingabefeld für Ticker/WKN/ISIN
default = "SAP.DE, ALV.DE, MSFT, AAPL"
user_input = st.text_input("Aktien-Ticker, WKN oder ISIN (Komma-getrennt):", default)

if st.button("Analyse starten"):
    tickers = [t.strip().upper() for t in user_input.split(",") if t.strip()]
    results = []
    now = datetime.datetime.now().strftime("%H:%M:%S")
    for identifier in tickers:
        try:
            stock = yf.Ticker(identifier)
            info = stock.info
            name = info.get('longName', identifier)
            price = info.get('regularMarketPrice', 0)
            dividend = info.get('trailingAnnualDividendRate', 0)
            dividend_yield = info.get('dividendYield', 0)
            # Sanity Check für dividend_yield
            if dividend_yield and dividend_yield > 1:
                dividend_yield = dividend_yield / 100
            if not dividend and dividend_yield and price:
                dividend = price * dividend_yield
            if dividend and price:
                rendite = (dividend / price) * 100
            else:
                rendite = 0
            results.append({
                "Unternehmen": name,
                "Ticker": identifier,
                "Kurs": price,
                "Jahresdividende": dividend,
                "Dividendenrendite (%)": rendite,
                "Stand": now
            })
        except Exception as e:
            results.append({
                "Unternehmen": f"Fehler bei {identifier}",
                "Ticker": identifier,
                "Kurs": "N/A",
                "Jahresdividende": "N/A",
                "Dividendenrendite (%)": "N/A",
                "Stand": now
            })
    df = pd.DataFrame(results)
    df = df.sort_values(by="Dividendenrendite (%)", ascending=False)
    st.dataframe(df.style.format({
        "Kurs": "{:,.2f}",
        "Jahresdividende": "{:,.2f}",
        "Dividendenrendite (%)": "{:.2f}"
    }))
