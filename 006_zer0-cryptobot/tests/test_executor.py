"""Executor Lambda のユニットテスト。
boto3クライアントはconftest.pyでモック済み。bitbank実APIには接続しない。
"""
import json
from unittest.mock import MagicMock
import pytest


# ── 純関数 ────────────────────────────────────────────────────────────────

def test_round_price_zero_prec_rounds_to_int_string(executor):
    assert executor.round_price(10153052.4, 0) == "10153052"


def test_round_price_nonzero_prec_keeps_decimals(executor):
    assert executor.round_price(271.554, 1) == "271.6"


def test_round_amount_formats_fixed_decimals(executor):
    assert executor.round_amount(0.0068123, 4) == "0.0068"


def test_order_fill_returns_none_when_average_price_missing(executor):
    assert executor.order_fill({"executed_amount": "0.01"}) is None


def test_order_fill_returns_none_when_amount_is_zero(executor):
    assert executor.order_fill({"average_price": "100", "executed_amount": "0"}) is None


def test_order_fill_returns_tuple_on_valid_fill(executor):
    result = executor.order_fill({"average_price": "10153052", "executed_amount": "0.0002"})
    assert result == (10153052.0, 0.0002)


# ── state⇄実建玉リコンサイル ─────────────────────────────────────────────

def test_reconcile_matches_no_notification(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = [
        {"pair": "btc_jpy", "position_side": "long", "open_amount": "0.001"}
    ]
    state = {"positions": {"btc_jpy": {"status": "active", "direction": "long"}}}
    executor.reconcile_positions(mock_bb, state)
    assert not executor.send_email.called


def test_reconcile_detects_orphan_state(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = []
    state = {"positions": {"btc_jpy": {"status": "active", "direction": "long"}}}
    executor.reconcile_positions(mock_bb, state)
    assert executor.send_email.called
    assert "孤児state" in executor.send_email.call_args[0][1]


def test_reconcile_detects_orphan_real_position(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = [
        {"pair": "eth_jpy", "position_side": "short", "open_amount": "0.05"}
    ]
    state = {"positions": {}}
    executor.reconcile_positions(mock_bb, state)
    assert executor.send_email.called
    assert "孤児建玉" in executor.send_email.call_args[0][1]


def test_reconcile_detects_direction_mismatch(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = [
        {"pair": "sol_jpy", "position_side": "short", "open_amount": "0.1"}
    ]
    state = {"positions": {"sol_jpy": {"status": "trailing", "direction": "long"}}}
    executor.reconcile_positions(mock_bb, state)
    assert executor.send_email.called
    assert "不一致" in executor.send_email.call_args[0][1]


def test_reconcile_ignores_buy_pending(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = []
    state = {"positions": {"btc_jpy": {"status": "buy_pending", "direction": "long"}}}
    executor.reconcile_positions(mock_bb, state)
    assert not executor.send_email.called


def test_reconcile_skips_silently_on_api_failure(executor, mock_bb):
    mock_bb.get_margin_positions.side_effect = Exception("network error")
    executor.reconcile_positions(mock_bb, {"positions": {}})
    assert not executor.send_email.called


# ── セーフモード・キルスイッチ ───────────────────────────────────────────

def _patch_lambda_handler_deps(executor, monkeypatch, mode_value):
    def fake_get_ssm(name, decrypt=False):
        if name == executor.SSM_MODE:
            if mode_value is None:
                raise Exception("ParameterNotFound")
            return mode_value
        if name == executor.SSM_API_KEY:
            return "key"
        if name == executor.SSM_API_SECRET:
            return "secret"
        raise Exception("unexpected ssm name")

    monkeypatch.setattr(executor, "get_ssm", fake_get_ssm)
    monkeypatch.setattr(executor, "reconcile_positions", MagicMock())
    monkeypatch.setattr(executor, "check_margin_health", MagicMock(return_value=True))
    monkeypatch.setattr(executor, "maintain_positions", MagicMock(side_effect=lambda bb, state, event: state))
    monkeypatch.setattr(executor, "place_new_orders", MagicMock(side_effect=lambda bb, state, signals, event: state))
    monkeypatch.setattr(executor, "save_state", MagicMock())
    monkeypatch.setattr(executor, "load_state", MagicMock(return_value={"positions": {}}))


def test_mode_unset_behaves_as_normal(executor, monkeypatch):
    _patch_lambda_handler_deps(executor, monkeypatch, None)
    result = executor.lambda_handler({"signals": [{"pair": "btc_jpy"}]}, MagicMock())
    assert result["statusCode"] == 200
    assert executor.place_new_orders.called


def test_mode_halt_skips_everything(executor, monkeypatch):
    _patch_lambda_handler_deps(executor, monkeypatch, "halt")
    result = executor.lambda_handler({"signals": [{"pair": "btc_jpy"}]}, MagicMock())
    body = json.loads(result["body"])
    assert body["skipped"] is True
    assert not executor.maintain_positions.called
    assert not executor.place_new_orders.called
    assert not executor.reconcile_positions.called


def test_namespace_validation_reads_only_configured_ssm_values(executor, monkeypatch):
    """切替検証イベントは取引・保存・通知を一切実行しない。"""
    calls = []

    def fake_get_ssm(name, decrypt=False):
        calls.append((name, decrypt))
        values = {
            executor.SSM_MODE: "halt",
            executor.SSM_API_KEY: "key",
            executor.SSM_API_SECRET: "secret",
            executor.SSM_STATE: '{"positions": {}}',
        }
        return values[name]

    monkeypatch.setattr(executor, "get_ssm", fake_get_ssm)
    monkeypatch.setattr(executor, "BitbankClient", MagicMock())
    monkeypatch.setattr(executor, "save_state", MagicMock())
    monkeypatch.setattr(executor, "send_email", MagicMock())
    monkeypatch.setattr(executor, "reconcile_positions", MagicMock())

    result = executor.lambda_handler({"action": "validate_ssm_namespace"}, MagicMock())

    assert result == {"statusCode": 200, "body": '{"valid": true}'}
    assert calls == [
        (executor.SSM_MODE, False),
        (executor.SSM_API_KEY, True),
        (executor.SSM_API_SECRET, True),
        (executor.SSM_STATE, False),
    ]
    assert not executor.BitbankClient.called
    assert not executor.save_state.called
    assert not executor.send_email.called
    assert not executor.reconcile_positions.called


def test_namespace_validation_rejects_non_halt_mode(executor, monkeypatch):
    get_ssm = MagicMock(return_value="normal")
    monkeypatch.setattr(executor, "get_ssm", get_ssm)
    monkeypatch.setattr(executor, "BitbankClient", MagicMock())

    result = executor.lambda_handler({"action": "validate_ssm_namespace"}, MagicMock())

    assert result == {"statusCode": 409, "body": '{"valid": false}'}
    assert get_ssm.call_args_list == [((executor.SSM_MODE,), {"decrypt": False})]
    assert not executor.BitbankClient.called


def test_mode_pause_entry_runs_phase_a_skips_phase_b(executor, monkeypatch):
    _patch_lambda_handler_deps(executor, monkeypatch, "pause_entry")
    result = executor.lambda_handler({"signals": [{"pair": "btc_jpy"}]}, MagicMock())
    assert result["statusCode"] == 200
    assert executor.maintain_positions.called
    assert not executor.place_new_orders.called


def test_mode_invalid_value_falls_back_to_normal(executor, monkeypatch):
    _patch_lambda_handler_deps(executor, monkeypatch, "something_invalid")
    result = executor.lambda_handler({"signals": [{"pair": "btc_jpy"}]}, MagicMock())
    assert result["statusCode"] == 200
    assert executor.place_new_orders.called


# ── 通知レベル分け ────────────────────────────────────────────────────────

def test_notify_trail_updated_does_not_send_email(executor):
    executor.notify_trail_updated("btc_jpy", "long", 9000000.0, 9100000.0)
    assert not executor.send_email.called


# ── 公開統計JSON（004ポートフォリオ非公開ダッシュボード用） ────────────────

def test_update_stats_json_skips_silently_when_bucket_unset(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "")
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)
    executor.update_stats_json()
    assert not mock_put.called


def test_update_stats_json_builds_cumulative_equity_curve(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    trades = [
        {"ts": "2026-06-24T22:45:18+09:00", "pair": "btc_jpy", "direction": "short", "reason": "TP1部分利確", "pnl_jpy": 35.8},
        {"ts": "2026-06-23T17:45:18+09:00", "pair": "eth_jpy", "direction": "short", "reason": "TP1部分利確", "pnl_jpy": 41.4},
        {"ts": "2026-06-25T04:45:18+09:00", "pair": "btc_jpy", "direction": "short", "reason": "トレーリングSL", "pnl_jpy": 176.9},
    ]
    monkeypatch.setattr(executor, "_load_all_trades", MagicMock(return_value=trades))
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)

    executor.update_stats_json()

    assert mock_put.called
    kwargs = mock_put.call_args.kwargs
    assert kwargs["Bucket"] == "zer0-cryptobot-stats-s3"
    assert kwargs["Key"] == "stats.json"
    payload = json.loads(kwargs["Body"])
    assert payload["trade_count"] == 3
    assert payload["total_pnl_jpy"] == 254.1
    # ts昇順に並び替えられ、累計損益が単調に積み上がっていること
    ts_order = [p["ts"] for p in payload["points"]]
    assert ts_order == sorted(ts_order)
    assert payload["points"][0]["cumulative_pnl_jpy"] == 41.4
    assert payload["points"][-1]["cumulative_pnl_jpy"] == 254.1


def test_update_stats_json_includes_position_id(executor, monkeypatch):
    """position_idが無いとportfolio側がポジション単位で勝率を再集計できず、
    レコード単位（TP1部分利確とクローズが別カウント）にフォールバックして
    勝率が実態より低く出てしまうバグの再発防止（2026-08-20発見・修正）。"""
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    trades = [
        {"ts": "2026-06-23T17:45:18+09:00", "pair": "eth_jpy", "direction": "short",
         "reason": "TP1部分利確", "pnl_jpy": 41.4, "position_id": "eth_jpy-123"},
        {"ts": "2026-06-24T21:00:10+09:00", "pair": "eth_jpy", "direction": "short",
         "reason": "トレーリングSL", "pnl_jpy": -2.6, "position_id": "eth_jpy-123"},
    ]
    monkeypatch.setattr(executor, "_load_all_trades", MagicMock(return_value=trades))
    monkeypatch.setattr(executor._s3, "put_object", MagicMock())

    executor.update_stats_json()

    payload = json.loads(executor._s3.put_object.call_args.kwargs["Body"])
    assert all(p["position_id"] == "eth_jpy-123" for p in payload["points"])


def test_record_trade_calls_update_stats_json_on_success(executor, monkeypatch):
    monkeypatch.setattr(executor._s3, "put_object", MagicMock())
    mock_update = MagicMock()
    monkeypatch.setattr(executor, "update_stats_json", mock_update)
    executor.record_trade("btc_jpy", "long", "トレーリングSL", 100.0, 110.0, 0.01, "pos-1")
    assert mock_update.called


def test_record_trade_skips_stats_update_when_s3_write_fails(executor, monkeypatch):
    monkeypatch.setattr(executor._s3, "put_object", MagicMock(side_effect=Exception("s3 down")))
    mock_update = MagicMock()
    monkeypatch.setattr(executor, "update_stats_json", mock_update)
    executor.record_trade("btc_jpy", "long", "トレーリングSL", 100.0, 110.0, 0.01, "pos-1")
    assert not mock_update.called


def test_record_trade_does_not_raise_when_stats_update_fails(executor, monkeypatch):
    """stats.json更新に失敗しても取引処理全体（呼び出し元）が落ちないこと。"""
    monkeypatch.setattr(executor._s3, "put_object", MagicMock())
    monkeypatch.setattr(executor, "update_stats_json", MagicMock(side_effect=Exception("stats write failed")))
    executor.record_trade("btc_jpy", "long", "トレーリングSL", 100.0, 110.0, 0.01, "pos-1")  # 例外が伝播しないこと


# ── 現在ポジションのスナップショット（positions.json） ─────────────────────

def test_update_positions_json_skips_silently_when_bucket_unset(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "")
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)
    executor.update_positions_json({"positions": {}})
    assert not mock_put.called


def test_update_positions_json_excludes_buy_pending(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=11000000.0))
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)

    state = {"positions": {"btc_jpy": {"status": "buy_pending", "direction": "long"}}}
    executor.update_positions_json(state)

    payload = json.loads(mock_put.call_args.kwargs["Body"])
    assert payload["positions"] == []


def test_update_positions_json_active_position_unrealized_pnl(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=10600000.0))
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)

    state = {"positions": {"btc_jpy": {
        "status": "active", "direction": "long", "entry_price": 10493433.0,
        "total_amount": 0.0006, "atr_jpy": 144042.0,
        "tp1_price": 10673486.0, "sl_price": 10133348.0,
    }}}
    executor.update_positions_json(state)

    assert mock_put.call_args.kwargs["Bucket"] == "zer0-cryptobot-stats-s3"
    assert mock_put.call_args.kwargs["Key"] == "positions.json"
    payload = json.loads(mock_put.call_args.kwargs["Body"])
    pos = payload["positions"][0]
    assert pos["pair"] == "btc_jpy"
    assert pos["status"] == "active"
    assert pos["current_price"] == 10600000.0
    assert pos["unrealized_pnl_jpy"] == round((10600000.0 - 10493433.0) * 0.0006, 1)


