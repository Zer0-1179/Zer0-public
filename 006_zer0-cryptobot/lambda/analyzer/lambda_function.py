"""
Zer0-CryptoBot Analyzer Lambda
EventBridge 4時間毎起動 → Binance で BTC/ETH/SOL の指標を計算し
BTC 200EMAで市場方向（ロング/ショート）を判定、シグナルがあれば Executor を invoke する。
"""

import os
import json
import time
import boto3
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.parse
import urllib.error

import alert_mail

# ── 定数 ──────────────────────────────────────────────────────────────────────
# 単一ホスト障害・レート制限時にシグナル検出が4時間丸ごと欠落するのを防ぐため、
# フォールバックホストを順にローテーションする（同一URL再試行はやらない）。
# data-api.binance.vision は認証不要な公開マーケットデータ専用ミラー（/api/v3/klines対応）。
BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://data-api.binance.vision",
]
BINANCE_PATH   = "/api/v3/klines"
BTC_SYMBOL     = "BTCUSDT"
INTERVAL       = "4h"
KLINES_LIMIT   = 500      # 200EMA ウォームアップ用に余裕を持って取得（末尾の未確定足を除外するため+1）
EMA_PERIOD     = 200
ATR_PERIOD     = 8
ST_MULT        = 2.5
VOL_PERIOD     = 20

# dst（ダブルSupertrend）フィルター: 遅いSupertrend（ATR20×4.0）が
# シグナル方向と同方向であることを要求する（ダマシ転換の除外。バックテストで PF +0.18）。
ST_SLOW_ATR    = 20
ST_SLOW_MULT   = 4.0

PAIRS = {
    "btc_jpy": {"binance": "BTCUSDT"},
    "eth_jpy": {"binance": "ETHUSDT"},
    "sol_jpy": {"binance": "SOLUSDT"},
}

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
EXECUTOR_NAME = os.environ["EXECUTOR_FUNCTION_NAME"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")

# ── モジュールスコープ boto3 クライアント ──────────────────────────────────────
_ses    = boto3.client("ses",    region_name=AWS_REGION)
_lambda = boto3.client("lambda", region_name=AWS_REGION)


# ── ユーティリティ ────────────────────────────────────────────────────────────
def log(msg: str):
    print(f"[Analyzer] {msg}")


JST = timezone(timedelta(hours=9))


def next_run_jst(now: datetime | None = None) -> str:
    """次回の Analyzer 定期実行時刻（cron(0 */4 * * ? *) = UTC 4時間境界）を JST 文字列で返す。"""
    now = now or datetime.now(timezone.utc)
    base = now.replace(minute=0, second=0, microsecond=0)
    nxt = base + timedelta(hours=4 - base.hour % 4)
    return nxt.astimezone(JST).strftime("%m/%d %H:%M")


def send_error_email(subject: str, level: str, title: str, headline: str,
                     rows: list[tuple[str, str]], action: str):
    """重要度バッジ付きHTML（alert_mail 共通テンプレート）で通知する。"""
    body = headline + "\n\n" + "\n".join(f"{k}：{v}" for k, v in rows)
    kw = {"level": level, "action": action, "title": title}
    try:
        mail_body = {
            "Text": {"Data": alert_mail.render_text(subject, body, **kw), "Charset": "UTF-8"},
            "Html": {"Data": alert_mail.render_html(subject, body, service="Zer0-CryptoBot",
                                                    source="Analyzer", **kw), "Charset": "UTF-8"},
        }
    except Exception as e:
        # 装飾の不具合で通知そのものが失われないよう、素のテキストで送る
        log(f"メール整形失敗（テキストのみで送信）: {e}")
        mail_body = {"Text": {"Data": body, "Charset": "UTF-8"}}
    try:
        _ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [SES_RECIPIENT]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": mail_body,
            },
        )
    except Exception as e:
        log(f"SES エラー通知送信失敗: {e}")


