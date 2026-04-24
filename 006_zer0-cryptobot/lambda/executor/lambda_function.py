"""
Zer0-CryptoBot Executor Lambda
Analyzer から invoke される。
Phase A: 既存ポジションのメンテナンス（24h未約定キャンセル / TP1約定後SL更新）
Phase B: 新規シグナルの注文発注
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
INVEST_JPY      = 3000          # 1ポジション投資額（円）
MAX_POSITIONS   = 2
CANCEL_AFTER_S  = 86400         # 未約定注文キャンセルまでの秒数（24時間）
BITBANK_PUB     = "https://public.bitbank.cc"
BITBANK_REST    = "https://api.bitbank.cc/v1"
SSM_API_KEY     = "/Zer0/CryptoBot/bitbank/api_key"
SSM_API_SECRET  = "/Zer0/CryptoBot/bitbank/api_secret"
SSM_STATE       = "/Zer0/CryptoBot/state"

# TP/SL 倍率
TP1_MULT  = 2.0
TP2_MULT  = 4.0
SL_MULT   = 1.5
TP1_RATIO = 0.3   # TP1 の数量割合
TP2_RATIO = 0.7   # TP2 の数量割合

# コイン別精度（price小数桁数, amount小数桁数）
PAIRS = {
    "sol_jpy":  {"price_prec": 0, "amount_prec": 4},
    "avax_jpy": {"price_prec": 0, "amount_prec": 4},
    "arb_jpy":  {"price_prec": 3, "amount_prec": 2},
}

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


# ── ユーティリティ ────────────────────────────────────────────────────────────
def log(msg: str):
    print(f"[Executor] {msg}")


def round_price(value: float, prec: int) -> str:
    """bitbank API に渡す価格文字列（小数桁数を揃える）"""
    if prec == 0:
        return str(int(round(value, 0)))
    return f"{value:.{prec}f}"


def round_amount(value: float, prec: int) -> str:
    """bitbank API に渡す数量文字列"""
    return f"{value:.{prec}f}"


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
    try:
        ses = boto3.client("ses", region_name=AWS_REGION)
        ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [SES_RECIPIENT]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body":    {"Text": {"Data": body,    "Charset": "UTF-8"}},
            },
        )
        log(f"メール送信: {subject}")
    except Exception as e:
        log(f"SES 送信失敗: {e}")


def notify_buy_order(pair: str, price: float, amount: float):
    total = price * amount
    subject = f"【Zer0-CryptoBot】買い注文発注 - {pair.upper()}"
    body = (
        f"コイン：{pair.upper()}\n"
        f"価格：{price:,.0f}円\n"
        f"数量：{amount}\n"
        f"投資額：{total:,.0f}円\n"
        f"※ 24時間で未約定の場合はキャンセルします"
    )
    send_email(subject, body)


def notify_buy_fill(pair: str, entry: float, amount: float, sl: float, tp1: float, tp2: float):
    subject = f"【Zer0-CryptoBot】買い執行 - {pair.upper()}"
    body = (
        f"コイン：{pair.upper()}\n"
        f"価格：{entry:,.4f}円\n"
        f"数量：{amount}\n"
        f"投資額：{entry * amount:,.0f}円\n"
        f"損切り：{sl:,.4f}円\n"
        f"TP1：{tp1:,.4f}円\n"
        f"TP2：{tp2:,.4f}円"
    )
    send_email(subject, body)


def notify_sell(pair: str, reason: str, price: float, entry: float, amount: float):
    pnl     = (price - entry) * amount
    pnl_pct = (price - entry) / entry * 100
    subject = f"【Zer0-CryptoBot】売り執行 - {pair.upper()}"
    body = (
        f"コイン：{pair.upper()}\n"
        f"種別：{reason}\n"
        f"売却価格：{price:,.4f}円\n"
        f"損益：{pnl:+,.0f}円（{pnl_pct:+.2f}%）"
    )
    send_email(subject, body)


def notify_sl_updated(pair: str, new_sl: float):
    subject = f"【Zer0-CryptoBot】SL更新（ブレイクイーブン） - {pair.upper()}"
    body = (
        f"コイン：{pair.upper()}\n"
        f"TP1 約定 → 損切りをブレイクイーブンに更新しました。\n"
        f"新SL：{new_sl:,.4f}円"
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

    def get_order(self, pair: str, order_id: int) -> dict:
        return self._get("/user/spot/order", {"pair": pair, "order_id": order_id})["data"]

    def get_active_orders(self, pair: str) -> list:
        return self._get("/user/spot/active_orders", {"pair": pair})["data"]["orders"]

    def create_order(self, pair: str, amount: str, price: str, side: str) -> dict:
        body = {"pair": pair, "amount": amount, "price": price,
                "side": side, "type": "limit"}
        return self._post("/user/spot/order", body)["data"]

    def cancel_order(self, pair: str, order_id: int) -> dict:
        return self._post("/user/spot/cancel_order",
                          {"pair": pair, "order_id": order_id})["data"]


def get_bitbank_price(pair: str) -> float:
    url = f"{BITBANK_PUB}/{pair}/ticker"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    return float(data["data"]["last"])


# ── Phase A: 既存ポジション管理 ───────────────────────────────────────────────
def maintain_positions(bb: BitbankClient, state: dict) -> dict:
    """
    既存ポジションを確認し、約定・24h未約定キャンセル・TP1後SL更新を処理する。
    state を更新して返す。
    """
    to_delete = []

    for pair, pos in state["positions"].items():
        cfg = PAIRS.get(pair, {"price_prec": 2, "amount_prec": 4})

        try:
            # ── 買い注文 未約定チェック ────────────────────────────────────
            if pos["status"] == "buy_pending":
                order = bb.get_order(pair, pos["buy_order_id"])
                status = order.get("status", "")

                if status == "FULLY_FILLED":
                    log(f"{pair}: 買い約定 → TP1/TP2/SL 発注")
                    entry     = float(order["average_price"])
                    amount    = float(order["executed_amount"])
                    atr_ratio = pos["atr_jpy"] / pos["entry_price_signal"]
                    atr_jpy   = atr_ratio * entry

                    tp1_price  = entry + atr_jpy * TP1_MULT
                    tp2_price  = entry + atr_jpy * TP2_MULT
                    sl_price   = entry - atr_jpy * SL_MULT
                    tp1_amount = round(amount * TP1_RATIO, cfg["amount_prec"])
                    tp2_amount = round(amount * TP2_RATIO, cfg["amount_prec"])

                    # TP1/TP2/SL 発注
                    o_tp1 = bb.create_order(pair,
                                            round_amount(tp1_amount, cfg["amount_prec"]),
                                            round_price(tp1_price, cfg["price_prec"]), "sell")
                    o_tp2 = bb.create_order(pair,
                                            round_amount(tp2_amount, cfg["amount_prec"]),
                                            round_price(tp2_price, cfg["price_prec"]), "sell")
                    o_sl  = bb.create_order(pair,
                                            round_amount(amount, cfg["amount_prec"]),
                                            round_price(sl_price, cfg["price_prec"]), "sell")

                    pos.update({
                        "status":       "active",
                        "entry_price":  entry,
                        "total_amount": amount,
                        "tp1_price":    tp1_price,
                        "tp2_price":    tp2_price,
                        "sl_price":     sl_price,
                        "tp1_order_id": o_tp1["order_id"],
                        "tp2_order_id": o_tp2["order_id"],
                        "sl_order_id":  o_sl["order_id"],
                        "tp1_filled":   False,
                    })
                    notify_buy_fill(pair, entry, amount, sl_price, tp1_price, tp2_price)

                elif time.time() - pos["buy_timestamp"] > CANCEL_AFTER_S:
                    log(f"{pair}: 24時間未約定 → キャンセル")
                    try:
                        bb.cancel_order(pair, pos["buy_order_id"])
                    except Exception as ce:
                        log(f"{pair}: キャンセル失敗（既にキャンセル済み？）: {ce}")
                    to_delete.append(pair)
                    send_email(
                        f"【Zer0-CryptoBot】注文キャンセル - {pair.upper()}",
                        f"コイン：{pair.upper()}\n24時間未約定のため注文をキャンセルしました。",
                    )

            # ── アクティブポジション: TP1/SL チェック ───────────────────
            elif pos["status"] == "active":
                if not pos.get("tp1_filled"):
                    o_tp1 = bb.get_order(pair, pos["tp1_order_id"])
                    if o_tp1.get("status") == "FULLY_FILLED":
                        log(f"{pair}: TP1 約定 → SL をブレイクイーブンに更新")
                        # 既存 SL をキャンセルして entry 価格で再発注
                        try:
                            bb.cancel_order(pair, pos["sl_order_id"])
                        except Exception as ce:
                            log(f"{pair}: SL キャンセル失敗: {ce}")

                        entry  = pos["entry_price"]
                        remain = round(pos["total_amount"] * TP2_RATIO, cfg["amount_prec"])
                        o_sl_new = bb.create_order(
                            pair,
                            round_amount(remain, cfg["amount_prec"]),
                            round_price(entry, cfg["price_prec"]),
                            "sell",
                        )
                        pos["sl_order_id"]  = o_sl_new["order_id"]
                        pos["sl_price"]     = entry
                        pos["tp1_filled"]   = True
                        notify_sl_updated(pair, entry)

                # TP2 または SL 約定確認（ポジション終了判定）
                if pos.get("tp1_filled"):
                    o_tp2 = bb.get_order(pair, pos["tp2_order_id"])
                    if o_tp2.get("status") == "FULLY_FILLED":
                        log(f"{pair}: TP2 約定 → ポジション終了")
                        notify_sell(pair, "TP2",
                                    float(o_tp2["average_price"]),
                                    pos["entry_price"],
                                    float(o_tp2["executed_amount"]))
                        to_delete.append(pair)

                o_sl = bb.get_order(pair, pos["sl_order_id"])
                if o_sl.get("status") == "FULLY_FILLED" and pair not in to_delete:
                    reason = "ブレイクイーブン" if pos.get("tp1_filled") else "損切り"
                    log(f"{pair}: SL({reason}) 約定 → ポジション終了")
                    notify_sell(pair, reason,
                                float(o_sl["average_price"]),
                                pos["entry_price"],
                                float(o_sl["executed_amount"]))
                    to_delete.append(pair)

        except Exception as e:
            log(f"{pair} メンテナンスエラー: {e}")
            send_email(
                f"【Zer0-CryptoBot】Executor メンテナンスエラー - {pair.upper()}",
                f"コイン：{pair.upper()}\nエラー：{e}",
            )

    for pair in to_delete:
        state["positions"].pop(pair, None)

    return state


# ── Phase B: 新規シグナル注文 ─────────────────────────────────────────────────
def place_new_orders(bb: BitbankClient, state: dict, signals: list) -> dict:
    """新規シグナルの指値注文を発注する"""
    active_count = len(state["positions"])

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

        cfg = PAIRS[pair]

        try:
            # 残高確認
            assets = bb.get_assets()
            jpy    = float(assets.get("jpy", {}).get("free_amount", "0"))
            if jpy < INVEST_JPY:
                log(f"{pair}: JPY 残高不足 ({jpy:.0f} < {INVEST_JPY}) → スキップ")
                continue

            # 現在価格を取得して指値を計算
            bb_price  = get_bitbank_price(pair)
            buy_price = bb_price * 0.99
            amount    = INVEST_JPY / buy_price

            price_str  = round_price(buy_price, cfg["price_prec"])
            amount_str = round_amount(amount, cfg["amount_prec"])

            log(f"{pair}: 買い指値発注 price={price_str} amount={amount_str}")
            order = bb.create_order(pair, amount_str, price_str, "buy")

            state["positions"][pair] = {
                "status":              "buy_pending",
                "buy_order_id":        order["order_id"],
                "buy_timestamp":       time.time(),
                "entry_price_signal":  sig["binance_price"],   # ATR比率計算用
                "atr_jpy":             sig["atr"],             # Binance ATR（USDT）
                "tp1_order_id":        None,
                "tp2_order_id":        None,
                "sl_order_id":         None,
                "tp1_filled":          False,
            }
            active_count += 1
            notify_buy_order(pair, buy_price, amount)

        except Exception as e:
            log(f"{pair} 注文エラー: {e}")
            send_email(
                f"【Zer0-CryptoBot】発注エラー - {pair.upper()}",
                f"コイン：{pair.upper()}\nエラー：{e}",
            )

    return state


# ── メイン ────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    log(f"Executor 開始 signals={event.get('signals', [])}")
    signals = event.get("signals", [])

    try:
        # SSM からキー取得
        api_key    = get_ssm(SSM_API_KEY, decrypt=True)
        api_secret = get_ssm(SSM_API_SECRET, decrypt=True)
        bb         = BitbankClient(api_key, api_secret)

        # 状態読み込み
        state = load_state()
        log(f"現在のポジション: {list(state['positions'].keys())}")

        # Phase A: メンテナンス
        log("Phase A: 既存ポジションメンテナンス")
        state = maintain_positions(bb, state)

        # Phase B: 新規シグナル
        if signals:
            log(f"Phase B: 新規シグナル処理 ({len(signals)} 件)")
            state = place_new_orders(bb, state, signals)
        else:
            log("Phase B: シグナルなし → スキップ")

        # 状態保存
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
