"""
006_Zer0_CryptoBot バックテスト
対象: BTC/ETH/SOL  データ: Binance 4時間足 直近2年分
戦略: BTC200EMAで市場方向判定 → ロング/ショート両方向
  ロング: コイン200EMA上 + Supertrend緑転換 + Volume増加
  ショート: コイン200EMA下 + Supertrend赤転換 + Volume増加
TP1: ±ATR×2(30%) / 残り70%: TP1後トレーリングSL
合格基準: 勝率50%以上 / PF1.5以上 / 最大DD30%以内
"""

import time
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
from datetime import datetime, timezone

# ── 設定 ──────────────────────────────────────────────
COINS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}
BTC_SYMBOL  = "BTCUSDT"
INTERVAL    = "4h"
YEARS       = 2
MAX_CANDLES = YEARS * 365 * 6       # 4h足で1日6本 → 2年=4380本
BINANCE_MAX = 1000                  # 1リクエストあたりの最大本数
EMA_PERIOD  = 200
ATR_PERIOD  = 8
ST_MULT     = 2.5
VOL_PERIOD      = 20
INITIAL_CAPITAL = 10000.0   # 初期資本（単位: 円換算の仮想値）
POSITION_RATIO  = 0.90      # 使用率: 資本 × 90% を MAX_POSITIONS で均等割り
MIN_INVEST      = 1000.0    # 最小発注額
MAX_POSITIONS   = 3

TP1_MULT   = 2.0
SL_MULT    = 1.5
TRAIL_MULT = 1.5


