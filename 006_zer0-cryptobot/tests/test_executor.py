"""Executor Lambda のユニットテスト。
boto3クライアントはconftest.pyでモック済み。bitbank実APIには接続しない。
"""
import json
from unittest.mock import MagicMock


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
