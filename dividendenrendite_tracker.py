import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yfinance as yf
import pandas as pd
import threading
import datetime
import os
import json

CONFIG_FILE = "config.txt"
OVERRIDE_FILE = "dividend_overrides.json"
DEFAULT_TICKERS = "VOW3.DE, INGA.AS, LHA.DE, NEDAP.AS, VICI, KMI, O, ENB, ECMPA.AS, NCCB.ST, SAN, COLD, VEI.OL, ALV.DE, DG.PA, SCMN.SW, IMB.L, ITX.MC, NESN.SW, SAN.PA"

def load_defaults():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("# Tragen Sie hier Ihre Standard-Aktien-Ticker ein (mit Komma getrennt).\n")
            f.write(DEFAULT_TICKERS)
        return DEFAULT_TICKERS
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                if cleaned and not cleaned.startswith('#'):
                    return cleaned
        return DEFAULT_TICKERS
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        return DEFAULT_TICKERS

def get_fx_rate_yahoo(src="USD", dst="EUR"):
    if src == dst:
        return 1.0
    try:
        pair = f"{src}{dst}=X"
        fx = yf.Ticker(pair)
        fxdata = fx.history(period="1d")
        rate = fxdata["Close"].iloc[-1]
        return float(rate)
    except Exception as e:
        print(f"Wechselkurs-Fehler {src}->{dst}: {e}")
        return 1.0

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