# ── Binance API ────────────────────────────────────────────────────────────────
# HTTP 418（IPバン）/429（レート制限）は送信元IP単位で全ホスト共通に効くため、
# ホストを変えても無駄で、叩き続けるとバン期間が延びる。即座にローテーションを打ち切り、
# Retry-After が待機予算内なら1回だけ待って再試行する。
# Lambda（VPC外）の送信元IPはAWS共有IPのため、本Botの呼出量（4時間毎4リクエスト）と無関係に
# 同じIPを使う他者の過剰アクセスでバンされることがある（2026-10-07 09:00に実例）。
BAN_STATUS_CODES  = (418, 429)
BAN_WAIT_BUDGET_S = 60     # 1回の起動で待機に使ってよい合計秒数（Lambdaタイムアウト120秒内に収める）
_ban_wait_left    = BAN_WAIT_BUDGET_S


class BinanceBanError(RuntimeError):
    """Binance が送信元IPをバン/レート制限している（418/429）。時間経過で自然復旧する。"""


def _fetch_binance_raw(symbol: str, params: str):
    """全ホストを順に試行する。418/429 を受けたら BinanceBanError を送出する。"""
    last_err = "不明"
    for i, host in enumerate(BINANCE_HOSTS):
        url = f"{host}{BINANCE_PATH}?{params}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            log(f"Binance取得失敗({symbol}, {host}): {last_err}")
            if e.code in BAN_STATUS_CODES:
                retry_after = None
                try:
                    retry_after = int(e.headers.get("Retry-After")) if e.headers else None
                except (TypeError, ValueError):
                    pass
                err = BinanceBanError(
                    f"Binance がIPバン/レート制限中({symbol}): {last_err}"
                    + (f", Retry-After={retry_after}秒" if retry_after is not None else "")
                )
                err.retry_after = retry_after
                raise err
        except Exception as e:
            last_err = str(e)
            log(f"Binance取得失敗({symbol}, {host}): {last_err}")
        if i < len(BINANCE_HOSTS) - 1:
            time.sleep(1)
    raise RuntimeError(f"Binance 全ホスト取得失敗({symbol}): {last_err}")


def fetch_binance(symbol: str) -> list[dict]:
    """Binance から 4h 足を KLINES_LIMIT 本取得して辞書リストで返す。
    ホストを変えながら BINANCE_HOSTS を順に試行する（同一ホスト再試行はしない）。
    418/429 は Retry-After が待機予算内なら1回だけ待って再試行する。"""
    global _ban_wait_left
    params = urllib.parse.urlencode({
        "symbol": symbol, "interval": INTERVAL, "limit": KLINES_LIMIT,
    })

    try:
        data = _fetch_binance_raw(symbol, params)
    except BinanceBanError as e:
        wait = e.retry_after
        if wait is None or wait > _ban_wait_left:
            raise
        log(f"Binance制限中のため {wait}秒待って再試行({symbol})")
        _ban_wait_left -= wait
        time.sleep(wait)
        data = _fetch_binance_raw(symbol, params)

    return [
        {
            "open":   float(c[1]),
            "high":   float(c[2]),
            "low":    float(c[3]),
            "close":  float(c[4]),
            "volume": float(c[5]),
        }
        for c in data
    ]


# ── テクニカル指標（純 Python） ────────────────────────────────────────────────
def ema(values: list[float], period: int) -> list[float]:
    """EWM EMA（pandas の ewm(adjust=False) 相当）"""
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def calc_atr(candles: list[dict], period: int = ATR_PERIOD) -> list[float]:
    """ATR（True Range の EWM 平滑化、period 期間）"""
    tr = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return ema(tr, period)


def calc_supertrend(candles: list[dict], atr_values: list[float],
                    mult: float = ST_MULT) -> dict:
    """
    Supertrend(ATR, mult) を計算する。
    atr_values は candles と同じ長さ（candles[0] に対する ATR は None 扱い）。
    ATR の先頭 1 要素は欠損のため、candles[1:] と atr_values を合わせる。
    mult を変えることで遅いSupertrend（dstフィルター用）も同関数で計算できる。
    """
    n = len(atr_values)
    highs  = [c["high"]  for c in candles[1:]]
    lows   = [c["low"]   for c in candles[1:]]
    closes = [c["close"] for c in candles[1:]]

    hl2         = [(h + l) / 2 for h, l in zip(highs, lows)]
    basic_upper = [hl + mult * a for hl, a in zip(hl2, atr_values)]
    basic_lower = [hl - mult * a for hl, a in zip(hl2, atr_values)]

    final_upper = basic_upper[:]
    final_lower = basic_lower[:]
    direction   = [1 if closes[0] > basic_upper[0] else -1]

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

    return {
        "direction":       direction[-1],
        "prev_direction":  direction[-2] if len(direction) >= 2 else direction[-1],
        "atr":             atr_values[-1],
        "last_close":      closes[-1],
    }


