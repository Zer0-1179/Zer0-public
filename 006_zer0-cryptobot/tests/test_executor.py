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
    r = executor.check_account(_account_bb("11184.7337"))
    assert r["matched"] is True and abs(r["diff_jpy"]) < 0.01
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
    bb = _account_bb("11084.7337")   # 100円の記録漏れ
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


# ── 2026-10-02: レバレッジ対策（同時2件・1件=受入保証金×0.75） ──
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
    bb.get_margin_positions.return_value = [{"pair": "eth_jpy", "position_side": "long", "open_amount": open_amount}]
    bb.create_market_order.return_value = {"order_id": 999}
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
    bb, rec, mail, pos = _rescue_env(executor, monkeypatch, "FULLY_FILLED")
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