def test_update_positions_json_trailing_position_locked_pnl(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=10700000.0))
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)

    state = {"positions": {"btc_jpy": {
        "status": "trailing", "direction": "long", "entry_price": 10493433.0,
        "trail_amount": 0.0005, "atr_jpy": 144042.0, "tp1_price": 10673486.0,
        "trail_sl_price": 10688597.0, "highest_price": 10796629.0, "lowest_price": None,
    }}}
    executor.update_positions_json(state)

    payload = json.loads(mock_put.call_args.kwargs["Body"])
    pos = payload["positions"][0]
    assert pos["status"] == "trailing"
    assert pos["trail_sl_price"] == 10688597.0
    # trail_sl_price は entry を上回っており、これに達しても含み益が確保される想定
    assert pos["locked_pnl_jpy"] == round((10688597.0 - 10493433.0) * 0.0005, 1)
    assert pos["locked_pnl_jpy"] > 0
    assert pos["unrealized_pnl_jpy"] == round((10700000.0 - 10493433.0) * 0.0005, 1)


def test_update_positions_json_skips_pair_on_price_fetch_failure(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(side_effect=Exception("timeout")))
    mock_put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", mock_put)

    state = {"positions": {"btc_jpy": {"status": "active", "direction": "long", "entry_price": 100.0, "total_amount": 1.0}}}
    executor.update_positions_json(state)

    payload = json.loads(mock_put.call_args.kwargs["Body"])
    assert payload["positions"] == []


# ── 2026-10-02: 取引記録を bitbank 実績（手数料・利息控除後）と1円単位で一致させる ──
# 実データ: 2026-09-27 SOL/JPY ロングのトレーリングSL（order_id=60895638803）の約定履歴
_SOL_TRAIL_FILL = {
    "trade_id": 1, "pair": "sol_jpy", "order_id": 60895638803, "side": "sell",
    "position_side": "long", "type": "stop_limit", "amount": "0.2466", "price": "19267.1",
    "maker_taker": "taker", "fee_amount_base": "0", "fee_amount_quote": "11.3357",
    "fee_occurred_amount_quote": "5.7015", "profit_loss": "41.034358368000560",
    "interest": "3.75611255999999960", "executed_at": 1790516100000,
}


def test_fetch_exact_close_uses_bitbank_profit_loss(executor):
    bb = MagicMock()
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    r = executor.fetch_exact_close(bb, "sol_jpy", 60895638803)
    assert r["pnl_jpy"] == 41.0344          # 価格差 (19267.1-19039.5)*0.2466=56.1 ではなく実損益
    assert r["fee_jpy"] == 11.3357
    assert r["interest_jpy"] == 3.7561
    assert r["gross_pnl_jpy"] == 56.1262
    assert r["exit_price"] == 19267.1 and r["amount"] == 0.2466


def test_fetch_exact_close_sums_multiple_fills_and_ignores_other_orders(executor):
    a = dict(_SOL_TRAIL_FILL, amount="0.1", profit_loss="10.5", fee_amount_quote="1", interest="0.5", price="100")
    b = dict(_SOL_TRAIL_FILL, amount="0.3", profit_loss="-2.25", fee_amount_quote="2", interest="0", price="200")
    other = dict(_SOL_TRAIL_FILL, order_id=1, profit_loss="999")
    bb = MagicMock()
    bb.get_trade_history.return_value = [a, b, other]
    r = executor.fetch_exact_close(bb, "sol_jpy", 60895638803)
    assert r["pnl_jpy"] == 8.25 and r["fee_jpy"] == 3.0 and r["fill_count"] == 2
    assert r["exit_price"] == 175.0          # 数量加重平均