def analyze_coin(symbol: str, direction: str) -> dict | None:
    """
    コインのシグナルを判定して返す。
    direction: "long" または "short"
      long  条件: close > 200EMA, Supertrend緑転換（赤→緑）, Volume > 20本平均
      short 条件: close < 200EMA, Supertrend赤転換（緑→赤）, Volume > 20本平均
    条件を満たさない場合は None。
    """
    candles = fetch_binance(symbol)[:-1]  # 末尾の未確定足（オープン中）を除外
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]

    ema200      = ema(closes, EMA_PERIOD)
    last_close  = closes[-1]
    last_ema200 = ema200[-1]

    atr_values = calc_atr(candles)
    st         = calc_supertrend(candles, atr_values)

    # dst（ダブルSupertrend）フィルター用: 遅いSupertrend（ATR20×4.0）の方向
    atr_slow_values = calc_atr(candles, ST_SLOW_ATR)
    st_slow         = calc_supertrend(candles, atr_slow_values, ST_SLOW_MULT)

    if direction == "long":
        if last_close < last_ema200:
            log(f"  {symbol}: 200EMA以下 ({last_close:.4f} < {last_ema200:.4f}) → ロングスキップ")
            return None
        just_turned = (st["direction"] == 1 and st["prev_direction"] == -1)
        if not just_turned:
            dir_str = "緑継続" if st["direction"] == 1 else "赤"
            log(f"  {symbol}: ST緑転換なし ({dir_str})")
            return None
    else:  # short
        if last_close >= last_ema200:
            log(f"  {symbol}: 200EMA以上 ({last_close:.4f} >= {last_ema200:.4f}) → ショートスキップ")
            return None
        just_turned = (st["direction"] == -1 and st["prev_direction"] == 1)
        if not just_turned:
            dir_str = "赤継続" if st["direction"] == -1 else "緑"
            log(f"  {symbol}: ST赤転換なし ({dir_str})")
            return None

    # dst フィルター: 遅いSupertrend（ATR20×4.0）がシグナル方向と同方向か
    want_slow_dir = 1 if direction == "long" else -1
    if st_slow["direction"] != want_slow_dir:
        slow_str = "緑" if st_slow["direction"] == 1 else "赤"
        log(f"  {symbol}: dstフィルター棄却（遅いSupertrend={slow_str} ≠ {direction}方向）")
        return None

    vol_avg  = sum(volumes[-VOL_PERIOD - 1:-1]) / VOL_PERIOD
    last_vol = volumes[-1]
    if last_vol <= vol_avg:
        log(f"  {symbol}: Volume不足 ({last_vol:.0f} <= avg {vol_avg:.0f})")
        return None

    log(f"  {symbol}: {direction}シグナル確認 close={last_close:.4f} atr={st['atr']:.4f}")
    return {
        "binance_symbol": symbol,
        "binance_price":  last_close,
        "atr":            st["atr"],
    }


