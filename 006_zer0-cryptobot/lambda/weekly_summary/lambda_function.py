"""Zer0-CryptoBot Weekly Summary Lambda

毎週日曜09:00 JSTに現在のポジション状況と含み損益をSESメールで送信する。
"""

import json
import os
import boto3
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
BITBANK_PUB   = "https://public.bitbank.cc"
SSM_STATE     = "/Zer0/CryptoBot/state"
SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
TRADES_BUCKET     = os.environ.get("TRADES_BUCKET", "zer0-dev-s3")
# 取引履歴は Executor が「1決済=1オブジェクト」で put する（追記消失レース回避）。
# 集計側は prefix を list_objects して各オブジェクトを読む。
TRADES_KEY_PREFIX = "cryptobot/trades/"

# ポジションを閉じない決済理由はTP1部分利確のみ（ポジション継続中の部分決済）。
# それ以外の理由文字列は全てポジションを閉じたとみなす。理由の列挙をクローズ側で
# 保守すると、新しい決済経路（緊急決済の派生パターン・手動決済の事後記録等）を
# 追加/変更するたびに更新漏れが起きやすい（実際に「手動決済（トレーリング中）」が
# 抜けており、2026-07-21分の2ポジションが勝率・PF・増額判断の集計から欠落していた）。
NON_CLOSING_REASONS = ("TP1部分利確",)

PAIR_LABELS   = {"btc_jpy": "BTC/JPY", "eth_jpy": "ETH/JPY", "sol_jpy": "SOL/JPY"}
SIDE_LABELS   = {"long": "ロング", "short": "ショート"}
STATUS_LABELS = {"buy_pending": "発注待ち", "active": "保有中", "trailing": "トレーリング中"}


def get_ssm(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    return ssm.get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def get_current_price(pair: str) -> float | None:
    try:
        url = f"{BITBANK_PUB}/{pair}/ticker"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return float(json.loads(resp.read())["data"]["last"])
    except Exception as e:
        print(f"価格取得失敗 {pair}: {e}")
        return None


def load_trades() -> list[dict]:
    """S3 の取引履歴（1決済=1オブジェクト）を prefix 配下から全件読み込む。
    オブジェクト未作成・読込失敗は空リスト/個別スキップで継続する。"""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    keys: list[str] = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=TRADES_BUCKET, Prefix=TRADES_KEY_PREFIX):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    keys.append(obj["Key"])
    except Exception as e:
        print(f"取引履歴一覧取得スキップ: {e}")
        return []

    trades = []
    for key in keys:
        try:
            raw = s3.get_object(Bucket=TRADES_BUCKET, Key=key)["Body"].read().decode("utf-8")
            trades.append(json.loads(raw))
        except Exception as e:
            print(f"取引履歴オブジェクト読込スキップ {key}: {e}")
    return trades


