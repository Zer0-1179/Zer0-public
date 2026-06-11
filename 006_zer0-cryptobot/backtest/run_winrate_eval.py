"""
2026-06-11 勝率向上 評価ドライバ
プロトレーダー系記事で推奨される未検証の改善案7種を、現行(base)と
2/3/4/5年の全期間で一括比較する。エグジットは全variant共通で fix（本番相当）。

シグナルフィルタ系（エグジットは現行と同一）:
  rsimom : Supertrend転換 + RSIモメンタム整合（L:RSI>50 / S:RSI<50）
  noext  : Supertrend転換 + RSI過熱回避（L:RSI<70 / S:RSI>30）
  macd   : Supertrend転換 + MACDライン/シグナルの方向一致（12/26/9）
  dst    : Supertrend転換 + 遅いSupertrend(ATR20×4.0)の方向一致（ダブルST）

エグジット調整系（シグナルは現行と同一）:
  tp1_15 : TP1_MULT 2.0→1.5（部分利確を早め、早期にブレイクイーブン化）
  sl_20  : SL_MULT 1.5→2.0（初期SLを広げ、ノイズでの損切りを減らす）
  trail10: TRAIL_MULT 1.5→1.0（トレールを締めて含み益の維持率を上げる）

採用基準: 勝率が全期間で base 超え、かつ PF≥1.5（全期間）、DD≤30%、
          資本成長率が base から大幅悪化しないこと（総合判断）

使い方:
  python3 run_winrate_eval.py
"""

import backtest as bt

YEARS_LIST = (2, 3, 4, 5)
COINS      = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
MAX_4H     = 5 * 365 * 6

# エグジット調整系: (TP1_MULT, SL_MULT, TRAIL_MULT)
EXIT_BASE     = (bt.TP1_MULT, bt.SL_MULT, bt.TRAIL_MULT)
EXIT_VARIANTS = {
    "tp1_15":  (1.5, 1.5, 1.5),
    "sl_20":   (2.0, 2.0, 1.5),
    "trail10": (2.0, 1.5, 1.0),
}


def set_exit(params: tuple):
    bt.TP1_MULT, bt.SL_MULT, bt.TRAIL_MULT = params


def main():
    print("=== データ取得（5年分を一括取得し期間別にスライス） ===")
    raw4h = {}
    for coin, sym in COINS.items():
        print(f"  {sym} 4h ...")
        raw4h[coin] = bt.fetch_klines(sym, total=MAX_4H)

    summary = {}
    for years in YEARS_LIST:
        n4  = years * 365 * 6
        dfs = {c: bt.add_indicators(raw4h[c].tail(n4).reset_index(drop=True))
               for c in COINS}
        btc_df = dfs["BTC"]

        variants = [
            ("base",    "flip",        EXIT_BASE),
            ("rsimom",  "flip_rsimom", EXIT_BASE),
            ("noext",   "flip_noext",  EXIT_BASE),
            ("macd",    "flip_macd",   EXIT_BASE),
            ("dst",     "flip_dst",    EXIT_BASE),
            ("tp1_15",  "flip",        EXIT_VARIANTS["tp1_15"]),
            ("sl_20",   "flip",        EXIT_VARIANTS["sl_20"]),
            ("trail10", "flip",        EXIT_VARIANTS["trail10"]),
        ]

        print(f"\n===== {years}年 =====")
        print(f"  {'variant':<8} {'trades':>6} {'勝率':>7} {'PF':>6} {'最大DD':>7} {'成長率':>8}")
        for name, mode, exit_params in variants:
            set_exit(exit_params)
            try:
                res = bt.run_backtest(btc_df, dfs, strategy="fix", signal_mode=mode)
            finally:
                set_exit(EXIT_BASE)
            stats  = bt.calc_stats(res["trades"], res["equity"])
            growth = (res["final_pool"] / bt.INITIAL_CAPITAL - 1) * 100
            summary[(years, name)] = {**stats, "growth": growth}
            print(f"  {name:<8} {stats['total']:>6.0f} {stats['win_rate']:>6.1f}% "
                  f"{stats['pf']:>6.2f} {stats['max_dd']:>6.1f}% {growth:>+7.1f}%")

    # ── 採否判定 ──────────────────────────────────────────────────────────
    print("\n===== 採否判定（全期間で base と比較） =====")
    names = ("rsimom", "noext", "macd", "dst", "tp1_15", "sl_20", "trail10")
    for name in names:
        rows = [(summary[(y, "base")], summary[(y, name)]) for y in YEARS_LIST]
        all_wr  = all(v["win_rate"] > b["win_rate"] for b, v in rows)
        all_pf  = all(v["pf"] >= 1.5 for _, v in rows)
        all_gr  = all(v["growth"] >= b["growth"] for b, v in rows)
        all_dd  = all(v["max_dd"] <= max(b["max_dd"], 30) for b, v in rows)
        print(f"  {name:<8} 勝率全期間>base: {all_wr}  PF全期間≥1.5: {all_pf}  "
              f"成長率全期間≥base: {all_gr}  DD許容: {all_dd}")


if __name__ == "__main__":
    main()
