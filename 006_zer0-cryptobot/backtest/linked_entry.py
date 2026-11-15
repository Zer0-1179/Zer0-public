"""連動エントリーのバックテスト（2026-11-15）
案: 1銘柄が本番シグナル（4h flip_dst）でエントリーしたら、他の銘柄も同じ方向で同時に成行エントリーする。
約定・決済・手数料・金利は entry_1h.py と同じ（1h足で再現、SL優先の保守的判定）。
追随銘柄の TP1/SL/トレールは追随銘柄自身のATR（同じ4h足）で計算する。
変種:
  A 無条件で追随
  B 追随銘柄の速いST（4h確定足）が同方向のときだけ
  C Bに加えて、追随銘柄の200EMA・遅いSTも同方向（=フリップ以外の本番条件をすべて満たす）
枠: 同時2件×資金0.6（現行）。参考に3件×0.4（合計建玉は同じ1.2倍）も比較する。
python3 -I linked_entry.py <backtest_dir> <cache_dir>
"""
import sys, os, pickle
sys.path.insert(0, sys.argv[1])
import numpy as np
import pandas as pd
import entry_1h as E
E.HERE = sys.argv[2]   # klinesキャッシュの置き場（リポジトリに大きいpklを置かない）

COINS = ["BTC", "ETH", "SOL"]


def follower_sig(d4i, coin, ts, d, cond):
    df = d4i[coin]
    if ts not in df.index:
        return None
    r = df.loc[ts]
    want = 1 if d == "long" else -1
    if cond in ("B", "C") and r["st_dir"] != want:
        return None
    if cond == "C":
        if d == "long" and not (r["close"] >= r["ema200"] and r["st_dir_slow"] == 1):
            return None
        if d == "short" and not (r["close"] < r["ema200"] and r["st_dir_slow"] == -1):
            return None
    return dict(coin=coin, ts=ts, t_close=ts + pd.Timedelta(hours=4), close=float(r["close"]),
                open=float(r["open"]), atr=float(r["atr"]), dir=d,
                body=abs(r["close"] - r["open"]) / r["atr"], follower=True)


def simulate(sigs, d4i, h1, cond, maxpos, ratio, t_from=None, t_to=None):
    pool, busy, eq = E.INIT, [], [E.INIT]
    trades = []
    mkt = dict(kind="market")

    def settle(now):
        nonlocal pool, busy
        still = []
        for b in sorted(busy):
            if b[0] <= now:
                pool += b[2]; eq.append(pool)
            else:
                still.append(b)
        busy = still

    def open_pos(sig, now):
        h = h1[sig["coin"]]
        fills, _ = E.entry(sig, h, mkt)
        if not fills:
            return False
        invest = pool * ratio
        r, ei, why = E.manage(sig, h, fills[0])
        pnl = invest * r
        busy.append((pd.Timestamp(h["t"][ei]), sig["coin"], pnl))
        trades.append(dict(t=now, coin=sig["coin"], dir=sig["dir"], pnl=pnl, rate=r,
                           follower=sig.get("follower", False)))
        return True

    i = 0
    while i < len(sigs):
        # 同じ4h足で出たシグナルはまとめて処理する（本物のシグナルを追随より優先）
        now = sigs[i]["t_close"]
        group = []
        while i < len(sigs) and sigs[i]["t_close"] == now:
            group.append(sigs[i]); i += 1
        if t_from is not None and now < t_from: continue
        if t_to is not None and now >= t_to: continue
        settle(now)
        entered = []
        for sig in group:
            if len(busy) >= maxpos or any(b[1] == sig["coin"] for b in busy):
                continue
            if open_pos(sig, now):
                entered.append(sig)
        if cond is None:
            continue
        own = {s["coin"] for s in group}
        for lead in entered:
            for c in COINS:
                if c in own or len(busy) >= maxpos or any(b[1] == c for b in busy):
                    continue
                f = follower_sig(d4i, c, lead["ts"], lead["dir"], cond)
                if f:
                    open_pos(f, now)
    settle(pd.Timestamp.max.tz_localize("UTC"))
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    loss = [-t["pnl"] for t in trades if t["pnl"] <= 0]
    peak, dd = eq[0], 0.0
    for x in eq:
        peak = max(peak, x); dd = max(dd, (peak - x) / peak * 100)
    return dict(n=len(trades), nf=sum(t["follower"] for t in trades),
                wr=len(wins) / max(1, len(trades)) * 100, pf=sum(wins) / sum(loss) if loss else 99,
                dd=dd, growth=(pool / E.INIT - 1) * 100, trades=trades)