# ── Binance データ取得 ────────────────────────────────
def fetch_klines(symbol: str, total: int = MAX_CANDLES) -> pd.DataFrame:
    """Binance から 4h 足を oldest→newest の順で取得して DataFrame を返す"""
    url = "https://api.binance.com/api/v3/klines"
    all_candles = []
    end_ms = None  # None = 現在時刻から遡る

    while len(all_candles) < total:
        need = min(BINANCE_MAX, total - len(all_candles))
        params = {"symbol": symbol, "interval": INTERVAL, "limit": need}
        if end_ms:
            params["endTime"] = end_ms

        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Binance API エラー({symbol}): {e}")
                time.sleep(1)

        if not data:
            break

        # Binance は古い順で返す。先頭を endTime として次のバッチに使う
        all_candles = data + all_candles
        end_ms = data[0][0] - 1  # 先頭バーの開始時刻 -1ms

        if len(data) < need:
            break  # これ以上データなし
        time.sleep(0.2)  # レート制限対策

    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore"]
    df = pd.DataFrame(all_candles, columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    return df


# ── テクニカル指標計算 ────────────────────────────────
def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder の TR を EWM で平滑化した ATR"""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_supertrend(df: pd.DataFrame, atr: pd.Series, mult: float) -> pd.Series:
    """
    Supertrend の方向を計算して返す。
    +1 = 上昇トレンド（緑）、-1 = 下降トレンド（赤）
    """
    hl2 = (df["high"] + df["low"]) / 2
    basic_upper = (hl2 + mult * atr).values
    basic_lower = (hl2 - mult * atr).values
    close       = df["close"].values

    n           = len(close)
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction   = np.zeros(n, dtype=int)

    # 初期方向：価格が upper より上なら上昇、そうでなければ下降
    direction[0] = 1 if close[0] > basic_upper[0] else -1

    for i in range(1, n):
        # Upper band: 前バーの終値が前バーの upper を超えていたら確定、でなければ小さい方を採用
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Lower band: 前バーの終値が前バーの lower を下回っていたら確定、でなければ大きい方を採用
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # 方向判定（前バーの方向から継続 or 転換）
        if direction[i - 1] == -1 and close[i] > final_upper[i]:
            direction[i] = 1       # 赤 → 緑 転換
        elif direction[i - 1] == 1 and close[i] < final_lower[i]:
            direction[i] = -1      # 緑 → 赤 転換
        else:
            direction[i] = direction[i - 1]

    return pd.Series(direction, index=df.index)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema200"]      = calc_ema(df["close"], EMA_PERIOD)
    df["atr"]         = calc_atr(df, ATR_PERIOD)
    df["st_dir"]      = calc_supertrend(df, df["atr"], ST_MULT)
    df["vol_avg20"]   = df["volume"].rolling(VOL_PERIOD).mean()
    df["st_flip_green"] = (df["st_dir"] == 1) & (df["st_dir"].shift(1) == -1)
    df["st_flip_red"]   = (df["st_dir"] == -1) & (df["st_dir"].shift(1) == 1)
    return df


# ── バックテストシミュレーション ───────────────────────
class Trade:
    """1トレードの記録（ロング/ショート対応、TP1後トレーリングSL方式）"""
    def __init__(self, coin, entry_time, entry, atr, invest, direction="long"):
        self.coin        = coin
        self.entry_time  = entry_time
        self.entry       = entry
        self.atr         = atr
        self.invest      = invest
        self.direction   = direction

        if direction == "long":
            self.tp1      = entry + atr * TP1_MULT
            self.sl       = entry - atr * SL_MULT
            self.trail_sl = entry - atr * SL_MULT
        else:  # short
            self.tp1      = entry - atr * TP1_MULT
            self.sl       = entry + atr * SL_MULT
            self.trail_sl = entry + atr * SL_MULT

        self.tp1_filled  = False
        self.tp1_pnl     = 0.0
        # ロング: trail_high = 最高値追跡 / ショート: trail_high = 最安値追跡（変数名共用）
        self.trail_high  = entry

        self.pnl         = 0.0
        self.exit_time   = None
        self.exit_reason = ""
        self.closed      = False

        self.amount       = invest / entry
        self.tp1_amount   = self.amount * 0.3
        self.trail_amount = self.amount * 0.7

    def check_bar(self, bar_high, bar_low, bar_time):
        """1バーを処理。TP/SLヒット時に損益を計算してcloseする。"""
        if self.closed:
            return

        if self.direction == "long":
            if not self.tp1_filled:
                if bar_high >= self.tp1:
                    self.tp1_pnl    = (self.tp1 - self.entry) * self.tp1_amount
                    self.tp1_filled = True
                    self.trail_sl   = self.entry   # BE からトレール開始
                    self.trail_high = bar_high

                if not self.tp1_filled and bar_low <= self.sl:
                    self.pnl         = (self.sl - self.entry) * self.amount
                    self.exit_reason = "SL"
                    self.exit_time   = bar_time
                    self.closed      = True
                    return

            if self.tp1_filled:
                if bar_high > self.trail_high:
                    self.trail_high = bar_high
                new_trail = self.trail_high - self.atr * TRAIL_MULT
                new_trail = max(new_trail, self.entry)  # BE より下には下げない
                if new_trail > self.trail_sl:
                    self.trail_sl = new_trail

                if bar_low <= self.trail_sl:
                    self.pnl         = self.tp1_pnl + (self.trail_sl - self.entry) * self.trail_amount
                    self.exit_reason = "TRAIL"
                    self.exit_time   = bar_time
                    self.closed      = True

        else:  # short
            if not self.tp1_filled:
                if bar_low <= self.tp1:
                    self.tp1_pnl    = (self.entry - self.tp1) * self.tp1_amount
                    self.tp1_filled = True
                    self.trail_sl   = self.entry   # BE からトレール開始
                    self.trail_high = bar_low      # 最安値追跡

                if not self.tp1_filled and bar_high >= self.sl:
                    self.pnl         = (self.entry - self.sl) * self.amount  # 負値
                    self.exit_reason = "SL"
                    self.exit_time   = bar_time
                    self.closed      = True
                    return

            if self.tp1_filled:
                if bar_low < self.trail_high:
                    self.trail_high = bar_low      # 最安値を更新
                new_trail = self.trail_high + self.atr * TRAIL_MULT
                new_trail = min(new_trail, self.entry)  # BE より上には上げない
                if new_trail < self.trail_sl:
                    self.trail_sl = new_trail      # SL を下方向に更新

                if bar_high >= self.trail_sl:
                    self.pnl         = self.tp1_pnl + (self.entry - self.trail_sl) * self.trail_amount
                    self.exit_reason = "TRAIL"
                    self.exit_time   = bar_time
                    self.closed      = True


def run_backtest(btc_df: pd.DataFrame, coin_dfs: dict) -> dict:
    """
    全コインを統合してシミュレーションを実行する。
    BTCの200EMAで市場方向（ロング/ショート）を決定し、
    各コインのシグナルを方向に応じて収集・実行する。
    """
    min_idx = EMA_PERIOD + VOL_PERIOD + 5

    # BTC の ema200 と close を時刻→値の辞書として保持
    btc_ema200 = btc_df.set_index("open_time")["ema200"].to_dict()
    btc_close  = btc_df.set_index("open_time")["close"].to_dict()

    # 各コインのシグナルを収集
    all_signals: list[dict] = []
    for coin, df in coin_dfs.items():
        for i in range(min_idx, len(df)):
            row = df.iloc[i]
            ts  = row["open_time"]

            # 市場方向の判定
            if ts not in btc_ema200:
                continue
            market_dir = "long" if btc_close.get(ts, 0) >= btc_ema200[ts] else "short"

            # コイン条件（方向に応じて判定）
            if market_dir == "long":
                if row["close"] < row["ema200"]:
                    continue
                if not row["st_flip_green"]:
                    continue
            else:  # short
                if row["close"] >= row["ema200"]:
                    continue
                if not row["st_flip_red"]:
                    continue

            if pd.isna(row["vol_avg20"]) or row["volume"] <= row["vol_avg20"]:
                continue

            all_signals.append({
                "coin":      coin,
                "ts":        ts,
                "close":     row["close"],
                "atr":       row["atr"],
                "direction": market_dir,
            })

    # シグナルを時刻でソート・辞書化（ts → list[signal]）
    sig_by_ts: dict = {}
    for s in all_signals:
        sig_by_ts.setdefault(s["ts"], []).append(s)

    # 各コインの OHLC を時刻→行 の辞書として保持
    coin_ohlc: dict[str, dict] = {}
    for coin, df in coin_dfs.items():
        coin_ohlc[coin] = df.set_index("open_time")[["high", "low"]].to_dict("index")

    # 統合タイムライン（全コインの全バー）
    all_ts = sorted(set(ts for df in coin_dfs.values() for ts in df["open_time"]))

    pool_nav      = INITIAL_CAPITAL
    active_trades: list[Trade] = []
    completed:     list[Trade] = []
    equity = [0.0]

    for ts in all_ts:
        # ── 既存ポジションの TP/SL チェック ──────────────────────────────
        newly_closed = []
        for t in active_trades:
            bar = coin_ohlc.get(t.coin, {}).get(ts)
            if bar is None:
                continue
            t.check_bar(bar["high"], bar["low"], ts)
            if t.closed:
                newly_closed.append(t)

        for t in newly_closed:
            active_trades.remove(t)
            completed.append(t)
            pool_nav += t.pnl
            equity.append(pool_nav - INITIAL_CAPITAL)

        # ── シグナルチェック ───────────────────────────────────────────────
        for sig in sig_by_ts.get(ts, []):
            if len(active_trades) >= MAX_POSITIONS:
                break
            if any(t.coin == sig["coin"] for t in active_trades):
                continue

            if pool_nav < MIN_INVEST:
                break

            invest = pool_nav * POSITION_RATIO / MAX_POSITIONS
            invest = max(invest, MIN_INVEST)

            direction = sig["direction"]
            entry = sig["close"] * 0.99 if direction == "long" else sig["close"] * 1.01
            t = Trade(sig["coin"], ts, entry, sig["atr"], invest, direction)
            active_trades.append(t)

    # 残ポジションを最終バー終値で強制決済
    for t in active_trades:
        last_close = coin_dfs[t.coin].iloc[-1]["close"]
        if t.direction == "long":
            if not t.tp1_filled:
                t.pnl = (last_close - t.entry) * t.amount
            else:
                t.pnl = t.tp1_pnl + (last_close - t.entry) * t.trail_amount
        else:  # short
            if not t.tp1_filled:
                t.pnl = (t.entry - last_close) * t.amount
            else:
                t.pnl = t.tp1_pnl + (t.entry - last_close) * t.trail_amount
        t.exit_reason = "EOD"
        t.closed = True
        completed.append(t)
        pool_nav += t.pnl
        equity.append(pool_nav - INITIAL_CAPITAL)

    return {"trades": completed, "equity": equity, "timestamps": [], "final_pool": pool_nav}


# ── 統計計算 ──────────────────────────────────────────
def calc_stats(trades: list, equity: list) -> dict:
    if not trades:
        return {"total": 0}

    wins  = [t for t in trades if t.pnl > 0]
    loses = [t for t in trades if t.pnl <= 0]

    win_rate  = len(wins) / len(trades) * 100
    gross_win = sum(t.pnl for t in wins)
    gross_los = abs(sum(t.pnl for t in loses))
    pf        = gross_win / gross_los if gross_los else float("inf")

    # 最大ドローダウン
    eq_abs = [INITIAL_CAPITAL + v for v in equity]
    peak   = eq_abs[0]
    max_dd = 0.0
    for val in eq_abs:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

    # コイン別集計
    coin_stats = {}
    for coin in COINS:
        coin_trades = [t for t in trades if t.coin == coin]
        if not coin_trades:
            continue
        coin_wins = [t for t in coin_trades if t.pnl > 0]
        long_trades  = [t for t in coin_trades if t.direction == "long"]
        short_trades = [t for t in coin_trades if t.direction == "short"]
        coin_stats[coin] = {
            "total":    len(coin_trades),
            "wins":     len(coin_wins),
            "win_rate": len(coin_wins) / len(coin_trades) * 100 if coin_trades else 0,
            "pnl":      sum(t.pnl for t in coin_trades),
            "long":     len(long_trades),
            "short":    len(short_trades),
        }

    # 方向別集計
    long_trades  = [t for t in trades if t.direction == "long"]
    short_trades = [t for t in trades if t.direction == "short"]
    long_wins    = [t for t in long_trades  if t.pnl > 0]
    short_wins   = [t for t in short_trades if t.pnl > 0]

    return {
        "total":     len(trades),
        "wins":      len(wins),
        "win_rate":  win_rate,
        "pf":        pf,
        "max_dd":    max_dd,
        "total_pnl": sum(t.pnl for t in trades),
        "coin":      coin_stats,
        "long_total":  len(long_trades),
        "long_wr":     len(long_wins) / len(long_trades) * 100 if long_trades else 0,
        "short_total": len(short_trades),
        "short_wr":    len(short_wins) / len(short_trades) * 100 if short_trades else 0,
    }


def print_stats(stats: dict):
    print("\n" + "=" * 55)
    print("  バックテスト結果")
    print("=" * 55)
    if stats.get("total", 0) == 0:
        print("  トレードなし")
        return

    print(f"  総トレード数: {stats['total']}")
    print(f"  勝率        : {stats['win_rate']:.1f}%  (勝:{stats['wins']} / 負:{stats['total']-stats['wins']})")
    print(f"  プロフィットファクター: {stats['pf']:.2f}")
    print(f"  最大ドローダウン      : {stats['max_dd']:.1f}%")
    print(f"  総損益(USDT)          : {stats['total_pnl']:+.2f}")
    print()

    print(f"  方向別内訳:")
    print(f"    ロング : {stats['long_total']:3d}件  勝率:{stats['long_wr']:.1f}%")
    print(f"    ショート: {stats['short_total']:3d}件  勝率:{stats['short_wr']:.1f}%")
    print()

    print("  コイン別内訳:")
    for coin, cs in stats["coin"].items():
        print(f"    {coin:5s} | 計:{cs['total']:3d}(L:{cs['long']:2d}/S:{cs['short']:2d}) | "
              f"勝率:{cs['win_rate']:5.1f}% | 損益:{cs['pnl']:+.2f} USDT")

    print()
    ok_wr  = "✓" if stats["win_rate"] >= 50    else "✗"
    ok_pf  = "✓" if stats["pf"]       >= 1.5   else "✗"
    ok_dd  = "✓" if stats["max_dd"]   <= 30.0  else "✗"
    passed = all([stats["win_rate"] >= 50, stats["pf"] >= 1.5, stats["max_dd"] <= 30.0])
    print(f"  合格基準チェック:")
    print(f"    {ok_wr} 勝率   50%以上 → {stats['win_rate']:.1f}%")
    print(f"    {ok_pf} PF   1.5以上 → {stats['pf']:.2f}")
    print(f"    {ok_dd} 最大DD 30%以内 → {stats['max_dd']:.1f}%")
    print()
    print(f"  判定: {'【合格】' if passed else '【不合格】'}")
    print("=" * 55)


def save_chart(equity: list, timestamps: list, path: str, final_pool: float):
    fig, ax = plt.subplots(figsize=(12, 5))
    x = list(range(len(equity)))
    ax.plot(x, equity, linewidth=1.5, color="#3EA8FF")
    ax.axhline(0, color="#666", linewidth=0.8, linestyle="--")
    ax.fill_between(x, equity, 0, where=[v >= 0 for v in equity],
                    alpha=0.2, color="#3EA8FF")
    ax.fill_between(x, equity, 0, where=[v < 0 for v in equity],
                    alpha=0.2, color="#FF6B6B")
    growth = (final_pool / INITIAL_CAPITAL - 1) * 100
    ax.set_title(
        f"Zer0-CryptoBot バックテスト 損益推移  "
        f"（初期{INITIAL_CAPITAL:,.0f}円 → 最終{final_pool:,.0f}円 / {growth:+.1f}%）",
        fontsize=13,
    )
    ax.set_xlabel("トレード番号")
    ax.set_ylabel("累積損益（初期資本比, 円）")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    print(f"\n  チャート保存: {path}")


# ── メイン ────────────────────────────────────────────
def main():
    print("Zer0-CryptoBot バックテスト開始（ロング＋ショート版）")
    print(f"  期間: 直近 {YEARS} 年  足: {INTERVAL}  EMA:{EMA_PERIOD}  ATR:{ATR_PERIOD}  ST倍率:{ST_MULT}")
    print()

    # BTC データ取得（フィルター兼トレード対象）
    print(f"[1/4] BTC データ取得中... ({BTC_SYMBOL})")
    btc_raw = fetch_klines(BTC_SYMBOL)
    btc_df  = add_indicators(btc_raw)
    print(f"      取得: {len(btc_df)} 本  期間: {btc_df['open_time'].iloc[0]} ～ {btc_df['open_time'].iloc[-1]}")

    # コインデータ取得（BTCはbtc_dfを再利用）
    coin_dfs = {"BTC": btc_df}
    for idx, (coin, symbol) in enumerate(
        [("ETH", "ETHUSDT"), ("SOL", "SOLUSDT")], start=2
    ):
        print(f"[{idx}/4] {coin} データ取得中... ({symbol})")
        raw = fetch_klines(symbol)
        coin_dfs[coin] = add_indicators(raw)
        df = coin_dfs[coin]
        print(f"      取得: {len(df)} 本  期間: {df['open_time'].iloc[0]} ～ {df['open_time'].iloc[-1]}")

    # バックテスト実行
    print("\n[4/4] バックテスト実行中...")
    result  = run_backtest(btc_df, coin_dfs)
    trades  = result["trades"]
    equity     = result["equity"]
    timestamps = result["timestamps"]
    final_pool = result["final_pool"]

    # 結果出力
    stats = calc_stats(trades, equity)
    print_stats(stats)
    growth = (final_pool / INITIAL_CAPITAL - 1) * 100
    print(f"  資本推移: {INITIAL_CAPITAL:,.0f}円 → {final_pool:,.0f}円 ({growth:+.1f}%)")

    # チャート保存
    chart_path = "/root/Zer0/006_Zer0_CryptoBot/backtest/result.png"
    if len(equity) > 1:
        save_chart(equity, timestamps, chart_path, final_pool)
    else:
        print("  トレードなし → チャート生成スキップ")


if __name__ == "__main__":
    main()
