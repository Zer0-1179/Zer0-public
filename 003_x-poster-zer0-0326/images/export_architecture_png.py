#!/usr/bin/env python3
"""
構成図(通信アニメーション付きSVG: {NUM}_architecture_plugin_flowdot.svg)から、
ポートフォリオサイトの一覧・詳細ページで実際に表示されるPNGサムネイルを作る（プロジェクト専用・自己完結版）。

ポートフォリオのプロジェクトページはデフォルトで{NUM}_architecture.png（軽量な静止画）を表示し、
{NUM}_architecture.svg（アニメーション付き）はズーム時にしか使わない
（src/src/components/ImageLightbox.astro参照）。
そのため build_architecture_flowdot.py でSVGを更新しただけでは
ページの見た目は変わらず、このスクリプトでPNGも作り直す必要がある。

使い方（build_architecture_flowdot.pyの実行後に）:
    python3 export_architecture_png.py

このファイルと同じフォルダ内で実行すると {NUM}_architecture.png が(再)生成される。

【新しいプロジェクトへコピーする場合】
1. このファイルを {新番号}_プロジェクト名/images/ へコピー
2. 下のNUMを新しい番号に変更するだけでよい
"""
import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

BASE = Path(__file__).resolve().parent

NUM = "003"
WIDTH = 2600  # CLAUDE.md「構成図PNG」規約: 幅上限2600px


def build():
    src = BASE / f"{NUM}_architecture_plugin_flowdot.svg"
    dst = BASE / f"{NUM}_architecture.png"
    if not src.exists():
        print(f"[{NUM}] スキップ: {src} が見つかりません(先にbuild_architecture_flowdot.pyを実行してください)")
        return False

    png_bytes = cairosvg.svg2png(url=str(src), output_width=WIDTH, background_color="#FFFFFF")
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    im_p = im.convert("P", palette=Image.ADAPTIVE, colors=256)  # CLAUDE.md規約: LANCZOS+ADAPTIVE 256色
    im_p.save(dst, optimize=True)

    print(f"[{NUM}] {im.size[0]}x{im.size[1]} -> {dst} ({dst.stat().st_size // 1024}KB)")
    return True


def main():
    ok = build()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
