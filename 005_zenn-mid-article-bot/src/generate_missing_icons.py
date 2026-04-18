"""
不足しているAWSアイコンを生成するスクリプト。
既存アイコンと同じ 80x80 PNG 形式で出力する。
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_SCRIPT_DIR, 'aws_icons')


# (bg_color, text_color, short_label, shape)
# shape: 'square' | 'circle'
ICON_DEFS = {
    # Security & Identity
    'acm':               ('#DD344C', '#FFFFFF', 'ACM',    'square'),
    'guardduty':         ('#DD344C', '#FFFFFF', 'GD',     'square'),
    'security_hub':      ('#DD344C', '#FFFFFF', 'SHub',   'square'),
    'shield':            ('#DD344C', '#FFFFFF', 'Shield', 'square'),
    'secrets_manager':   ('#DD344C', '#FFFFFF', 'SM',     'square'),
    # Developer Tools
    'codepipeline':      ('#C7131F', '#FFFFFF', 'CP',     'square'),
    'codebuild':         ('#C7131F', '#FFFFFF', 'CB',     'square'),
    'codecommit':        ('#C7131F', '#FFFFFF', 'CC',     'square'),
    'codedeploy':        ('#C7131F', '#FFFFFF', 'CD',     'square'),
    # Analytics
    'glue':              ('#8C4FFF', '#FFFFFF', 'Glue',   'square'),
    'opensearch':        ('#0D8EFF', '#FFFFFF', 'OS',     'square'),
    'quicksight':        ('#8C4FFF', '#FFFFFF', 'QS',     'square'),
    'lake_formation':    ('#8C4FFF', '#FFFFFF', 'LF',     'square'),
    # Management & Governance
    'cloudformation':    ('#E7157B', '#FFFFFF', 'CFn',    'square'),
    'config':            ('#E7157B', '#FFFFFF', 'Cfg',    'square'),
    'control_tower':     ('#E7157B', '#FFFFFF', 'CT',     'square'),
    'backup':            ('#E7157B', '#FFFFFF', 'Bkp',    'square'),
    'service_catalog':   ('#E7157B', '#FFFFFF', 'SC',     'square'),
    'compute_optimizer': ('#ED7100', '#FFFFFF', 'CO',     'square'),
    'xray':              ('#E7157B', '#FFFFFF', 'X-Ray',  'square'),
    # Container
    'ecr':               ('#ED7100', '#FFFFFF', 'ECR',    'square'),
    # Cost Management
    'cost_explorer':     ('#E7157B', '#FFFFFF', 'CE',     'square'),
    'budgets':           ('#E7157B', '#FFFFFF', 'Bgts',   'square'),
    # Organizations
    'organizations':     ('#E7157B', '#FFFFFF', 'Org',    'square'),
}


def _setup_font():
    import matplotlib.font_manager as fm
    bundled = os.path.join(_SCRIPT_DIR, 'fonts', 'NotoSansCJK-Regular.ttc')
    system_candidates = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    ]
    for path in [bundled] + system_candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            plt.rcParams['font.family'] = 'Noto Sans CJK JP'
            return


def generate_icon(name: str, bg_color: str, text_color: str, label: str, shape: str = 'square'):
    """80x80 PNGアイコンを生成して保存する。"""
    fig, ax = plt.subplots(figsize=(0.8, 0.8), dpi=100)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.axis('off')

    PAD = 0.06
    if shape == 'circle':
        circle = plt.Circle((0.5, 0.5), 0.5 - PAD, color=bg_color, zorder=1)
        ax.add_patch(circle)
    else:
        rect = FancyBboxPatch(
            (PAD, PAD), 1 - 2 * PAD, 1 - 2 * PAD,
            boxstyle='round,pad=0.05',
            facecolor=bg_color,
            edgecolor='none',
            zorder=1,
        )
        ax.add_patch(rect)

    # ラベルが長い場合はフォントサイズを小さく
    fontsize = 18 if len(label) <= 3 else (14 if len(label) <= 5 else 11)
    ax.text(0.5, 0.5, label, ha='center', va='center',
            fontsize=fontsize, color=text_color, fontweight='bold',
            zorder=2, transform=ax.transData)

    out_path = os.path.join(_ICON_DIR, f'{name}.png')
    plt.savefig(out_path, dpi=100, bbox_inches='tight',
                facecolor='none', format='png', pad_inches=0)
    plt.close(fig)
    return out_path


def main():
    _setup_font()
    os.makedirs(_ICON_DIR, exist_ok=True)

    existing = {f[:-4] for f in os.listdir(_ICON_DIR) if f.endswith('.png')}
    missing = {k: v for k, v in ICON_DEFS.items() if k not in existing}

    if not missing:
        print("全てのアイコンが既に存在します。")
        return

    print(f"生成するアイコン数: {len(missing)}")
    for name, (bg, fg, label, shape) in missing.items():
        path = generate_icon(name, bg, fg, label, shape)
        print(f"  ✓ {name:25s} -> {path}")

    print(f"\n完了: {len(missing)} 個のアイコンを生成しました。")
    print(f"アイコンディレクトリ: {_ICON_DIR}")

    # 検証: 全ての必要アイコンが存在するか確認
    print("\n--- 不足チェック ---")
    all_icons = {f[:-4] for f in os.listdir(_ICON_DIR) if f.endswith('.png')}
    still_missing = set(ICON_DEFS.keys()) - all_icons
    if still_missing:
        print(f"まだ不足: {sorted(still_missing)}")
    else:
        print("全アイコン揃っています。")


if __name__ == '__main__':
    main()