def test_fetch_exact_close_returns_none_without_fills_or_on_error(executor):
    bb = MagicMock()
    bb.get_trade_history.return_value = []
    assert executor.fetch_exact_close(bb, "sol_jpy", 1) is None
    bb.get_trade_history.side_effect = Exception("boom")
    assert executor.fetch_exact_close(bb, "sol_jpy", 1) is None
    assert executor.fetch_exact_close(None, "sol_jpy", 1) is None


def test_record_trade_writes_bitbank_actual_pnl(executor, monkeypatch):
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    monkeypatch.setattr(executor, "update_stats_json", MagicMock())
    bb = MagicMock()
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    executor.record_trade("sol_jpy", "long", "トレーリングSL", 19039.5, 19267.1, 0.2466,
                          "sol_jpy-1790337610", bb=bb, order_id=60895638803)
    rec = json.loads(put.call_args.kwargs["Body"])
    assert rec["pnl_jpy"] == 41.0344 and rec["pnl_source"] == "bitbank"
    assert rec["order_id"] == 60895638803 and rec["estimated"] is False


def test_record_trade_marks_pending_when_history_not_ready(executor, monkeypatch):
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    monkeypatch.setattr(executor, "update_stats_json", MagicMock())
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    bb = MagicMock()
    bb.get_trade_history.return_value = []
    executor.record_trade("sol_jpy", "long", "トレーリングSL", 19039.5, 19267.1, 0.2466,
                          "p", bb=bb, order_id=60895638803)
    rec = json.loads(put.call_args.kwargs["Body"])
    assert rec["pnl_source"] == "pending" and rec["pnl_jpy"] == 56.1
    assert bb.get_trade_history.call_count == 2   # 1回だけ再取得


def test_reconcile_trade_records_overwrites_pending_with_actual(executor, monkeypatch):
    pending = {"ts": "2026-09-27T22:45:18+09:00", "pair": "sol_jpy", "direction": "long",
               "reason": "トレーリングSL", "pnl_jpy": 56.1, "order_id": 60895638803,
               "pnl_source": "pending", "estimated": False}
    done = dict(pending, pnl_source="bitbank", pnl_jpy=1.0)
    pages = [{"Contents": [{"Key": "cryptobot/trades/a.json"}, {"Key": "cryptobot/trades/b.json"}]}]
    paginator = MagicMock(); paginator.paginate.return_value = pages
    monkeypatch.setattr(executor._s3, "get_paginator", MagicMock(return_value=paginator))
    bodies = {"cryptobot/trades/a.json": pending, "cryptobot/trades/b.json": done}
    monkeypatch.setattr(executor._s3, "get_object",
                        MagicMock(side_effect=lambda Bucket, Key: {"Body": MagicMock(read=lambda: json.dumps(bodies[Key]).encode())}))
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    monkeypatch.setattr(executor, "update_stats_json", MagicMock())
    bb = MagicMock()
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    assert executor.reconcile_trade_records(bb) == 1
    assert put.call_args.kwargs["Key"] == "cryptobot/trades/a.json"
    rec = json.loads(put.call_args.kwargs["Body"])
    assert rec["pnl_jpy"] == 41.0344 and rec["pnl_source"] == "bitbank"


def test_update_stats_json_includes_fee_interest_breakdown(executor, monkeypatch):
    monkeypatch.setattr(executor, "STATS_BUCKET", "zer0-cryptobot-stats-s3")
    trades = [
        {"ts": "2026-09-27T22:45:18+09:00", "pair": "sol_jpy", "direction": "long", "reason": "トレーリングSL",
         "pnl_jpy": 41.0344, "gross_pnl_jpy": 56.1262, "fee_jpy": 11.3357, "interest_jpy": 3.7561, "pnl_source": "bitbank"},
        {"ts": "2026-09-28T00:00:00+09:00", "pair": "btc_jpy", "direction": "long", "reason": "緊急決済",
         "pnl_jpy": -10.0, "pnl_source": "pending"},
    ]
    monkeypatch.setattr(executor, "_load_all_trades", MagicMock(return_value=trades))
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    executor.update_stats_json()
    payload = json.loads(put.call_args.kwargs["Body"])
    assert payload["total_pnl_jpy"] == 31.0344
    assert payload["total_fee_jpy"] == 11.3357 and payload["total_interest_jpy"] == 3.7561
    assert payload["total_gross_pnl_jpy"] == 56.1262
    assert payload["points"][0]["fee_jpy"] == 11.3357
    assert payload["points"][1]["fee_jpy"] is None and payload["points"][1]["pnl_source"] == "pending"


# ── 2026-10-02 Fableレビュー指摘の修正 ──
def test_fetch_exact_close_returns_none_when_fills_are_partial(executor):
    bb = MagicMock()
    bb.get_trade_history.return_value = [dict(_SOL_TRAIL_FILL, amount="0.1")]
    # 決済数量 0.2466 に対し履歴は 0.1 しか出ていない → 確定させない
    assert executor.fetch_exact_close(bb, "sol_jpy", 60895638803, 0.2466) is None
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    assert executor.fetch_exact_close(bb, "sol_jpy", 60895638803, 0.2466)["pnl_jpy"] == 41.0344


def test_record_trade_uses_order_id_key_for_idempotency(executor, monkeypatch):
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    monkeypatch.setattr(executor, "update_stats_json", MagicMock())
    bb = MagicMock()
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    for _ in range(2):
        executor.record_trade("sol_jpy", "long", "トレーリングSL", 19039.5, 19267.1, 0.2466,
                              "p", bb=bb, order_id=60895638803)
    keys = {c.kwargs["Key"] for c in put.call_args_list}
    assert keys == {"cryptobot/trades/order_sol_jpy_60895638803.json"}


def test_reconcile_continues_after_broken_object(executor, monkeypatch):
    pending = {"ts": "2026-09-27T22:45:18+09:00", "pair": "sol_jpy", "direction": "long",
               "reason": "トレーリングSL", "pnl_jpy": 56.1, "order_id": 60895638803,
               "expected_amount": 0.2466, "pnl_source": "pending", "estimated": False}
    pages = [{"Contents": [{"Key": "cryptobot/trades/broken.json"}, {"Key": "cryptobot/trades/a.json"}]}]
    paginator = MagicMock(); paginator.paginate.return_value = pages
    monkeypatch.setattr(executor._s3, "get_paginator", MagicMock(return_value=paginator))
    bodies = {"cryptobot/trades/broken.json": b"{not json", "cryptobot/trades/a.json": json.dumps(pending).encode()}
    monkeypatch.setattr(executor._s3, "get_object",
                        MagicMock(side_effect=lambda Bucket, Key: {"Body": MagicMock(read=lambda: bodies[Key])}))
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    monkeypatch.setattr(executor, "update_stats_json", MagicMock())
    bb = MagicMock()
    bb.get_trade_history.return_value = [_SOL_TRAIL_FILL]
    assert executor.reconcile_trade_records(bb) == 1


def test_reconcile_alerts_once_for_stale_pending(executor, monkeypatch):
    pending = {"ts": "2026-09-01T00:00:00+09:00", "pair": "sol_jpy", "direction": "long",
               "reason": "トレーリングSL", "pnl_jpy": 56.1, "order_id": 1,
               "expected_amount": 0.2466, "pnl_source": "pending", "estimated": False}
    pages = [{"Contents": [{"Key": "cryptobot/trades/a.json"}]}]
    paginator = MagicMock(); paginator.paginate.return_value = pages
    monkeypatch.setattr(executor._s3, "get_paginator", MagicMock(return_value=paginator))
    monkeypatch.setattr(executor._s3, "get_object",
                        MagicMock(return_value={"Body": MagicMock(read=lambda: json.dumps(pending).encode())}))
    put = MagicMock()
    monkeypatch.setattr(executor._s3, "put_object", put)
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    bb = MagicMock()
    bb.get_trade_history.return_value = []
    executor.reconcile_trade_records(bb)
    assert mail.call_count == 1
    assert json.loads(put.call_args.kwargs["Body"])["pending_alerted"] is True


def _account_bb(balance: str):
    bb = MagicMock()
    bb.get_assets.return_value = {"jpy": {"asset": "jpy", "onhand_amount": balance}}
    bb.get_margin_positions.return_value = [
        {"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0157",
         "unrealized_fee_amount": "8.0917", "unrealized_interest_amount": "1.5"},
        {"pair": "btc_jpy", "position_side": "long", "open_amount": "0.0000",
         "unrealized_fee_amount": "0", "unrealized_interest_amount": "0"},
    ]
    return bb


