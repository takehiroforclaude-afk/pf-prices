# 市場の終値を Yahoo Finance から取り、data/prices.csv（日付×銘柄の終値）と data/latest.csv（直近の終値と前日比）を書く
# v3.3（2026-11-17）：Yahoo が一時的に行を落としても消えないよう、前回の prices.csv の値と重ねる（新しい値が優先。前回の値は、今回の取得が空のところだけ使う）
# v3.2（2026-11-16）：FRED の公開の画面からは GitHub で応答なし（6通りとも時間切れ）。FRED の API（登録キー）に切り替え。キー（GitHub の Secrets の FRED_API_KEY）が無いときは取りに行かず、すぐ飛ばす
# v3.1（2026-11-16）：FRED の取り方を3通りに増やし、結果を data/credit_status.txt に書く（失敗の理由を外から見るため）
# v3（2026-11-16）：信用の指標を追加。FRED の社債の上乗せ金利（ハイイールド・投資適格）を data/credit.csv に書き、latest.csv に足す。代わりの目安として HYG・LQD の価格も取る
# v2（2026-11-16）：米国5年金利（^FVX）を追加。財務省の国債金利（日次）を data/jgb.csv に書き、日本の2年・5年・10年の直近の値を latest.csv に足す
import sys, time, re, io, urllib.request, datetime as dt
import pandas as pd
import yfinance as yf

