"""エントリータイミング徹底比較（1時間足で約定・決済を再現）
シグナル: 本番と同じ 4h flip_dst（backtest.py の指標を使用）
約定・決済: 1h足。SL優先の保守的判定、手数料は決済種別ごと（TP1=メイカー、SL/トレール=テイカー＋滑り）、金利0.04%/日
ポートフォリオ: 同時2件（待ち注文も枠を使う）、1件=資金×0.6、複利
python3 -I entry_1h.py <backtest_dir>
"""
import sys, os, pickle, math
sys.path.insert(0, sys.argv[1])
import numpy as np
import pandas as pd
import backtest as bt

HERE = os.path.dirname(os.path.abspath(__file__))
H = pd.Timedelta(hours=1)
TAKER = {"BTC": 0.0010, "ETH": 0.0012, "SOL": 0.0012}
MAKER = {"BTC": 0.0, "ETH": -0.0002, "SOL": -0.0002}
SLIP_MKT = 0.001     # 成行エントリーの滑り
SLIP_STOP = 0.0005   # 逆指値決済の滑り
FILL_EPS = 0.0005    # 指値は0.05%突き抜けで約定とみなす
INTEREST_DAY = 0.0004
EQ_RATIO, MAXPOS, INIT = 0.6, 2, 10000.0
TP1, SL, TRAIL = bt.TP1_MULT, bt.SL_MULT, bt.TRAIL_MULT


def cache(name, fn):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        return pickle.load(open(p, "rb"))
    v = fn(); pickle.dump(v, open(p, "wb")); return v


def load():
    raw4 = cache("klines5y.pkl", lambda: {c: bt.fetch_klines(s, total=5*365*6) for c, s in bt.COINS.items()})
    raw1 = cache("klines5y_1h.pkl", lambda: {c: bt.fetch_klines(s, total=5*365*24+24*30, interval="1h") for c, s in bt.COINS.items()})
    d4 = {c: bt.add_indicators(raw4[c].reset_index(drop=True)) for c in bt.COINS}
    h1 = {}
    for c, df in raw1.items():
        df = df.reset_index(drop=True)
        d = dict(t=pd.DatetimeIndex(df["open_time"]), o=df["open"].values.astype(float), h=df["high"].values.astype(float),
                 l=df["low"].values.astype(float), c=df["close"].values.astype(float))
        # 1h RSI14
        d["rsi"] = bt.calc_rsi(df["close"].astype(float), 14).values
        # 各1h足の時点で確定済みの直近4h足のST方向
        s4 = d4[c].set_index("open_time")["st_dir"]
        last_closed = (df["open_time"].dt.floor("4h") - pd.Timedelta(hours=4))
        d["st4"] = last_closed.map(s4).values
        d["idx"] = {t: i for i, t in enumerate(df["open_time"])}
        h1[c] = d
    return d4, h1


def signals(d4):
    btc = d4["BTC"].set_index("open_time")
    out = []
    for coin, df in d4.items():
        for i in range(bt.EMA_PERIOD + bt.VOL_PERIOD + 5, len(df) - 1):   # 最終足(未確定)は除外
            r = df.iloc[i]; ts = r["open_time"]
            if ts not in btc.index:
                continue
            d = "long" if btc.at[ts, "close"] >= btc.at[ts, "ema200"] else "short"
            if d == "long" and not (r["close"] >= r["ema200"] and r["st_flip_green"] and r["st_dir_slow"] == 1):
                continue
            if d == "short" and not (r["close"] < r["ema200"] and r["st_flip_red"] and r["st_dir_slow"] == -1):
                continue
            if r["volume"] <= r["vol_avg20"]:
                continue
            out.append(dict(coin=coin, ts=ts, t_close=ts + pd.Timedelta(hours=4), close=float(r["close"]),
                            open=float(r["open"]), atr=float(r["atr"]), dir=d,
                            body=abs(r["close"] - r["open"]) / r["atr"]))
    out.sort(key=lambda s: s["t_close"])
    return out