def test_check_account_matches_when_balance_equals_records(executor, monkeypatch):
    monkeypatch.setattr(executor, "_load_all_trades",
                        MagicMock(return_value=[{"pnl_jpy": 1321.8268, "pnl_source": "bitbank"}]))
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    bal = executor.ACCOUNT_CAPITAL_JPY + executor.Decimal("1321.8268") + executor.EXCLUDED_PNL_JPY
    r = executor.check_account(_account_bb(str(bal)))
    assert r["matched"] is True and r["diff_jpy"] == 0.0
    assert r["unrealized"] == {"eth_jpy:long": {"fee_jpy": 8.0917, "interest_jpy": 1.5}}
    mail.assert_not_called()


def test_check_account_alerts_once_on_unrecorded_close(executor, monkeypatch):
    monkeypatch.setattr(executor, "_load_all_trades",
                        MagicMock(return_value=[{"pnl_jpy": 1321.8268, "pnl_source": "bitbank"}]))
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    stored = {}
    monkeypatch.setattr(executor._s3, "put_object",
                        MagicMock(side_effect=lambda **kw: stored.update({kw["Key"]: kw["Body"]})))
    def _get(Bucket, Key):
        if Key not in stored:
            raise Exception("NoSuchKey")
        return {"Body": MagicMock(read=lambda: stored[Key])}
    monkeypatch.setattr(executor._s3, "get_object", MagicMock(side_effect=_get))
    bal = executor.ACCOUNT_CAPITAL_JPY + executor.Decimal("1321.8268") + executor.EXCLUDED_PNL_JPY - 100
    bb = _account_bb(str(bal))       # 100円の記録漏れ
    r = executor.check_account(bb)
    assert r["matched"] is False and round(r["diff_jpy"], 2) == -100.0
    executor.check_account(bb)       # 同じ差額では再送しない
    assert mail.call_count == 1


def test_check_account_skips_alert_while_pending(executor, monkeypatch):
    monkeypatch.setattr(executor, "_load_all_trades",
                        MagicMock(return_value=[{"pnl_jpy": 50.0, "pnl_source": "pending"}]))
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    executor.check_account(_account_bb("11184.7337"))
    mail.assert_not_called()


def test_net_pnl_lines_in_notification(executor):
    rec = {"pnl_source": "bitbank", "pnl_jpy": 41.0344, "fee_jpy": 11.3357, "interest_jpy": 3.7561}
    assert "+41.03円" in executor._net_pnl_lines(rec)
    assert "反映待ち" in executor._net_pnl_lines({"pnl_source": "pending"})
    assert executor._net_pnl_lines(None) == ""


def test_sl_after_tp1_path_records_both_tp1_and_sl(executor, monkeypatch):
    """TP1約定→旧SLキャンセル失敗→SLも約定済み、の経路で TP1 分の記録が抜けないこと"""
    pos = {"status": "active", "direction": "long", "position_id": "eth_jpy-1", "entry_price": 429501.0,
           "atr_jpy": 6595.2, "tp1_order_id": 11, "sl_order_id": 22, "tp1_price": 437745.0,
           "tp1_amount": 0.0047, "trail_amount": 0.011, "sl_price": 413013.0, "total_amount": 0.0157}
    state = {"positions": {"eth_jpy": pos}}
    bb = MagicMock()
    orders = {11: {"status": "FULLY_FILLED", "average_price": "437745", "executed_amount": "0.0047"},
              22: {"status": "FULLY_FILLED", "average_price": "413013", "executed_amount": "0.011"}}
    bb.get_order.side_effect = lambda pair, oid: orders[oid]
    bb.cancel_order.side_effect = Exception("already filled")
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    monkeypatch.setattr(executor, "notify_close", MagicMock())
    monkeypatch.setattr(executor, "get_available_margin", MagicMock(return_value=10000))
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=413000))
    monkeypatch.setattr(executor, "send_email", MagicMock())
    executor.maintain_positions(bb, state, {})
    reasons = [c.args[2] for c in rec.call_args_list]
    assert reasons == ["TP1部分利確", "SL（TP1後）"]
    assert rec.call_args_list[0].kwargs["order_id"] == 11
    assert rec.call_args_list[1].kwargs["order_id"] == 22


def test_record_partial_fill_after_cancel_records_only_when_filled(executor, monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(executor, "record_trade", rec)
    bb = MagicMock()
    pos = {"entry_price": 100.0, "position_id": "x"}
    bb.get_order.return_value = {"status": "CANCELED_PARTIALLY_FILLED", "average_price": "110", "executed_amount": "0.002"}
    assert executor.record_partial_fill_after_cancel(bb, "eth_jpy", "long", "r", pos, 5) == 0.002
    assert rec.call_args.kwargs["order_id"] == 5 and rec.call_args.args[5] == 0.002
    rec.reset_mock()
    bb.get_order.return_value = {"status": "CANCELED_UNFILLED", "average_price": "0", "executed_amount": "0"}
    assert executor.record_partial_fill_after_cancel(bb, "eth_jpy", "long", "r", pos, 5) == 0.0
    rec.assert_not_called()


# ── 2026-10-02: レバレッジ対策（同時2件・1件=受入保証金×0.6） ──
def test_position_limits_keep_margin_ratio_above_call_line(executor):
    assert executor.MAX_POSITIONS == 2
    total = executor.MAX_POSITIONS * executor.POSITION_EQUITY_RATIO      # 資金比の建玉合計
    worst = (1 - total * 0.12) / (total * 0.88)                          # 2件同時に過去最大12%で損切り後の保証金率
    assert worst > executor.MARGIN_EMRG_PCT / 100                        # 自ら手仕舞うラインより上
    assert executor.MARGIN_EMRG_PCT > 50                                 # 追証の前に自ら手仕舞う


def test_get_available_margin_uses_short_side(executor):
    bb = MagicMock()
    bb.get_margin_status.return_value = {"available_balances": [{"pair": "eth_jpy", "long": "100", "short": "40"}]}
    assert executor.get_available_margin(bb, "eth_jpy", "short") == 40.0
    assert executor.get_available_margin(bb, "eth_jpy") == 100.0


def test_get_margin_equity_returns_zero_on_failure(executor):
    bb = MagicMock()
    bb.get_margin_status.return_value = {"total_margin_balance": "11270.2170"}
    assert executor.get_margin_equity(bb) == 11270.217
    bb.get_margin_status.side_effect = Exception("down")
    assert executor.get_margin_equity(bb) == 0.0


# ── 2026-10-02: SL未約定の安全網 ──
def test_sl_needs_rescue_conditions(executor):
    now = 1_790_000_000.0
    assert executor._sl_needs_rescue({"status": "INACTIVE"}, now) is None
    assert executor._sl_needs_rescue({"status": "UNFILLED"}, now) is None             # 未発動の指値
    assert executor._sl_needs_rescue({"status": "UNFILLED", "triggered_at": (now - 60) * 1000}, now) is None
    assert executor._sl_needs_rescue({"status": "UNFILLED", "triggered_at": (now - 300) * 1000}, now)
    assert executor._sl_needs_rescue({"status": "PARTIALLY_FILLED", "triggered_at": now - 300}, now)
    assert executor._sl_needs_rescue({"status": "CANCELED_UNFILLED"}, now)
    assert executor._sl_needs_rescue({"status": "REJECTED"}, now)
    assert executor._sl_needs_rescue({"status": "FULLY_FILLED"}, now) is None


def _rescue_env(executor, monkeypatch, order_status_after_cancel, open_amount="0.0110"):
    bb = MagicMock()
    bb.get_order.return_value = {"status": order_status_after_cancel, "average_price": "0", "executed_amount": "0"}
    after = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0000"}]
    bb.get_margin_positions.side_effect = [[{"pair": "eth_jpy", "position_side": "long", "open_amount": open_amount}]] + [after] * 10
    bb.create_market_order.return_value = {"order_id": 999}
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=410000.0))
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    pos = {"direction": "long", "entry_price": 429501.0, "position_id": "p",
           "tp1_order_id": 11, "sl_order_id": 22}
    return bb, rec, mail, pos


def test_rescue_close_market_closes_actual_open_amount(executor, monkeypatch):
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "CANCELED_UNFILLED")
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is True
    bb.create_market_order.assert_called_once_with("eth_jpy", "0.0110", "sell", position_side="long")
    assert rec.call_args.kwargs["order_id"] == 999
    assert "rescue_pending" not in pos


def test_rescue_close_does_not_market_close_while_order_still_alive(executor, monkeypatch):
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "INACTIVE")
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is False
    bb.create_market_order.assert_not_called()       # 二重決済しない
    assert pos["rescue_pending"] is True and mail.call_count == 1


def test_rescue_close_marks_pending_when_market_order_fails(executor, monkeypatch):
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "CANCELED_UNFILLED")
    bb.create_market_order.side_effect = Exception("70020 CB中")
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is False
    assert pos["rescue_pending"] is True