def summarize_trades(trades: list[dict], now: datetime) -> dict:
    """実現損益の週次・累計サマリーを計算する。
    勝率・PF はポジション単位（position_id でTP1部分利確とクローズを合算）。
    クローズ記録がまだ無いポジション（TP1のみ）は勝敗計算から除外する。
    最大DDは全取引記録を時系列でcumsumした「実現損益ベースの資産曲線」から算出する参考値
    （口座残高そのものではなく実現損益の推移のみを見ているため、バックテストの資本比%DDとは
    単純比較できない。円建てのまま参考表示する）。"""
    week_ago   = now - timedelta(days=7)
    weekly     = [t for t in trades if datetime.fromisoformat(t["ts"]) >= week_ago]
    weekly_pnl = sum(t["pnl_jpy"] for t in weekly)

    positions: dict[str, dict] = {}
    for i, t in enumerate(trades):
        pid = t.get("position_id") or f"_solo_{i}"
        p = positions.setdefault(pid, {"pnl": 0.0, "closed": False})
        p["pnl"] += t["pnl_jpy"]
        if t.get("reason") not in NON_CLOSING_REASONS:
            p["closed"] = True

    closed  = [p["pnl"] for p in positions.values() if p["closed"]]
    wins    = [v for v in closed if v > 0]
    losses  = [v for v in closed if v <= 0]

    sorted_trades = sorted(trades, key=lambda t: t["ts"])
    cum = 0.0
    peak = 0.0
    max_dd_jpy = 0.0
    for t in sorted_trades:
        cum += t["pnl_jpy"]
        peak = max(peak, cum)
        max_dd_jpy = max(max_dd_jpy, peak - cum)

    return {
        "total_pnl":    sum(t["pnl_jpy"] for t in trades),
        "weekly_pnl":   weekly_pnl,
        "weekly_count": len(weekly),
        "closed_count": len(closed),
        "win_rate":     len(wins) / len(closed) * 100 if closed else None,
        "pf":           (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None,
        "max_dd_jpy":   max_dd_jpy,
    }


# 資金増額判断の基準（project_006_scale_up_plan.md で確定・2026-06-25合意）
SCALE_UP_MIN_TRADES  = 20   # 最低ライン
SCALE_UP_SAFE_TRADES = 30   # 安心ライン
SCALE_UP_WIN_RATE_MIN  = 55.0
SCALE_UP_WIN_RATE_REC  = 60.0
SCALE_UP_PF_MIN         = 1.0


def compute_scale_up_metrics(stats: dict) -> dict:
    """資金増額判断に使う指標を構造化して返す（テキスト・HTML両方の整形の元データ）。"""
    n = stats["closed_count"]
    win_rate = stats["win_rate"]
    pf = stats["pf"]

    if win_rate is None:
        win_str, win_mark = "—（クローズ済みポジションなし）", ""
    else:
        win_mark = "○" if win_rate >= SCALE_UP_WIN_RATE_REC else ("△" if win_rate >= SCALE_UP_WIN_RATE_MIN else "×")
        win_str = f"{win_rate:.1f}%"

    if pf is None:
        pf_str, pf_mark = ("—（クローズ済みポジションなし）", "") if n == 0 else ("∞（無敗のためPF計算不可）", "○")
    else:
        pf_mark = "○" if pf > SCALE_UP_PF_MIN else "×"
        pf_str = f"{pf:.2f}"

    dd_val = -stats["max_dd_jpy"] if stats["max_dd_jpy"] else 0.0
    return {
        "closed_count": n,
        "win_str": win_str, "win_mark": win_mark,
        "pf_str": pf_str, "pf_mark": pf_mark,
        "dd_str": fmt_jpy(dd_val),
    }


def build_scale_up_progress(stats: dict) -> list[str]:
    """資金増額判断の進捗をテキスト本文用の行リストで返す。"""
    m = compute_scale_up_metrics(stats)
    n = m["closed_count"]
    return [
        f"  累計クローズ: {n}/{SCALE_UP_MIN_TRADES}（最低ライン）・{n}/{SCALE_UP_SAFE_TRADES}（安心ライン）",
        f"  実勝率: {m['win_str']} {m['win_mark']}（基準: 60%推奨/55%最低）".rstrip(),
        f"  実PF:   {m['pf_str']} {m['pf_mark']}（基準: >1.0）".rstrip(),
        f"  実現ベース最大DD: {m['dd_str']}（参考値・バックテストDD5.2%は資本比%のため単純比較不可）",
    ]


def build_scale_up_progress_html(stats: dict) -> str:
    """資金増額判断の進捗をHTMLメール用のテーブル行として返す（他ブロックと統一した表形式）。"""
    m = compute_scale_up_metrics(stats)
    n = m["closed_count"]
    mark_color = {"○": "#27ae60", "△": "#e2a03f", "×": "#e74c3c", "": "#888"}

    def row(label: str, value: str, note: str = "", mark: str = "") -> str:
        color = mark_color.get(mark, "#e0e0e0")
        mark_html = f' <span style="color:{color};font-weight:bold;">{mark}</span>' if mark else ""
        note_html = f' <span style="color:#666;">{note}</span>' if note else ""
        return f"""
        <tr>
          <td style="padding:6px;color:#888;">{label}</td>
          <td style="padding:6px;">{value}{mark_html}{note_html}</td>
        </tr>"""

    return (
        row("累計クローズ", f"{n}/{SCALE_UP_MIN_TRADES}（最低ライン）・{n}/{SCALE_UP_SAFE_TRADES}（安心ライン）")
        + row("実勝率", m["win_str"], "（基準: 60%推奨/55%最低）", m["win_mark"])
        + row("実PF", m["pf_str"], "（基準: >1.0）", m["pf_mark"])
        + row("実現ベース最大DD", m["dd_str"], "（参考値・単純比較不可）")
    )


def build_status_message(stats: dict | None) -> str:
    """「稼働状況」セクションの本文（HTML/テキスト共通）を1文で返す。
    シグナルが無い週は一見「止まっている」ように見えるため、Analyzer/Executorが
    定期実行を継続していることと、異常時は別途アラームメールで通知される旨を
    明示し、週次サマリー単体で「動いているか」の不安に答えられるようにする。"""
    if stats is None:
        return "取引履歴がまだありません。Analyzer（4時間毎）・Executor（30分毎）は正常に定期実行されています。"
    if stats["weekly_count"] > 0:
        return f"今週は{stats['weekly_count']}件の決済がありました。Bot は正常に稼働しています。"
    return (
        "今週は新規のエントリー・決済はありませんでした。"
        "Supertrendの転換シグナル待ちのため様子見しているだけで、異常ではありません。"
        "Analyzer（4時間毎）・Executor（30分毎）は定期実行を継続しており、"
        "実際に問題が起きた場合は別途アラームメールで即時通知されます。"
    )


def fmt_jpy(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}¥{value:,.0f}"


def fmt_pct(pnl: float, cost: float) -> str:
    if cost <= 0:
        return ""
    pct = pnl / cost * 100
    sign = "+" if pct >= 0 else ""
    return f"({sign}{pct:.2f}%)"


def build_position_info(pair: str, pos: dict) -> dict:
    status    = pos.get("status", "unknown")
    direction = pos.get("direction", "long")
    info = {
        "pair":          PAIR_LABELS.get(pair, pair),
        "side":          SIDE_LABELS.get(direction, direction),
        "direction":     direction,
        "status":        STATUS_LABELS.get(status, status),
        "entry_price":   None,
        "current_price": None,
        "quantity":      None,
        "pnl":           None,
        "cost":          None,
    }

    if status in ("active", "trailing"):
        entry = float(pos.get("entry_price", 0))
        qty   = float(pos.get("trail_amount" if status == "trailing" else "total_amount", 0))
        current = get_current_price(pair)
        if current and entry > 0 and qty > 0:
            pnl  = (current - entry) * qty if direction == "long" else (entry - current) * qty
            cost = entry * qty
            info.update({
                "entry_price":   entry,
                "current_price": current,
                "quantity":      qty,
                "pnl":           pnl,
                "cost":          cost,
            })
    elif status == "buy_pending":
        pass  # 成行発注のため約定前は参考JPY価格なし（entry_price_signal はBinance USDT建て）

    return info


def lambda_handler(event, context):
    now = datetime.now(JST)
    timestamp = now.strftime("%Y-%m-%d %H:%M JST")

    try:
        state = json.loads(get_ssm(SSM_STATE))
    except Exception as e:
        print(f"SSM読み込み失敗: {e}")
        state = {"positions": {}}

    positions = state.get("positions", {})
    pos_infos = [build_position_info(pair, pos) for pair, pos in positions.items()]
    total_pnl = sum(p["pnl"] for p in pos_infos if p["pnl"] is not None)
    has_pos   = bool(positions)

    trades = load_trades()
    stats  = summarize_trades(trades, now) if trades else None
    status_message = build_status_message(stats)

    # ── テキスト本文 ──────────────────────────────────────────────────────────
    lines = [f"【Zer0-CryptoBot】週次サマリー - {timestamp}", "", "■ 稼働状況", f"  {status_message}", ""]
    if not has_pos:
        lines.append("■ 現在のポジション: なし（キャッシュポジション）")
    else:
        lines.append(f"■ 現在のポジション（{len(positions)}件）")
        lines.append("")
        for p in pos_infos:
            lines.append(f"  {p['pair']} {p['side']} [{p['status']}]")
            if p["entry_price"]:
                lines.append(f"    エントリー: ¥{p['entry_price']:,.0f}")
            if p["current_price"]:
                lines.append(f"    現在価格:   ¥{p['current_price']:,.0f}")
            if p["pnl"] is not None:
                lines.append(f"    含み損益:   {fmt_jpy(p['pnl'])} {fmt_pct(p['pnl'], p['cost'])}")
            lines.append("")
        lines.append(f"■ 含み損益合計: {fmt_jpy(total_pnl)}")
    if stats:
        win_str = f"{stats['win_rate']:.1f}%" if stats["win_rate"] is not None else "—"
        pf_str  = f"{stats['pf']:.2f}" if stats["pf"] is not None else "—"
        lines += [
            "",
            "■ 実現損益（確定分）",
            f"  今週の確定損益: {fmt_jpy(stats['weekly_pnl'])}（決済 {stats['weekly_count']}件）",
            f"  累計確定損益:   {fmt_jpy(stats['total_pnl'])}",
            f"  クローズ済み:   {stats['closed_count']}ポジション / 勝率 {win_str} / PF {pf_str}",
            "  （参考: バックテスト2年・現実コスト込み 勝率72.9% / PF1.16 / 最大DD5.2%）",
            "",
            "■ 資金増額判断の進捗",
            *build_scale_up_progress(stats),
        ]
    lines += ["", "このメールは毎週日曜 09:00 JST に自動送信されます。"]
    body_text = "\n".join(lines)

    # ── HTML 本文 ─────────────────────────────────────────────────────────────
    pnl_color = "#27ae60" if total_pnl >= 0 else "#e74c3c"
    pos_rows  = ""
    for p in pos_infos:
        entry_str = f"¥{p['entry_price']:,.0f}" if p["entry_price"] else "—"
        curr_str  = f"¥{p['current_price']:,.0f}" if p["current_price"] else "—"
        if p["pnl"] is not None:
            pnl_str   = f"{fmt_jpy(p['pnl'])} {fmt_pct(p['pnl'], p['cost'])}"
            cell_color = "#27ae60" if p["pnl"] >= 0 else "#e74c3c"
        else:
            pnl_str    = "—"
            cell_color = "#666"
        pos_rows += f"""
          <tr>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;">{p['pair']}</td>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;">{p['side']}</td>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;">{p['status']}</td>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;">{entry_str}</td>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;">{curr_str}</td>
            <td style="padding:8px;border-bottom:1px solid #2a3a5c;color:{cell_color};font-weight:bold;">{pnl_str}</td>
          </tr>"""

    if not has_pos:
        pos_rows = """
          <tr><td colspan="6" style="padding:20px;text-align:center;color:#888;">
            ポジションなし（キャッシュポジション）
          </td></tr>"""

    total_block = "" if not has_pos else f"""
    <div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;text-align:center;">
      <span style="font-size:20px;font-weight:bold;color:{pnl_color};">
        含み損益合計: {fmt_jpy(total_pnl)}
      </span>
    </div>"""

    realized_block = ""
    if stats:
        win_str   = f"{stats['win_rate']:.1f}%" if stats["win_rate"] is not None else "—"
        pf_str    = f"{stats['pf']:.2f}" if stats["pf"] is not None else "—"
        wk_color  = "#27ae60" if stats["weekly_pnl"] >= 0 else "#e74c3c"
        cum_color = "#27ae60" if stats["total_pnl"]  >= 0 else "#e74c3c"
        realized_block = f"""
    <div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;">
      <h3 style="color:#3ea8ff;margin:0 0 12px;">実現損益（確定分）</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:6px;color:#888;">今週の確定損益</td>
          <td style="padding:6px;color:{wk_color};font-weight:bold;">{fmt_jpy(stats['weekly_pnl'])}（決済 {stats['weekly_count']}件）</td>
        </tr>
        <tr>
          <td style="padding:6px;color:#888;">累計確定損益</td>
          <td style="padding:6px;color:{cum_color};font-weight:bold;">{fmt_jpy(stats['total_pnl'])}</td>
        </tr>
        <tr>
          <td style="padding:6px;color:#888;">クローズ済み</td>
          <td style="padding:6px;">{stats['closed_count']}ポジション / 勝率 {win_str} / PF {pf_str}</td>
        </tr>
      </table>
      <p style="color:#555;font-size:12px;margin:8px 0 0;">参考: バックテスト2年・現実コスト込み 勝率72.9% / PF1.16 / 最大DD5.2%</p>
    </div>
    <div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;">
      <h3 style="color:#3ea8ff;margin:0 0 12px;">資金増額判断の進捗</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">{build_scale_up_progress_html(stats)}
      </table>
    </div>"""

    body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;background:#0d1b2e;color:#e0e0e0;padding:24px;margin:0;">
  <div style="max-width:660px;margin:0 auto;">
    <h2 style="color:#3ea8ff;margin-bottom:4px;">Zer0-CryptoBot 週次サマリー</h2>
    <p style="color:#888;margin-top:0;">{timestamp}</p>
    <div style="background:#16321f;border-left:4px solid #27ae60;border-radius:8px;padding:14px 16px;margin:16px 0;">
      <p style="margin:0;font-size:13px;color:#9fd6ad;">稼働状況</p>
      <p style="margin:4px 0 0;font-size:14px;">{status_message}</p>
    </div>
    <div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="color:#888;">
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">ペア</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">方向</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">状態</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">エントリー</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">現在価格</th>
            <th style="padding:8px;text-align:left;border-bottom:1px solid #2a3a5c;">含み損益</th>
          </tr>
        </thead>
        <tbody>{pos_rows}
        </tbody>
      </table>
    </div>
    {total_block}
    {realized_block}
    <p style="color:#555;font-size:12px;">このメールは毎週日曜 09:00 JST に自動送信されます。</p>
  </div>
</body>
</html>"""

    pnl_summary = fmt_jpy(total_pnl) if has_pos else "ポジションなし"
    subject = f"【Zer0-CryptoBot】週次サマリー {now.strftime('%m/%d')} | {pnl_summary}"
    boto3.client("ses", region_name=AWS_REGION).send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [SES_RECIPIENT]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"},
            },
        },
    )
    print(f"送信完了: {subject}")
    return {"statusCode": 200, "body": "ok"}