# ── エントリー方式 ─────────────────────────────────────────────
# 戻り値: list of (fill_idx, price, open_fee, intrabar)  intrabar=True なら約定足はSLのみ判定
#         空リスト=見送り。wait_end_idx も返す（枠の占有終了の目安）
def entry(sig, h, v):
    s = h["idx"].get(sig["t_close"])
    if s is None:
        return [], None
    d, coin = sig["dir"], sig["coin"]
    sgn = 1 if d == "long" else -1
    want = 1 if d == "long" else -1
    n = len(h["t"])

    def mkt(i):
        return (i, h["o"][i] * (1 + sgn * SLIP_MKT), TAKER[coin], False)

    kind = v["kind"]
    if v.get("cond") is not None and sig["body"] < v["cond"]:
        return [mkt(s)], s
    if kind == "market":
        return [mkt(s)], s
    if kind == "delay":
        i = s + v["T"]
        if i >= n: return [], None
        if v.get("cancel_flip", True) and h["st4"][i] != want: return [], i
        return [mkt(i)], i

    def limit_fill(L, T, fb, start=s):
        for i in range(start, min(start + T, n)):
            if v.get("cancel_flip", True) and h["st4"][i] != want:
                return None, i
            if (d == "short" and h["h"][i] >= L * (1 + FILL_EPS)) or (d == "long" and h["l"][i] <= L * (1 - FILL_EPS)):
                return (i, L, MAKER[coin], True), i
        e = start + T
        if e >= n: return None, None
        if fb == "market" and h["st4"][e] == want:
            return mkt(e), e
        return None, e

    if kind in ("atr", "body", "fib_sl"):
        if kind == "atr":
            L = sig["close"] - sgn * v["k"] * sig["atr"]
        else:
            L = sig["close"] - sgn * v["k"] * abs(sig["close"] - sig["open"])
        f, e = limit_fill(L, v["T"], v.get("fb", "market"))
        return ([f] if f else []), e
    if kind == "oco":   # 戻り指値 or 順行m×ATRで追撃（先に来た方）
        L = sig["close"] - sgn * v["k"] * sig["atr"]
        S = sig["close"] + sgn * v["m"] * sig["atr"]
        for i in range(s, min(s + v["T"], n)):
            if h["st4"][i] != want:
                return [], i
            hitL = (d == "short" and h["h"][i] >= L * (1 + FILL_EPS)) or (d == "long" and h["l"][i] <= L * (1 - FILL_EPS))
            hitS = (d == "short" and h["l"][i] <= S) or (d == "long" and h["h"][i] >= S)
            if hitS:   # 同じ足で両方なら不利な追撃側を採用（保守的）
                px = min(S, h["o"][i]) if d == "short" else max(S, h["o"][i])
                return [(i, px * (1 + sgn * SLIP_STOP), TAKER[coin], True)], i
            if hitL:
                return [(i, L, MAKER[coin], True)], i
        e = s + v["T"]
        if e >= n: return [], None
        return ([mkt(e)] if v.get("fb", "market") == "market" and h["st4"][e] == want else []), e
    if kind == "split":   # 半分成行＋半分指値
        L = sig["close"] - sgn * v["k"] * sig["atr"]
        f, e = limit_fill(L, v["T"], v.get("fb", "cancel"))
        return [mkt(s)] + ([f] if f else []), e
    if kind == "ladder":  # 2段の指値（各半分）
        fills, e_max = [], s
        for k in v["ks"]:
            L = sig["close"] - sgn * k * sig["atr"]
            f, e = limit_fill(L, v["T"], v.get("fb", "market"))
            if f: fills.append(f)
            e_max = max(e_max, e or s)
        return fills, e_max
    if kind == "rsi1h":   # 1h RSIが行き過ぎなら戻るまで待つ
        lo, hi = v["lvl"]
        def extended(i):
            return (d == "short" and h["rsi"][i - 1] < lo) or (d == "long" and h["rsi"][i - 1] > 100 - lo)
        if not extended(s):
            return [mkt(s)], s
        for i in range(s + 1, min(s + v["T"], n)):
            if h["st4"][i] != want: return [], i
            if (d == "short" and h["rsi"][i - 1] >= hi) or (d == "long" and h["rsi"][i - 1] <= 100 - hi):
                return [mkt(i)], i
        e = s + v["T"]
        if e >= n: return [], None
        return ([mkt(e)] if v.get("fb", "market") == "market" and h["st4"][e] == want else []), e
    if kind == "reclaim":  # 1hで逆行足が出た後、トレンド方向の足で確定したら成行
        seen_counter = False
        for i in range(s, min(s + v["T"], n)):
            if h["st4"][i] != want: return [], i
            up = h["c"][i] > h["o"][i]
            if (d == "short" and up) or (d == "long" and not up):
                seen_counter = True
            elif seen_counter and i + 1 < n:
                return [mkt(i + 1)], i + 1
        e = s + v["T"]
        if e >= n: return [], None
        return ([mkt(e)] if h["st4"][e] == want else []), e
    raise ValueError(kind)