def test_rescue_close_no_position_left(executor, monkeypatch):
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "CANCELED_UNFILLED", open_amount="0.0000")
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is True
    bb.create_market_order.assert_not_called()


def test_create_order_stop_type_omits_price(executor, monkeypatch):
    bb = executor.BitbankClient("k", "s")
    sent = {}
    monkeypatch.setattr(bb, "_post", lambda path, body: sent.update(body) or {"success": 1, "data": {"order_id": 1}})
    monkeypatch.setattr(executor, "SL_ORDER_TYPE", "stop")
    bb.create_order("eth_jpy", "0.0110", "411000", "sell", position_side="long", trigger_price="413000")
    assert sent["type"] == "stop" and "price" not in sent and sent["trigger_price"] == "413000"
    monkeypatch.setattr(executor, "SL_ORDER_TYPE", "stop_limit")
    bb.create_order("eth_jpy", "0.0110", "411000", "sell", position_side="long", trigger_price="413000")
    assert sent["type"] == "stop_limit" and sent["price"] == "411000"
    bb.create_order("eth_jpy", "0.0047", "437745", "sell", position_side="long")
    assert sent["type"] == "limit" and sent["price"] == "437745"


def test_trailing_sl_rejected_after_tp1_triggers_rescue(executor, monkeypatch):
    """TP1約定後に建値トレールSLが60018で拒否されたら、TP1を記録して成行救済する"""
    pos = {"status": "active", "direction": "long", "position_id": "eth_jpy-1", "entry_price": 429501.0,
           "atr_jpy": 6595.2, "tp1_order_id": 11, "sl_order_id": 22, "tp1_price": 437745.0,
           "tp1_amount": 0.0047, "trail_amount": 0.011, "sl_price": 413013.0, "total_amount": 0.0157}
    state = {"positions": {"eth_jpy": pos}}
    bb = MagicMock()
    bb.get_order.side_effect = lambda pair, oid: {11: {"status": "FULLY_FILLED", "average_price": "437745",
                                                        "executed_amount": "0.0047"}}.get(oid, {"status": "CANCELED_UNFILLED"})
    bb.create_order.side_effect = Exception("create_order失敗: code=60018")
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    rescue = MagicMock(return_value=True)
    monkeypatch.setattr(executor, "rescue_close", rescue)
    monkeypatch.setattr(executor, "send_email", MagicMock())
    out = executor.maintain_positions(bb, state, {})
    assert rec.call_args_list[0].args[2] == "TP1部分利確"
    assert rescue.called and "tp1_order_id" not in rescue.call_args.args[2]
    assert "eth_jpy" not in out["positions"]


def test_stop_order_live_test_is_blocked_without_force_flag(executor, monkeypatch):
    monkeypatch.setattr(executor, "FORCE_TEST_ENABLED", False)
    r = executor.lambda_handler({"action": "stop_order_live_test"}, None)
    assert r["statusCode"] == 403



# ── 2026-10-02 Fable第3回レビューの修正 ──
def test_rescue_close_records_filled_orders_and_closes_rest(executor, monkeypatch):
    """取消後に約定済み(FULLY_FILLED)だった注文は記録し、保留にせず残りの建玉を決済する"""
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "CANCELED_UNFILLED", open_amount="0.0047")
    bb.get_order.side_effect = lambda pair, oid: (
        {"status": "FULLY_FILLED", "average_price": "413000", "executed_amount": "0.011"} if oid == 22
        else {"status": "CANCELED_UNFILLED", "average_price": "0", "executed_amount": "0"})
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is True
    reasons = [c.args[2] for c in rec.call_args_list]
    assert reasons == ["損切り（SL約定）", "損切り（SL未約定→成行救済）"]
    bb.create_market_order.assert_called_once_with("eth_jpy", "0.0047", "sell", position_side="long")
    assert pos["sl_order_id"] is None and "rescue_pending" not in pos


def test_rescue_close_keeps_pending_when_market_close_is_partial(executor, monkeypatch):
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "CANCELED_UNFILLED")
    left = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0050"}]
    bb.get_margin_positions.side_effect = [[{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0110"}]] + [left] * 10
    assert executor.rescue_close(bb, "eth_jpy", pos, "test", {"amount_prec": 4, "price_prec": 0}) is False
    assert pos["rescue_pending"] is True
    assert rec.call_args.args[5] == 0.006      # 実際に約定した数量で記録


def test_cancel_order_raises_on_api_failure(executor, monkeypatch):
    bb = executor.BitbankClient("k", "s")
    monkeypatch.setattr(bb, "_post", lambda path, body: {"success": 0, "data": {"code": 50010}})
    import pytest
    with pytest.raises(Exception):
        bb.cancel_order("eth_jpy", 1)
    monkeypatch.setattr(bb, "_post", lambda path, body: {"success": 1, "data": {"order_id": 1}})
    assert bb.cancel_order("eth_jpy", 1)["order_id"] == 1


def test_get_open_amount(executor):
    bb = MagicMock()
    bb.get_margin_positions.return_value = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0157"},
                                            {"pair": "eth_jpy", "position_side": "short", "open_amount": "0"}]
    assert executor.get_open_amount(bb, "eth_jpy", "long") == 0.0157
    assert executor.get_open_amount(bb, "btc_jpy", "long") == 0.0
    bb.get_margin_positions.side_effect = Exception("down")
    assert executor.get_open_amount(bb, "eth_jpy", "long") is None


def test_emergency_close_uses_actual_open_amount(executor, monkeypatch):
    pos = {"status": "active", "direction": "long", "entry_price": 429501.0, "position_id": "p",
           "total_amount": 0.0157, "tp1_order_id": 11, "sl_order_id": 22}
    state = {"positions": {"eth_jpy": pos}}
    bb = MagicMock()
    bb.get_order.return_value = {"status": "CANCELED_UNFILLED", "average_price": "0", "executed_amount": "0"}
    bb.get_margin_positions.return_value = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0110"}]
    bb.create_market_order.return_value = {"order_id": 5}
    monkeypatch.setattr(executor, "record_trade", MagicMock())
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=400000.0))
    executor._emergency_close_all(bb, state)
    bb.create_market_order.assert_called_once_with("eth_jpy", "0.0110", "sell", position_side="long")


def test_sl_filled_with_tp1_also_filled_records_tp1_and_skips_residual(executor, monkeypatch):
    """同じ30分の間に SL と TP1 の両方が約定 → TP1を記録し、建玉が残っていなければ成行しない"""
    pos = {"status": "active", "direction": "long", "position_id": "eth_jpy-1", "entry_price": 429501.0,
           "atr_jpy": 6595.2, "tp1_order_id": 11, "sl_order_id": 22, "tp1_price": 437745.0,
           "tp1_amount": 0.0047, "trail_amount": 0.011, "sl_price": 413013.0, "total_amount": 0.0157}
    state = {"positions": {"eth_jpy": pos}}
    bb = MagicMock()
    orders = {11: {"status": "UNFILLED"},
              22: {"status": "FULLY_FILLED", "average_price": "413013", "executed_amount": "0.011"}}
    def _get(pair, oid):
        return orders[oid]
    bb.get_order.side_effect = _get
    def _cancel(pair, oid):
        orders[11] = {"status": "FULLY_FILLED", "average_price": "437745", "executed_amount": "0.0047"}
        raise Exception("cancel_order失敗 code=50010")
    bb.cancel_order.side_effect = _cancel
    bb.get_margin_positions.return_value = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0000"}]
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    monkeypatch.setattr(executor, "notify_close", MagicMock())
    monkeypatch.setattr(executor, "get_available_margin", MagicMock(return_value=10000))
    monkeypatch.setattr(executor, "send_email", MagicMock())
    executor.maintain_positions(bb, state, {})
    reasons = [c.args[2] for c in rec.call_args_list]
    assert reasons == ["TP1部分利確", "損切り（SL約定）"]
    bb.create_market_order.assert_not_called()


def _capture_ses(executor, monkeypatch, token="tok/en+1"):
    sent = []
    ssm = MagicMock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": token}}
    monkeypatch.setattr(executor, "_ssm", ssm)
    monkeypatch.setattr(executor, "_stats_url_cache", None)
    ses = MagicMock()
    ses.send_email.side_effect = lambda **k: sent.append(k)
    monkeypatch.setattr(executor, "_ses", ses)
    monkeypatch.setattr(executor, "send_email", executor._real_send_email)
    return sent


