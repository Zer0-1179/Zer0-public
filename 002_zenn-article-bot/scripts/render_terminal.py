"""Zenn記事evidence画像用のターミナル風レンダラー（Windows コマンドプロンプト風）。

実際のコマンド・出力（AWS CLI等で実機検証した本物のテキスト）を、Windows Terminal上で
コマンドプロンプト(cmd.exe)を開いたときの見た目に似せてPNG化する。あくまで見た目の演出であり、
実際のWindowsのスクリーンショットではない（GUIのないLinux環境のため撮影不可）。

呼び出し側(gen_evidence.py等)のインターフェースは旧macOS風スクリプトと同一
（render(title, lines, result, out_path, width_chars=100)）なので、
既存の呼び出しコードを変更せずに差し替え可能。

複数ステップ（複数コマンド実行）を1本のアニメーションGIFにまとめたい場合は
render_gif(steps, out_path) を使う（2026-08-20追加。エビデンス画像の枚数削減用）。
"""
import io
import re
import textwrap
import matplotlib
from matplotlib import font_manager

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(FONT_PATH)
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image

# AWSアカウントIDは12桁の連続数字。特定のIDをソースにハードコードすると
# 公開リポジトリの機密情報スキャンに引っかかるため、パターンマッチで汎用的にマスクする
ACCOUNT_ID_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
MASK = "${AWS::AccountId}"

# コマンドプロンプトのプロンプトに使う汎用ユーザー名（個人情報を含まない汎用表記）
CMD_USER = "user"
CMD_PROMPT = f"C:\\Users\\{CMD_USER}>"


def mask(s: str) -> str:
    return ACCOUNT_ID_RE.sub(MASK, s)


def _wrap_lines(lines, width_chars):
    """(kind, text)のリストを、1画面行=1要素の(kind, text, is_prompt_line)リストに変換する。
    render()・render_gif()で共通利用。"""
    prompt_prefix = CMD_PROMPT
    wrapped = []
    for kind, text in lines:
        text = mask(text)
        indent = " " * len(prompt_prefix) if kind == "cmd" else ""
        for line_idx, sub in enumerate(text.split("\n")):
            if sub == "":
                wrapped.append((kind, "", False))
                continue
            sub_indent = "" if (kind != "cmd" or line_idx == 0) else indent
            pieces = textwrap.wrap(
                sub, width=width_chars, subsequent_indent="    ",
                break_long_words=True, break_on_hyphens=False,
            ) or [""]
            for p in pieces:
                is_prompt_line = (kind == "cmd" and line_idx == 0 and p == pieces[0])
                wrapped.append((kind, sub_indent + p, is_prompt_line))
    return wrapped