def manage(sig, h, fill, anchor=None):
    """1建玉を決済まで追う。戻り値: (投入額あたり損益率, 決済idx, 理由)"""
    i0, E, fee_open, intrabar = fill
    coin, d, atr = sig["coin"], sig["dir"], sig["atr"]
    base = anchor if anchor is not None else E
    long = d == "long"
    tp1 = base + atr * TP1 if long else base - atr * TP1
    sl = base - atr * SL if long else base + atr * SL
    r = -fee_open   # 投入額(=建玉notional)比の損益率
    n = len(h["t"])
    tp_done, ext, trail = False, None, None
    for i in range(i0, n):
        hi, lo = h["h"][i], h["l"][i]
        first = (i == i0)
        if not tp_done:
            if (long and lo <= sl) or (not long and hi >= sl):
                px = sl * (1 - SLIP_STOP) if long else sl * (1 + SLIP_STOP)
                r += ((px - E) if long else (E - px)) / E - TAKER[coin]
                r -= INTEREST_DAY * (i - i0 + 1) / 24
                return r, i, "SL"
            if first and intrabar:
                continue
            if (long and hi >= tp1) or (not long and lo <= tp1):
                r += 0.3 * (((tp1 - E) if long else (E - tp1)) / E - MAKER[coin])
                r -= INTEREST_DAY * (i - i0 + 1) / 24 * 0.3
                tp_done, ext = True, (hi if long else lo)
                trail = max(base, ext - atr * TRAIL) if long else min(base, ext + atr * TRAIL)
                i_tp = i
            continue
        # 決済判定は前の足までで決まったラインで（保守的）
        if (long and lo <= trail) or (not long and hi >= trail):
            px = trail * (1 - SLIP_STOP) if long else trail * (1 + SLIP_STOP)
            r += 0.7 * (((px - E) if long else (E - px)) / E - TAKER[coin])
            r -= INTEREST_DAY * (i - i0 + 1) / 24 * 0.7
            return r, i, "TRAIL"
        ext = max(ext, hi) if long else min(ext, lo)
        trail = max(trail, ext - atr * TRAIL) if long else min(trail, ext + atr * TRAIL)
    # 期末
    px = h["c"][-1]
    rem = 0.7 if tp_done else 1.0
    r += rem * (((px - E) if long else (E - px)) / E)
    return r, n - 1, "EOD"


def simulate(sigs, h1, v, t_from=None, t_to=None):
    """ポートフォリオ: 同時2件（待機中も枠を使う）、複利。"""
    # 各シグナルの結果を先に計算（サイズに依存しないので）
    pool, busy, eq = INIT, [], [INIT]   # busy: (end_time, coin, pnl_rate_list, invest)
    trades = []
    stat = {"filled": 0, "skipped": 0, "nofill": 0}
    events = []  # (time, pnl) 決済時に反映
    for sig in sigs:
        if t_from is not None and sig["t_close"] < t_from: continue
        if t_to is not None and sig["t_close"] >= t_to: continue
        h = h1[sig["coin"]]
        now = sig["t_close"]
        # now までに終わった玉を反映
        still = []
        for b in busy:
            if b[0] <= now:
                pool += b[2]; eq.append(pool)
            else:
                still.append(b)
        busy = still
        if len(busy) >= MAXPOS or any(b[1] == sig["coin"] for b in busy):
            stat["skipped"] += 1; continue
        fills, wait_end = entry(sig, h, v)
        invest = pool * EQ_RATIO
        if not fills:
            stat["nofill"] += 1
            end_t = pd.Timestamp(h["t"][wait_end]) if wait_end is not None else now
            busy.append((end_t, sig["coin"], 0.0))
            continue
        pnl, end_i = 0.0, 0
        rates = []
        ws = [1.0]
        if v["kind"] == "split":
            ws = [v.get("w", 0.5), 1 - v.get("w", 0.5)]
        elif v["kind"] == "ladder":
            ws = [0.5, 0.5]
        for f, share in zip(fills, ws):
            anchor = sig["close"] if v.get("anchor") else None
            r, ei, why = manage(sig, h, f, anchor)
            pnl += invest * share * r
            end_i = max(end_i, ei)
            rates.append(r)
        end_i = max(end_i, wait_end or 0)
        end_t = pd.Timestamp(h["t"][end_i])
        busy.append((end_t, sig["coin"], pnl))
        trades.append(dict(t=now, coin=sig["coin"], dir=sig["dir"], pnl=pnl, invest=invest,
                           rate=pnl / invest, n_fill=len(fills)))
        stat["filled"] += 1
    for b in sorted(busy):
        pool += b[2]; eq.append(pool)
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    loss = [-t["pnl"] for t in trades if t["pnl"] <= 0]
    peak, dd = eq[0], 0.0
    for x in eq:
        peak = max(peak, x); dd = max(dd, (peak - x) / peak * 100)
    return dict(n=len(trades), wr=len(wins) / max(1, len(trades)) * 100,
                pf=sum(wins) / sum(loss) if loss else 99, dd=dd, growth=(pool / INIT - 1) * 100,
                trades=trades, **stat)


