"""backtest.py（pandas実装）と analyzer/lambda_function.py（純Python実装）の
ATR・Supertrendが同じ値・方向を返すことを検証するパリティテスト。

二重実装のドリフトはバックテスト成績と実運用の乖離に直結するため、
戦略パラメータ変更のたびに手動で突き合わせるのではなく自動で検証する。

既知の非本質的な差異: backtest.calc_atr は pandas の shift(1)+max(axis=1, skipna=True)
の副作用で先頭バーのTrue Rangeがhigh-lowのみ（3項の最大値ではなく）になり、
analyzer.calc_atr（先頭バーを持たずcandles[1]から計算）とEWMの起点が微妙にズレる。
この差はEWMの減衰（8期間で1バーあたり約0.78倍）により数十バーで消滅するため、
本番の意思決定バー（500本ウォームアップの最終バー）には実質的に影響しない。
このテストは意図的にウォームアップ期間（先頭30バー）を除外して比較する。
"""
import numpy as np
import pandas as pd


WARMUP_SKIP = 30  # ATR EWM起点差が実質ゼロに収束するまでのバー数


def _synthetic_ohlcv(n=300, seed=42):
    """トレンド転換が複数回起きる合成OHLCVデータ（決定的・再現可能）。"""
    rng = np.random.RandomState(seed)
    t = np.arange(n)
    trend = 5 * np.sin(t / 25) + 0.05 * t
    noise = np.cumsum(rng.randn(n) * 0.5)
    close = 100 + trend + noise
    high = close + np.abs(rng.randn(n) * 0.8)
    low = close - np.abs(rng.randn(n) * 0.8)
    open_ = close + rng.randn(n) * 0.3
    volume = np.abs(rng.randn(n) * 100 + 500)
    return open_, high, low, close, volume


def _to_candles(open_, high, low, close, volume):
    return [
        {"open": float(open_[i]), "high": float(high[i]), "low": float(low[i]),
         "close": float(close[i]), "volume": float(volume[i])}
        for i in range(len(close))
    ]


def test_atr_converges_between_implementations(analyzer):
    import backtest as bt

    open_, high, low, close, volume = _synthetic_ohlcv()
    candles = _to_candles(open_, high, low, close, volume)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

    az_atr = analyzer.calc_atr(candles, period=8)
    bt_atr = bt.calc_atr(df, period=8).iloc[1:].reset_index(drop=True)  # candles[1:]に対応

    assert len(az_atr) == len(bt_atr)
    diff = np.abs(np.array(az_atr) - bt_atr.values)
    assert diff[WARMUP_SKIP:].max() < 1e-3, \
        f"ウォームアップ後もATRが乖離している（最大差分={diff[WARMUP_SKIP:].max()}）"


def test_supertrend_direction_converges_between_implementations(analyzer):
    import backtest as bt

    open_, high, low, close, volume = _synthetic_ohlcv()
    candles = _to_candles(open_, high, low, close, volume)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

    az_atr = analyzer.calc_atr(candles, period=8)
    bt_atr = bt.calc_atr(df, period=8)

    az_dir = _analyzer_full_direction_history(analyzer, candles, az_atr, mult=2.5)
    bt_dir = bt.calc_supertrend(df, bt_atr, mult=2.5).tolist()[1:]  # candles[1:]に対応

    assert len(az_dir) == len(bt_dir)
    mismatches_after_warmup = [
        i for i in range(WARMUP_SKIP, len(az_dir)) if az_dir[i] != bt_dir[i]
    ]
    assert not mismatches_after_warmup, \
        f"ウォームアップ後にSupertrend方向が不一致: {mismatches_after_warmup[:5]}..."


def _analyzer_full_direction_history(analyzer, candles, atr_values, mult):
    """analyzer.calc_supertrend は最新の direction/prev_direction しか返さないため、
    パリティ検証用に全履歴のdirectionリストを同じロジックで計算する。"""
    n = len(atr_values)
    highs = [c["high"] for c in candles[1:]]
    lows = [c["low"] for c in candles[1:]]
    closes = [c["close"] for c in candles[1:]]
    hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
    basic_upper = [hl + mult * a for hl, a in zip(hl2, atr_values)]
    basic_lower = [hl - mult * a for hl, a in zip(hl2, atr_values)]
    final_upper = basic_upper[:]
    final_lower = basic_lower[:]
    direction = [1 if closes[0] > basic_upper[0] else -1]
    for i in range(1, n):
        if basic_upper[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]
        if basic_lower[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]
        if direction[-1] == -1 and closes[i] > final_upper[i]:
            direction.append(1)
        elif direction[-1] == 1 and closes[i] < final_lower[i]:
            direction.append(-1)
        else:
            direction.append(direction[-1])
    return direction
