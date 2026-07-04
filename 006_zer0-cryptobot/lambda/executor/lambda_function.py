"""
Zer0-CryptoBot Executor Lambda
Phase A: 既存ポジション管理（約定確認 / TP1後トレーリングSL / 24h未約定キャンセル）
Phase B: 新規シグナルの成行発注（動的ポジションサイズ）

v2変更: 信用取引（ロング＋ショート）対応 / ペア変更: BTC/ETH/SOL
v2.8変更: TP/SL倍率を変更（TP1 2.0→1.75 / SL 1.5→2.0 / トレール 1.5→1.0）
v3.1変更: 現実コスト（スリッページ＋手数料）込みバックテストで最適化
          （TP1 1.75→1.25 / SL 2.0→2.5 / トレール 1.0→0.75）
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
from datetime import datetime, timezone, timedelta

# ── 定数 ──────────────────────────────────────────────────────────────────────
MIN_INVEST_JPY  = 1000          # 最小発注額（円）
MAX_POSITIONS   = 3
MAX_PER_SIDE    = 2   # ロング・ショートそれぞれの最大同時保有数
CANCEL_AFTER_S  = 86400         # 未約定注文キャンセルまでの秒数（24時間）
BITBANK_PUB     = "https://public.bitbank.cc"
BITBANK_REST    = "https://api.bitbank.cc/v1"
SSM_API_KEY     = "/Zer0/CryptoBot/bitbank/api_key"
SSM_API_SECRET  = "/Zer0/CryptoBot/bitbank/api_secret"
SSM_STATE       = "/Zer0/CryptoBot/state"
SSM_MODE        = "/Zer0/CryptoBot/mode"

# セーフモード: normal（通常）/ pause_entry（新規建てのみ停止、既存ポジション管理は継続）
# / halt（全処理停止）。パラメータ未作成・不正値・読み込み失敗はすべて normal 扱い
# （SSM障害時に既存ポジションのSL管理まで止まる方が危険なため、fail-safeはnormal側に倒す）。
# 切替: aws ssm put-parameter --name /Zer0/CryptoBot/mode --value halt --type String --overwrite
BOT_MODE_NORMAL       = "normal"
BOT_MODE_PAUSE_ENTRY  = "pause_entry"
BOT_MODE_HALT         = "halt"
VALID_BOT_MODES       = (BOT_MODE_NORMAL, BOT_MODE_PAUSE_ENTRY, BOT_MODE_HALT)

# 取引履歴（確定損益）の保存先
TRADES_BUCKET      = os.environ.get("TRADES_BUCKET", "zer0-dev-s3")
TRADES_KEY_PREFIX  = "cryptobot/trades/"  # 1決済1ファイル: prefix/{ts}_{pair}_{ns}.json
JST                = timezone(timedelta(hours=9))

# 004ポートフォリオの非公開ダッシュボードページ用の統計JSON置き場（バケットは完全非公開。
# 閲覧は004 SSR LambdaのIAMロールに付与したs3:GetObjectのみで行い、匿名アクセスは不可）
STATS_BUCKET = os.environ.get("STATS_BUCKET", "")
STATS_KEY    = "stats.json"

# TP/SL 倍率（v3.1: 現実コスト込みグリッドスイープ＋ウォークフォワード検証で最適化）
TP1_MULT    = 1.25  # TP1 = entry ± ATR × 1.25
SL_MULT     = 2.5   # 初期SL = entry ∓ ATR × 2.5
TRAIL_MULT  = 0.75  # トレーリング幅 = 極値 ± ATR × 0.75（最大効果・OOSでも頑健）
TP1_RATIO   = 0.3   # TP1 の数量割合
TRAIL_RATIO = 0.7   # トレーリングSL 対象の数量割合
SL_SLIPPAGE = 0.003 # stop_limit SL の price オフセット率（急落/急騰での未約定防止）
FILL_POLL_INTERVAL_S = 2   # 成行約定待機ポーリング間隔（秒）
FILL_POLL_TIMEOUT_S  = 20  # 成行約定待機タイムアウト（秒）（MAX_POSITIONS=3 時最大 60s / Lambda timeout 300s）

# 証拠金維持率閾値（total_margin_balance_percentage = 残高/建玉時価総額×100）
# 通常の運用値: 3ポジション満杯で約55〜70%。実口座で確認済み（2026-04-28）
MARGIN_WARN_PCT = 50   # この値以下で警告メール（処理継続）
MARGIN_EMRG_PCT = 30   # この値以下で全ポジション緊急成行決済

# テスト専用強制フラグの有効化（ENABLE_FORCE_TEST=1 の時のみ動作）
# 本番Lambdaではこの環境変数を設定しないこと
FORCE_TEST_ENABLED = os.environ.get("ENABLE_FORCE_TEST", "0") == "1"

# コイン別精度（price小数桁数, amount小数桁数）
# price_prec は bitbank /spot/pairs の price_digits（= tick size）に一致させること。
#   btc_jpy: 0桁（tick 1円） / eth_jpy: 0桁（tick 1円） / sol_jpy: 1桁（tick 0.1円）
#   ※ sol_jpy を 0桁にすると tick size と不整合になり、丸めた価格で発注拒否や
#     意図せぬ価格ずれが起きるため 1桁に設定する（2026-06-15 実APIで確認）。
PAIRS = {
    "btc_jpy": {"price_prec": 0, "amount_prec": 4},
    "eth_jpy": {"price_prec": 0, "amount_prec": 4},
    "sol_jpy": {"price_prec": 1, "amount_prec": 4},
}

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")

# ── モジュールスコープ boto3 クライアント（再利用でコールドスタートを削減）──────
_ssm = boto3.client("ssm", region_name=AWS_REGION)
_ses = boto3.client("ses", region_name=AWS_REGION)
_s3  = boto3.client("s3",  region_name=AWS_REGION)


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


def order_fill(order: dict) -> tuple[float, float] | None:
    """約定済み注文から (average_price, executed_amount) を安全に取り出す。
    average_price / executed_amount が欠落・0・None の場合は None を返す
    （未約定・部分約定で値が取れないケース。KeyError を握りつぶさず明示スキップする）。"""
    avg = order.get("average_price")
    amt = order.get("executed_amount")
    if avg is None or amt is None:
        return None
    try:
        avg_f = float(avg)
        amt_f = float(amt)
    except (TypeError, ValueError):
        return None
    if avg_f <= 0 or amt_f <= 0:
        return None
    return avg_f, amt_f


# ── SSM ───────────────────────────────────────────────────────────────────────
def get_ssm(name: str, decrypt: bool = False) -> str:
    return _ssm.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]


def load_state() -> dict:
    try:
        raw = get_ssm(SSM_STATE, decrypt=False)
        return json.loads(raw)
    except Exception:
        return {"positions": {}}


def get_bot_mode() -> str:
    """セーフモード設定を読む。パラメータ未作成・不正値・読み込み失敗は normal 扱い。"""
    try:
        mode = get_ssm(SSM_MODE, decrypt=False).strip()
    except Exception:
        return BOT_MODE_NORMAL
    if mode not in VALID_BOT_MODES:
        log(f"不正なmode値のためnormal扱い: {mode!r}")
        return BOT_MODE_NORMAL
    return mode


def save_state(state: dict):
    for attempt in range(1, 4):
        try:
            _ssm.put_parameter(
                Name=SSM_STATE, Value=json.dumps(state),
                Type="String", Overwrite=True,
            )
            return
        except Exception as e:
            log(f"SSM書き込み失敗({attempt}/3): {e}")
            if attempt < 3:
                time.sleep(2)
    send_email(
        "【Zer0-CryptoBot】🚨SSM状態保存失敗",
        f"ポジション状態の保存に3回失敗しました。ポジション情報が失われた可能性があります。\n"
        f"手動でSSMを確認・修正してください。\n\nパラメータ: {SSM_STATE}",
    )


# ── SES ───────────────────────────────────────────────────────────────────────
def record_trade(pair: str, direction: str, reason: str, entry: float,
                 exit_price: float, amount: float, position_id: str | None = None,
                 estimated: bool = False):
    """確定損益を S3 に「1決済 = 1オブジェクト」で書き込む（put_object のみ）。

    キーは {prefix}{ts}_{pair}_{time_ns}.json でナノ秒サフィックス付き。
    get→modify→put の read-modify-write を一切行わないため、Executor の
    同時実行（現状は ReservedConcurrentExecutions:1 で抑止）やリトライが
    重なっても既存レコードを上書き・消失させない（追記消失レースが構造的に発生しない）。
    集計は Analyzer / WeeklySummary 側で prefix の list_objects により行う。
    記録失敗で取引処理を止めないこと（ログのみ残して継続）。
    estimated=True は成行クローズ等で約定価格が取れず現在価格で代用した記録。"""
    if direction == "long":
        pnl = (exit_price - entry) * amount
    else:
        pnl = (entry - exit_price) * amount
    record = {
        "ts":          datetime.now(JST).isoformat(timespec="seconds"),
        "pair":        pair,
        "direction":   direction,
        "reason":      reason,
        "entry_price": entry,
        "exit_price":  exit_price,
        "amount":      amount,
        "pnl_jpy":     round(pnl, 1),
        "position_id": position_id,
        "estimated":   estimated,
    }
    try:
        ts  = datetime.now(JST).strftime("%Y%m%dT%H%M%S")
        key = f"{TRADES_KEY_PREFIX}{ts}_{pair}_{time.time_ns()}.json"
        _s3.put_object(Bucket=TRADES_BUCKET, Key=key,
                       Body=json.dumps(record, ensure_ascii=False).encode("utf-8"))
        log(f"{pair}: 取引履歴記録 {reason} pnl={pnl:+,.1f}円")
    except Exception as e:
        log(f"{pair}: 取引履歴記録失敗（取引処理は継続）: {e}")
        return

    try:
        update_stats_json()
    except Exception as e:
        log(f"統計JSON更新失敗（取引履歴記録自体は成功・処理は継続）: {e}")


def _load_all_trades() -> list[dict]:
    """TRADES_BUCKET配下の全取引履歴オブジェクトを読み込む（WeeklySummaryと同じprefix走査）。"""
    trades = []
    try:
        paginator = _s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=TRADES_BUCKET, Prefix=TRADES_KEY_PREFIX):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    try:
                        raw = _s3.get_object(Bucket=TRADES_BUCKET, Key=obj["Key"])["Body"].read().decode("utf-8")
                        trades.append(json.loads(raw))
                    except Exception as e:
                        log(f"取引履歴オブジェクト読込スキップ {obj['Key']}: {e}")
    except Exception as e:
        log(f"取引履歴一覧取得失敗: {e}")
    return trades


def update_stats_json():
    """全取引履歴から資産推移（equity curve）を計算し、004ポートフォリオの
    非公開ダッシュボードページ用の統計JSONとして非公開S3バケットへ書き出す
    （閲覧は004 SSR Lambdaのs3:GetObject経由のみ。匿名アクセス不可）。
    ベストエフォート処理。失敗しても取引処理自体は継続する（呼び出し元がtry/exceptで包む）。"""
    if not STATS_BUCKET:
        return
    trades = _load_all_trades()
    trades.sort(key=lambda t: t["ts"])
    cum = 0.0
    points = []
    for t in trades:
        cum += t["pnl_jpy"]
        points.append({
            "ts":                 t["ts"],
            "pair":               t["pair"],
            "direction":          t["direction"],
            "reason":             t["reason"],
            "pnl_jpy":            t["pnl_jpy"],
            "cumulative_pnl_jpy": round(cum, 1),
        })
    payload = {
        "generated_at":  datetime.now(JST).isoformat(timespec="seconds"),
        "total_pnl_jpy": round(cum, 1),
        "trade_count":   len(trades),
        "points":        points,
    }
    _s3.put_object(
        Bucket=STATS_BUCKET, Key=STATS_KEY,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
        CacheControl="public, max-age=300",
    )
    log(f"統計JSON更新完了（{len(trades)}件）")


def send_email(subject: str, body: str):
    html_body = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="UTF-8">'
        '</head><body style="font-family:sans-serif;font-size:14px;line-height:1.8;">'
        + body.replace("\n", "<br>")
        + "</body></html>"
    )
    try:
        _ses.send_email(
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
        f"約定価格　：{entry:,.0f}円\n"
        f"購入金額　：{position_jpy:,.0f}円（{amount:.4f} {coin}）\n"
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
    """トレーリングSL更新はメール送信しない（ログのみ、呼び出し元で既に記録済み）。
    強トレンド時は30分毎に更新され得るため、毎回メールすると約定・クローズ・警告・緊急
    といった重要通知が埋もれてしまう。更新の事実自体はCloudWatch Logsで追跡できる。"""
    pass


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
        f"購入金額　：{entry * amount:,.0f}円（{amount:.4f} {coin}）\n"
        f"損益　　　：{pnl:+,.1f}円\n"
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

    def get_margin_positions(self) -> list[dict]:
        return self._get("/user/margin/positions")["data"]["positions"]

    def get_order(self, pair: str, order_id: int) -> dict:
        return self._get("/user/spot/order", {"pair": pair, "order_id": order_id})["data"]

    def create_order(self, pair: str, amount: str, price: str, side: str,
                     position_side: str | None = None,
                     trigger_price: str | None = None) -> dict:
        """
        信用取引は開設・決済ともに position_side が必須。
          開設ロング : side="buy",  position_side="long"
          決済ロング : side="sell", position_side="long"
          開設ショート: side="sell", position_side="short"
          決済ショート: side="buy",  position_side="short"
        trigger_price を指定すると stop_limit 注文（逆指値）になる。
        SL には必ず trigger_price を指定すること（指値のみだと即時約定する）。
        """
        order_type = "stop_limit" if trigger_price else "limit"
        body = {"pair": pair, "amount": amount, "price": price,
                "side": side, "type": order_type}
        if position_side is not None:
            body["position_side"] = position_side
        if trigger_price is not None:
            body["trigger_price"] = trigger_price
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


def _apply_entry_fill(bb: "BitbankClient", pair: str, pos: dict, order: dict, cfg: dict):
    """約定済みエントリー注文からTP1/SLを発注し pos を active に更新する（破壊的）。
    TP1/SL の order_id は発注直後に pos へ書き込むため、SL失敗後の再試行でもTP1を二重発注しない。
    (entry, amount, sl_price, tp1_price) を返す。notify_entry_fill は呼び出し側が行う。"""
    fill = order_fill(order)
    if not fill:
        raise ValueError(f"約定情報欠落: status={order.get('status')}, order={order.get('order_id')}")
    entry, amount = fill

    direction  = pos["direction"]
    close_side = "sell" if direction == "long" else "buy"
    atr_ratio  = pos["atr_jpy"] / pos["entry_price_signal"]
    atr_jpy    = atr_ratio * entry

    if direction == "long":
        tp1_price = entry + atr_jpy * TP1_MULT
        sl_price  = entry - atr_jpy * SL_MULT
    else:
        tp1_price = entry - atr_jpy * TP1_MULT
        sl_price  = entry + atr_jpy * SL_MULT

    # tp1_amount は切り捨てで算出し、trail_amount は残り全量とする。
    # 両方を四捨五入すると合計が amount（実際の保有数量）を超え、
    # トレーリングSL等の決済注文が拒否される恐れがあるため。
    prec        = cfg["amount_prec"]
    tp1_amount  = math.floor(amount * TP1_RATIO * (10 ** prec)) / (10 ** prec)
    trail_amount = round(amount - tp1_amount, prec)

    # TP1: pos に order_id が記録済みなら再試行のため既存注文を再利用（二重発注防止）
    if pos.get("tp1_order_id") is None:
        o_tp1 = bb.create_order(pair,
                                round_amount(tp1_amount, cfg["amount_prec"]),
                                round_price(tp1_price,   cfg["price_prec"]),
                                close_side, position_side=direction)
        verify_order(bb, pair, o_tp1["order_id"], "TP1注文")
        pos["tp1_order_id"] = o_tp1["order_id"]

    # SL: 同上
    if pos.get("sl_order_id") is None:
        sl_trigger_str = round_price(sl_price, cfg["price_prec"])
        sl_limit_f     = sl_price * (1 - SL_SLIPPAGE if direction == "long" else 1 + SL_SLIPPAGE)
        sl_limit_str   = round_price(sl_limit_f, cfg["price_prec"])
        o_sl = bb.create_order(pair,
                               round_amount(trail_amount, cfg["amount_prec"]),
                               sl_limit_str,
                               close_side, position_side=direction,
                               trigger_price=sl_trigger_str)
        verify_order(bb, pair, o_sl["order_id"], "初期SL注文（stop_limit）")
        pos["sl_order_id"] = o_sl["order_id"]

    pos.update({
        "status":        "active",
        "entry_price":   entry,
        "total_amount":  amount,
        "atr_jpy":       atr_jpy,
        "tp1_price":     tp1_price,
        "tp1_amount":    tp1_amount,
        "trail_amount":  trail_amount,
        "sl_price":      sl_price,
        "tp1_filled":    False,
    })
    return entry, amount, sl_price, tp1_price


def _apply_and_notify_fill(bb: "BitbankClient", pair: str, pos: dict, order: dict, cfg: dict):
    """_apply_entry_fill を呼び約定通知メールを送る。Phase A / Phase B 共通。"""
    entry, amount, sl_price, tp1_price = _apply_entry_fill(bb, pair, pos, order, cfg)
    remaining = get_available_margin(bb, pair)
    notify_entry_fill(pair, pos["direction"], entry, amount, sl_price, tp1_price, remaining)


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
        # フォールバック: available_balances が取れない場合は新規建てを抑制
        log("available_balances 取得不可 → 新規建て抑制のため 0 を返す")
        return 0.0
    except Exception as e:
        log(f"新規建て可能額取得失敗: {e}")
        return 0.0


# ── 証拠金維持率監視 ──────────────────────────────────────────────────────────
def _emergency_close_all(bb: BitbankClient, state: dict) -> list[str]:
    """全ポジションの未決済注文をキャンセルし、保有中のものを成行決済する。
    個別の失敗は無視して全ペアを処理し続けるが、成行決済（または約定数量確認）に
    失敗したペアは戻り値の failed_pairs に含めて呼び出し側に返す。
    呼び出し側はこれらを state から削除してはならない（実際の建玉が残っている可能性があるため）。"""
    failed_pairs: list[str] = []
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
        elif status == "buy_pending":
            # エントリーは成行のため buy_pending でも建玉は約定済みのことが多い。
            # 実際の約定数量を取得して決済する（未約定なら 0 → スキップ）。
            try:
                entry_order = bb.get_order(pair, pos["buy_order_id"])
                fill = order_fill(entry_order)
                amount = fill[1] if fill else 0
            except Exception as ge:
                log(f"{pair}: buy_pending 約定数量取得失敗 → 手動確認必要: {ge}")
                failed_pairs.append(pair)  # 実際の建玉有無が不明なため state から消さない
                continue
            if amount <= 0:
                continue  # 未約定エントリーはキャンセル済みで決済不要
        else:
            continue

        if amount > 0:
            amount_str = round_amount(amount, cfg["amount_prec"])
            try:
                bb.create_market_order(pair, amount_str, close_side, position_side=direction)
                log(f"{pair}: 緊急成行決済 {close_side} {amount_str}")
                try:
                    est_price = get_bitbank_price(pair)
                    record_trade(pair, direction, "緊急決済",
                                 pos.get("entry_price", est_price), est_price, amount,
                                 pos.get("position_id"), estimated=True)
                except Exception as re_:
                    log(f"{pair}: 緊急決済記録失敗: {re_}")
            except Exception as e:
                log(f"{pair}: 緊急成行決済失敗: {e}")
                failed_pairs.append(pair)  # 建玉が無防備なまま残っている

    return failed_pairs


def _notify_emergency_close_result(bb: BitbankClient, state: dict, trigger_reason: str):
    """緊急決済を実行し、失敗ペアが残っていれば state から消さず手動対応メールを送る。
    全ペア成功時のみ state["positions"] を空にする（失敗分を誤って消失させない）。"""
    failed_pairs = _emergency_close_all(bb, state)
    if failed_pairs:
        state["positions"] = {p: v for p, v in state["positions"].items() if p in failed_pairs}
        send_email(
            "【Zer0-CryptoBot】🚨緊急決済失敗 - 手動対応が必要",
            f"{trigger_reason}\n"
            f"緊急成行決済を試みましたが、以下のペアは決済に失敗し建玉が残っている可能性があります。\n"
            f"至急 bitbank 管理画面で手動確認・決済してください。\n\n"
            f"対象ペア: {', '.join(failed_pairs)}",
        )
    else:
        state["positions"] = {}
        send_email(
            "【Zer0-CryptoBot】🚨緊急決済実行",
            f"{trigger_reason}\n"
            f"全ポジションを成行決済しました。速やかに状況を確認してください。",
        )


def reconcile_positions(bb: BitbankClient, state: dict):
    """SSM state と bitbank実建玉のズレを検知する（自動修復はしない、通知のみ）。
    過去のHIGHバグ（緊急決済取りこぼし・部分約定孤児化等）はいずれも
    「stateと実態がズレる」ことが根本原因だったため、未知の経路によるズレも
    含めて毎サイクル検出する最終安全網として導入。
    buy_pending（発注直後で約定未確認）は一時的な状態のため対象外とする。"""
    try:
        actual = bb.get_margin_positions()
    except Exception as e:
        log(f"建玉リコンサイル: 実建玉取得失敗 → スキップ: {e}")
        return

    actual_by_pair = {}
    for p in actual:
        try:
            amount = float(p.get("open_amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            actual_by_pair[p["pair"]] = {"position_side": p.get("position_side"), "open_amount": amount}

    mismatches = []

    for pair, pos in state.get("positions", {}).items():
        if pos.get("status") == "buy_pending":
            continue
        direction = pos.get("direction")
        real = actual_by_pair.pop(pair, None)
        if real is None:
            mismatches.append(f"{pair}({direction}): stateにあるが実建玉なし（決済済み？孤児state）")
        elif real["position_side"] != direction:
            mismatches.append(f"{pair}: state方向={direction} vs 実建玉方向={real['position_side']}（不一致）")

    # state に対応エントリのない実建玉（孤児建玉）
    for pair, real in actual_by_pair.items():
        mismatches.append(f"{pair}({real['position_side']}): 実建玉があるがstateに記録なし（孤児建玉）")

    if mismatches:
        log(f"建玉リコンサイル不一致検出: {mismatches}")
        send_email(
            "【Zer0-CryptoBot】⚠️state⇄実建玉の不一致検出",
            "SSM stateとbitbank実建玉のズレを検出しました。自動修復は行っていません。手動確認をお願いします。\n\n"
            + "\n".join(mismatches),
        )
    else:
        log("建玉リコンサイル: 一致確認OK")


def check_margin_health(bb: BitbankClient, state: dict) -> bool:
    """証拠金維持率を確認する。
    - status が CALL/LOSSCUT: 緊急成行決済
    - total_margin_balance_percentage が MARGIN_EMRG_PCT(30%)以下: 緊急成行決済
    - MARGIN_WARN_PCT(50%)以下: 警告メール送信（処理継続）
    - 建玉なし(null) / 取得失敗: スキップして True を返す"""
    try:
        margin = bb.get_margin_status()
        log(f"margin/status raw: {json.dumps(margin, ensure_ascii=False)}")

        # status フィールドで危険状態を直接検出（percentage スケール不問）
        status = margin.get("status", "NORMAL")
        if status in ("CALL", "LOSSCUT", "DEBT"):
            log(f"証拠金ステータス異常: {status} → 緊急成行決済を実行")
            _notify_emergency_close_result(bb, state, f"証拠金ステータス: {status}")
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

    if ratio <= MARGIN_EMRG_PCT:
        log(f"証拠金維持率{MARGIN_EMRG_PCT}%以下 → 緊急成行決済を実行")
        _notify_emergency_close_result(
            bb, state, f"証拠金維持率 {ratio:.1f}% が{MARGIN_EMRG_PCT}%以下になりました"
        )
        return False

    if ratio <= MARGIN_WARN_PCT:
        send_email(
            "【Zer0-CryptoBot】⚠️証拠金警告",
            f"証拠金維持率が {ratio:.1f}% に低下しています（警告水準: {MARGIN_WARN_PCT}%以下）。\n"
            f"ポジション状況を確認してください。",
        )

    return True


# ── Phase A: 既存ポジション管理 ───────────────────────────────────────────────
def maintain_positions(bb: BitbankClient, state: dict, event: dict = {}) -> dict:
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

                # Phase B の即時ポーリングが成功した場合は通常ここに到達しない（タイムアウト時のfallback）
                # PARTIALLY_FILLED も約定済みとして扱う（成行で流動性不足時の部分約定対応）。
                # CANCELED_PARTIALLY_FILLED（一部約定後に残数量がキャンセルされた状態）も
                # 約定分の建玉が実在するため同様に扱う（そうしないとTP1/SLなしで孤児化する）。
                if status in ("FULLY_FILLED", "PARTIALLY_FILLED") or (
                    status.startswith("CANCELED") and order_fill(order)
                ):
                    log(f"{pair}({direction}): エントリー約定確認 (status={status}) → TP1/SL 発注")
                    try:
                        _apply_and_notify_fill(bb, pair, pos, order, cfg)
                    except ValueError as ve:
                        log(f"{pair}({direction}): {ve} → スキップ")
                        continue

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
                    # テスト専用フラグ: TP1 強制約定 / SL 強制約定（FORCE_TEST_ENABLED=True 時のみ有効）
                    if FORCE_TEST_ENABLED and event.get("test_force_tp1_fill"):
                        log(f"{pair}({direction}): [TEST] TP1 強制約定フラグ")
                        o_tp1 = {"status": "FULLY_FILLED",
                                 "average_price": str(pos["tp1_price"]),
                                 "executed_amount": str(pos.get("tp1_amount", 0))}
                    elif FORCE_TEST_ENABLED and event.get("test_force_sl_fill"):
                        o_tp1 = {"status": "UNFILLED"}
                    else:
                        o_tp1 = bb.get_order(pair, pos["tp1_order_id"])

                    tp1_fill = order_fill(o_tp1) if o_tp1.get("status") == "FULLY_FILLED" else None
                    if o_tp1.get("status") == "FULLY_FILLED" and not tp1_fill:
                        log(f"{pair}({direction}): TP1 FULLY_FILLED だが約定情報欠落 → 次回再評価")
                    elif o_tp1.get("status") == "FULLY_FILLED":
                        log(f"{pair}({direction}): TP1 約定 → トレーリングSL 開始")

                        sl_already_filled = False
                        sl_cancel_ok      = False
                        try:
                            bb.cancel_order(pair, pos["sl_order_id"])
                            sl_cancel_ok = True
                        except Exception as ce:
                            log(f"{pair}: 旧SL キャンセル失敗: {ce}")
                            try:
                                sl_chk = bb.get_order(pair, pos["sl_order_id"])
                                sl_fill = order_fill(sl_chk)
                                sl_status = sl_chk.get("status")
                                if sl_status == "FULLY_FILLED" and sl_fill:
                                    sl_price_f, sl_amount_f = sl_fill
                                    sl_already_filled = True
                                    log(f"{pair}: 旧SL 既に約定 → TP1+SL両方確定 → 終了")
                                    remaining = get_available_margin(bb, pair)
                                    record_trade(pair, direction, "SL（TP1後）",
                                                 pos["entry_price"],
                                                 sl_price_f,
                                                 sl_amount_f,
                                                 pos.get("position_id"))
                                    notify_close(pair, direction, "SL（TP1後）",
                                                 sl_price_f,
                                                 pos["entry_price"],
                                                 sl_amount_f,
                                                 remaining)
                                    to_delete.append(pair)
                                elif sl_status in ("CANCELED_UNFILLED",
                                                   "CANCELED_PARTIALLY_FILLED", "REJECTED"):
                                    # 既に消えている → 二重発注の心配なし。移行続行可。
                                    sl_cancel_ok = True
                            except Exception:
                                pass

                        if sl_already_filled:
                            continue

                        # 旧SL(70%)がまだ板に残っている可能性がある状態でトレーリングSLを
                        # 追加すると 70%+70% の二重決済注文になる。キャンセル未確認なら
                        # 今サイクルは移行を見送り、次回再試行する（active のまま据え置き）。
                        if not sl_cancel_ok:
                            log(f"{pair}: 旧SL キャンセル未確認 → トレーリング移行を次回へ延期")
                            continue

                        entry        = pos["entry_price"]
                        trail_amount = pos["trail_amount"]
                        atr_jpy      = pos["atr_jpy"]

                        trail_sl_price    = entry
                        trail_sl_str      = round_price(trail_sl_price, cfg["price_prec"])
                        trail_limit_f     = trail_sl_price * (1 - SL_SLIPPAGE if direction == "long" else 1 + SL_SLIPPAGE)
                        trail_limit_str   = round_price(trail_limit_f, cfg["price_prec"])
                        o_trail = bb.create_order(
                            pair,
                            round_amount(trail_amount, cfg["amount_prec"]),
                            trail_limit_str,
                            close_side, position_side=direction,
                            trigger_price=trail_sl_str,
                        )
                        verify_order(bb, pair, o_trail["order_id"], "トレーリングSL注文（stop_limit）")
                        state["positions"][pair] = {
                            "status":            "trailing",
                            "direction":         direction,
                            "entry_price":       entry,
                            "atr_jpy":           atr_jpy,
                            "position_id":       pos.get("position_id"),
                            "tp1_price":         pos["tp1_price"],
                            "trail_amount":      trail_amount,
                            "trail_sl_order_id": o_trail["order_id"],
                            "trail_sl_price":    trail_sl_price,
                            "highest_price": pos["tp1_price"] if direction == "long" else None,
                            "lowest_price":  pos["tp1_price"] if direction == "short" else None,
                        }
                        tp1_fill_price, tp1_filled_amount = tp1_fill
                        if direction == "long":
                            realized_pnl = (tp1_fill_price - entry) * tp1_filled_amount
                        else:
                            realized_pnl = (entry - tp1_fill_price) * tp1_filled_amount
                        record_trade(pair, direction, "TP1部分利確", entry,
                                     tp1_fill_price, tp1_filled_amount,
                                     pos.get("position_id"))
                        notify_trail_started(pair, direction, entry, pos["tp1_price"],
                                             tp1_fill_price, realized_pnl)
                        continue

                    # TP1未約定: 取消済/拒否 検出（外部キャンセル・異常系）
                    # bitbank API の status 値（CANCELED は L 1個）に一致させること。
                    elif o_tp1.get("status") in ("CANCELED_UNFILLED", "CANCELED_PARTIALLY_FILLED", "REJECTED"):
                        log(f"{pair}({direction}): TP1注文がキャンセル/拒否済み → SL確認")
                        try:
                            o_sl_chk = bb.get_order(pair, pos["sl_order_id"])
                            if o_sl_chk.get("status") in ("CANCELED_UNFILLED", "CANCELED_PARTIALLY_FILLED", "REJECTED"):
                                send_email(
                                    f"【Zer0-CryptoBot】🚨注文喪失 - {pair.upper()}",
                                    f"TP1・SL注文がともに喪失しています。手動対応が必要です。\n\n"
                                    f"コイン：{pair.upper()}\n方向：{direction}\n"
                                    f"TP1注文ID：{pos.get('tp1_order_id')}\n"
                                    f"SL注文ID：{pos.get('sl_order_id')}",
                                )
                        except Exception as chk_e:
                            log(f"{pair}: SL確認失敗: {chk_e}")

                    # TP1未約定時: 初期SL 約定確認
                    if FORCE_TEST_ENABLED and event.get("test_force_sl_fill"):
                        log(f"{pair}({direction}): [TEST] SL 強制約定フラグ")
                        o_sl = {"status": "FULLY_FILLED",
                                "average_price": str(pos.get("sl_price", pos["entry_price"])),
                                "executed_amount": str(pos.get("trail_amount", 0))}
                    else:
                        o_sl = bb.get_order(pair, pos["sl_order_id"])
                    sl_fill = order_fill(o_sl) if o_sl.get("status") == "FULLY_FILLED" else None
                    if o_sl.get("status") == "FULLY_FILLED" and not sl_fill:
                        log(f"{pair}({direction}): SL FULLY_FILLED だが約定情報欠落 → 次回再評価")
                    elif o_sl.get("status") == "FULLY_FILLED":
                        sl_fill_price, sl_fill_amount = sl_fill
                        log(f"{pair}({direction}): SL（損切り）約定 → TP1キャンセル → 残30%成行クローズ → 終了")
                        try:
                            bb.cancel_order(pair, pos["tp1_order_id"])
                        except Exception as ce:
                            log(f"{pair}: TP1キャンセル失敗: {ce}")
                            send_email(
                                f"【Zer0-CryptoBot】⚠️TP1キャンセル失敗 - {pair.upper()}",
                                f"SL約定後のTP1注文キャンセルに失敗しました。手動キャンセルが必要です。\n\n"
                                f"コイン：{pair.upper()}\n方向：{direction}\n"
                                f"TP1注文ID：{pos.get('tp1_order_id')}\nエラー：{ce}",
                            )
                        # SL(70%)約定後、残30%(tp1_amount)を成行クローズ
                        tp1_amt = pos.get("tp1_amount", 0)
                        if tp1_amt > 0:
                            try:
                                bb.create_market_order(pair,
                                                       round_amount(tp1_amt, cfg["amount_prec"]),
                                                       close_side, position_side=direction)
                                log(f"{pair}: 残30% 成行クローズ {tp1_amt}")
                                try:
                                    est_price = get_bitbank_price(pair)
                                    record_trade(pair, direction, "損切り（残30%成行）",
                                                 pos["entry_price"], est_price, tp1_amt,
                                                 pos.get("position_id"), estimated=True)
                                except Exception as re_:
                                    log(f"{pair}: 残30%記録失敗: {re_}")
                            except Exception as me:
                                log(f"{pair}: 残30%成行クローズ失敗: {me}")
                                send_email(
                                    f"【Zer0-CryptoBot】🚨残30%クローズ失敗 - {pair.upper()}",
                                    f"SL約定後の残30%成行クローズに失敗しました。手動決済が必要です。\n\n"
                                    f"コイン：{pair.upper()}\n方向：{direction}\n"
                                    f"数量：{tp1_amt}\nエラー：{me}",
                                )
                        remaining = get_available_margin(bb, pair)
                        # 損益記録・通知は SL の実約定量（sl_fill_amount）を使う。
                        # pos["trail_amount"] は発注時の想定数量で、部分約定時にはずれるため。
                        record_trade(pair, direction, "損切り（SL約定）",
                                     pos["entry_price"],
                                     sl_fill_price,
                                     sl_fill_amount,
                                     pos.get("position_id"))
                        notify_close(pair, direction, "損切り",
                                     sl_fill_price,
                                     pos["entry_price"],
                                     sl_fill_amount,
                                     remaining)
                        to_delete.append(pair)

            # ── トレーリングSL 管理 ────────────────────────────────────────
            elif pos["status"] == "trailing":
                if pos.get("trail_sl_order_id") is None:
                    # 前回のトレーリングSL更新でキャンセル後の再発注に失敗し、
                    # 保護注文が存在しない状態。高値/安値更新を待たず直近の
                    # trail_sl_price で即座に再発注して自己修復する。
                    log(f"{pair}({direction}): トレーリングSL不在を検知 → 直近水準で再発注")
                    try:
                        heal_price     = pos["trail_sl_price"]
                        heal_side      = "sell" if direction == "long" else "buy"
                        heal_trig_str  = round_price(heal_price, cfg["price_prec"])
                        heal_limit_f   = heal_price * (1 - SL_SLIPPAGE if direction == "long" else 1 + SL_SLIPPAGE)
                        heal_limit_str = round_price(heal_limit_f, cfg["price_prec"])
                        heal_order = bb.create_order(
                            pair,
                            round_amount(pos["trail_amount"], cfg["amount_prec"]),
                            heal_limit_str,
                            heal_side, position_side=direction,
                            trigger_price=heal_trig_str,
                        )
                        verify_order(bb, pair, heal_order["order_id"], "トレーリングSL再発注（自己修復）")
                        pos["trail_sl_order_id"] = heal_order["order_id"]
                        log(f"{pair}({direction}): トレーリングSL再発注成功 order_id={heal_order['order_id']}")
                    except Exception as heal_e:
                        log(f"{pair}: トレーリングSL再発注失敗（次回再試行）: {heal_e}")
                        send_email(
                            f"【Zer0-CryptoBot】🚨SL不在 - {pair.upper()}",
                            f"トレーリングSLの再発注に失敗し、ポジションが無防備な状態です。手動確認が必要です。\n\n"
                            f"コイン：{pair.upper()}\n方向：{direction}\nエラー：{heal_e}",
                        )
                    continue

                trail_order = bb.get_order(pair, pos["trail_sl_order_id"])

                trail_status = trail_order.get("status", "")
                trail_fill = order_fill(trail_order) if trail_status == "FULLY_FILLED" else None
                if trail_status == "FULLY_FILLED" and not trail_fill:
                    log(f"{pair}({direction}): トレーリングSL FULLY_FILLED だが約定情報欠落 → 次回再評価")
                elif trail_status == "FULLY_FILLED":
                    exit_p, exit_a = trail_fill
                    log(f"{pair}({direction}): トレーリングSL 約定 → 終了 exit={exit_p}")
                    remaining = get_available_margin(bb, pair)
                    record_trade(pair, direction, "トレーリングSL",
                                 pos["entry_price"], exit_p, exit_a,
                                 pos.get("position_id"))
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
                                        pos["trail_sl_order_id"] = None  # 以後は再発注失敗時も次回自己修復させる
                                    except Exception as ce:
                                        log(f"{pair}: トレーリングSLキャンセル失敗 → 更新スキップ: {ce}")
                                        continue
                                    new_trail_limit_str = round_price(new_trail_f * (1 - SL_SLIPPAGE), cfg["price_prec"])
                                    new_order = bb.create_order(
                                        pair,
                                        round_amount(pos["trail_amount"], cfg["amount_prec"]),
                                        new_trail_limit_str,
                                        "sell", position_side="long",
                                        trigger_price=new_trail_str,
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
                                        pos["trail_sl_order_id"] = None  # 以後は再発注失敗時も次回自己修復させる
                                    except Exception as ce:
                                        log(f"{pair}: トレーリングSLキャンセル失敗 → 更新スキップ: {ce}")
                                        continue
                                    new_trail_limit_str = round_price(new_trail_f * (1 + SL_SLIPPAGE), cfg["price_prec"])
                                    new_order = bb.create_order(
                                        pair,
                                        round_amount(pos["trail_amount"], cfg["amount_prec"]),
                                        new_trail_limit_str,
                                        "buy", position_side="short",
                                        trigger_price=new_trail_str,
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
    test_invest_jpy = event.get("test_invest_jpy")

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

        if direction == "long" and long_count >= MAX_PER_SIDE:
            log(f"{pair}: ロング上限({long_count}/{MAX_PER_SIDE}) → スキップ")
            continue
        if direction == "short" and short_count >= MAX_PER_SIDE:
            log(f"{pair}: ショート上限({short_count}/{MAX_PER_SIDE}) → スキップ")
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

            # 現在価格を取得して成行発注
            bb_price   = get_bitbank_price(pair)
            order_side = "buy" if direction == "long" else "sell"
            amount     = invest_jpy / bb_price
            amount_str = round_amount(amount, cfg["amount_prec"])

            log(f"{pair}({direction}): 成行発注 amount={amount_str} market={bb_price:.0f}円 invest={invest_jpy:.0f}円")
            order = bb.create_market_order(pair, amount_str, order_side, position_side=direction)
            verify_order(bb, pair, order["order_id"], "エントリー注文")

            pos = {
                "status":             "buy_pending",
                "direction":          direction,
                "position_id":        f"{pair}-{int(time.time())}",
                "buy_order_id":       order["order_id"],
                "buy_timestamp":      time.time(),
                "entry_price_signal": sig["binance_price"],
                "atr_jpy":            sig["atr"],
                "invest_jpy":         invest_jpy,
                "tp1_order_id":       None,
                "sl_order_id":        None,
                "tp1_filled":         False,
            }
            state["positions"][pair] = pos
            active_count += 1
            if direction == "long":
                long_count += 1
            else:
                short_count += 1

            # 成行約定を待って即時 TP1/SL 発注（最大 FILL_POLL_TIMEOUT_S 秒）
            # タイムアウト時は buy_pending のまま → Phase A が次回定期実行で処理
            filled_order = None
            deadline = time.time() + FILL_POLL_TIMEOUT_S
            while time.time() < deadline:
                try:
                    o = bb.get_order(pair, order["order_id"])
                    status = o.get("status", "")
                    # CANCELED_PARTIALLY_FILLED も部分約定分の建玉が実在するため filled 扱いにする
                    if status in ("FULLY_FILLED", "PARTIALLY_FILLED", "CANCELED_PARTIALLY_FILLED") and order_fill(o):
                        filled_order = o
                        break
                    if status.startswith("CANCELED"):
                        log(f"{pair}: 成行注文がキャンセルされた (status={status})")
                        break
                except Exception as pe:
                    log(f"{pair}: 約定ポーリングエラー: {pe}")
                time.sleep(FILL_POLL_INTERVAL_S)

            if filled_order:
                log(f"{pair}({direction}): 成行即時約定確認 (status={filled_order.get('status')}) → TP1/SL即時発注")
                try:
                    _apply_and_notify_fill(bb, pair, pos, filled_order, cfg)
                except Exception as fe:
                    log(f"{pair}: TP1/SL即時発注失敗（buy_pendingで継続）: {fe}")
            else:
                log(f"{pair}({direction}): 成行約定待機タイムアウト({FILL_POLL_TIMEOUT_S}s) → buy_pendingで次回確認")

        except OrderVerificationError:
            pass  # verify_order 内でメール送���済み
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
        mode = get_bot_mode()
        log(f"Bot mode: {mode}")
        if mode == BOT_MODE_HALT:
            log("mode=halt → 全処理スキップ（既存ポジション管理も含め停止中）")
            return {"statusCode": 200, "body": json.dumps({"mode": mode, "skipped": True})}

        api_key    = get_ssm(SSM_API_KEY,    decrypt=True)
        api_secret = get_ssm(SSM_API_SECRET, decrypt=True)
        bb         = BitbankClient(api_key, api_secret)

        # テスト専用: 指定注文を強制キャンセル（ENABLE_FORCE_TEST=1 時のみ有効）
        if FORCE_TEST_ENABLED:
            for cancel_req in event.get("cancel_orders", []):
                pair     = cancel_req.get("pair")
                order_id = cancel_req.get("order_id")
                try:
                    bb.cancel_order(pair, order_id)
                    log(f"[TEST] 強制キャンセル完了: {pair} order_id={order_id}")
                except Exception as ce:
                    log(f"[TEST] 強制キャンセル失敗: {pair} order_id={order_id}: {ce}")

            # テスト専用: 指定ペアを成行クローズ
            for close_req in event.get("market_close", []):
                pair     = close_req.get("pair")
                amount   = close_req.get("amount")
                side     = close_req.get("side")          # "buy" or "sell"
                pos_side = close_req.get("position_side")  # "long" or "short"
                cfg      = PAIRS.get(pair, {"price_prec": 0, "amount_prec": 4})
                try:
                    bb.create_market_order(pair, round_amount(float(amount), cfg["amount_prec"]),
                                           side, position_side=pos_side)
                    log(f"[TEST] 成行クローズ完了: {pair} {side} {amount} ({pos_side})")
                except Exception as me:
                    log(f"[TEST] 成行クローズ失敗: {pair}: {me}")

        state = load_state()
        log(f"現在のポジション: {list(state['positions'].keys())}")

        log("state⇄実建玉リコンサイル確認")
        reconcile_positions(bb, state)

        log("証拠金維持率チェック")
        if not check_margin_health(bb, state):
            save_state(state)
            log("緊急決済完了 → Phase A/B をスキップ")
            return {"statusCode": 200, "body": json.dumps({"emergency_close": True})}

        log("Phase A: 既存ポジションメンテナンス")
        state = maintain_positions(bb, state, event)

        if mode == BOT_MODE_PAUSE_ENTRY:
            log("mode=pause_entry → Phase Bスキップ（新規建て停止、既存ポジション管理は継続）")
        elif signals:
            log(f"Phase B: 新規シグナル処理 ({len(signals)} 件)")
            state = place_new_orders(bb, state, signals, event)
        else:
            # signals が空 = Analyzer 未呼び出し（EventBridge の :15/:45 直接起動）か
            # Analyzer が失敗してシグナルなしで invoke した場合。
            # いずれも Phase A（既存ポジション管理）は継続し、新規建てのみスキップする。
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