def render(title, lines, result, out_path, width_chars=100):
    """
    lines: list of (kind, text) where kind in {"cmd", "out", "comment"}
    result: final green summary line (string, no prefix)
    """
    wrapped = _wrap_lines(lines, width_chars)

    n_lines = len(wrapped)
    line_h = 0.30
    top_pad = 1.15
    bottom_pad = 1.4
    fig_h = top_pad + bottom_pad + n_lines * line_h + 0.6
    fig_w = 13.5

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    # 先にaxesを全面表示にしておく（後から動かすとtransDataがずれ、実測済みの
    # テキストx座標がsavefig時の座標系と食い違ってプロンプトのセグメントが重なる/開く）
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    TERM_BG = "#0c0c0c"
    TAB_BG = "#202020"
    fig.patch.set_facecolor(TERM_BG)
    ax.set_facecolor(TERM_BG)

    # window body
    body = FancyBboxPatch(
        (0.15, 0.15), fig_w - 0.3, fig_h - 0.3,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=0, facecolor=TERM_BG, zorder=0,
    )
    ax.add_patch(body)

    # tab strip (Windows Terminal style: tab chip on the left, window controls on the right)
    bar_h = 0.62
    bar_y = fig_h - bar_h
    titlebar = FancyBboxPatch(
        (0.15, bar_y), fig_w - 0.3, bar_h,
        boxstyle="round,pad=0.0,rounding_size=0.12",
        linewidth=0, facecolor=TAB_BG, zorder=1,
    )
    ax.add_patch(titlebar)

    # active tab chip ("コマンド プロンプト")
    tab_w = 2.9
    tab = FancyBboxPatch(
        (0.35, bar_y + 0.08), tab_w, bar_h - 0.16,
        boxstyle="round,pad=0.0,rounding_size=0.08",
        linewidth=0, facecolor="#2d2d2d", zorder=2,
    )
    ax.add_patch(tab)
    ax.text(
        0.55, bar_y + bar_h / 2, ">_",
        color="#c5c5c5", fontsize=10, ha="left", va="center", zorder=3,
        weight="bold", parse_math=False,
    )
    ax.text(
        0.85, bar_y + bar_h / 2, "コマンド プロンプト",
        color="#e8e8e8", fontsize=9.5, ha="left", va="center", zorder=3,
        parse_math=False,
    )

    # window title (center)
    ax.text(
        fig_w / 2, bar_y + bar_h / 2, title,
        color="#a8a8a8", fontsize=11, ha="center", va="center", zorder=2,
        parse_math=False,
    )

    # window controls (minimize / maximize / close) — Windows風は右側・単色アイコン
    ctrl_y = bar_y + bar_h / 2
    ax.text(fig_w - 1.05, ctrl_y, "–", color="#c5c5c5", fontsize=13,
            ha="center", va="center", zorder=3, parse_math=False)  # minimize
    ax.text(fig_w - 0.65, ctrl_y, "□", color="#c5c5c5", fontsize=10,
            ha="center", va="center", zorder=3, parse_math=False)  # maximize
    ax.text(fig_w - 0.25, ctrl_y, "x", color="#c5c5c5", fontsize=11,
            ha="center", va="center", zorder=3, parse_math=False)  # close

    y = fig_h - bar_h - 0.4
    x0 = 0.5
    for kind, text, is_prompt_line in wrapped:
        if kind == "cmd":
            # cmd.exeのプロンプトは単色（色分けなし）: C:\Users\user>command
            line_text = (CMD_PROMPT + text) if is_prompt_line else text
            ax.text(x0, y, line_text, color="#f2f2f2", fontsize=10.5,
                    ha="left", va="top", family="Noto Sans CJK JP", zorder=2, parse_math=False)
        elif kind == "comment":
            ax.text(x0, y, text, color="#7f9a7f", fontsize=10.5,
                    ha="left", va="top", family="Noto Sans CJK JP", zorder=2, parse_math=False)
        else:
            ax.text(x0, y, text, color="#cccccc", fontsize=10.5,
                    ha="left", va="top", family="Noto Sans CJK JP", zorder=2, parse_math=False)
        y -= line_h

    # result line
    y -= 0.15
    result_lines = textwrap.wrap(
        "結果: " + result, width=width_chars - 5, subsequent_indent="      "
    )
    for rl in result_lines:
        ax.text(
            x0, y, rl, color="#3ddc71", fontsize=11.5,
            ha="left", va="top", weight="bold", zorder=2, parse_math=False,
        )
        y -= line_h

    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"saved {out_path}")