# ── メイン ────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    global _ban_wait_left
    _ban_wait_left = BAN_WAIT_BUDGET_S  # ウォームスタートでも起動ごとに待機予算をリセット
    log("Analyzer 開始")
    signals = []
    market_direction = "unknown"
    analysis_error = None

    try:
        # ── BTC 200EMA で市場方向を判定 ──────────────────────────────────
        log("BTC 200EMA 市場方向判定中...")
        btc_candles  = fetch_binance(BTC_SYMBOL)[:-1]  # 末尾の未確定足を除外
        btc_closes   = [c["close"] for c in btc_candles]
        btc_ema200   = ema(btc_closes, EMA_PERIOD)
        btc_price    = btc_closes[-1]
        btc_ema_val  = btc_ema200[-1]

        market_direction = "long" if btc_price >= btc_ema_val else "short"
        log(f"BTC {btc_price:.0f} vs EMA200 {btc_ema_val:.0f} → 市場方向: {market_direction.upper()}")

        # ── 各コイン分析 ──────────────────────────────────────────────
        for pair_jpy, cfg in PAIRS.items():
            log(f"分析中: {cfg['binance']} ({pair_jpy}) direction={market_direction}")
            try:
                result = analyze_coin(cfg["binance"], market_direction)
                if result:
                    result["pair"] = pair_jpy
                    result["side"] = market_direction
                    signals.append(result)
            except Exception as e:
                log(f"  {cfg['binance']} 分析エラー: {e}")
                send_error_email(
                    f"【Zer0-CryptoBot】⚠️要確認 Analyzer エラー - {pair_jpy}",
                    "warning",
                    f"{pair_jpy} の分析に失敗しました",
                    "このコインだけ今回のシグナル判定をスキップしました。他のコインの分析とポジション管理（Executor）は通常どおり動いています。",
                    [("対象コイン", pair_jpy), ("エラー", str(e)),
                     ("影響", "このコインの今回分のシグナルを取りこぼした可能性があります"),
                     ("次回の分析", f"{next_run_jst()} JST（自動で再試行）")],
                    "1回だけなら対応は不要です。同じコインで続けて届く場合は Analyzer のログ（CloudWatch Logs）を確認してください。",
                )

    except BinanceBanError as e:
        log(f"Binance制限で分析スキップ: {e}")
        analysis_error = e
        send_error_email(
            "【Zer0-CryptoBot】✅対応不要 Analyzer 分析スキップ（Binance一時制限）",
            "info",
            "今回の分析をスキップしました（自動で復旧します）",
            "Binance がアクセス元のIPを一時的に制限していたため、今回の4時間足の分析を見送りました。"
            "このBotの使い方が原因ではなく、時間がたてば自然に解除されます。",
            [("エラー", str(e)),
             ("原因", "Lambdaの送信元IPは他のAWS利用者と共有のため、同じIPの他者の過剰アクセスでBinanceに制限されることがあります（本Botの呼び出しは4時間ごと4回のみ）"),
             ("影響", "今回分のシグナル判定のみ。保有中ポジションの管理（Executor）は通常どおり動いています"),
             ("次回の分析", f"{next_run_jst()} JST（自動で再試行）")],
            "対応は不要です。このメールが3回以上続けて届く場合のみ、制限が長引いているのでご確認ください。",
        )
    except Exception as e:
        log(f"致命的エラー: {e}")
        analysis_error = e
        send_error_email(
            "【Zer0-CryptoBot】⚠️要確認 Analyzer 致命的エラー",
            "warning",
            "Analyzer で予期せぬエラーが発生しました",
            "今回の分析は全コイン分スキップしました。保有中ポジションの管理（Executor）は継続して起動しています。",
            [("エラー", str(e)),
             ("影響", "今回分の全コインのシグナル判定"),
             ("次回の分析", f"{next_run_jst()} JST（自動で再試行）")],
            "Analyzer のログ（CloudWatch Logs）でエラー内容を確認してください。次回も同じメールが届く場合はコードの不具合の可能性があります。",
        )

    # 分析エラー時もポジション管理のため常に Executor を invoke
    log(f"シグナル数: {len(signals)} → Executor invoke（メンテナンス含む）")
    try:
        payload = json.dumps({"signals": signals}).encode()
        _lambda.invoke(
            FunctionName=EXECUTOR_NAME,
            InvocationType="Event",   # 非同期
            Payload=payload,
        )
        log("Executor invoke 完了")
    except Exception as ie:
        log(f"Executor invoke 失敗: {ie}")
        send_error_email(
            "【Zer0-CryptoBot】🚨要対応 Executor invoke 失敗",
            "critical",
            "Executor（注文・ポジション管理）を起動できませんでした",
            "今回はポジションのTP/SL・トレーリング管理が行われていない可能性があります。",
            [("エラー", str(ie)),
             ("影響", "保有中ポジションの管理と、今回のシグナルによる新規注文"),
             ("次回の起動", f"{next_run_jst()} JST")],
            "bitbank でポジションと注文（SL）が残っているか確認してください。続く場合は /cryptobot/mode を pause_entry にして調査してください。",
        )

    if analysis_error:
        return {"statusCode": 500, "body": json.dumps({"error": str(analysis_error)})}

    return {
        "statusCode": 200,
        "body": json.dumps({
            "market_direction": market_direction,
            "signal_count": len(signals),
            "signals": signals,
        }),
    }
