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
