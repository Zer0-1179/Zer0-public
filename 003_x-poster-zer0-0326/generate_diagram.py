"""003_x-poster_zer0-0326 アーキテクチャ図生成スクリプト"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

for _fp in [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
]:
    if os.path.exists(_fp):
        font_manager.fontManager.addfont(_fp)
        matplotlib.rcParams['font.family'] = 'Noto Sans CJK JP'
        break

_BASE     = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_BASE, '..', 'images', 'AWS-icon')
_SVC = 'Architecture-Service-Icons_07312025'
_GRP = 'Architecture-Group-Icons_07312025'

ICONS = {
    'eventbridge': f'{_SVC}/Arch_App-Integration/64/Arch_Amazon-EventBridge_64.png',
    'lambda':      f'{_SVC}/Arch_Compute/64/Arch_AWS-Lambda_64.png',
    'bedrock':     f'{_SVC}/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock_64.png',
    'ssm':         f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Systems-Manager_64.png',
    'cloudwatch':  f'{_SVC}/Arch_Management-Governance/64/Arch_Amazon-CloudWatch_64.png',
    'region':      f'{_GRP}/Region_32.png',
}

_USER_PNG = os.path.join(_BASE, '..', '002_Zenn_Auto_Article_Bot', 'src', 'aws_icons', 'user.png')


def _load(key):
    if key == 'user':
        return mpimg.imread(_USER_PNG) if os.path.exists(_USER_PNG) else None
    path = os.path.join(_ICON_DIR, ICONS[key])
    return mpimg.imread(path) if os.path.exists(path) else None


def draw():
    # ── レイアウト ──
    # xlim=15, ylim=8  figsize=(15,8)
    # ap-northeast-1:
    #   EB-Evening(2.5,5.5)  Lambda(6,4)  Bedrock(10,6)
    #   EB-Trend(2.5,2.5)                 SSM(10,4)
    #                                     CW(10,2)
    # 投稿先:
    #   X API(13,2.5)
    #
    # Lambda→X API: y=4→2.5, at x=10: y=4-1.5*(4/7)=3.14
    # SSM bottom = 4-0.55=3.45 > 3.14 → 矢印はSSMの下を通過 ✓
    HALF = 0.55

    nodes = [
        {'id': 'eb_eve', 'icon': 'eventbridge', 'label': 'EventBridge\n毎日 22:00 JST',        'x': 2.5,  'y': 5.5},
        {'id': 'eb_trd', 'icon': 'eventbridge', 'label': 'EventBridge\n日曜 10:00 JST',        'x': 2.5,  'y': 2.5},
        {'id': 'lambda', 'icon': 'lambda',      'label': 'Lambda\nx-poster-zer0-0326',         'x': 6.0,  'y': 4.0},
        {'id': 'bedrock','icon': 'bedrock',     'label': 'Bedrock\nClaude Haiku',              'x': 10.0, 'y': 6.0},
        {'id': 'ssm',    'icon': 'ssm',         'label': 'SSM\nAPI認証+履歴',                  'x': 10.0, 'y': 4.0},
        {'id': 'cw',     'icon': 'cloudwatch',  'label': 'CloudWatch\nLogs',                   'x': 10.0, 'y': 2.0},
        {'id': 'xapi',   'icon': 'user',        'label': 'X API\n(@Zer0_0326)',                'x': 13.0, 'y': 2.5},
    ]

    edges = [
        ('eb_eve', 'lambda',  ''),
        ('eb_trd', 'lambda',  ''),
        ('lambda', 'bedrock', ''),
        ('lambda', 'ssm',     ''),
        ('lambda', 'cw',      ''),
        ('lambda', 'xapi',    'X投稿'),
    ]

    clusters = [
        {
            'label': 'ap-northeast-1', 'icon': 'region',
            'x': 0.4, 'y': 0.4, 'w': 10.9, 'h': 7.0,
            'color': '#F0F7EE', 'edgecolor': '#6BAE75',
            'linestyle': '-', 'linewidth': 2.0,
        },
        {
            'label': '投稿先', 'icon': None,
            'x': 11.7, 'y': 0.9, 'w': 2.6, 'h': 2.9,
            'color': '#F5F5F5', 'edgecolor': '#AAAAAA',
            'linestyle': '-', 'linewidth': 1.5,
        },
    ]

    # ── 自動パディング調整 ──
    _PAD_H   = HALF + 0.45
    _PAD_TOP = HALF + 0.55
    _PAD_BOT = HALF + 1.05
    for cl in clusters:
        for n in nodes:
            nx, ny = n['x'], n['y']
            if not (cl['x'] - 0.1 <= nx <= cl['x'] + cl['w'] + 0.1 and
                    cl['y'] - 0.1 <= ny <= cl['y'] + cl['h'] + 0.1):
                continue
            if nx - cl['x'] < _PAD_H:
                d = _PAD_H - (nx - cl['x']); cl['x'] -= d; cl['w'] += d
            if (cl['x'] + cl['w']) - nx < _PAD_H:
                cl['w'] += _PAD_H - ((cl['x'] + cl['w']) - nx)
            if (cl['y'] + cl['h']) - ny < _PAD_TOP:
                cl['h'] += _PAD_TOP - ((cl['y'] + cl['h']) - ny)
            if ny - cl['y'] < _PAD_BOT:
                d = _PAD_BOT - (ny - cl['y']); cl['y'] -= d; cl['h'] += d

    fig, ax = plt.subplots(figsize=(15, 8), dpi=150)
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title('003 X Poster Bot (@Zer0_0326) — アーキテクチャ図',
                 fontsize=13, fontweight='bold', pad=10, color='#232F3E')

    ICON_SZ = 0.45
    for cl in clusters:
        has_icon = bool(cl.get('icon'))
        rect = FancyBboxPatch(
            (cl['x'], cl['y']), cl['w'], cl['h'],
            boxstyle='round,pad=0.15',
            facecolor=cl.get('color', '#EAF4FB'),
            edgecolor=cl.get('edgecolor', '#8AAFCC'),
            linewidth=cl.get('linewidth', 2.0),
            linestyle=cl.get('linestyle', '-'),
            zorder=1,
        )
        ax.add_patch(rect)
        if has_icon:
            img_c = _load(cl['icon'])
            ix = cl['x'] + 0.15
            iy = cl['y'] + cl['h'] - ICON_SZ - 0.05
            if img_c is not None:
                ax.imshow(img_c, extent=[ix, ix + ICON_SZ, iy, iy + ICON_SZ],
                          aspect='auto', zorder=6, interpolation='bilinear')
            tx = ix + ICON_SZ + 0.12
            ty = cl['y'] + cl['h'] - ICON_SZ / 2 - 0.05
        else:
            tx = cl['x'] + 0.2
            ty = cl['y'] + cl['h']
        ax.text(tx, ty, cl['label'],
                ha='left', va='center' if has_icon else 'bottom',
                fontsize=7.5, color='#4A7FA5', style='italic', zorder=6)

    node_map = {n['id']: n for n in nodes}
    SHRINK = 42
    for edge in edges:
        from_id, to_id = edge[0], edge[1]
        label = edge[2] if len(edge) > 2 else ''
        n1, n2 = node_map[from_id], node_map[to_id]
        ax.annotate(
            '', xy=(n2['x'], n2['y']), xytext=(n1['x'], n1['y']),
            arrowprops=dict(
                arrowstyle='->', color='#555555', lw=1.5,
                shrinkA=SHRINK, shrinkB=SHRINK,
                connectionstyle='arc3,rad=0.0',
            ),
            zorder=3,
        )
        if label:
            mx = (n1['x'] + n2['x']) / 2
            my = (n1['y'] + n2['y']) / 2
            ax.text(mx, my + 0.18, label, ha='center', va='bottom',
                    fontsize=7, color='#666666',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                              edgecolor='none', alpha=0.85),
                    zorder=4)

    for n in nodes:
        x, y = n['x'], n['y']
        img = _load(n['icon'])
        if img is not None:
            ax.imshow(img, extent=[x - HALF, x + HALF, y - HALF, y + HALF],
                      aspect='auto', zorder=4, interpolation='bilinear')
        ax.text(x, y - HALF - 0.2, n['label'],
                ha='center', va='top', fontsize=7.5,
                color='#232F3E', fontweight='bold', zorder=5)

    out = os.path.join(_BASE, 'images', '003_architecture.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white', format='png')
    plt.close(fig)
    print(f'saved → {out}')


if __name__ == '__main__':
    draw()
