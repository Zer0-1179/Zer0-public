"""Executorの見回り間隔（30分・15分・10分）の比較（2026-11-24）
シグナル: 本番と同じ 4h flip_dst（entry_1h.signals をそのまま使用）
約定・決済: 5分足で本番Executorの動きを再現する
  - エントリー: 4h足確定直後の5分足の始値で成行（滑り込み）
  - TP1(30%・指値)とSL(70%・逆指値)は板に置いた注文 → 5分足の高値・安値で即約定（同じ足で両方ならSL優先）
  - SLが先に約定 → 残り30%は「次の見回り」で成行決済（TP1指値はそれまで板に残る）
  - TP1が先に約定 → 「次の見回り」で旧SLを取り消し、建値にトレーリングSLを置く
      （その時点で建値を割っていれば60018で置けない → 成行決済。それまでは旧SLが70%を守る）
  - トレーリング中は見回りのたびに「その時の価格」（5分足の始値）が極値を更新したら
      新ライン=max(価格-ATR×0.75, 建値) に引き上げる（本番と同じく足の高値は使わない）
  - どの案でも4h境界の:00は見回る（Analyzerが毎回Executorを呼ぶため。2026-11-24 Fableレビュー）
  - トレーリングSLは逆指値 → 5分足の安値・高値で即約定（窓開けは始値で約定）
手数料・滑り・金利・ポートフォリオ（同時2件・1件=資金×0.6・複利）は entry_1h.py と同じ
python3 -I trail_interval.py <backtest_dir> <data_dir>
  data_dir に k4h.pkl と k5m_{BTC,ETH,SOL}.pkl（backtest.fetch_klines の戻り値）を置く
"""
import sys, os, pickle, math
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]
BT_DIR, DATA_DIR = sys.argv[1], sys.argv[2]
sys.path.insert(0, BT_DIR)
import numpy as np
import pandas as pd
import backtest as bt
import entry_1h as e1

TAKER, MAKER = e1.TAKER, e1.MAKER
SLIP_MKT, SLIP_STOP, INTEREST_DAY = e1.SLIP_MKT, e1.SLIP_STOP, e1.INTEREST_DAY
TP1, SL, TRAIL = bt.TP1_MULT, bt.SL_MULT, bt.TRAIL_MULT
BARS_DAY = 288

CHECKS = None   # 見回りする「時の中の分」の集合（simulate前に設定）


def load():
    raw4 = pickle.load(open(os.path.join(DATA_DIR, "k4h.pkl"), "rb"))
    d4 = {c: bt.add_indicators(raw4[c].reset_index(drop=True)) for c in bt.COINS}
    h5 = {}
    for c in bt.COINS:
        df = pickle.load(open(os.path.join(DATA_DIR, f"k5m_{c}.pkl"), "rb")).reset_index(drop=True)
        t = pd.DatetimeIndex(df["open_time"])
        h5[c] = dict(t=t, o=df["open"].values.astype(float), h=df["high"].values.astype(float),
                     l=df["low"].values.astype(float), c=df["close"].values.astype(float),
                     minute=t.minute.values, hour=t.hour.values, idx={ts: i for i, ts in enumerate(df["open_time"])})
        # 5分足の抜け（取引所の停止等）を確認用に数える
        gaps = int((df["open_time"].diff().dropna() != pd.Timedelta(minutes=5)).sum())
        print(f"{c}: 5分足 {len(t)}本 {t[0]} 〜 {t[-1]}  抜け{gaps}箇所", flush=True)
    return d4, h5