T = {
    "^GSPC": "S&P500", "^NDX": "NASDAQ100", "^SOX": "SOX", "^N225": "Nikkei225", "1306.T": "TOPIX_ETF_1306",
    "^TNX": "US10Y_yield", "^FVX": "US5Y_yield", "JPY=X": "USDJPY", "GC=F": "Gold_futures", "BTC-USD": "BTC", "CL=F": "WTI_futures", "^VIX": "VIX",
    "NVDA": "NVDA", "MSFT": "MSFT", "GOOGL": "GOOGL", "AMZN": "AMZN", "TSM": "TSMC_ADR", "PLTR": "PLTR", "SOFI": "SOFI", "MSTR": "MSTR",
    "LLY": "LLY", "MDLZ": "MDLZ", "PEP": "PEP", "KDP": "KDP", "BTI": "BTI", "XEL": "XEL", "EXC": "EXC", "TMUS": "TMUS", "PAYX": "PAYX", "LMT": "LMT",
    "VIST": "VIST", "GLDM": "GLDM", "ACWI": "ACWI_ETF", "QQQ": "QQQ", "SOXX": "SOXX",
    "CME": "CME", "AJG": "AJG", "ROP": "ROP", "HYG": "HYG_HighYield_ETF", "LQD": "LQD_IG_ETF",
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
try:                                # 前回の値で、今回の取得が空のところだけ埋める（同じ期間・同じ銘柄の中だけ）
    old = pd.read_csv("data/prices.csv", index_col=0)
    old.index = old.index.astype(str)
    old = old.reindex(columns=got)
    old = old[old.index >= C.index.min()]
    filled = int((C.isna() & old.reindex(index=C.index).notna()).sum().sum())
    C = C.combine_first(old)[got].sort_index()
    C.index.name = "date"
    print("filled from previous prices.csv:", filled)
except FileNotFoundError:
    pass
except Exception as e:
    print("merge with previous prices.csv skipped:", repr(e))
C.round(4).to_csv("data/prices.csv")

now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
rows = []
for s in got:
    x = C[s].dropna()
    if len(x) < 2:
        continue
    c, p = float(x.iloc[-1]), float(x.iloc[-2])
    rows.append({"symbol": s, "name": T[s], "date": x.index[-1], "close": round(c, 4), "prev_date": x.index[-2], "prev_close": round(p, 4),
                 "change_pct": round((c / p - 1) * 100, 2), "change_bp": round((c - p) * 100, 1) if s in ("^TNX", "^FVX") else "", "fetched_at_utc": now})

# ---- 財務省の国債金利（日次）。失敗しても株価のファイルは残す ----
MOF = ["https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv",   # 1974年〜前月末
       "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"]            # 当月
ERA = {"S": 1925, "H": 1988, "R": 2018}

def jdate(t):
    t = t.strip().strip('"')
    m = re.match(r"^([SHR])(\d+)\.(\d+)\.(\d+)$", t)
    if m:
        return dt.date(ERA[m.group(1)] + int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.match(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})$", t)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None

def parse_jgb(raw):
    txt = raw.decode("cp932", errors="replace")
    lines = txt.splitlines()
    hi = next(i for i, l in enumerate(lines) if "基準日" in l)
    head = [h.strip().strip('"') for h in lines[hi].split(",")]
    cols = ["JGB" + h.replace("年", "Y") for h in head[1:] if h]
    out = []
    for l in lines[hi + 1:]:
        f = l.split(",")
        d = jdate(f[0]) if f else None
        if d is None:
            continue
        v = []
        for x in f[1:1 + len(cols)]:
            try:
                v.append(float(x))
            except ValueError:
                v.append(float("nan"))
        v += [float("nan")] * (len(cols) - len(v))
        out.append([d.isoformat()] + v)
    return pd.DataFrame(out, columns=["date"] + cols).set_index("date")

try:
    parts = []
    for u in MOF:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (pf-prices relay)"})
        parts.append(parse_jgb(urllib.request.urlopen(req, timeout=60).read()))
        time.sleep(2)
    J = pd.concat(parts)
    J = J[~J.index.duplicated(keep="last")].sort_index()
    J = J[J.index >= "2000-01-01"]
    J.round(4).to_csv("data/jgb.csv")
    print("jgb rows", len(J), "last", J.index[-1], "cols", list(J.columns))
    for col, name in (("JGB2Y", "JP2Y_yield_MOF"), ("JGB5Y", "JP5Y_yield_MOF"), ("JGB10Y", "JP10Y_yield_MOF")):
        if col in J.columns:
            x = J[col].dropna()
            if len(x) >= 2:
                c, p = float(x.iloc[-1]), float(x.iloc[-2])
                rows.append({"symbol": col, "name": name, "date": x.index[-1], "close": round(c, 4), "prev_date": x.index[-2], "prev_close": round(p, 4),
                             "change_pct": "", "change_bp": round((c - p) * 100, 1), "fetched_at_utc": now})
except Exception as e:
    print("JGB fetch failed (prices are kept):", repr(e))

# ---- FRED の社債の上乗せ金利（日次、%）。API の登録キーがあるときだけ取る。失敗しても他のファイルは残す。結果は data/credit_status.txt ----
import os, json
FRED = {"BAMLH0A0HYM2": "US_HY_OAS", "BAMLC0A0CM": "US_IG_OAS"}
KEY = os.environ.get("FRED_API_KEY", "").strip()
log = []

def fred_one(sid):
    u = ("https://api.stlouisfed.org/fred/series/observations?series_id=" + sid + "&api_key=" + KEY +
         "&file_type=json&observation_start=2000-01-01")
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "pf-prices relay"}), timeout=30).read())
        x = pd.Series({o["date"]: (float(o["value"]) if o["value"] not in (".", "") else float("nan")) for o in d["observations"]}, name=sid)
        if x.dropna().empty:
            raise ValueError("no numeric rows")
        log.append(f"{sid} api ok rows={len(x)} last={x.dropna().index[-1]}")
        return x
    except Exception as e:
        log.append(f"{sid} api failed: " + repr(e)[:200].replace(KEY, "***") if KEY else repr(e)[:200])
        return None

if not KEY:
    log.append("FRED skipped: no FRED_API_KEY")
else:
    try:
        parts = [x for x in (fred_one(sid) for sid in FRED) if x is not None]
        if parts:
            K = pd.concat(parts, axis=1).sort_index()
            K.index.name = "date"
            K.round(4).to_csv("data/credit.csv")
            for sid, name in FRED.items():
                if sid not in K.columns:
                    continue
                x = K[sid].dropna()
                if len(x) >= 2:
                    c, p = float(x.iloc[-1]), float(x.iloc[-2])
                    rows.append({"symbol": sid, "name": name, "date": x.index[-1], "close": round(c, 4), "prev_date": x.index[-2], "prev_close": round(p, 4),
                                 "change_pct": "", "change_bp": round((c - p) * 100, 1), "fetched_at_utc": now})
    except Exception as e:
        log.append("FRED block failed: " + repr(e)[:200].replace(KEY, "***"))
open("data/credit_status.txt", "w", encoding="utf-8").write(now + " UTC\n" + "\n".join(log) + "\n")
print("\n".join(log))

pd.DataFrame(rows).to_csv("data/latest.csv", index=False)
print("wrote", len(rows), "rows at", now)
