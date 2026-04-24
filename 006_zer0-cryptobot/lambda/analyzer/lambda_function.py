"""
Zer0-CryptoBot Analyzer Lambda
EventBridge 4時間毎起動 → Binance で BTC/SOL/AVAX/ARB の指標を計算し
シグナルがあれば（なくても）Executor を invoke する。
"""

import os
import json
import math
import time
import boto3
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── 定数 ──────────────────────────────────────────────────────────────────────
BINANCE_BASE   = "https://api.binance.com/api/v3/klines"
BTC_SYMBOL     = "BTCUSDT"
INTERVAL       = "4h"
KLINES_LIMIT   = 200      # 200EMA 計算に必要な本数
EMA_PERIOD     = 200
ATR_PERIOD     = 10
ST_MULT        = 3.0
VOL_PERIOD     = 20

PAIRS = {
    "sol_jpy":  {"binance": "SOLUSDT"},
    "avax_jpy": {"binance": "AVAXUSDT"},
    "ada_jpy":  {"binance": "ADAUSDT"},
}

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
EXECUTOR_NAME = os.environ["EXECUTOR_FUNCTION_NAME"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


# ── ユーティリティ ────────────────────────────────────────────────────────────
def log(msg: str):
    print(f"[Analyzer] {msg}")


def send_error_email(subject: str, body: str):
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
    except Exception as e:
        log(f"SES エラー通知送信失敗: {e}")


# ── Binance API ────────────────────────────────────────────────────────────────
def fetch_binance(symbol: str) -> list[dict]:
    """Binance から 4h 足を KLINES_LIMIT 本取得して辞書リストで返す"""
    params = urllib.parse.urlencode({
        "symbol": symbol, "interval": INTERVAL, "limit": KLINES_LIMIT,
    })
    url = f"{BINANCE_BASE}?{params}"

    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if attempt == 2:
                raise RuntimeError(f"Binance HTTP エラー({symbol}): {e.code}")
            time.sleep(1)
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Binance 取得エラー({symbol}): {e}")
            time.sleep(1)

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


def calc_atr(candles: list[dict]) -> list[float]:
    """ATR（True Range の EWM 平滑化、ATR_PERIOD 期間）"""
    tr = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return ema(tr, ATR_PERIOD)


def calc_supertrend(candles: list[dict], atr_values: list[float]) -> dict:
    """
    Supertrend(ATR_PERIOD, ST_MULT) を計算する。
    atr_values は candles と同じ長さ（candles[0] に対する ATR は None 扱い）。
    ATR の先頭 1 要素は欠損のため、candles[1:] と atr_values を合わせる。
    """
    n = len(atr_values)
    # candles[1:] と atr_values が対応
    highs  = [c["high"]  for c in candles[1:]]
    lows   = [c["low"]   for c in candles[1:]]
    closes = [c["close"] for c in candles[1:]]

    hl2         = [(h + l) / 2 for h, l in zip(highs, lows)]
    basic_upper = [hl + ST_MULT * a for hl, a in zip(hl2, atr_values)]
    basic_lower = [hl - ST_MULT * a for hl, a in zip(hl2, atr_values)]

    final_upper = basic_upper[:]
    final_lower = basic_lower[:]
    direction   = [1 if closes[0] > basic_upper[0] else -1]

    for i in range(1, n):
        # upper band
        if basic_upper[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]
        # lower band
        if basic_lower[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]
        # 方向
        if direction[-1] == -1 and closes[i] > final_upper[i]:
            direction.append(1)
        elif direction[-1] == 1 and closes[i] < final_lower[i]:
            direction.append(-1)
        else:
            direction.append(direction[-1])

    # 最新バー（[-1]）と1本前（[-2]）の方向
    return {
        "direction":       direction[-1],
        "prev_direction":  direction[-2] if len(direction) >= 2 else direction[-1],
        "atr":             atr_values[-1],
        "last_close":      closes[-1],
    }


def analyze_coin(symbol: str) -> dict | None:
    """
    コインのシグナルを判定して返す。
    条件を満たさない場合は None。
    """
    candles = fetch_binance(symbol)
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]

    # 200EMA
    ema200      = ema(closes, EMA_PERIOD)
    last_close  = closes[-1]
    last_ema200 = ema200[-1]

    if last_close < last_ema200:
        log(f"  {symbol}: 200EMA以下 ({last_close:.4f} < {last_ema200:.4f})")
        return None

    # ATR + Supertrend
    atr_values = calc_atr(candles)
    st         = calc_supertrend(candles, atr_values)

    # Supertrend 緑転換（前バー赤 → 今バー緑）
    just_turned = (st["direction"] == 1 and st["prev_direction"] == -1)
    if not just_turned:
        dir_str = "緑継続" if st["direction"] == 1 else "赤"
        log(f"  {symbol}: ST転換なし ({dir_str})")
        return None

    # Volume（直近20本平均より大きい）
    vol_avg = sum(volumes[-VOL_PERIOD - 1:-1]) / VOL_PERIOD
    last_vol = volumes[-1]
    if last_vol <= vol_avg:
        log(f"  {symbol}: Volume不足 ({last_vol:.0f} <= avg {vol_avg:.0f})")
        return None

    log(f"  {symbol}: シグナル確認 close={last_close:.4f} atr={st['atr']:.4f}")
    return {
        "binance_symbol": symbol,
        "binance_price":  last_close,
        "atr":            st["atr"],
    }