def manage(sig, h, fill, anchor=None):
    """1建玉を決済まで追う。戻り値: (建玉額あたり損益率, 決済idx, 理由)"""
    i0, E, fee_open, _ = fill
    coin, atr = sig["coin"], sig["atr"]
    long = sig["dir"] == "long"
    sgn = 1 if long else -1
    tp1 = E + sgn * atr * TP1
    sl = E - sgn * atr * SL
    n = len(h["o"])
    r = -fee_open
    phase = "active"
    trail = ext = None

    def pnl(px):
        return sgn * (px - E) / E

    def interest(i, share):
        return INTEREST_DAY * (i - i0 + 1) / BARS_DAY * share

    for i in range(i0, n):
        o, hi, lo = h["o"][i], h["h"][i], h["l"][i]
        # ── 見回り（足の始値の時点。エントリーした足では何もしない）──
        # 本番はAnalyzerが4h足の確定(:00)ごとにExecutorを呼び、新規建ての前に既存建玉を管理する
        # （analyzer:383-389・executor:2340-2347、Fableレビュー）ため、どの案でも4h境界の:00は見回る
        if i > i0 and (h["minute"][i] in CHECKS or (h["minute"][i] == 0 and h["hour"][i] % 4 == 0)):
            if phase == "sl_wait":       # SL約定後、残り30%を成行で決済
                px = o * (1 - sgn * SLIP_MKT)
                r += 0.3 * (pnl(px) - TAKER[coin]) - interest(i, 0.3)
                return r, i, "SL"
            if phase == "tp_wait":       # TP1約定後、建値にトレーリングSLを置く
                if (long and o <= E) or (not long and o >= E):   # 60018 → 成行
                    px = o * (1 - sgn * SLIP_MKT)
                    r += 0.7 * (pnl(px) - TAKER[coin]) - interest(i, 0.7)
                    return r, i, "TP1→建値割れ成行"
                phase, trail, ext = "trailing", E, tp1
            elif phase == "trailing":
                if (long and o > ext) or (not long and o < ext):
                    nt = max(o - atr * TRAIL, E) if long else min(o + atr * TRAIL, E)
                    if (long and nt > trail) or (not long and nt < trail):
                        trail = nt
                    ext = o
        # ── 足の中の約定（板に置いた注文）──
        if phase == "active":
            if (long and lo <= sl) or (not long and hi >= sl):
                px = (min(sl, o) if long else max(sl, o)) * (1 - sgn * SLIP_STOP)
                r += 0.7 * (pnl(px) - TAKER[coin]) - interest(i, 0.7)
                phase = "sl_wait"
                continue   # 同じ足でTP1には戻らない（保守的）
            if (long and hi >= tp1) or (not long and lo <= tp1):
                r += 0.3 * (pnl(tp1) - MAKER[coin]) - interest(i, 0.3)
                phase = "tp_wait"
            continue
        if phase == "sl_wait":
            if (long and hi >= tp1) or (not long and lo <= tp1):   # 残りのTP1指値に戻って約定
                r += 0.3 * (pnl(tp1) - MAKER[coin]) - interest(i, 0.3)
                return r, i, "SL"
            continue
        if phase == "tp_wait":           # 旧SL(70%)がまだ板にある
            if (long and lo <= sl) or (not long and hi >= sl):
                px = (min(sl, o) if long else max(sl, o)) * (1 - sgn * SLIP_STOP)
                r += 0.7 * (pnl(px) - TAKER[coin]) - interest(i, 0.7)
                return r, i, "TP1後に旧SL"
            continue
        # trailing
        if (long and lo <= trail) or (not long and hi >= trail):
            px = (min(trail, o) if long else max(trail, o)) * (1 - sgn * SLIP_STOP)
            r += 0.7 * (pnl(px) - TAKER[coin]) - interest(i, 0.7)
            return r, i, "TRAIL"
    px = h["c"][-1]
    rem = 0.3 if phase == "sl_wait" else (1.0 if phase == "active" else 0.7)
    return r + rem * (pnl(px) - TAKER[coin]) - interest(n - 1, rem), n - 1, "EOD"


e1.manage = manage   # e1.simulate がこの manage を使う


def per_signal(sigs, h5, t_from=None):
    """枠の制約なしで全シグナルを1件ずつ評価（対応のある比較用）"""
    out = {}
    for s in sigs:
        if t_from is not None and s["t_close"] < t_from:
            continue
        h = h5[s["coin"]]
        fills, _ = e1.entry(s, h, {"kind": "market"})
        if not fills:
            continue
        r, ei, why = manage(s, h, fills[0])
        out[(s["coin"], s["t_close"])] = (r, why, ei - fills[0][0])
    return out


