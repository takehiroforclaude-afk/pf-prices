# 市場の終値を Yahoo Finance から取り、data/prices.csv（日付×銘柄の終値）と data/latest.csv（直近の終値と前日比）を書く
import sys, time, datetime as dt
import pandas as pd
import yfinance as yf

T = {
    "^GSPC": "S&P500", "^NDX": "NASDAQ100", "^SOX": "SOX", "^N225": "Nikkei225", "1306.T": "TOPIX_ETF_1306",
    "^TNX": "US10Y_yield", "JPY=X": "USDJPY", "GC=F": "Gold_futures", "BTC-USD": "BTC", "CL=F": "WTI_futures", "^VIX": "VIX",
    "NVDA": "NVDA", "MSFT": "MSFT", "GOOGL": "GOOGL", "AMZN": "AMZN", "TSM": "TSMC_ADR", "PLTR": "PLTR", "SOFI": "SOFI", "MSTR": "MSTR",
    "LLY": "LLY", "MDLZ": "MDLZ", "PEP": "PEP", "KDP": "KDP", "BTI": "BTI", "XEL": "XEL", "EXC": "EXC", "TMUS": "TMUS", "PAYX": "PAYX", "LMT": "LMT",
    "VIST": "VIST", "GLDM": "GLDM", "ACWI": "ACWI_ETF", "QQQ": "QQQ", "SOXX": "SOXX",
    "2914.T": "JT", "9432.T": "NTT", "2503.T": "KirinHD", "7203.T": "Toyota", "8306.T": "MUFG", "8316.T": "SMFG", "8411.T": "Mizuho",
    "3350.T": "Metaplanet", "8035.T": "TokyoElectron", "6857.T": "Advantest", "1489.T": "NF_Nikkei_HighDiv50", "1367.T": "TOPIX_Lev2x",
}

def closes(symbols):
    for i in range(3):
        try:
            df = yf.download(symbols, period="1y", interval="1d", auto_adjust=False, progress=False, threads=False)
            c = df["Close"]
            if isinstance(c, pd.Series):
                c = c.to_frame(symbols[0])
            c = c.dropna(how="all")
            if len(c):
                return c
        except Exception as e:
            print("retry", i, repr(e))
        time.sleep(20)
    return pd.DataFrame()

syms = list(T)
C = closes(syms)
for s in syms:                      # まとめて取れなかった銘柄は1本ずつ取り直す
    if s not in C.columns or C[s].dropna().empty:
        one = closes([s])
        if len(one):
            C = C.drop(columns=[s], errors="ignore").join(one[[s]], how="outer")
        time.sleep(2)
got = [s for s in syms if s in C.columns and not C[s].dropna().empty]
print("got", len(got), "of", len(syms), "missing", [s for s in syms if s not in got])
if len(got) < len(syms) // 2:
    print("too few symbols; keep the previous files")
    sys.exit(1)

C = C[got].sort_index()
C.index = pd.to_datetime(C.index).strftime("%Y-%m-%d")
C.index.name = "date"
C.round(4).to_csv("data/prices.csv")

now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
rows = []
for s in got:
    x = C[s].dropna()
    if len(x) < 2:
        continue
    c, p = float(x.iloc[-1]), float(x.iloc[-2])
    rows.append({"symbol": s, "name": T[s], "date": x.index[-1], "close": round(c, 4), "prev_date": x.index[-2], "prev_close": round(p, 4),
                 "change_pct": round((c / p - 1) * 100, 2), "change_bp": round((c - p) * 100, 1) if s == "^TNX" else "", "fetched_at_utc": now})
pd.DataFrame(rows).to_csv("data/latest.csv", index=False)
print("wrote", len(rows), "rows at", now)
