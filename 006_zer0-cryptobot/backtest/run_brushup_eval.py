"""
2026-06 ブラッシュアップ評価ドライバ
現行(flip) / ADXフィルタ / 日足HTFフィルタ / 遅延エントリー(flip_late) / XRP追加 を
2/3/4/5年の全期間で一括比較する。エグジットは全variant共通で fix（本番相当）。

採用基準: 全期間で現行(base)と同等以上（勝率・PF・最大DD・資本成長率を総合判断）
XRP追加のみユーザー指定基準: 現行のバックテスト勝率を超えること

使い方:
  python3 run_brushup_eval.py
"""

import backtest as bt

YEARS_LIST = (2, 3, 4, 5)
ALL_COINS  = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
BASE_COINS = ("BTC", "ETH", "SOL")
MAX_4H     = 5 * 365 * 6
MAX_DAILY  = 5 * 365


def main():
    print("=== データ取得（5年分を一括取得し期間別にスライス） ===")
    raw4h = {}
    rawd  = {}
    for coin, sym in ALL_COINS.items():
        print(f"  {sym} 4h ...")
        raw4h[coin] = bt.fetch_klines(sym, total=MAX_4H)
        print(f"  {sym} 1d ...")
        rawd[coin]  = bt.fetch_klines(sym, total=MAX_DAILY, interval="1d")

    summary = {}
    for years in YEARS_LIST:
        n4, nd = years * 365 * 6, years * 365
        dfs = {c: bt.add_indicators(raw4h[c].tail(n4).reset_index(drop=True))
               for c in ALL_COINS}
        daily_lookup = {c: bt.build_daily_lookup(bt.add_daily_trend(rawd[c].tail(nd).reset_index(drop=True)))
                        for c in BASE_COINS}
        btc_df = dfs["BTC"]
        coin3  = {c: dfs[c] for c in BASE_COINS}
        coin4  = {c: dfs[c] for c in ALL_COINS}

        variants = [
            ("base",  "flip",      coin3, None),
            ("ADX",   "flip_adx",  coin3, None),
            ("HTF",   "flip_htf",  coin3, daily_lookup),
            ("late2", "flip_late", coin3, None),
            ("XRP+",  "flip",      coin4, None),
        ]

        print(f"\n===== {years}年 =====")
        print(f"  {'variant':<8} {'trades':>6} {'勝率':>7} {'PF':>6} {'最大DD':>7} {'成長率':>8}")
        for name, mode, cdfs, dl in variants:
            res    = bt.run_backtest(btc_df, cdfs, strategy="fix", signal_mode=mode, daily_lookup=dl)
            stats  = bt.calc_stats(res["trades"], res["equity"])
            growth = (res["final_pool"] / bt.INITIAL_CAPITAL - 1) * 100
            summary[(years, name)] = {**stats, "growth": growth}
            print(f"  {name:<8} {stats['total']:>6.0f} {stats['win_rate']:>6.1f}% "
                  f"{stats['pf']:>6.2f} {stats['max_dd']:>6.1f}% {growth:>+7.1f}%")

    # ── 採否判定 ──────────────────────────────────────────────────────────
    print("\n===== 採否判定（全期間で base と比較） =====")
    for name in ("ADX", "HTF", "late2", "XRP+"):
        verdict = []
        for years in YEARS_LIST:
            b, v = summary[(years, "base")], summary[(years, name)]
            better_wr = v["win_rate"] >= b["win_rate"]
            better_pf = v["pf"] >= b["pf"]
            better_gr = v["growth"] >= b["growth"]
            ok_dd     = v["max_dd"] <= max(b["max_dd"], 30)
            verdict.append((years, better_wr, better_pf, better_gr, ok_dd))
        all_wr = all(v[1] for v in verdict)
        all_pf = all(v[2] for v in verdict)
        all_gr = all(v[3] for v in verdict)
        all_dd = all(v[4] for v in verdict)
        print(f"  {name:<6} 勝率全期間≧base: {all_wr}  PF全期間≧base: {all_pf}  "
              f"成長率全期間≧base: {all_gr}  DD許容: {all_dd}")


if __name__ == "__main__":
    main()
