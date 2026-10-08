"""
通知メール共通テンプレート（重要度バッジ付きHTML + テキスト版）。

各Lambdaの既存の「件名 + プレーンテキスト本文」をそのまま渡すと、
冒頭に「✅対応不要 / ⚠️要確認 / 🚨要対応」のバッジを付けたダーク基調のHTMLに整形する。
本文は以下のルールで構造化する（既存の文面を書き換えずに見た目だけ整えるため）:
  - 最初の空行までの段落            → 見出し下の説明文
  - 「■ 見出し」                     → セクション見出し
  - 「項目：値」「項目: 値」          → 詳細テーブルの行
  - 「・」「- 」「  - 」で始まる行     → 箇条書き
  - URL                               → リンク
重要度は level 引数で明示するか、件名の 🚨/⚠️・「エラー/失敗/不一致」から自動判定する。

外部ライブラリ非依存。同一内容のコピーを各Lambdaディレクトリに置いて使う
（006: analyzer/executor/failure_notifier、008: lp_waitlist/stripe_webhook）。
"""

import html
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

LEVELS = {
    "info":     {"badge": "対応不要", "color": "#3ecf8e", "icon": "✅"},
    "warning":  {"badge": "要確認",   "color": "#f5a623", "icon": "⚠️"},
    "critical": {"badge": "要対応",   "color": "#ff5c5c", "icon": "🚨"},
}

DEFAULT_ACTIONS = {
    "info":     "対応は不要です。",
    "warning":  "内容を確認してください。1回だけで以後届かなければ様子見で構いません。続けて届く場合はログ（CloudWatch Logs）で原因を確認してください。",
    "critical": "すぐに上の内容を確認し、記載の手順に従って対応してください。",
}

_KV_RE   = re.compile(r"^\s*([^\s：:・■\-][^：:]{0,19}?)\s*[：:]\s*(.+)$")
_URL_RE  = re.compile(r"(https?://[^\s<>\"']+)")
_LIST_RE = re.compile(r"^\s*(?:・|- )\s*(.+)$")
_CODE_PREFIXES = ("aws ", "bash ", "--", "$ ")
_PREFIX_RE = re.compile(r"^【[^】]*】\s*")
_EMOJI_RE  = re.compile(r"^(?:[🚨⚠✅️\s]|要対応|要確認|対応不要)+")  # 既存の絵文字・バッジ文言


def detect_level(subject: str) -> str:
    if "🚨" in subject:
        return "critical"
    if "⚠" in subject or re.search(r"エラー|失敗|不一致", subject):
        return "warning"
    return "info"


def _title_from_subject(subject: str) -> str:
    return _EMOJI_RE.sub("", _PREFIX_RE.sub("", subject)).strip() or subject