def _draw_window(title, visible_lines, cursor_on, fig_w, line_h):
    """render_gif()の1フレーム分を描画しPIL Imageで返す（renderの窓chromeを流用）。"""
    top_pad = 1.15
    bottom_pad = 1.4
    visible_n = max(len(visible_lines), 1)
    fig_h = top_pad + bottom_pad + visible_n * line_h + 0.6

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    TERM_BG = "#0c0c0c"
    TAB_BG = "#202020"
    fig.patch.set_facecolor(TERM_BG)
    ax.set_facecolor(TERM_BG)

    body = FancyBboxPatch(
        (0.15, 0.15), fig_w - 0.3, fig_h - 0.3,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=0, facecolor=TERM_BG, zorder=0,
    )
    ax.add_patch(body)

    bar_h = 0.62
    bar_y = fig_h - bar_h
    titlebar = FancyBboxPatch(
        (0.15, bar_y), fig_w - 0.3, bar_h,
        boxstyle="round,pad=0.0,rounding_size=0.12",
        linewidth=0, facecolor=TAB_BG, zorder=1,
    )
    ax.add_patch(titlebar)

    tab_w = 2.9
    tab = FancyBboxPatch(
        (0.35, bar_y + 0.08), tab_w, bar_h - 0.16,
        boxstyle="round,pad=0.0,rounding_size=0.08",
        linewidth=0, facecolor="#2d2d2d", zorder=2,
    )
    ax.add_patch(tab)
    ax.text(0.55, bar_y + bar_h / 2, ">_", color="#c5c5c5", fontsize=10,
            ha="left", va="center", zorder=3, weight="bold", parse_math=False)
    ax.text(0.85, bar_y + bar_h / 2, "コマンド プロンプト", color="#e8e8e8", fontsize=9.5,
            ha="left", va="center", zorder=3, parse_math=False)
    ax.text(fig_w / 2, bar_y + bar_h / 2, title, color="#a8a8a8", fontsize=11,
            ha="center", va="center", zorder=2, parse_math=False)
    ctrl_y = bar_y + bar_h / 2
    ax.text(fig_w - 1.05, ctrl_y, "–", color="#c5c5c5", fontsize=13,
            ha="center", va="center", zorder=3, parse_math=False)
    ax.text(fig_w - 0.65, ctrl_y, "□", color="#c5c5c5", fontsize=10,
            ha="center", va="center", zorder=3, parse_math=False)
    ax.text(fig_w - 0.25, ctrl_y, "x", color="#c5c5c5", fontsize=11,
            ha="center", va="center", zorder=3, parse_math=False)

    y = fig_h - bar_h - 0.4
    x0 = 0.5
    COLORS = {"cmd": "#f2f2f2", "comment": "#7f9a7f", "out": "#cccccc", "result": "#3ddc71"}
    for kind, text, is_prompt_line in visible_lines:
        color = COLORS.get(kind, "#cccccc")
        weight = "bold" if kind == "result" else "normal"
        line_text = (CMD_PROMPT + text) if (kind == "cmd" and is_prompt_line) else text
        ax.text(x0, y, line_text, color=color, fontsize=10.5, ha="left", va="top",
                family="Noto Sans CJK JP", zorder=2, parse_math=False, weight=weight)
        y -= line_h

    if cursor_on and visible_lines:
        cursor_kind, cursor_text, cursor_is_prompt = visible_lines[-1]
        prefix = CMD_PROMPT if (cursor_kind == "cmd" and cursor_is_prompt) else ""
        cursor_x = x0 + 0.092 * (len(prefix) + len(cursor_text))
        cursor_y_top = y + line_h + 0.02
        ax.add_patch(plt.Rectangle((cursor_x, cursor_y_top - line_h * 0.85),
                                    0.13, line_h * 0.75, facecolor="#f2f2f2", zorder=3))

    buf = io.BytesIO()
    fig.savefig(buf, dpi=110, facecolor=fig.get_facecolor(), format="png")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def render_gif(steps, out_path, width_chars=100, visible_lines=20,
                reveal_ms=90, step_pause_ms=1100, final_hold_ms=2200):
    """複数ステップ（各ステップ=1コマンド実行の実機検証記録）を1本のアニメーションGIFに
    まとめる。エビデンス画像の枚数を減らす目的（2026-08-20追加）。

    steps: [{"title": str, "lines": [(kind, text), ...], "result": str}, ...]
           kind は render() と同じ "cmd" / "out" / "comment"。
           表示される内容は実機で実際に実行した本物のコマンド・出力であること
           （タイプ演出・スクロールはあくまで見せ方の演出で、内容の捏造ではない）。
    out_path: 出力するGIFファイルパス
    visible_lines: ウィンドウに同時表示する行数。超えると古い行が上にスクロールして消える
    """
    all_lines = []
    for step in steps:
        all_lines.extend(_wrap_lines(step["lines"], width_chars))
        result_lines = textwrap.wrap(
            "結果: " + step["result"], width=width_chars - 5, subsequent_indent="      "
        )
        for rl in result_lines:
            all_lines.append(("result", rl, False))
        all_lines.append(("out", "", False))  # ステップ間の空行

    title = steps[0]["title"] if len(steps) == 1 else f"{steps[0]['title']} 〜 全{len(steps)}ステップ"

    frames, durations = [], []
    fig_w = 13.5
    line_h = 0.30

    for i in range(1, len(all_lines) + 1):
        window = all_lines[max(0, i - visible_lines):i]
        blink_on = (i % 2 == 0)
        frames.append(_draw_window(title, window, blink_on, fig_w, line_h))
        is_step_boundary = all_lines[i - 1][0] == "result"
        durations.append(step_pause_ms if is_step_boundary else reveal_ms)

    if frames:
        durations[-1] = final_hold_ms

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True,
    )
    print(f"saved {out_path} ({len(frames)} frames)")
