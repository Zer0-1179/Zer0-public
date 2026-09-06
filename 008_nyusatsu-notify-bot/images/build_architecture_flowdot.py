#!/usr/bin/env python3
"""
構成図(draw.io「プラグイン様式」)から、通信の流れが見える版のSVGを作る（008プロジェクト専用・自己完結版）。

draw.ioで 008_architecture_plugin.drawio を編集 → SVGエクスポート
(同じフォルダに 008_architecture_plugin.drawio.svg として上書き保存)した後、
このファイルと同じフォルダ内で実行すると 008_architecture_plugin_flowdot.svg が
(再)生成される。アイコン位置やラベルを直しただけならこのファイルの編集は不要で、
再実行するだけで反映される。

使い方:
    python3 build_architecture_flowdot.py

このスクリプトは他プロジェクトへそのままコピーして使える自己完結型
（プロジェクト横断の一括処理は /root/Zer0/build_architecture_flowdot.py --all を使うこと）。

【新しいプロジェクトへコピーする場合】
1. このファイルを {新番号}_プロジェクト名/images/ へコピー
2. 下のNUMを新しい番号に変更
3. HOPS（主要フロー。処理が流れる順に矢印IDを並べる。同時発生する矢印は同じ内側リストへ）
   AUX（補助経路の矢印ID一覧）を、新しい構成図の<mxCell id="e-..." edge="1" ...>に合わせて書き換える
"""
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent

NUM = "008"
HOPS = [
            ["e-eventbridge-lambda"],
            ["e-lambda-kokoku"],
            ["e-lambda-dynamodb"],
            ["e-lambda-ses"],
            ["e-ses-email"],
]
AUX = ["e-lambda-ssm", "e-lambda-sqs", "e-ses-sns", "e-sns-bouncehandler", "e-bouncehandler-dynamodb"]

DUR = "8s"
MOVE_FRAC = 0.6

MAIN_PATH_PAT = re.compile(r'<path [^>]*style="[^"]*animation:[^"]*stroke-dashoffset:\s*([0-9.]+);[^"]*"\s*/>')
AUX_PATH_PAT = re.compile(
    r'<path d="([^"]+)" fill="none" stroke="#000000"(?: stroke-width="[\d.]+")? '
    r'stroke-miterlimit="10" pointer-events="stroke"[^/]*/>'
)


def _path_length(d):
    pts = re.findall(r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', d)
    pts = [(float(x), float(y)) for x, y in pts]
    return sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))


def _find_edge_block(data, eid):
    pat = re.compile(r'(<g data-cell-id="' + re.escape(eid) + r'">)(.*?)(</g></g>)', re.DOTALL)
    return pat.search(data)


def add_main_flow_dots(data, hops):
    n = len(hops)
    slot = 100.0 / n
    edge_to_window = {}
    for i, ids in enumerate(hops):
        start = i * slot
        end = start + slot * MOVE_FRAC
        for eid in ids:
            edge_to_window[eid] = (start / 100.0, end / 100.0)

    count, missing = 0, []
    for eid, (s, e) in edge_to_window.items():
        m = _find_edge_block(data, eid)
        if not m:
            missing.append(eid)
            continue
        block = m.group(2)
        pm = MAIN_PATH_PAT.search(block)
        if not pm:
            missing.append(eid)
            continue
        d_val = re.search(r'\bd="([^"]+)"', pm.group(0)).group(1)
        start_offset = pm.group(1)
        kf_name = f"flow-{eid}"

        opacity_keytimes = f"0;{s:.4f};{s:.4f};{e:.4f};{e:.4f};1"
        motion_keytimes = f"0;{s:.4f};{e:.4f};1"

        dot = (
            f'<circle r="5" fill="#FF9900" stroke="#232F3E" stroke-width="1" pointer-events="none" opacity="0">'
            f'<animate attributeName="opacity" dur="{DUR}" repeatCount="indefinite" '
            f'keyTimes="{opacity_keytimes}" values="0;0;1;1;0;0"/>'
            f'<animateMotion dur="{DUR}" repeatCount="indefinite" calcMode="linear" '
            f'keyTimes="{motion_keytimes}" keyPoints="0;0;1;1" path="{d_val}"/>'
            f'</circle>'
        )
        new_block = block[:pm.end()] + dot + block[pm.end():]
        data = data[:m.start(2)] + new_block + data[m.end(2):]
        count += 1
    return data, count, missing