def _inline(text: str) -> str:
    """HTMLエスケープした上でURLだけリンク化する。"""
    out, pos = [], 0
    for m in _URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        url = html.escape(m.group(1))
        out.append(f'<a href="{url}" style="color:#3ea8ff;">{url}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _parse(body: str) -> tuple[list[str], list[dict]]:
    """本文を (冒頭段落の行リスト, セクションのリスト) に分解する。
    セクション = {"heading": str|None, "blocks": [("kv", k, v) | ("li", text) | ("p", text)]}"""
    lines = body.strip("\n").split("\n")
    lead: list[str] = []
    i = 0
    # 冒頭段落: 最初の空行・見出し・項目行までの通常文
    while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("■") \
            and not _KV_RE.match(lines[i]) and not _LIST_RE.match(lines[i]):
        lead.append(lines[i].strip())
        i += 1
    sections: list[dict] = [{"heading": None, "blocks": []}]
    for line in lines[i:]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("■"):
            sections.append({"heading": s.lstrip("■ ").strip(), "blocks": []})
            continue
        kv = _KV_RE.match(line)
        li = _LIST_RE.match(line)
        if s.startswith(_CODE_PREFIXES):
            sections[-1]["blocks"].append(("code", s))
        elif li:
            sections[-1]["blocks"].append(("li", li.group(1)))
        elif kv and not s.startswith("http"):  # 「https://...」を項目行と誤認しない
            sections[-1]["blocks"].append(("kv", kv.group(1).strip(), kv.group(2).strip()))
        else:
            sections[-1]["blocks"].append(("p", s))
    return lead, [sec for sec in sections if sec["blocks"]]


def _blocks_html(blocks: list) -> str:
    parts, rows, items, code = [], [], [], []

    def flush():
        if code:
            parts.append('<pre style="background:#0d1b2e;border:1px solid #2a3a5c;border-radius:6px;padding:10px;'
                         'font-size:12px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0;">'
                         + html.escape("\n".join(code)) + "</pre>")
            code.clear()
        if rows:
            parts.append('<table style="width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;">'
                         + "".join(rows) + "</table>")
            rows.clear()
        if items:
            parts.append('<ul style="margin:6px 0;padding-left:20px;font-size:14px;line-height:1.7;">'
                         + "".join(items) + "</ul>")
            items.clear()

    for b in blocks:
        if b[0] == "code":
            if rows or items:
                flush()
            code.append(b[1])
            continue
        if code:
            flush()
        if b[0] == "kv":
            if items:
                flush()
            rows.append(
                '<tr><td style="padding:8px 10px;color:#8a9bb5;white-space:nowrap;vertical-align:top;'
                f'border-bottom:1px solid #2a3a5c;">{html.escape(b[1])}</td>'
                '<td style="padding:8px 10px;border-bottom:1px solid #2a3a5c;overflow-wrap:break-word;">'
                f'{_inline(b[2])}</td></tr>')
        elif b[0] == "li":
            if rows:
                flush()
            items.append(f"<li>{_inline(b[1])}</li>")
        else:
            flush()
            parts.append(f'<p style="margin:8px 0;font-size:14px;line-height:1.7;overflow-wrap:break-word;">{_inline(b[1])}</p>')
    flush()
    return "".join(parts)


def render_html(subject: str, body: str, *, service: str, source: str = "",
                level: str | None = None, action: str | None = None, title: str | None = None) -> str:
    level = level or detect_level(subject)
    lv = LEVELS[level]
    action = action or DEFAULT_ACTIONS[level]
    title = title or _title_from_subject(subject)
    lead, sections = _parse(body)
    lead_html = "".join(f'<p style="margin:0 0 4px;font-size:14px;line-height:1.7;">{_inline(l)}</p>' for l in lead)
    sec_html = ""
    for sec in sections:
        heading = sec["heading"] or "詳細"
        sec_html += (
            '<div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;">'
            f'<h3 style="color:#3ea8ff;margin:0 0 10px;font-size:15px;">{html.escape(heading)}</h3>'
            f"{_blocks_html(sec['blocks'])}</div>"
        )
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    origin = f"{service} / {source}" if source else service
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:sans-serif;background:#0d1b2e;color:#e0e0e0;padding:24px 16px;margin:0;">
  <div style="max-width:660px;margin:0 auto;">
    <p style="color:#8a9bb5;font-size:12px;margin:0 0 6px;">{html.escape(origin)} ・ {now_jst} JST</p>
    <div style="background:#1a2a3e;border-radius:8px;border-left:6px solid {lv['color']};padding:18px 20px;">
      <span style="display:inline-block;background:{lv['color']};color:#0d1b2e;font-weight:bold;font-size:13px;padding:3px 12px;border-radius:12px;">{lv['icon']} {lv['badge']}</span>
      <h2 style="color:#ffffff;font-size:19px;margin:12px 0 8px;">{html.escape(title)}</h2>
      {lead_html}
    </div>
    {sec_html}
    <div style="background:#1a2a3e;border-radius:8px;padding:16px;margin:16px 0;border:1px solid {lv['color']};">
      <h3 style="color:{lv['color']};margin:0 0 8px;font-size:15px;">あなたがすること</h3>
      <p style="margin:0;font-size:14px;line-height:1.7;">{_inline(action)}</p>
    </div>
    <p style="color:#5a6b85;font-size:12px;margin:8px 0 0;">このメールは {html.escape(origin)} から自動送信されています。</p>
  </div>
</body></html>"""


def render_text(subject: str, body: str, *, level: str | None = None, action: str | None = None,
                title: str | None = None) -> str:
    """HTML非対応メーラー向け。既存本文の前後にバッジと「あなたがすること」を足す。"""
    level = level or detect_level(subject)
    lv = LEVELS[level]
    action = action or DEFAULT_ACTIONS[level]
    return f"【{lv['badge']}】{title or _title_from_subject(subject)}\n\n{body.strip()}\n\n■ あなたがすること\n{action}\n"


def decorate_subject(subject: str, level: str | None = None) -> str:
    """件名の【サービス名】直後にバッジを入れる（既に🚨/⚠️/✅が付いていれば重複させない）。"""
    level = level or detect_level(subject)
    lv = LEVELS[level]
    m = _PREFIX_RE.match(subject)
    prefix, rest = (m.group(0).rstrip(), subject[m.end():]) if m else ("", subject)
    rest = _EMOJI_RE.sub("", rest)
    return f"{prefix}{lv['icon']}{lv['badge']} {rest}".strip()