def test_tp1_mail_has_single_admin_link(executor, monkeypatch):
    sent = _capture_ses(executor, monkeypatch)
    monkeypatch.setattr(executor, "TRADE_MAIL_ENABLED", True)
    executor.notify_trail_started("eth_jpy", "long", 500000, 510000, 512000, 3000, None)
    text = sent[0]["Message"]["Body"]["Text"]["Data"]
    html = sent[0]["Message"]["Body"]["Html"]["Data"]
    admin_url = executor.PORTFOLIO_STATS_URL + "?admin=tok%2Fen%2B1"
    assert text.count(executor.PORTFOLIO_STATS_URL) == 1
    assert admin_url in text
    assert html.count('href="' + admin_url) == 1


def test_info_mail_footer_has_admin_link(executor, monkeypatch):
    sent = _capture_ses(executor, monkeypatch)
    executor.send_email("【CryptoBot】テスト", "本文のみ")
    text = sent[0]["Message"]["Body"]["Text"]["Data"]
    assert text.count(executor.PORTFOLIO_STATS_URL + "?admin=tok%2Fen%2B1") == 1


def test_stats_url_falls_back_without_token(executor, monkeypatch):
    _capture_ses(executor, monkeypatch)
    executor._ssm.get_parameter.side_effect = Exception("AccessDenied")
    assert executor.stats_url() == executor.PORTFOLIO_STATS_URL


# ── 2026-11-15 入金前監査（Fable）の指摘1〜10の修正 ──
_CFG = {"amount_prec": 4, "price_prec": 0}


def test_load_state_returns_empty_only_when_parameter_missing(executor, monkeypatch):
    class ParameterNotFound(Exception):
        pass
    monkeypatch.setattr(executor, "get_ssm", MagicMock(side_effect=ParameterNotFound("x")))
    assert executor.load_state() == {"positions": {}}


def test_load_state_raises_on_transient_error_or_broken_json(executor, monkeypatch):
    monkeypatch.setattr(executor, "get_ssm", MagicMock(side_effect=Exception("ThrottlingException")))
    with pytest.raises(executor.StateLoadError):
        executor.load_state()
    monkeypatch.setattr(executor, "get_ssm", MagicMock(return_value="{broken"))
    with pytest.raises(executor.StateLoadError):
        executor.load_state()
    monkeypatch.setattr(executor, "get_ssm", MagicMock(return_value='{"x": 1}'))
    with pytest.raises(executor.StateLoadError):
        executor.load_state()


def test_handler_does_not_overwrite_state_when_load_fails(executor, monkeypatch):
    _patch_lambda_handler_deps(executor, monkeypatch, "normal")
    monkeypatch.setattr(executor, "reconcile_trade_records", MagicMock())
    monkeypatch.setattr(executor, "load_state", MagicMock(side_effect=executor.StateLoadError("x")))
    r = executor.lambda_handler({"signals": [{"pair": "btc_jpy"}]}, MagicMock())
    assert r["statusCode"] == 500
    assert not executor.save_state.called
    assert not executor.place_new_orders.called
    assert "中止" in executor.send_email.call_args.args[0]


def _entry_env(executor, monkeypatch):
    bb = MagicMock()
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    monkeypatch.setattr(executor, "get_available_margin", MagicMock(return_value=100000.0))
    monkeypatch.setattr(executor, "get_margin_equity", MagicMock(return_value=60000.0))
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=10_000_000.0))
    monkeypatch.setattr(executor, "save_state_now", MagicMock())
    monkeypatch.setattr(executor, "record_trade", MagicMock(return_value={"pnl_source": "pending"}))
    sig = [{"pair": "btc_jpy", "side": "short", "binance_price": 65000.0, "atr": 1000.0}]
    return bb, sig