# ── メイン ────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    log("Analyzer 開始")
    signals = []

    try:
        # ── BTC 200EMA フィルター ──────────────────────────────────────────
        log("BTC 200EMA フィルターチェック中...")
        btc_candles  = fetch_binance(BTC_SYMBOL)
        btc_closes   = [c["close"] for c in btc_candles]
        btc_ema200   = ema(btc_closes, EMA_PERIOD)
        btc_price    = btc_closes[-1]
        btc_ema_val  = btc_ema200[-1]

        if btc_price < btc_ema_val:
            log(f"BTC が 200EMA 以下 ({btc_price:.0f} < {btc_ema_val:.0f}) → 全コインスキップ")
        else:
            log(f"BTC 200EMA 上 ({btc_price:.0f} > {btc_ema_val:.0f}) → コイン分析開始")

            # ── 各コイン分析 ──────────────────────────────────────────────
            for pair_jpy, cfg in PAIRS.items():
                log(f"分析中: {cfg['binance']} ({pair_jpy})")
                try:
                    result = analyze_coin(cfg["binance"])
                    if result:
                        result["pair"] = pair_jpy
                        signals.append(result)
                except Exception as e:
                    log(f"  {cfg['binance']} 分析エラー: {e}")
                    send_error_email(
                        f"【Zer0-CryptoBot】Analyzer エラー - {pair_jpy}",
                        f"コイン分析中にエラーが発生しました。\n\nコイン: {pair_jpy}\nエラー: {e}",
                    )

    except Exception as e:
        log(f"致命的エラー: {e}")
        send_error_email(
            "【Zer0-CryptoBot】Analyzer 致命的エラー",
            f"Analyzer で予期せぬエラーが発生しました。\n\nエラー: {e}",
        )
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    log(f"シグナル数: {len(signals)} → Executor invoke（メンテナンス含む）")

    # ── Executor を常に invoke（シグナルなし時もメンテナンス実行） ──────────
    payload = json.dumps({"signals": signals}).encode()
    lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    lambda_client.invoke(
        FunctionName=EXECUTOR_NAME,
        InvocationType="Event",   # 非同期
        Payload=payload,
    )
    log("Executor invoke 完了")

    return {
        "statusCode": 200,
        "body": json.dumps({"signal_count": len(signals), "signals": signals}),
    }
