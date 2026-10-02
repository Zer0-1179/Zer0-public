"""
2026-10 エントリー方式評価ドライバ（高値づかみ対策の検討）
現行の成行エントリー vs 押し目指値（シグナル終値から k×ATR、N本以内）を
2/3/4/5年の全期間で比較する。シグナル・エグジットは本番相当（flip_dst / fix）で共通。

使い方:
  python3 run_entry_eval.py
"""

import backtest as bt

YEARS_LIST = (2, 3, 4, 5)
COINS      = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
MAX_4H     = 5 * 365 * 6

VARIANTS = [("market", "market", 0, 0)]
for k in (0.25, 0.5, 0.75, 1.0):
    for n in (1, 2, 3, 6):
        VARIANTS.append((f"lim{k}x{n}", "limit", k, n))
for k in (0.25, 0.5):
    for n in (1, 2):
        VARIANTS.append((f"fb{k}x{n}", "limit_fallback", k, n))


def main():
    raw = {c: bt.fetch_klines(s, total=MAX_4H) for c, s in COINS.items()}
    summary = {}
    for years in YEARS_LIST:
        n4  = years * 365 * 6
        dfs = {c: bt.add_indicators(raw[c].tail(n4).reset_index(drop=True)) for c in COINS}
        print(f"\n===== {years}年 =====")
        print(f"  {'variant':<11} {'trades':>6} {'見送り':>5} {'勝率':>7} {'PF':>6} {'最大DD':>7} {'成長率':>8}")
        for name, mode, k, n in VARIANTS:
            res = bt.run_backtest(dfs["BTC"], dfs, strategy="fix", signal_mode="flip_dst",
                                  same_dir_limit=2, entry_mode=mode, limit_atr=k, limit_bars=n)
            st  = bt.calc_stats(res["trades"], res["equity"])
            gr  = (res["final_pool"] / bt.INITIAL_CAPITAL - 1) * 100
            summary[(years, name)] = {**st, "growth": gr}
            print(f"  {name:<11} {st['total']:>6.0f} {res['missed_limits']:>5} {st['win_rate']:>6.1f}% "
                  f"{st['pf']:>6.2f} {st['max_dd']:>6.1f}% {gr:>+7.1f}%")

    print("\n===== 全期間で market 以上か（PF / 成長率 / DD） =====")
    for name, *_ in VARIANTS[1:]:
        rows = [(summary[(y, "market")], summary[(y, name)]) for y in YEARS_LIST]
        pf = all(v["pf"] >= b["pf"] for b, v in rows)
        gr = all(v["growth"] >= b["growth"] for b, v in rows)
        dd = all(v["max_dd"] <= b["max_dd"] * 1.2 for b, v in rows)
        mark = "  ★" if pf and gr and dd else ""
        print(f"  {name:<11} PF:{pf!s:<5} 成長率:{gr!s:<5} DD:{dd!s:<5}{mark}")


if __name__ == "__main__":
    main()