def main():
    d4, h1 = E.load()
    sigs = E.signals(d4)
    d4i = {c: df.set_index("open_time") for c, df in d4.items()}
    t_end = max(pd.Timestamp(h1[c]["t"][-1]) for c in h1)
    starts = {y: t_end - pd.Timedelta(days=365 * y) for y in (2, 3, 4, 5)}
    split = pd.Timestamp("2024-01-01", tz="UTC")
    print(f"本番シグナル{len(sigs)}件  {sigs[0]['t_close']:%Y-%m-%d} 〜 {t_end:%Y-%m-%d}")

    V = [("現行（2枠×0.6）", None, 2, 0.6),
         ("連動A 無条件", "A", 2, 0.6),
         ("連動B 速いSTが同方向", "B", 2, 0.6),
         ("連動C 本番条件(フリップ以外)", "C", 2, 0.6),
         ("参考: 現行 3枠×0.4", None, 3, 0.4),
         ("参考: 連動B 3枠×0.4", "B", 3, 0.4),
         ("参考: 連動C 3枠×0.4", "C", 3, 0.4)]
    rows = []
    print(f"{'方式':<26}{'5y件(追随)':>11}{'勝率':>7}{'PF':>6}{'最大DD':>7}{'5y成長':>8}{'4y':>8}{'3y':>8}{'2y':>8}{'IS':>8}{'OOS':>8}")
    for name, cond, mp, ratio in V:
        r = {y: simulate(sigs, d4i, h1, cond, mp, ratio, t_from=st) for y, st in starts.items()}
        r["IS"] = simulate(sigs, d4i, h1, cond, mp, ratio, t_from=starts[5], t_to=split)
        r["OOS"] = simulate(sigs, d4i, h1, cond, mp, ratio, t_from=split)
        s = r[5]
        print(f"{name:<26}{s['n']:>6}({s['nf']:>3}){s['wr']:>6.1f}%{s['pf']:>6.2f}{s['dd']:>6.1f}%{s['growth']:>+7.1f}%"
              f"{r[4]['growth']:>+7.1f}%{r[3]['growth']:>+7.1f}%{r[2]['growth']:>+7.1f}%"
              f"{r['IS']['growth']:>+7.1f}%{r['OOS']['growth']:>+7.1f}%")
        rows.append((name, r))

    # 追随トレード自体の質（1件あたりの損益率）。本物シグナルのトレードと比べる
    print("\n1件あたりの損益率（5年・手数料/金利込み）")
    for name, r in rows:
        tr = r[5]["trades"]
        lead = np.array([t["rate"] for t in tr if not t["follower"]])
        fol = np.array([t["rate"] for t in tr if t["follower"]])
        line = f"  {name:<26} 本物{len(lead):>3}件 平均{lead.mean()*100:+.2f}% 勝率{(lead>0).mean()*100:.0f}%"
        if len(fol):
            se = fol.std(ddof=1) / np.sqrt(len(fol)) if len(fol) > 1 else float('nan')
            line += f" ｜追随{len(fol):>3}件 平均{fol.mean()*100:+.2f}%(±{se*100:.2f}) 勝率{(fol>0).mean()*100:.0f}%"
        print(line)
    pickle.dump({n: {k: {kk: vv for kk, vv in v.items() if kk != "trades"} for k, v in r.items()} for n, r in rows},
                open(os.path.join(sys.argv[2], "linked_entry_result.pkl"), "wb"))


if __name__ == "__main__":
    main()
