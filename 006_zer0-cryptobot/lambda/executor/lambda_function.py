"""
Zer0-CryptoBot Executor Lambda
Phase A: 既存ポジション管理（約定確認 / TP1後トレーリングSL / 24h未約定キャンセル）
Phase B: 新規シグナルの指値発注（動的ポジションサイズ）

v3変更: 信用取引（ロング＋ショート）対応 / ペア変更: BTC/ETH/SOL
"""

import os
import json
import hmac
import math
import time
import hashlib
import urllib.request
import urllib.parse
import urllib.error
import boto3
from datetime import datetime, timezone

# ── 定数 ──────────────────────────────────────────────────────────────────────
MIN_INVEST_JPY  = 1000          # 最小発注額（円）
MAX_POSITIONS   = 3
CANCEL_AFTER_S  = 86400         # 未約定注文キャンセルまでの秒数（24時間）
BITBANK_PUB     = "https://public.bitbank.cc"
BITBANK_REST    = "https://api.bitbank.cc/v1"
SSM_API_KEY     = "/Zer0/CryptoBot/bitbank/api_key"
SSM_API_SECRET  = "/Zer0/CryptoBot/bitbank/api_secret"
SSM_STATE       = "/Zer0/CryptoBot/state"

# TP/SL 倍率
TP1_MULT    = 2.0   # TP1 = entry ± ATR × 2
SL_MULT     = 1.5   # 初期SL = entry ∓ ATR × 1.5
TRAIL_MULT  = 1.5   # トレーリング幅 = 極値 ± ATR × 1.5
TP1_RATIO   = 0.3   # TP1 の数量割合
TRAIL_RATIO = 0.7   # トレーリングSL 対象の数量割合

# コイン別精度（price小数桁数, amount小数桁数）
PAIRS = {
    "btc_jpy": {"price_prec": 0, "amount_prec": 4},
    "eth_jpy": {"price_prec": 0, "amount_prec": 4},
    "sol_jpy": {"price_prec": 0, "amount_prec": 4},
}

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


class OrderVerificationError(Exception):
    """注文確認の再試行が全て失敗した場合に送出する。verify_order 内でメール送信済み。"""
    pass


# ── ユーティリティ ────────────────────────────────────────────────────────────
def log(msg: str):
    print(f"[Executor] {msg}")


def round_price(value: float, prec: int) -> str:
    if prec == 0:
        return str(int(round(value, 0)))
    return f"{value:.{prec}f}"


def round_amount(value: float, prec: int) -> str:
    return f"{value:.{prec}f}"


def price_val(price_str: str) -> float:
    return float(price_str)


# ── SSM ───────────────────────────────────────────────────────────────────────
def get_ssm(name: str, decrypt: bool = False) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    return ssm.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]


def load_state() -> dict:
    try:
        raw = get_ssm(SSM_STATE, decrypt=False)
        return json.loads(raw)
    except Exception:
        return {"positions": {}}


def save_state(state: dict):
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    ssm.put_parameter(
        Name=SSM_STATE, Value=json.dumps(state),
        Type="String", Overwrite=True,
    )


# ── SES ───────────────────────────────────────────────────────────────────────
def send_email(subject: str, body: str):
    html_body = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="UTF-8">'
        '</head><body style="font-family:sans-serif;font-size:14px;line-height:1.8;">'
        + body.replace("\n", "<br>")
        + "</body></html>"
    )
    try:
        ses = boto3.client("ses", region_name=AWS_REGION)
        ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [SES_RECIPIENT]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body,      "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
        log(f"メール送信: {subject}")
    except Exception as e:
        log(f"SES 送信失敗: {e}")


def _coin(pair: str) -> str:
    return pair.split("_")[0].upper()


def notify_entry_order(pair: str, direction: str, price: float, amount: float,
                       invest: float, current_price: float, remaining: float):
    dir_str = "ロング（買い）" if direction == "long" else "ショート（売り）"
    coin = _coin(pair)
    subject = f"【CryptoBot】{dir_str}注文発注 - {coin}/JPY"
    body = (
        f"■ {coin}/JPY  {dir_str}\n"
        f"\n"
        f"現在価格：{current_price:,.0f}円\n"
        f"指値　　：{price:,.0f}円\n"
        f"数量　　：{amount} {coin}\n"
        f"購入金額：{invest:,.0f}円\n"
        f"証拠金　：{invest/2:,.0f}円（2倍レバレッジ）\n"
        f"残り証拠金：{remaining/2:,.0f}円\n"
        f"\n"
        f"※ 24時間で未約定の場合は自動キャンセルします"
    )
    send_email(subject, body)