def test_entry_is_saved_to_state_even_if_verify_fails(executor, monkeypatch):
    """指摘1: 発注後の確認に失敗しても state に載せ、次回 Phase A に拾わせる"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    bb.get_order.side_effect = Exception("timeout")
    out = executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert out["positions"]["btc_jpy"]["status"] == "buy_pending"
    assert out["positions"]["btc_jpy"]["buy_order_id"] == 555
    assert executor.save_state_now.called


def test_entry_exception_closes_position_that_was_actually_filled(executor, monkeypatch):
    """指摘2: 発注が例外でも建玉が増えていたら、増えた分だけ成行で決済する（手動建玉は残す）"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.side_effect = [
        [{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.0010"}],   # 発注前（手動分）
        [{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.0046"}],   # 発注後
    ]
    bb.create_market_order.side_effect = [Exception("timed out"), {"order_id": 777}]
    out = executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert bb.create_market_order.call_args_list[1].args == ("btc_jpy", "0.0036", "buy")
    assert bb.create_market_order.call_args_list[1].kwargs == {"position_side": "short"}
    assert executor.record_trade.call_args.kwargs["order_id"] == 777
    assert "btc_jpy" not in out["positions"]


def test_entry_exception_without_fill_does_not_close(executor, monkeypatch):
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.side_effect = Exception("code=70009")
    executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert bb.create_market_order.call_count == 1


def test_entry_canceled_unfilled_is_removed_from_state(executor, monkeypatch):
    """指摘8: 約定ゼロで取り消された成行は枠を塞がない"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    bb.get_order.return_value = {"status": "CANCELED_UNFILLED", "average_price": "0", "executed_amount": "0"}
    out = executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert out["positions"] == {}


def test_entry_waits_for_full_fill_before_placing_sl(executor, monkeypatch):
    """指摘7: PARTIALLY_FILLED の途中で確定せず、全量約定の数量で SL/TP1 を出す"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    part = {"status": "PARTIALLY_FILLED", "average_price": "10000000", "executed_amount": "0.0010"}
    full = {"status": "FULLY_FILLED", "average_price": "10000000", "executed_amount": "0.0036"}
    bb.get_order.side_effect = [part, part, full] + [full] * 10
    applied = MagicMock()
    monkeypatch.setattr(executor, "_apply_and_notify_fill", applied)
    executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert applied.call_args.args[3]["executed_amount"] == "0.0036"


def _filled_pos():
    return {"status": "buy_pending", "direction": "short", "position_id": "btc_jpy-1", "buy_order_id": 555,
            "buy_timestamp": 0, "entry_price_signal": 65000.0, "atr_jpy": 1000.0,
            "tp1_order_id": None, "sl_order_id": None}


_FILL = {"status": "FULLY_FILLED", "average_price": "10000000", "executed_amount": "0.0036"}


def test_sl_is_placed_before_tp1(executor, monkeypatch):
    """指摘4: SLを先に出す。order_idはverifyの前にposへ書く（指摘6）"""
    bb = MagicMock()
    bb.create_order.side_effect = [{"order_id": 1}, {"order_id": 2}]
    pos = _filled_pos()
    executor._apply_entry_fill(bb, "btc_jpy", pos, _FILL, _CFG)
    first = bb.create_order.call_args_list[0]
    assert first.kwargs.get("trigger_price")             # 1件目がSL（逆指値）
    assert pos["sl_order_id"] == 1 and pos["tp1_order_id"] == 2 and pos["status"] == "active"


def test_sl_order_id_kept_when_verify_fails(executor, monkeypatch):
    bb = MagicMock()
    bb.create_order.return_value = {"order_id": 1}
    bb.get_order.side_effect = Exception("timeout")
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    pos = _filled_pos()
    with pytest.raises(executor.OrderVerificationError):
        executor._apply_entry_fill(bb, "btc_jpy", pos, _FILL, _CFG)
    assert pos["sl_order_id"] == 1                        # 次回SLを二重発注しない


def test_sl_failure_alerts_and_rescues_after_repeated_failures(executor, monkeypatch):
    """指摘4: SL発注失敗は即🚨メール。SL_FAIL_RESCUE_COUNT回続いたら成行で決済"""
    bb = MagicMock()
    bb.get_order.return_value = _FILL
    bb.create_order.side_effect = Exception("code=70023")
    rescue = MagicMock(return_value=True)
    monkeypatch.setattr(executor, "rescue_close", rescue)
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    pos = _filled_pos()
    state = {"positions": {"btc_jpy": pos}}
    for i in range(executor.SL_FAIL_RESCUE_COUNT - 1):
        executor.maintain_positions(bb, state, {})
        assert not rescue.called
    assert "🚨SL発注失敗" in mail.call_args.args[0]
    assert all("メンテナンスエラー" not in c.args[0] for c in mail.call_args_list)
    out = executor.maintain_positions(bb, state, {})
    assert rescue.called and "btc_jpy" not in out["positions"]
    assert bb.create_order.call_count == executor.SL_FAIL_RESCUE_COUNT   # TP1は一度も出していない


def _trail_pos():
    return {"status": "trailing", "direction": "long", "entry_price": 100.0, "atr_jpy": 10.0,
            "position_id": "p", "trail_amount": 0.01, "trail_sl_order_id": 9, "trail_sl_price": 100.0,
            "highest_price": 110.0}


def test_replace_trail_sl_falls_back_to_old_price(executor, monkeypatch):
    """指摘5: 新価格で出せなければ同じ回のうちに旧価格で出し直す"""
    bb = MagicMock()
    bb.create_order.side_effect = [Exception("70023"), {"order_id": 42}]
    pos = _trail_pos()
    assert executor._replace_trail_sl(bb, "eth_jpy", pos, _CFG, 105.0) is False
    assert pos["trail_sl_order_id"] == 42 and pos["trail_sl_price"] == 100.0
    assert bb.create_order.call_args.kwargs["trigger_price"] == "100"


def test_replace_trail_sl_alerts_when_both_fail(executor, monkeypatch):
    bb = MagicMock()
    bb.create_order.side_effect = Exception("70023")
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    pos = _trail_pos()
    pos["trail_sl_order_id"] = None
    assert executor._replace_trail_sl(bb, "eth_jpy", pos, _CFG, 105.0) is False
    assert pos["trail_sl_order_id"] is None and "🚨SL不在" in mail.call_args.args[0]


def test_trailing_update_uses_fallback_in_maintain_positions(executor, monkeypatch):
    bb = MagicMock()
    bb.get_order.return_value = {"status": "INACTIVE"}
    bb.create_order.side_effect = [Exception("70023"), {"order_id": 42}]
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=130.0))
    monkeypatch.setattr(executor, "record_partial_fill_after_cancel", MagicMock())
    state = {"positions": {"eth_jpy": _trail_pos()}}
    out = executor.maintain_positions(bb, state, {})
    p = out["positions"]["eth_jpy"]
    assert p["trail_sl_order_id"] == 42 and p["trail_sl_price"] == 100.0 and p["highest_price"] == 110.0


def test_tp1_to_trailing_transient_failure_alerts_immediately(executor, monkeypatch):
    """旧SL取消後にトレーリングSLを出せない一時エラーは、1回再試行して🚨メール（activeのまま次回再試行）"""
    pos = {"status": "active", "direction": "long", "position_id": "eth_jpy-1", "entry_price": 429501.0,
           "atr_jpy": 6595.2, "tp1_order_id": 11, "sl_order_id": 22, "tp1_price": 437745.0,
           "tp1_amount": 0.0047, "trail_amount": 0.011, "sl_price": 413013.0, "total_amount": 0.0157}
    bb = MagicMock()
    bb.get_order.side_effect = lambda pair, oid: {11: {"status": "FULLY_FILLED", "average_price": "437745",
                                                        "executed_amount": "0.0047"}}.get(oid, {"status": "CANCELED_UNFILLED"})
    bb.create_order.side_effect = Exception("code=70023")
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    monkeypatch.setattr(executor, "record_partial_fill_after_cancel", MagicMock())
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    out = executor.maintain_positions(bb, {"positions": {"eth_jpy": pos}}, {})
    assert bb.create_order.call_count == 2
    assert "🚨SL不在" in mail.call_args.args[0]
    assert out["positions"]["eth_jpy"]["status"] == "active"


def test_trailing_order_id_kept_when_verify_fails_after_tp1(executor, monkeypatch):
    """指摘6: TP1後のトレーリングSLは verify 失敗でも order_id を state に残し、TP1も記録する"""
    pos = {"status": "active", "direction": "long", "position_id": "eth_jpy-1", "entry_price": 429501.0,
           "atr_jpy": 6595.2, "tp1_order_id": 11, "sl_order_id": 22, "tp1_price": 437745.0,
           "tp1_amount": 0.0047, "trail_amount": 0.011, "sl_price": 413013.0, "total_amount": 0.0157}
    bb = MagicMock()
    def get_order(pair, oid):
        if oid == 11:
            return {"status": "FULLY_FILLED", "average_price": "437745", "executed_amount": "0.0047"}
        if oid == 33:
            raise Exception("timeout")
        return {"status": "CANCELED_UNFILLED"}
    bb.get_order.side_effect = get_order
    bb.create_order.return_value = {"order_id": 33}
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    monkeypatch.setattr(executor, "record_partial_fill_after_cancel", MagicMock())
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    out = executor.maintain_positions(bb, {"positions": {"eth_jpy": pos}}, {})
    assert out["positions"]["eth_jpy"]["trail_sl_order_id"] == 33
    assert out["positions"]["eth_jpy"]["status"] == "trailing"
    assert rec.call_args.args[2] == "TP1部分利確"


def test_emergency_close_also_closes_positions_missing_from_state(executor, monkeypatch):
    """指摘3: 緊急決済は state に無い実建玉も決済する"""
    bb = MagicMock()
    bb.get_margin_positions.return_value = [{"pair": "sol_jpy", "position_side": "short", "open_amount": "0.5000"}]
    failed = executor._emergency_close_all(bb, {"positions": {}})
    bb.create_market_order.assert_called_once_with("sol_jpy", "0.5000", "buy", position_side="short")
    assert failed == []


def test_reconcile_orphan_real_position_is_urgent(executor, mock_bb):
    mock_bb.get_margin_positions.return_value = [{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.001"}]
    executor.reconcile_positions(mock_bb, {"positions": {}})
    assert "🚨" in executor.send_email.call_args.args[0]


def test_phase_a_drops_canceled_unfilled_entry(executor, monkeypatch):
    bb = MagicMock()
    bb.get_order.return_value = {"status": "CANCELED_UNFILLED", "average_price": "0", "executed_amount": "0"}
    out = executor.maintain_positions(bb, {"positions": {"btc_jpy": _filled_pos()}}, {})
    assert out["positions"] == {}


# ── 2026-11-15 修正後のFableレビュー指摘の修正 ──
def test_phase_a_keeps_canceled_partial_without_fill_info(executor, monkeypatch):
    """レビュー指摘1: 約定情報が欠けた CANCELED_PARTIALLY_FILLED は消さずに残し、1回だけ🚨"""
    bb = MagicMock()
    bb.get_order.return_value = {"status": "CANCELED_PARTIALLY_FILLED", "average_price": "0", "executed_amount": "0.0010"}
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    state = {"positions": {"btc_jpy": _filled_pos()}}
    out = executor.maintain_positions(bb, state, {})
    out = executor.maintain_positions(bb, out, {})
    assert "btc_jpy" in out["positions"] and mail.call_count == 1


def test_phase_b_keeps_canceled_partial_without_fill_info(executor, monkeypatch):
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    bb.get_order.return_value = {"status": "CANCELED_PARTIALLY_FILLED", "average_price": "0", "executed_amount": "0.001"}
    out = executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert out["positions"]["btc_jpy"]["status"] == "buy_pending"


def test_reconcile_does_not_flag_buy_pending_real_position(executor, mock_bb):
    """レビュー指摘2: SL/TP1待ちの buy_pending の建玉を孤児建玉と誤判定しない"""
    mock_bb.get_margin_positions.return_value = [{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.001"}]
    executor.reconcile_positions(mock_bb, {"positions": {"btc_jpy": _filled_pos()}})
    assert not executor.send_email.called


def test_sl_60018_in_phase_b_rescues_immediately(executor, monkeypatch):
    """レビュー指摘4: 60018（再試行しても通らない）のSL失敗は待たずに成行救済"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    bb.get_order.return_value = _FILL
    bb.create_order.side_effect = Exception("create_order失敗: code=60018")
    rescue = MagicMock(return_value=True)
    monkeypatch.setattr(executor, "rescue_close", rescue)
    monkeypatch.setattr(executor, "get_available_margin", MagicMock(return_value=100000.0))
    out = executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert rescue.called and "btc_jpy" not in out["positions"]


def test_entry_uses_partial_fill_when_still_partial_at_timeout(executor, monkeypatch):
    """待っても PARTIALLY_FILLED のままなら、その約定数量で SL/TP1 を出す（無防備にしない）"""
    bb, sig = _entry_env(executor, monkeypatch)
    bb.get_margin_positions.return_value = []
    bb.create_market_order.return_value = {"order_id": 555}
    bb.get_order.return_value = {"status": "PARTIALLY_FILLED", "average_price": "10000000", "executed_amount": "0.0010"}
    clock = iter(range(0, 10000, 5))
    monkeypatch.setattr(executor.time, "time", lambda: next(clock))
    applied = MagicMock()
    monkeypatch.setattr(executor, "_apply_and_notify_fill", applied)
    executor.place_new_orders(bb, {"positions": {}}, sig, {})
    assert applied.call_args.args[3]["executed_amount"] == "0.0010"


def test_close_unknown_entry_alerts_when_position_unknown(executor, monkeypatch):
    bb = MagicMock()
    bb.get_margin_positions.side_effect = Exception("down")
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    executor._close_unknown_entry(bb, "btc_jpy", "short", None, _CFG, Exception("timeout"))
    bb.create_market_order.assert_not_called()
    assert "🚨発注結果が不明" in mail.call_args.args[0]


def test_close_unknown_entry_alerts_when_close_fails(executor, monkeypatch):
    bb = MagicMock()
    bb.get_margin_positions.return_value = [{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.0036"}]
    bb.create_market_order.side_effect = Exception("70020")
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    mail = MagicMock()
    monkeypatch.setattr(executor, "send_email", mail)
    executor._close_unknown_entry(bb, "btc_jpy", "short", 0.0, _CFG, Exception("timeout"))
    assert "🚨SLなしの建玉が残っています" in mail.call_args.args[0]


def test_emergency_close_does_not_double_close_state_pairs(executor, monkeypatch):
    bb = MagicMock()
    bb.get_margin_positions.return_value = [{"pair": "eth_jpy", "position_side": "long", "open_amount": "0.0110"}]
    monkeypatch.setattr(executor, "record_trade", MagicMock())
    monkeypatch.setattr(executor, "record_partial_fill_after_cancel", MagicMock())
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=400000.0))
    state = {"positions": {"eth_jpy": {"status": "trailing", "direction": "long", "trail_amount": 0.011,
                                       "trail_sl_order_id": 9, "entry_price": 1.0, "position_id": "p"}}}
    executor._emergency_close_all(bb, state)
    assert bb.create_market_order.call_count == 1


def test_real_rescue_close_on_buy_pending_after_sl_failures(executor, monkeypatch):
    """本物の rescue_close を buy_pending（total_amount なし）に通しても実約定価格で記録して決済する"""
    bb = MagicMock()
    bb.get_order.return_value = _FILL
    bb.create_order.side_effect = Exception("code=70023")
    bb.get_margin_positions.side_effect = (
        [[{"pair": "btc_jpy", "position_side": "short", "open_amount": "0.0036"}]]
        + [[{"pair": "btc_jpy", "position_side": "short", "open_amount": "0"}]] * 10)
    bb.create_market_order.return_value = {"order_id": 888}
    monkeypatch.setattr(executor.time, "sleep", MagicMock())
    monkeypatch.setattr(executor, "get_bitbank_price", MagicMock(return_value=10_100_000.0))
    rec = MagicMock(return_value={"pnl_source": "pending"})
    monkeypatch.setattr(executor, "record_trade", rec)
    pos = _filled_pos()
    pos["sl_fail_count"] = executor.SL_FAIL_RESCUE_COUNT - 1
    out = executor.maintain_positions(bb, {"positions": {"btc_jpy": pos}}, {})
    bb.create_market_order.assert_called_once_with("btc_jpy", "0.0036", "buy", position_side="short")
    assert rec.call_args.args[3] == 10_000_000.0       # 建値は実約定価格
    assert "btc_jpy" not in out["positions"]


def test_trade_mails_are_suppressed_by_default(executor, monkeypatch):
    """取引連絡メール（約定・TP1・決済）は既定で送らない（2026-11-16ユーザー判断）。異常通知は送る。"""
    sent = _capture_ses(executor, monkeypatch)
    assert executor.TRADE_MAIL_ENABLED is False
    executor.notify_entry_fill("btc_jpy", "short", 12000000, 0.002, 12300000, 11800000, 50000)
    executor.notify_trail_started("eth_jpy", "long", 500000, 510000, 512000, 3000, None)
    executor.notify_close("sol_jpy", "long", "損切り", 20000, 21000, 1.0, 50000, None)
    assert sent == []
    executor.send_email("【CryptoBot】異常テスト", "本文", level="critical")
    assert len(sent) == 1


def test_trade_mails_log_subject_only_when_suppressed(executor, monkeypatch):
    """停止中は件名だけログに出す（本文の管理者トークン付きURLをログに残さない）。"""
    _capture_ses(executor, monkeypatch)
    logs = []
    monkeypatch.setattr(executor, "log", lambda m: logs.append(m))
    executor.notify_trail_started("eth_jpy", "long", 500000, 510000, 512000, 3000, None)
    assert any("TP1約定・トレーリング開始" in m for m in logs)
    assert not any("admin=" in m for m in logs)


def test_trade_mails_sent_when_enabled(executor, monkeypatch):
    """再開（TRADE_MAIL_ENABLED=True）時は約定・決済メールが従来どおり送られる。"""
    sent = _capture_ses(executor, monkeypatch)
    monkeypatch.setattr(executor, "TRADE_MAIL_ENABLED", True)
    executor.notify_entry_fill("btc_jpy", "short", 12000000, 0.002, 12300000, 11800000, 50000)
    executor.notify_close("sol_jpy", "long", "損切り", 20000, 21000, 1.0, 50000, None)
    subjects = [m["Message"]["Subject"]["Data"] for m in sent]
    assert len(subjects) == 2
    assert "ショート約定 - BTC/JPY" in subjects[0] and "ロングクローズ - SOL/JPY" in subjects[1]


# ---- 証拠金維持率の取得失敗→復旧のメール(2026-11-18) ----
def test_margin_fetch_failure_then_recovery_sends_recovery_mail(executor):
    bb = MagicMock()
    bb.get_margin_status.side_effect = Exception("<urlopen error [Errno 104] Connection reset by peer>")
    state = {"positions": {}}
    assert executor.check_margin_health(bb, state) is True
    assert executor.MARGIN_FETCH_FAILED_KEY in state
    first_failed_at = state[executor.MARGIN_FETCH_FAILED_KEY]
    assert "取得失敗" in executor.send_email.call_args[0][0]
    assert "復旧" in executor.send_email.call_args.kwargs["action"]

    # 続けて失敗しても、最初に失敗した時刻のまま
    assert executor.check_margin_health(bb, state) is True
    assert state[executor.MARGIN_FETCH_FAILED_KEY] == first_failed_at

    # 次の確認で取得できたら、復旧(対応不要)のメールを1通送ってフラグを消す
    executor.send_email.reset_mock()
    bb.get_margin_status.side_effect = None
    bb.get_margin_status.return_value = {"status": "NORMAL", "total_margin_balance_percentage": None}
    assert executor.check_margin_health(bb, state) is True
    assert executor.MARGIN_FETCH_FAILED_KEY not in state
    assert executor.send_email.call_count == 1
    assert "復旧" in executor.send_email.call_args[0][0]
    assert executor.send_email.call_args.kwargs["level"] == "info"

    # その次の確認ではもう送らない
    executor.send_email.reset_mock()
    assert executor.check_margin_health(bb, state) is True
    assert not executor.send_email.called


def test_margin_fetch_success_without_prior_failure_sends_nothing(executor):
    bb = MagicMock()
    bb.get_margin_status.return_value = {"status": "NORMAL", "total_margin_balance_percentage": "250.0"}
    state = {"positions": {}}
    assert executor.check_margin_health(bb, state) is True
    assert not executor.send_email.called


def test_margin_unexpected_payload_keeps_failure_without_recovery_mail(executor):
    """取得できても中身が想定外(数値にできない)なら、復旧メールは送らず失敗のまま(Fableレビュー 中1)"""
    bb = MagicMock()
    state = {"positions": {}, executor.MARGIN_FETCH_FAILED_KEY: "11/18 06:15"}
    bb.get_margin_status.return_value = {"status": "NORMAL", "total_margin_balance_percentage": "abc"}
    assert executor.check_margin_health(bb, state) is True
    assert state[executor.MARGIN_FETCH_FAILED_KEY] == "11/18 06:15"
    subjects = [c[0][0] for c in executor.send_email.call_args_list]
    assert not any("復旧" in s for s in subjects)
    assert any("取得失敗" in s for s in subjects)


def test_margin_recovery_with_ratio_and_saves_immediately(executor, monkeypatch):
    saved = MagicMock()
    monkeypatch.setattr(executor, "save_state_now", saved)
    bb = MagicMock()
    bb.get_margin_status.return_value = {"status": "NORMAL", "total_margin_balance_percentage": "250.0"}
    state = {"positions": {}, executor.MARGIN_FETCH_FAILED_KEY: "11/18 06:15"}
    assert executor.check_margin_health(bb, state) is True
    assert executor.MARGIN_FETCH_FAILED_KEY not in state
    assert saved.called
    assert any("復旧" in c[0][0] for c in executor.send_email.call_args_list)
