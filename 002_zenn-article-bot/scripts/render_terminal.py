"""Zenn記事evidence画像用のターミナル風レンダラー（Windows コマンドプロンプト風）。

実際のコマンド・出力（AWS CLI等で実機検証した本物のテキスト）を、Windows Terminal上で
コマンドプロンプト(cmd.exe)を開いたときの見た目に似せてPNG化する。あくまで見た目の演出であり、
実際のWindowsのスクリーンショットではない（GUIのないLinux環境のため撮影不可）。

呼び出し側(gen_evidence.py等)のインターフェースは旧macOS風スクリプトと同一
（render(title, lines, result, out_path, width_chars=100)）なので、
既存の呼び出しコードを変更せずに差し替え可能。
"""
import re
import textwrap
import matplotlib
from matplotlib import font_manager

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(FONT_PATH)
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# AWSアカウントIDは12桁の連続数字。特定のIDをソースにハードコードすると
# 公開リポジトリの機密情報スキャンに引っかかるため、パターンマッチで汎用的にマスクする
ACCOUNT_ID_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
MASK = "${AWS::AccountId}"

# コマンドプロンプトのプロンプトに使う汎用ユーザー名（個人情報を含まない汎用表記）
CMD_USER = "user"
CMD_PROMPT = f"C:\\Users\\{CMD_USER}>"


def mask(s: str) -> str:
    return ACCOUNT_ID_RE.sub(MASK, s)


def render(title, lines, result, out_path, width_chars=100):
    """
    lines: list of (kind, text) where kind in {"cmd", "out", "comment"}
    result: final green summary line (string, no prefix)
    """
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