def notify_entry_fill(pair: str, direction: str, entry: float, amount: float,
                      sl: float, tp1: float, remaining_margin: float):
    dir_str = "ロング" if direction == "long" else "ショート"
    coin = _coin(pair)
    position_jpy = entry * amount
    if direction == "long":
        sl_pct  = (sl  - entry) / entry * 100
        tp1_pct = (tp1 - entry) / entry * 100
    else:
        sl_pct  = (entry - sl)  / entry * 100
        tp1_pct = (entry - tp1) / entry * 100
    subject = f"【CryptoBot】{dir_str}約定 - {coin}/JPY"
    body = (
        f"■ {coin}/JPY  {dir_str}  約定\n"
        f"\n"
        f"現在価格　：{entry:,.0f}円\n"
        f"購入金額　：{position_jpy:,.0f}円（{amount} {coin}）\n"
        f"残り証拠金：{remaining_margin/2:,.0f}円\n"
        f"\n"
        f"損切り（70%）：{sl:,.0f}円（{sl_pct:+.1f}%）\n"
        f"TP1　（30%）：{tp1:,.0f}円（{tp1_pct:+.1f}%）\n"
        f"TP1約定後 → 残り70%をトレーリングSL（ATR×{TRAIL_MULT}）で管理"
    )
    send_email(subject, body)


def notify_trail_started(pair: str, direction: str, entry: float, tp1_price: float,
                         current_price: float, realized_pnl: float):
    dir_str = "ロング" if direction == "long" else "ショート"
    coin = _coin(pair)
    if direction == "long":
        tp1_pct = (tp1_price - entry) / entry * 100
    else:
        tp1_pct = (entry - tp1_price) / entry * 100
    subject = f"【CryptoBot】TP1約定・トレーリング開始 - {coin}/JPY"
    body = (
        f"■ {coin}/JPY  {dir_str}  TP1約定\n"
        f"\n"
        f"現在価格　　：{current_price:,.0f}円\n"
        f"TP1約定価格：{tp1_price:,.0f}円（{tp1_pct:+.1f}%）\n"
        f"確定利益　　：{realized_pnl:+,.0f}円\n"
        f"現在SL　　　：{entry:,.0f}円（ブレイクイーブン）\n"
        f"\n"
        f"残り70%のトレーリングSLを開始しました。\n"
        f"高値/安値更新ごとにSLが自動追従します（ATR×{TRAIL_MULT}）。"
    )
    send_email(subject, body)


def notify_trail_updated(pair: str, direction: str, new_trail: float, current_price: float):
    dir_str = "ロング" if direction == "long" else "ショート"
    coin = _coin(pair)
    subject = f"【CryptoBot】トレーリングSL更新 - {coin}/JPY"
    body = (
        f"■ {coin}/JPY  {dir_str}  トレーリングSL更新\n"
        f"\n"
        f"現在価格：{current_price:,.0f}円\n"
        f"新SL　　：{new_trail:,.0f}円"
    )
    send_email(subject, body)


def notify_close(pair: str, direction: str, reason: str, price: float,
                 entry: float, amount: float, remaining_margin: float):
    if direction == "long":
        pnl = (price - entry) * amount
        price_diff_pct = (price - entry) / entry * 100
    else:
        pnl = (entry - price) * amount
        price_diff_pct = (entry - price) / entry * 100
    dir_str = "ロング" if direction == "long" else "ショート"
    coin = _coin(pair)
    subject = f"【CryptoBot】{dir_str}クローズ - {coin}/JPY"
    body = (
        f"■ {coin}/JPY  {dir_str}  クローズ（{reason}）\n"
        f"\n"
        f"現在価格　：{price:,.0f}円\n"
        f"エントリー：{entry:,.0f}円\n"
        f"変動　　　：{price_diff_pct:+.1f}%\n"
        f"購入金額　：{entry * amount:,.0f}円（{amount} {coin}）\n"
        f"損益　　　：{pnl:+,.0f}円\n"
        f"残り証拠金：{remaining_margin/2:,.0f}円"
    )
    send_email(subject, body)