def add_aux_dots(data, aux_edges, color="#8C8C8C"):
    count, missing = 0, []
    for eid in aux_edges:
        m = _find_edge_block(data, eid)
        if not m:
            missing.append(eid)
            continue
        block = m.group(2)
        pm = AUX_PATH_PAT.search(block)
        if not pm:
            missing.append(eid)
            continue
        d_val = pm.group(1)
        dur = max(1.2, min(3.0, _path_length(d_val) / 100.0))
        dot = (
            f'<circle r="4.5" fill="{color}" stroke="#232F3E" stroke-width="1" pointer-events="none">'
            f'<animateMotion dur="{dur:.2f}s" repeatCount="indefinite" path="{d_val}"/>'
            f'</circle>'
        )
        new_block = block[:pm.end()] + dot + block[pm.end():]
        data = data[:m.start(2)] + new_block + data[m.end(2):]
        count += 1
    return data, count, missing


def add_legend_gray_dot_note(data, extra_height=20):
    pat = re.compile(r'(<div><b>—— Solid</b>: [^<]*</div>)(</div></div></div></foreignObject>)')
    m = pat.search(data)
    if not m:
        return data, False
    if "グレーの点" not in data[max(0, m.start() - 400):m.end() + 400]:
        insertion = '<div style="color:#8C8C8C;"><b>● グレーの点</b>: 補助経路にも通信は発生</div>'
        data = data[:m.end(1)] + insertion + data[m.end(1):]

    box_pat = re.compile(r'<rect x="[\d.]+" y="[\d.]+" width="([\d.]+)" height="([\d.]+)" fill="#f5f5f5" stroke="#666666"')
    sizes = {(bm.group(1), bm.group(2)) for bm in box_pat.finditer(data)}
    candidates = [k for k in sizes if k[0] == "440"]
    if len(candidates) == 1:
        w, h = candidates[0]
        if float(h) < 100:  # avoid double-growing an already-widened box on rerun
            new_h = f"{float(h) + extra_height:.2f}"
            data = data.replace(f'width="{w}" height="{h}" fill="#f5f5f5" stroke="#666666"',
                                 f'width="{w}" height="{new_h}" fill="#f5f5f5" stroke="#666666"')
    return data, True


def force_light_mode(data):
    """draw.ioのダーク/ライト自動切替(`color-scheme: light dark` + `light-dark(...)`)を
    無効化し、常にライトモードの配色で表示されるようにする。

    ポートフォリオサイト(004)の詳細ページではこのSVGを`<img>`でそのまま埋め込んでおり、
    閲覧者のOS/ブラウザがダークモードだと`light-dark()`がダーク側の色（背景が黒に近い等）
    に自動的に解決されてしまう（2026-09-06発見: PNGだった頃は常に固定色でエクスポートされて
    いたため気づかなかったが、SVGを生でも表示するようになって表面化した）。
    SVGルート要素の`color-scheme`を`light`のみに固定することで、`light-dark()`の解決先を
    常にライト側の値に強制する（CSS仕様上、light-dark()は最も近い祖先のcolor-schemeの
    algorithmic valueを見るため、これだけで子要素の`light-dark()`もすべてライト固定になる）。"""
    new_data = re.sub(r'color-scheme:\s*light\s+dark\s*;', 'color-scheme: light;', data)
    changed = new_data != data
    return new_data, changed

def build():
    src = BASE / f"{NUM}_architecture_plugin.drawio.svg"
    dst = BASE / f"{NUM}_architecture_plugin_flowdot.svg"
    if not src.exists():
        print(f"[{NUM}] スキップ: {src} が見つかりません(draw.ioでSVGエクスポートしてから実行してください)")
        return False

    data = src.read_text(encoding="utf-8")
    data, light_forced = force_light_mode(data)
    data, n_main, missing_main = add_main_flow_dots(data, HOPS)
    n_aux, missing_aux, legend_changed = 0, [], False
    if AUX:
        data, n_aux, missing_aux = add_aux_dots(data, AUX)
        data, legend_changed = add_legend_gray_dot_note(data)

    dst.write_text(data, encoding="utf-8")
    ET.parse(dst)  # 壊れたXMLで書き出していないかの確認

    total_main = sum(len(h) for h in HOPS)
    print(f"[{NUM}] main={n_main}/{total_main} aux={n_aux}/{len(AUX)} legend_note={legend_changed} light_forced={light_forced} -> {dst}")
    if missing_main:
        print(f"   ⚠ 主要フローで見つからなかった矢印ID: {missing_main}")
    if missing_aux:
        print(f"   ⚠ 補助経路で見つからなかった矢印ID: {missing_aux}")
    return not (missing_main or missing_aux)


def main():
    ok = build()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