def variants():
    V = [("成行(現行)", dict(kind="market"))]
    for T in (1, 2, 4, 8):
        V.append((f"遅延{T}h→成行", dict(kind="delay", T=T)))
    for k in (0.1, 0.2, 0.3, 0.4, 0.5):
        for T in (2, 4, 6, 8, 10, 12, 16):
            V.append((f"ATR{k}指値/{T}h/成行", dict(kind="atr", k=k, T=T, fb="market")))
    for k in (0.2, 0.3):
        for T in (4, 8, 12):
            V.append((f"ATR{k}指値/{T}h/見送り", dict(kind="atr", k=k, T=T, fb="cancel")))
    for k in (0.236, 0.382, 0.5, 0.618):
        for T in (4, 8, 12):
            V.append((f"実体{k}戻し/{T}h/成行", dict(kind="body", k=k, T=T, fb="market")))
    for k in (0.3, 0.5):
        for T in (8, 16):
            V.append((f"半分成行+半分ATR{k}/{T}h", dict(kind="split", k=k, T=T, fb="cancel")))
    for T in (8, 12):
        V.append((f"2段指値ATR0.2+0.4/{T}h", dict(kind="ladder", ks=(0.2, 0.4), T=T, fb="market")))
    for lo, hi in ((30, 40), (30, 45), (35, 45)):
        for T in (8, 12):
            V.append((f"1hRSI<{lo}なら≥{hi}待ち/{T}h", dict(kind="rsi1h", lvl=(lo, hi), T=T)))
    for T in (4, 8, 12):
        V.append((f"1h戻り後の再開足/{T}h", dict(kind="reclaim", T=T)))
    for c in (0.8, 1.2):
        V.append((f"ATR0.3/8h[実体≥{c}のみ待つ]", dict(kind="atr", k=0.3, T=8, fb="market", cond=c)))
    V.append(("ATR0.3/8h/SL基準=シグナル終値", dict(kind="atr", k=0.3, T=8, fb="market", anchor=True)))
    return V


def main():
    d4, h1 = load()
    sigs = signals(d4)
    t_end = max(pd.Timestamp(h1[c]["t"][-1]) for c in h1)
    starts = {y: t_end - pd.Timedelta(days=365 * y) for y in (2, 3, 4, 5)}
    split = pd.Timestamp("2024-01-01", tz="UTC")
    print(f"シグナル{len(sigs)}件  期間 {sigs[0]['t_close']} 〜 {t_end}")
    rows = []
    for name, v in variants():
        r = {"name": name}
        for y, st in starts.items():
            s = simulate(sigs, h1, v, t_from=st)
            r[y] = s
        r["IS"] = simulate(sigs, h1, v, t_from=starts[5], t_to=split)
        r["OOS"] = simulate(sigs, h1, v, t_from=split)
        yr = {}
        for t in r[5]["trades"]:
            yr[t["t"].year] = yr.get(t["t"].year, 0) + t["rate"] * 100
        r["yr"] = yr
        rows.append(r)
    pickle.dump([{k: (v if k not in (2, 3, 4, 5, "IS", "OOS") else {kk: vv for kk, vv in v.items() if kk != "trades"})
                  for k, v in r.items()} for r in rows], open(os.path.join(HERE, "entry_1h_result.pkl"), "wb"))
    b = rows[0]
    print(f"{'方式':<30}{'5y件':>5}{'勝率':>6}{'PF':>5}{'DD':>6}{'5y成長':>8}{'4y':>7}{'3y':>7}{'2y':>7}{'IS成長':>8}{'OOS成長':>8}{'OOS PF':>7}  年別勝ち")
    for r in rows:
        s5 = r[5]
        beat = sum(1 for y in b["yr"] if r["yr"].get(y, 0) >= b["yr"][y] - 1e-9)
        print(f"{r['name']:<30}{s5['n']:>5}{s5['wr']:>5.1f}%{s5['pf']:>5.2f}{s5['dd']:>5.1f}%{s5['growth']:>+7.1f}%"
              f"{r[4]['growth']:>+6.1f}%{r[3]['growth']:>+6.1f}%{r[2]['growth']:>+6.1f}%"
              f"{r['IS']['growth']:>+7.1f}%{r['OOS']['growth']:>+7.1f}%{r['OOS']['pf']:>7.2f}  {beat}/{len(b['yr'])}")


if __name__ == "__main__":
    main()
