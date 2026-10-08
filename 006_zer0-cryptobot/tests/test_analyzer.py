"""Analyzer Lambda のユニットテスト。
boto3クライアントはconftest.pyでモック済み。Binance実APIには接続しない
（フォールバックホストのテストはurllib.request.urlopenをモックする）。
"""
import json
import urllib.error
from unittest.mock import MagicMock, patch


# ── EMA ───────────────────────────────────────────────────────────────────

def test_ema_seed_is_first_value(analyzer):
    result = analyzer.ema([10.0, 20.0, 30.0], period=2)
    assert result[0] == 10.0


def test_ema_matches_pandas_ewm_adjust_false(analyzer):
    import pandas as pd
    values = [100.0, 102.0, 101.0, 105.0, 103.0, 108.0]
    result = analyzer.ema(values, period=3)
    expected = pd.Series(values).ewm(span=3, adjust=False).mean().tolist()
    for a, b in zip(result, expected):
        assert abs(a - b) < 1e-9


# ── ATR / Supertrend（挙動確認・境界値） ───────────────────────────────────

def test_calc_atr_length_is_candles_minus_one(analyzer):
    candles = [
        {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 10},
        {"open": 102, "high": 104, "low": 101, "close": 103, "volume": 10},
    ]
    atr = analyzer.calc_atr(candles, period=2)
    assert len(atr) == len(candles) - 1


def test_calc_supertrend_direction_is_plus_or_minus_one(analyzer):
    candles = [{"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 10} for i in range(20)]
    atr = analyzer.calc_atr(candles, period=8)
    st = analyzer.calc_supertrend(candles, atr, mult=2.5)
    assert st["direction"] in (1, -1)
    assert st["prev_direction"] in (1, -1)


# ── Binance フォールバックホスト ────────────────────────────────────────────

def _make_klines_response(count=3):
    body = json.dumps([[i, "1", "2", "0.5", "1.5", "10", i, "1", 1, "1", "1", "0"] for i in range(count)]).encode()
    m = MagicMock()
    m.read.return_value = body
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


def test_fetch_binance_succeeds_on_first_host(analyzer):
    with patch("urllib.request.urlopen", return_value=_make_klines_response(5)) as mock_open:
        result = analyzer.fetch_binance("BTCUSDT")
        assert len(result) == 5
        assert mock_open.call_count == 1
        assert analyzer.BINANCE_HOSTS[0] in mock_open.call_args[0][0]


def test_fetch_binance_falls_back_to_next_host_on_failure(analyzer, monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: None)
    calls = []

    def side_effect(url, timeout=15):
        calls.append(url)
        if len(calls) <= 2:
            raise urllib.error.URLError("connection timed out")
        return _make_klines_response(3)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = analyzer.fetch_binance("ETHUSDT")
        assert len(result) == 3
        assert len(calls) == 3
        assert analyzer.BINANCE_HOSTS[2] in calls[2]


def test_fetch_binance_raises_after_all_hosts_fail(analyzer, monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: None)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network down")):
        try:
            analyzer.fetch_binance("SOLUSDT")
            assert False, "RuntimeErrorが発生するはず"
        except RuntimeError as e:
            assert "全ホスト取得失敗" in str(e)


def _ban_error(code=418, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://api.binance.com", code, "banned", headers, None)


def test_fetch_binance_stops_rotation_on_ban(analyzer, monkeypatch):
    """418はIP単位のバンなので他ホストへローテーションせず即打ち切る（叩くとバン延長）。"""
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: None)
    monkeypatch.setattr(analyzer, "_ban_wait_left", analyzer.BAN_WAIT_BUDGET_S)
    with patch("urllib.request.urlopen", side_effect=_ban_error(418, 7200)) as mock_open:
        try:
            analyzer.fetch_binance("BTCUSDT")
            assert False, "BinanceBanErrorが発生するはず"
        except analyzer.BinanceBanError as e:
            assert "Retry-After=7200" in str(e)
        assert mock_open.call_count == 1


def test_fetch_binance_waits_and_retries_when_retry_after_within_budget(analyzer, monkeypatch):
    slept = []
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(analyzer, "_ban_wait_left", analyzer.BAN_WAIT_BUDGET_S)
    side = [_ban_error(429, 10), _make_klines_response(4)]
    with patch("urllib.request.urlopen", side_effect=side) as mock_open:
        result = analyzer.fetch_binance("BTCUSDT")
        assert len(result) == 4
        assert mock_open.call_count == 2
    assert slept == [10]
    assert analyzer._ban_wait_left == analyzer.BAN_WAIT_BUDGET_S - 10


def test_fetch_binance_ban_without_retry_after_raises(analyzer, monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: None)
    monkeypatch.setattr(analyzer, "_ban_wait_left", analyzer.BAN_WAIT_BUDGET_S)
    with patch("urllib.request.urlopen", side_effect=_ban_error(418)):
        try:
            analyzer.fetch_binance("BTCUSDT")
            assert False
        except analyzer.BinanceBanError:
            pass


# ── analyze_coin シグナル判定 ────────────────────────────────────────────

def _flat_uptrend_candles(n=250):
    """close > 200EMA・Supertrend緑継続・出来高普通、になるよう単調上昇の合成データを作る。"""
    return [
        {"open": 100 + i * 0.5, "high": 101 + i * 0.5, "low": 99 + i * 0.5,
         "close": 100.3 + i * 0.5, "volume": 500}
        for i in range(n)
    ]


def test_analyze_coin_returns_none_when_below_ema200_for_long(analyzer, monkeypatch):
    """closeがEMA200未満ならロング条件を満たさずNoneを返すこと。"""
    candles = list(reversed(_flat_uptrend_candles(250)))  # 下降トレンドに反転
    monkeypatch.setattr(analyzer, "fetch_binance", MagicMock(return_value=candles + [candles[-1]]))
    result = analyzer.analyze_coin("BTCUSDT", "long")
    assert result is None


# ── アラートメール ────────────────────────────────────────────────────────

def test_next_run_jst_rounds_up_to_next_4h_boundary(analyzer):
    from datetime import datetime, timezone
    # 00:00 UTC(09:00 JST)ちょうどの実行中 → 次回は 04:00 UTC = 13:00 JST
    assert analyzer.next_run_jst(datetime(2026, 10, 7, 0, 0, 5, tzinfo=timezone.utc)) == "10/07 13:00"
    assert analyzer.next_run_jst(datetime(2026, 10, 7, 14, 30, tzinfo=timezone.utc)) == "10/08 01:00"


def test_handler_ban_sends_no_action_needed_email(analyzer, monkeypatch):
    err = analyzer.BinanceBanError("Binance がIPバン/レート制限中(BTCUSDT): HTTP 418")
    err.retry_after = None
    monkeypatch.setattr(analyzer, "fetch_binance", MagicMock(side_effect=err))
    sent = []
    monkeypatch.setattr(analyzer, "send_error_email", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(analyzer, "_lambda", MagicMock())
    res = analyzer.lambda_handler({}, None)
    assert res["statusCode"] == 500
    assert len(sent) == 1
    subject, level, *_rest, action = sent[0]
    assert "対応不要" in subject and level == "info"
    assert "対応は不要です" in action
    analyzer._lambda.invoke.assert_called_once()  # Executor は継続起動