class ManualDividendDialog(tk.Toplevel):
    def __init__(self, parent, company_ticker_map, overrides, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.title("Dividende manuell erfassen")
        self.geometry("400x180")
        self.grab_set()
        self.resizable(False, False)
        self.company_ticker_map = company_ticker_map
        self.overrides = overrides
        self.result = None

        label = ttk.Label(self, text="Unternehmen auswählen:")
        label.pack(pady=(15, 2))

        self.selected_company = tk.StringVar()
        company_names = sorted(list(company_ticker_map.keys()))
        self.dropdown = ttk.Combobox(self, textvariable=self.selected_company, values=company_names, state="readonly")
        self.dropdown.pack(pady=2)
        self.dropdown.current(0)

        value_label = ttk.Label(self, text="Dividende in Euro (leer = Override löschen):")
        value_label.pack(pady=(10, 2))
        self.value_entry = ttk.Entry(self)
        ticker = company_ticker_map[self.dropdown.get()]
        if ticker in overrides:
            self.value_entry.insert(0, str(overrides[ticker]))
        self.value_entry.pack(pady=2)

        self.dropdown.bind("<<ComboboxSelected>>", self.on_company_change)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ok_button = ttk.Button(button_frame, text="OK", command=self.on_ok)
        ok_button.pack(side="left", padx=5)
        cancel_button = ttk.Button(button_frame, text="Abbrechen", command=self.destroy)
        cancel_button.pack(side="left", padx=5)

    def on_company_change(self, event=None):
        company = self.selected_company.get()
        ticker = self.company_ticker_map[company]
        self.value_entry.delete(0, tk.END)
        if ticker in self.overrides:
            self.value_entry.insert(0, str(self.overrides[ticker]))

    def on_ok(self):
        company = self.selected_company.get()
        ticker = self.company_ticker_map[company]
        value = self.value_entry.get().replace(",", ".").strip()
        self.result = (ticker, value)
        self.destroy()

class DividendTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dividendenrendite Tracker (Override per Button, Dropdown Unternehmen)")
        self.geometry("1250x650")

        self.ticker_frame = ttk.LabelFrame(self, text="Aktien-Ticker (kommagetrennt, z.B. SAP.DE, MSFT, O, IMB.L)")
        self.ticker_frame.pack(padx=10, pady=10, fill="x")
        self.ticker_input = ttk.Entry(self.ticker_frame, font=("Helvetica", 12))
        self.ticker_input.pack(pady=5, padx=10, fill="x")
        self.ticker_input.insert(0, load_defaults())

        self.button_frame = ttk.Frame(self)
        self.button_frame.pack(padx=10, pady=5, fill="x")
        # Links: Analyse starten
        self.analyze_button = ttk.Button(self.button_frame, text="Analyse starten", command=self.start_analysis_thread)
        self.analyze_button.pack(side="left", padx=5)
        # Rechts: Dividende manuell erfassen, dann alle löschen
        self.override_button = ttk.Button(self.button_frame, text="Dividende manuell erfassen", command=self.set_manual_dividend)
        self.override_button.pack(side="right", padx=5)
        self.clear_overrides_button = ttk.Button(self.button_frame, text="Alle manuellen Dividenden löschen", command=self.clear_all_overrides)
        self.clear_overrides_button.pack(side="right", padx=5)

        self.progress_bar = ttk.Progressbar(self, orient="horizontal", length=100, mode="determinate")
        self.progress_bar.pack(pady=5, padx=10, fill="x")

        self.tree_frame = ttk.LabelFrame(self, text="Ergebnisse (manuelle Dividende = dezent markiert)")
        self.tree_frame.pack(padx=10, pady=10, expand=True, fill="both")

        self.columns = ("Unternehmen", "Ticker", "Kurs (€)", "Jahresdividende (€)", "Dividendenrendite (%)", "Stand")
        self.tree = ttk.Treeview(self.tree_frame, columns=self.columns, show="headings", selectmode="browse")
        numeric_columns = ["Kurs (€)", "Jahresdividende (€)", "Dividendenrendite (%)"]
        for col in self.columns:
            self.tree.heading(col, text=col)
            if col in numeric_columns:
                anchor = 'e'
            elif col == "Stand":
                anchor = 'center'
            else:
                anchor = 'w'
            self.tree.column(col, width=150, anchor=anchor)
        self.tree.column("Stand", width=100)
        self.tree.pack(expand=True, fill="both")
        self.results_df = None
        self.dividend_overrides = load_overrides()

        # Dezente Markierung für Overrides
        self.tree.tag_configure("override", background="#2A3B4D", foreground="#F9F9F9")

    def clear_all_overrides(self):
        if os.path.exists(OVERRIDE_FILE):
            os.remove(OVERRIDE_FILE)
        self.dividend_overrides = {}
        self.start_analysis_thread()

    def set_manual_dividend(self):
        if self.results_df is None or self.results_df.empty:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Analyse starten.")
            return
        # Mapping Unternehmen → Ticker
        company_ticker_map = {row["Unternehmen"]: row["Ticker"] for _, row in self.results_df.iterrows()}
        dialog = ManualDividendDialog(self, company_ticker_map, self.dividend_overrides)
        self.wait_window(dialog)
        if dialog.result:
            ticker, value = dialog.result
            if value == "":
                if ticker in self.dividend_overrides:
                    del self.dividend_overrides[ticker]
            else:
                try:
                    self.dividend_overrides[ticker] = float(value)
                except Exception:
                    messagebox.showerror("Fehler", f"Ungültiger Wert für {ticker}: {value}")
                    return
            save_overrides(self.dividend_overrides)
            self.start_analysis_thread()

    def start_analysis_thread(self):
        self.analyze_button.config(state="disabled")
        for i in self.tree.get_children():
            self.tree.delete(i)
        identifiers = [identifier.strip().upper() for identifier in self.ticker_input.get().split(',') if identifier.strip()]
        if not identifiers:
            messagebox.showwarning("Eingabe fehlt", "Bitte geben Sie mindestens einen Ticker ein (z.B. SAP.DE, MSFT, O, IMB.L).")
            self.analyze_button.config(state="normal")
            return
        for ticker in identifiers:
            if len(ticker) == 6 and ticker.isalnum() and '.' not in ticker:
                messagebox.showerror("Ungültige Eingabe", f"'{ticker}' sieht wie eine WKN aus. Bitte geben Sie NUR Ticker ein (z.B. SAP.DE, MSFT, O, IMB.L).")
                self.analyze_button.config(state="normal")
                return
            if len(ticker) == 12 and ticker[:2].isalpha() and ticker[2:].isalnum():
                messagebox.showerror("Ungültige Eingabe", f"'{ticker}' sieht wie eine ISIN aus. Bitte geben Sie NUR Ticker ein (z.B. SAP.DE, MSFT, O, IMB.L).")
                self.analyze_button.config(state="normal")
                return
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(identifiers)
        thread = threading.Thread(target=self.fetch_data, args=(identifiers,))
        thread.start()

    def fetch_data(self, identifiers):
        results = []
        for i, ticker in enumerate(identifiers):
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
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
                display_symbol = "€"
                price_eur = round(current_price * fx_rate, 2) if current_price else None

                # Dividende: Erst Override (in Euro, direkt verwenden!), dann Yahoo, dann Historie
                annual_dividend = self.dividend_overrides.get(ticker)
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
                    dividend_str = f"{display_symbol} {dividend_eur:,.2f}"
                    yield_str = f"{yield_percent:.2f}"
                else:
                    dividend_str = "N/A"
                    yield_str = "N/A"
                price_str = f"{display_symbol} {price_eur:,.2f}" if price_eur else "N/A"
                results.append({
                    "Unternehmen": company_name,
                    "Ticker": resolved_ticker,
                    "Kurs (€)": price_str,
                    "Jahresdividende (€)": dividend_str,
                    "Dividendenrendite (%)": yield_str,
                    "Stand": timestamp
                })
            except Exception as e:
                print(f"Fehler bei der Verarbeitung von '{ticker}': {e}")
                results.append({
                    "Unternehmen": f"Fehler bei '{ticker}'",
                    "Ticker": ticker,
                    "Kurs (€)": "N/A",
                    "Jahresdividende (€)": "N/A",
                    "Dividendenrendite (%)": "N/A",
                    "Stand": timestamp
                })
            self.progress_bar["value"] = i + 1
            self.update_idletasks()
        self.results_df = pd.DataFrame(results)
        self.display_results()
        self.analyze_button.config(state="normal")

    def display_results(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        if self.results_df is not None and not self.results_df.empty:
            df_sorted = self.results_df.copy()
            df_sorted['numeric_yield'] = pd.to_numeric(df_sorted['Dividendenrendite (%)'], errors='coerce').fillna(0)
            df_sorted = df_sorted.sort_values(by="numeric_yield", ascending=False)
            for idx, row in df_sorted.iterrows():
                ticker = row["Ticker"]
                is_override = ticker in self.dividend_overrides
                tags = ("override",) if is_override else ()
                values = [row[col] for col in self.columns]
                self.tree.insert("", "end", values=values, tags=tags)
        # Dezente Markierung für Overrides
        self.tree.tag_configure("override", background="#2A3B4D", foreground="#F9F9F9")

    def sort_by_column(self, col, reverse):
        if self.results_df is None:
            return
        def get_sort_key(value_str):
            try:
                return float(''.join(c for c in value_str if c.isdigit() or c in '.,-').replace(',', '.'))
            except:
                return -1
        l = sorted([(get_sort_key(self.tree.set(k, col)), k) for k in self.tree.get_children('')], key=lambda t: t[0], reverse=reverse)
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda _col=col: self.sort_by_column(_col, not reverse))

    def export_to_csv(self):
        if self.results_df is None or self.results_df.empty:
            messagebox.showinfo("Keine Daten", "Es gibt keine Daten zum Exportieren.")
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV-Dateien", "*.csv")], initialfile=f"dividendenrendite_{now}.csv")
        if filepath:
            export_df = self.results_df.copy()
            if 'numeric_yield' in export_df.columns:
                export_df = export_df.drop(columns=['numeric_yield'])
            export_df.to_csv(filepath, index=False, sep=';', decimal=',')
            messagebox.showinfo("Export erfolgreich", f"Daten wurden in {filepath} gespeichert.")

if __name__ == "__main__":
    app = DividendTrackerApp()
    app.mainloop()