# ── bitbank クライアント ───────────────────────────────────────────────────────
class BitbankClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key    = api_key
        self.api_secret = api_secret

    def _nonce(self) -> str:
        return str(int(time.time() * 1000))

    def _sign(self, message: str) -> str:
        return hmac.new(
            self.api_secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

    def _get(self, path: str, params: dict | None = None) -> dict:
        nonce = self._nonce()
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        msg   = f"{nonce}/v1{path}{query}"
        headers = {
            "ACCESS-KEY":       self.api_key,
            "ACCESS-NONCE":     nonce,
            "ACCESS-SIGNATURE": self._sign(msg),
        }
        url = f"{BITBANK_REST}{path}{query}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, body: dict) -> dict:
        nonce    = self._nonce()
        body_str = json.dumps(body)
        msg      = f"{nonce}{body_str}"
        headers  = {
            "ACCESS-KEY":       self.api_key,
            "ACCESS-NONCE":     nonce,
            "ACCESS-SIGNATURE": self._sign(msg),
            "Content-Type":     "application/json",
        }
        url  = f"{BITBANK_REST}{path}"
        data = body_str.encode()
        req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def get_assets(self) -> dict:
        result = self._get("/user/assets")
        return {a["asset"]: a for a in result["data"]["assets"]}

    def get_margin_status(self) -> dict:
        return self._get("/user/margin/status")["data"]

    def get_order(self, pair: str, order_id: int) -> dict:
        return self._get("/user/spot/order", {"pair": pair, "order_id": order_id})["data"]

    def create_order(self, pair: str, amount: str, price: str, side: str,
                     position_side: str | None = None) -> dict:
        """
        信用取引は開設・決済ともに position_side が必須。
          開設ロング : side="buy",  position_side="long"
          決済ロング : side="sell", position_side="long"
          開設ショート: side="sell", position_side="short"
          決済ショート: side="buy",  position_side="short"
        """
        body = {"pair": pair, "amount": amount, "price": price,
                "side": side, "type": "limit"}
        if position_side is not None:
            body["position_side"] = position_side
        resp = self._post("/user/spot/order", body)
        if resp.get("success") != 1:
            raise Exception(f"create_order失敗 pair={pair} side={side} position_side={position_side}: code={resp.get('data', {}).get('code')}")
        return resp["data"]

    def create_market_order(self, pair: str, amount: str, side: str,
                            position_side: str | None = None) -> dict:
        body = {"pair": pair, "amount": amount, "side": side, "type": "market"}
        if position_side is not None:
            body["position_side"] = position_side
        resp = self._post("/user/spot/order", body)
        if resp.get("success") != 1:
            raise Exception(f"create_market_order失敗 pair={pair}: code={resp.get('data', {}).get('code')}")
        return resp["data"]

    def cancel_order(self, pair: str, order_id: int) -> dict:
        return self._post("/user/spot/cancel_order",
                          {"pair": pair, "order_id": order_id})["data"]


def get_bitbank_price(pair: str) -> float:
    url = f"{BITBANK_PUB}/{pair}/ticker"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    return float(data["data"]["last"])


def verify_order(bb: BitbankClient, pair: str, order_id: int, context: str = ""):
    """発注後に注文存在を確認する。失敗時は最大3回リトライ（5秒待機）。
    3回失敗した場合は緊急メールを送信して OrderVerificationError を送出する。"""
    for attempt in range(1, 4):
        try:
            bb.get_order(pair, order_id)
            return
        except Exception as e:
            log(f"{pair} 注文確認失敗({attempt}/3) [{context}]: {e}")
            if attempt < 3:
                time.sleep(5)
    send_email(
        "【Zer0-CryptoBot】🚨注文失敗",
        f"コイン：{pair.upper()}\n種別：{context}\n"
        f"注文ID {order_id} の確認に3回失敗しました。手動確認が必要です。",
    )
    raise OrderVerificationError(f"{pair} order {order_id} ({context}) unverifiable")


def get_available_margin(bb: BitbankClient, pair: str | None = None) -> float:
    """新規建て可能額（JPY）を返す。
    available_balances[pair]["long"] は証拠金 × レバレッジ後の建玉可能額。"""
    try:
        margin = bb.get_margin_status()
        balances = margin.get("available_balances", [])
        if balances:
            target = pair
            value = None
            for b in balances:
                if target and b["pair"] == target:
                    value = float(b.get("long", "0"))
                    break
            if value is None:
                value = float(balances[0].get("long", "0"))
            log(f"新規建て可能額({pair or balances[0]['pair']}): {value:,.0f}円")
            return value
        # フォールバック: total_margin_balance × 2（レバレッジ倍率）
        total = float(margin.get("total_margin_balance", "0"))
        value = total * 2
        log(f"新規建て可能額（証拠金×2）: {value:,.0f}円")
        return value
    except Exception as e:
        log(f"新規建て可能額取得失敗: {e}")
        return 0.0


# ── 証拠金維持率監視 ──────────────────────────────────────────────────────────
def _emergency_close_all(bb: BitbankClient, state: dict):
    """全ポジションの未決済注文をキャンセルし、保有中のものを成行決済する。
    個別の失敗は無視して全ペアを処理し続ける。"""
    for pair, pos in state["positions"].items():
        direction  = pos.get("direction", "long")
        close_side = "sell" if direction == "long" else "buy"
        status     = pos.get("status")
        cfg        = PAIRS.get(pair, {"price_prec": 0, "amount_prec": 4})

        # 未決済注文をすべてキャンセル
        for key in ("buy_order_id", "tp1_order_id", "sl_order_id", "trail_sl_order_id"):
            oid = pos.get(key)
            if oid:
                try:
                    bb.cancel_order(pair, oid)
                    log(f"{pair}: 緊急キャンセル {key}={oid}")
                except Exception as ce:
                    log(f"{pair}: キャンセル失敗 {key}={oid}: {ce}")

        # 保有中のみ成行決済
        if status == "active":
            amount = pos.get("total_amount", 0)
        elif status == "trailing":
            amount = pos.get("trail_amount", 0)
        else:
            continue  # buy_pending はエントリー取り消しのみで決済不要

        if amount > 0:
            amount_str = round_amount(amount, cfg["amount_prec"])
            try:
                bb.create_market_order(pair, amount_str, close_side, position_side=direction)
                log(f"{pair}: 緊急成行決済 {close_side} {amount_str}")
            except Exception as e:
                log(f"{pair}: 緊急成行決済失敗: {e}")


def check_margin_health(bb: BitbankClient, state: dict) -> bool:
    """証拠金維持率を確認する。
    - status が CALL/LOSSCUT: 緊急成行決済
    - total_margin_balance_percentage が 120%以下: 緊急成行決済
    - 150%以下: 警告メール送信（処理継続）
    - 建玉なし(null) / 取得失敗: スキップして True を返す"""
    try:
        margin = bb.get_margin_status()
        log(f"margin/status raw: {json.dumps(margin, ensure_ascii=False)}")

        # status フィールドで危険状態を直接検出（percentage スケール不問）
        status = margin.get("status", "NORMAL")
        if status in ("CALL", "LOSSCUT", "DEBT"):
            log(f"証拠金ステータス異常: {status} → 緊急成行決済を実行")
            _emergency_close_all(bb, state)
            state["positions"] = {}
            send_email(
                "【Zer0-CryptoBot】🚨緊急決済実行",
                f"証拠金ステータス: {status}\n"
                f"全ポジションを成行決済しました。速やかに状況を確認してください。",
            )
            return False

        raw = margin.get("total_margin_balance_percentage")
        if raw is None:
            return True  # 建玉なし → スキップ
        ratio = float(raw)
    except Exception as e:
        log(f"証拠金維持率取得失敗 → スキップ: {e}")
        send_email(
            "【Zer0-CryptoBot】⚠️証拠金維持率取得失敗",
            f"証拠金維持率の取得に失敗しました。手動で状況を確認してください。\nエラー: {e}",
        )
        return True

    log(f"証拠金維持率: {ratio:.1f}%")

    if ratio <= 120:
        log("証拠金維持率120%以下 → 緊急成行決済を実行")
        _emergency_close_all(bb, state)
        state["positions"] = {}
        send_email(
            "【Zer0-CryptoBot】🚨緊急決済実行",
            f"証拠金維持率 {ratio:.1f}% が120%以下になったため、"
            f"全ポジションを成行決済しました。\n速やかに状況を確認してください。",
        )
        return False

    if ratio <= 150:
        send_email(
            "【Zer0-CryptoBot】⚠️証拠金警告",
            f"証拠金維持率が {ratio:.1f}% に低下しています（警告水準: 150%以下）。\n"
            f"ポジション状況を確認してください。",
        )

    return True


# ── Phase A: 既存ポジション管理 ───────────────────────────────────────────────
def maintain_positions(bb: BitbankClient, state: dict) -> dict:
    to_delete = []

    for pair, pos in list(state["positions"].items()):
        cfg       = PAIRS.get(pair, {"price_prec": 2, "amount_prec": 4})
        direction = pos.get("direction", "long")
        close_side = "sell" if direction == "long" else "buy"

        try:
            # ── 買い注文 未約定チェック ────────────────────────────────────
            if pos["status"] == "buy_pending":
                order  = bb.get_order(pair, pos["buy_order_id"])
                status = order.get("status", "")

                if status == "FULLY_FILLED":
                    log(f"{pair}({direction}): エントリー約定 → TP1/SL 発注")
                    entry     = float(order["average_price"])
                    amount    = float(order["executed_amount"])
                    atr_ratio = pos["atr_jpy"] / pos["entry_price_signal"]
                    atr_jpy   = atr_ratio * entry

                    if direction == "long":
                        tp1_price = entry + atr_jpy * TP1_MULT
                        sl_price  = entry - atr_jpy * SL_MULT
                    else:
                        tp1_price = entry - atr_jpy * TP1_MULT
                        sl_price  = entry + atr_jpy * SL_MULT

                    tp1_amount   = round(amount * TP1_RATIO,   cfg["amount_prec"])
                    trail_amount = round(amount * TRAIL_RATIO, cfg["amount_prec"])

                    o_tp1 = bb.create_order(pair,
                                            round_amount(tp1_amount, cfg["amount_prec"]),
                                            round_price(tp1_price,   cfg["price_prec"]),
                                            close_side, position_side=direction)
                    verify_order(bb, pair, o_tp1["order_id"], "TP1注文")
                    o_sl  = bb.create_order(pair,
                                            round_amount(trail_amount, cfg["amount_prec"]),
                                            round_price(sl_price, cfg["price_prec"]),
                                            close_side, position_side=direction)
                    verify_order(bb, pair, o_sl["order_id"], "初期SL注文")

                    pos.update({
                        "status":        "active",
                        "entry_price":   entry,
                        "total_amount":  amount,
                        "atr_jpy":       atr_jpy,
                        "tp1_price":     tp1_price,
                        "tp1_amount":    tp1_amount,
                        "trail_amount":  trail_amount,
                        "sl_price":      sl_price,
                        "tp1_order_id":  o_tp1["order_id"],
                        "sl_order_id":   o_sl["order_id"],
                        "tp1_filled":    False,
                    })
                    remaining = get_available_margin(bb, pair)
                    notify_entry_fill(pair, direction, entry, amount, sl_price, tp1_price, remaining)

                elif time.time() - pos["buy_timestamp"] > CANCEL_AFTER_S:
                    log(f"{pair}({direction}): 24時間未約定 → キャンセル")
                    try:
                        bb.cancel_order(pair, pos["buy_order_id"])
                    except Exception as ce:
                        log(f"{pair}: キャンセル失敗: {ce}")
                    to_delete.append(pair)
                    send_email(
                        f"【Zer0-CryptoBot】注文キャンセル - {pair.upper()}",
                        f"コイン：{pair.upper()}\n方向：{direction}\n24時間未約定のため注文をキャンセルしました。",
                    )

            # ── アクティブ: TP1約定確認 → トレーリング移行 ───────────────
            elif pos["status"] == "active":
                if not pos.get("tp1_filled"):
                    o_tp1 = bb.get_order(pair, pos["tp1_order_id"])

                    if o_tp1.get("status") == "FULLY_FILLED":
                        log(f"{pair}({direction}): TP1 約定 → トレーリングSL 開始")

                        sl_already_filled = False
                        try:
                            bb.cancel_order(pair, pos["sl_order_id"])
                        except Exception as ce:
                            log(f"{pair}: 旧SL キャンセル失敗: {ce}")
                            try:
                                sl_chk = bb.get_order(pair, pos["sl_order_id"])
                                if sl_chk.get("status") == "FULLY_FILLED":
                                    sl_already_filled = True
                                    log(f"{pair}: 旧SL 既に約定 → TP1+SL両方確定 → 終了")
                                    remaining = get_available_margin(bb, pair)
                                    notify_close(pair, direction, "SL（TP1後）",
                                                 float(sl_chk["average_price"]),
                                                 pos["entry_price"],
                                                 float(sl_chk["executed_amount"]),
                                                 remaining)
                                    to_delete.append(pair)
                            except Exception:
                                pass

                        if sl_already_filled:
                            continue

                        entry        = pos["entry_price"]
                        trail_amount = pos["trail_amount"]
                        atr_jpy      = pos["atr_jpy"]

                        trail_sl_price = entry
                        o_trail = bb.create_order(
                            pair,
                            round_amount(trail_amount, cfg["amount_prec"]),
                            round_price(trail_sl_price, cfg["price_prec"]),
                            close_side, position_side=direction,
                        )
                        verify_order(bb, pair, o_trail["order_id"], "トレーリングSL注文")
                        state["positions"][pair] = {
                            "status":            "trailing",
                            "direction":         direction,
                            "entry_price":       entry,
                            "atr_jpy":           atr_jpy,
                            "tp1_price":         pos["tp1_price"],
                            "trail_amount":      trail_amount,
                            "trail_sl_order_id": o_trail["order_id"],
                            "trail_sl_price":    trail_sl_price,
                            "highest_price": pos["tp1_price"] if direction == "long" else None,
                            "lowest_price":  pos["tp1_price"] if direction == "short" else None,
                        }
                        tp1_fill_price    = float(o_tp1["average_price"])
                        tp1_filled_amount = float(o_tp1["executed_amount"])
                        if direction == "long":
                            realized_pnl = (tp1_fill_price - entry) * tp1_filled_amount
                        else:
                            realized_pnl = (entry - tp1_fill_price) * tp1_filled_amount
                        notify_trail_started(pair, direction, entry, pos["tp1_price"],
                                             tp1_fill_price, realized_pnl)
                        continue

                    # TP1未約定時: 初期SL 約定確認
                    o_sl = bb.get_order(pair, pos["sl_order_id"])
                    if o_sl.get("status") == "FULLY_FILLED":
                        log(f"{pair}({direction}): SL（損切り）約定 → TP1キャンセル → 終了")
                        try:
                            bb.cancel_order(pair, pos["tp1_order_id"])
                        except Exception as ce:
                            log(f"{pair}: TP1キャンセル失敗: {ce}")
                        remaining = get_available_margin(bb, pair)
                        notify_close(pair, direction, "損切り",
                                     float(o_sl["average_price"]),
                                     pos["entry_price"],
                                     float(o_sl["executed_amount"]),
                                     remaining)
                        to_delete.append(pair)

            # ── トレーリングSL 管理 ────────────────────────────────────────
            elif pos["status"] == "trailing":
                trail_order = bb.get_order(pair, pos["trail_sl_order_id"])

                if trail_order.get("status") == "FULLY_FILLED":
                    exit_p = float(trail_order["average_price"])
                    exit_a = float(trail_order["executed_amount"])
                    log(f"{pair}({direction}): トレーリングSL 約定 → 終了 exit={exit_p}")
                    remaining = get_available_margin(bb, pair)
                    notify_close(pair, direction, "トレーリングSL",
                                 exit_p, pos["entry_price"], exit_a, remaining)
                    to_delete.append(pair)
                else:
                    try:
                        current = get_bitbank_price(pair)

                        if direction == "long":
                            if current > pos["highest_price"]:
                                new_highest   = current
                                new_trail_f   = new_highest - pos["atr_jpy"] * TRAIL_MULT
                                new_trail_f   = max(new_trail_f, pos["entry_price"])
                                new_trail_str = round_price(new_trail_f, cfg["price_prec"])
                                new_trail_val = price_val(new_trail_str)

                                if new_trail_val > pos["trail_sl_price"]:
                                    log(f"{pair}(long): トレーリングSL更新 "
                                        f"{pos['trail_sl_price']} → {new_trail_val}")
                                    try:
                                        bb.cancel_order(pair, pos["trail_sl_order_id"])
                                    except Exception as ce:
                                        log(f"{pair}: トレーリングSLキャンセル失敗 → 更新スキップ: {ce}")
                                        continue
                                    new_order = bb.create_order(
                                        pair,
                                        round_amount(pos["trail_amount"], cfg["amount_prec"]),
                                        new_trail_str,
                                        "sell", position_side="long",
                                    )
                                    verify_order(bb, pair, new_order["order_id"], "トレーリングSL更新")
                                    pos["trail_sl_order_id"] = new_order["order_id"]
                                    pos["trail_sl_price"]    = new_trail_val
                                    pos["highest_price"]     = new_highest
                                    notify_trail_updated(pair, direction, new_trail_val, current)

                        else:  # short
                            if current < pos["lowest_price"]:
                                new_lowest    = current
                                new_trail_f   = new_lowest + pos["atr_jpy"] * TRAIL_MULT
                                new_trail_f   = min(new_trail_f, pos["entry_price"])
                                new_trail_str = round_price(new_trail_f, cfg["price_prec"])
                                new_trail_val = price_val(new_trail_str)

                                if new_trail_val < pos["trail_sl_price"]:
                                    log(f"{pair}(short): トレーリングSL更新 "
                                        f"{pos['trail_sl_price']} → {new_trail_val}")
                                    try:
                                        bb.cancel_order(pair, pos["trail_sl_order_id"])
                                    except Exception as ce:
                                        log(f"{pair}: トレーリングSLキャンセル失敗 → 更新スキップ: {ce}")
                                        continue
                                    new_order = bb.create_order(
                                        pair,
                                        round_amount(pos["trail_amount"], cfg["amount_prec"]),
                                        new_trail_str,
                                        "buy", position_side="short",
                                    )
                                    verify_order(bb, pair, new_order["order_id"], "トレーリングSL更新")
                                    pos["trail_sl_order_id"] = new_order["order_id"]
                                    pos["trail_sl_price"]    = new_trail_val
                                    pos["lowest_price"]      = new_lowest
                                    notify_trail_updated(pair, direction, new_trail_val, current)

                    except Exception as te:
                        log(f"{pair}: トレーリング更新失敗: {te}")

        except OrderVerificationError:
            pass  # verify_order 内でメール送信済み
        except Exception as e:
            log(f"{pair} メンテナンスエラー: {e}")
            send_email(
                f"【Zer0-CryptoBot】Executor メンテナンスエラー - {pair.upper()}",
                f"コイン：{pair.upper()}\n方向：{direction}\nエラー：{e}",
            )

    for pair in to_delete:
        state["positions"].pop(pair, None)

    return state


# ── Phase B: 新規シグナル注文 ─────────────────────────────────────────────────
def place_new_orders(bb: BitbankClient, state: dict, signals: list, event: dict = {}) -> dict:
    # テスト用フラグ（本番では使用しない）
    # test_invest_jpy: 投資額を固定（例: 500）
    # test_entry_above: True にすると現在価格+0.5%で発注し即時約定させる
    test_invest_jpy  = event.get("test_invest_jpy")
    test_entry_above = event.get("test_entry_above", False)

    active_count = len(state["positions"])
    long_count   = sum(1 for p in state["positions"].values() if p.get("direction") == "long")
    short_count  = sum(1 for p in state["positions"].values() if p.get("direction") == "short")

    for sig in signals:
        pair = sig.get("pair")
        if not pair or pair not in PAIRS:
            log(f"不明ペア スキップ: {pair}")
            continue

        if active_count >= MAX_POSITIONS:
            log("最大ポジション数到達 → 新規発注スキップ")
            break

        if pair in state["positions"]:
            log(f"{pair}: 既に保有中 → スキップ")
            continue

        direction  = sig.get("side", "long")

        if direction == "long" and long_count >= 2:
            log(f"{pair}: ロング上限({long_count}/2) → スキップ")
            continue
        if direction == "short" and short_count >= 2:
            log(f"{pair}: ショート上限({short_count}/2) → スキップ")
            continue
        cfg        = PAIRS[pair]

        try:
            # 証拠金残高確認 + 動的ポジションサイズ計算
            available = get_available_margin(bb, pair)

            remaining_slots = MAX_POSITIONS - active_count
            if test_invest_jpy:
                invest_jpy = int(test_invest_jpy)
                log(f"[TEST] 投資額を {invest_jpy}円 に固定")
            else:
                invest_jpy = math.floor(available / remaining_slots * 0.9) if remaining_slots > 0 else 0
                invest_jpy = max(invest_jpy, MIN_INVEST_JPY)

            if available < invest_jpy:
                log(f"{pair}: 残高不足 ({available:.0f} < {invest_jpy}) → スキップ")
                continue

            # 現在価格を取得して指値を計算
            bb_price = get_bitbank_price(pair)
            if direction == "long":
                entry_price = bb_price * (1.005 if test_entry_above else 0.99)
                order_side  = "buy"
            else:
                entry_price = bb_price * (0.995 if test_entry_above else 1.01)
                order_side  = "sell"
            if test_entry_above:
                log(f"[TEST] 即時約定モード: price={round_price(entry_price, PAIRS[pair]['price_prec'])}")

            amount = invest_jpy / entry_price

            price_str  = round_price(entry_price, cfg["price_prec"])
            amount_str = round_amount(amount, cfg["amount_prec"])

            log(f"{pair}({direction}): 指値発注 price={price_str} amount={amount_str} invest={invest_jpy:.0f}円")
            order = bb.create_order(pair, amount_str, price_str, order_side,
                                    position_side=direction)
            verify_order(bb, pair, order["order_id"], "エントリー注文")

            state["positions"][pair] = {
                "status":             "buy_pending",
                "direction":          direction,
                "buy_order_id":       order["order_id"],
                "buy_timestamp":      time.time(),
                "entry_price_signal": sig["binance_price"],
                "atr_jpy":            sig["atr"],
                "invest_jpy":         invest_jpy,
                "tp1_order_id":       None,
                "sl_order_id":        None,
                "tp1_filled":         False,
            }
            active_count += 1
            if direction == "long":
                long_count += 1
            else:
                short_count += 1
            notify_entry_order(pair, direction, entry_price, amount, invest_jpy,
                               bb_price, available - invest_jpy)

        except OrderVerificationError:
            pass  # verify_order 内でメール送信済み
        except Exception as e:
            log(f"{pair} 注文エラー: {e}")
            send_email(
                f"【Zer0-CryptoBot】発注エラー - {pair.upper()}",
                f"コイン：{pair.upper()}\n方向：{direction}\nエラー：{e}",
            )

    return state


# ── メイン ────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    log(f"Executor 開始 signals={event.get('signals', [])}")
    signals = event.get("signals", [])

    try:
        api_key    = get_ssm(SSM_API_KEY,    decrypt=True)
        api_secret = get_ssm(SSM_API_SECRET, decrypt=True)
        bb         = BitbankClient(api_key, api_secret)

        state = load_state()
        log(f"現在のポジション: {list(state['positions'].keys())}")

        log("証拠金維持率チェック")
        if not check_margin_health(bb, state):
            save_state(state)
            log("緊急決済完了 → Phase A/B をスキップ")
            return {"statusCode": 200, "body": json.dumps({"emergency_close": True})}

        log("Phase A: 既存ポジションメンテナンス")
        state = maintain_positions(bb, state)

        if signals:
            log(f"Phase B: 新規シグナル処理 ({len(signals)} 件)")
            state = place_new_orders(bb, state, signals, event)
        else:
            log("Phase B: シグナルなし → スキップ")

        save_state(state)
        log("状態保存完了")

    except Exception as e:
        log(f"致命的エラー: {e}")
        send_email(
            "【Zer0-CryptoBot】Executor 致命的エラー",
            f"Executor で予期せぬエラーが発生しました。\n\nエラー: {e}",
        )
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    return {"statusCode": 200, "body": json.dumps({"positions": list(state["positions"].keys())})}