VARIANTS = [
    ("30分(現行 :15/:45)", {15, 45}),
    ("15分(:00/:15/:30/:45)", {0, 15, 30, 45}),
    ("10分(:05/:15/…/:55)", {5, 15, 25, 35, 45, 55}),
    ("--参考-- 5分ごと", set(range(0, 60, 5))),
    ("--参考-- 30分(:00/:30)", {0, 30}),
    ("--参考-- 15分(:05/:20/:35/:50)", {5, 20, 35, 50}),
    ("--参考-- 10分(:00/:10/…/:50)", {0, 10, 20, 30, 40, 50}),
    ("--参考-- 60分(:15)", {15}),
    ("--参考-- 4h境界のみ", set()),
]


def main():
    global CHECKS
    d4, h5 = load()
    sigs = e1.signals(d4)
    t_end = min(pd.Timestamp(h5[c]["t"][-1]) for c in h5)
    t_beg = max(pd.Timestamp(h5[c]["t"][0]) for c in h5) + pd.Timedelta(days=2)
    sigs = [s for s in sigs if t_beg <= s["t_close"] <= t_end - pd.Timedelta(days=1)]
    years = {y: t_end - pd.Timedelta(days=365 * y) for y in (5, 3, 2, 1)}
    split = t_beg + (t_end - t_beg) / 2
    print(f"シグナル{len(sigs)}件  {sigs[0]['t_close']} 〜 {sigs[-1]['t_close']}  (IS/OOS境界 {split:%Y-%m-%d})\n")
    mk = {"kind": "market"}
    base = None
    rows = []
    for name, checks in VARIANTS:
        CHECKS = checks
        res = {y: e1.simulate(sigs, h5, mk, t_from=st) for y, st in years.items()}
        res["IS"] = e1.simulate(sigs, h5, mk, t_to=split)
        res["OOS"] = e1.simulate(sigs, h5, mk, t_from=split)
        ps = per_signal(sigs, h5)
        if base is None:
            base = ps
        keys = sorted(set(ps) & set(base))
        diff = np.array([ps[k][0] - base[k][0] for k in keys]) * 100
        t = diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff))) if diff.std() > 0 else 0.0
        reasons = {}
        for v in ps.values():
            reasons[v[1]] = reasons.get(v[1], 0) + 1
        hold = np.mean([v[2] for v in ps.values()]) / 12
        rows.append((name, res, diff, t, reasons, hold,
                     np.mean([v[0] for v in ps.values()]) * 100, sum(1 for d in diff if d > 1e-9), sum(1 for d in diff if d < -1e-9)))

    print(f"{'方式':<30}{'件':>4}{'勝率':>7}{'PF':>6}{'DD':>7}{'5y成長':>9}{'3y':>8}{'2y':>8}{'1y':>8}{'IS':>8}{'OOS':>8}")
    for name, res, *_ in rows:
        s = res[5]
        print(f"{name:<30}{s['n']:>4}{s['wr']:>6.1f}%{s['pf']:>6.2f}{s['dd']:>6.1f}%{s['growth']:>+8.1f}%"
              f"{res[3]['growth']:>+7.1f}%{res[2]['growth']:>+7.1f}%{res[1]['growth']:>+7.1f}%"
              f"{res['IS']['growth']:>+7.1f}%{res['OOS']['growth']:>+7.1f}%")
    print("\n全シグナルを1件ずつ（枠の制約なし）、現行30分との対応のある比較")
    print(f"{'方式':<30}{'平均/件':>9}{'差/件':>9}{'t値':>7}{'良化':>6}{'悪化':>6}{'保有h':>7}  決済理由")
    for name, res, diff, t, reasons, hold, mean, up, down in rows:
        rs = " ".join(f"{k}{v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1]))
        print(f"{name:<30}{mean:>+8.3f}%{diff.mean():>+8.3f}%{t:>7.2f}{up:>6}{down:>6}{hold:>7.1f}  {rs}")


if __name__ == "__main__":
    main()
