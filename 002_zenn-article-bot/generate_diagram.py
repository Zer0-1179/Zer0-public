"""002_Zenn_Auto_Article_Bot アーキテクチャ図生成スクリプト"""
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
    's3':          f'{_SVC}/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.png',
    'ses':         f'{_SVC}/Arch_Business-Applications/64/Arch_Amazon-Simple-Email-Service_64.png',
    'region':      f'{_GRP}/Region_32.png',
}

_USER_PNG = os.path.join(_BASE, 'src', 'aws_icons', 'user.png')


def _load(key):
    if key == 'user':
        return mpimg.imread(_USER_PNG) if os.path.exists(_USER_PNG) else None
    path = os.path.join(_ICON_DIR, ICONS[key])
    return mpimg.imread(path) if os.path.exists(path) else None


def draw():
    # ── レイアウト ──
    # xlim=13, ylim=8  figsize=(13,8)
    # ap-northeast-1:
    #   EventBridge(2,4)  Lambda(5.5,4)  Bedrock(9.5,4)
    #   SSM(5.5,6)        S3(9.5,6)
    #   CW(5.5,2)         SES(9.5,2)
    # 外部:
    #   受信者(12,2)

    HALF = 0.55

    nodes = [
        {'id': 'eb',      'icon': 'eventbridge', 'label': 'EventBridge\n(毎月1日・15日)', 'x': 2.0,  'y': 4.0},
        {'id': 'lambda',  'icon': 'lambda',      'label': 'Lambda\nzenn-article-bot',     'x': 5.5,  'y': 4.0},
        {'id': 'bedrock', 'icon': 'bedrock',     'label': 'Bedrock\nClaude Haiku',        'x': 9.5,  'y': 4.0},
        {'id': 'ssm',     'icon': 'ssm',         'label': 'SSM\nトピック管理',            'x': 5.5,  'y': 6.0},
        {'id': 's3',      'icon': 's3',          'label': 'S3\nPNG保存',                 'x': 9.5,  'y': 6.0},
        {'id': 'cw',      'icon': 'cloudwatch',  'label': 'CloudWatch\nLogs',             'x': 5.5,  'y': 2.0},
        {'id': 'ses',     'icon': 'ses',         'label': 'SES\nメール送信',              'x': 9.5,  'y': 2.0},
        {'id': 'user',    'icon': 'user',        'label': '通知先\nメール',               'x': 13.0, 'y': 2.0},
    ]

    edges = [
        ('eb',     'lambda',  ''),
        ('lambda', 'bedrock', '記事＋図生成'),
        ('lambda', 'ssm',     ''),
        ('lambda', 's3',      ''),
        ('lambda', 'cw',      ''),
        ('lambda', 'ses',     ''),
        ('ses',    'user',    ''),
    ]

    clusters = [
        {
            'label': 'ap-northeast-1', 'icon': 'region',
            'x': 0.4, 'y': 0.2, 'w': 10.5, 'h': 7.2,
            'color': '#F0F7EE', 'edgecolor': '#6BAE75',
            'linestyle': '-', 'linewidth': 2.0,
        },
        {
            'label': '通知先', 'icon': None,
            'x': 11.8, 'y': 0.8, 'w': 2.4, 'h': 2.8,
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

    # ── クラスター間重複解消 ──
    _MIN_GAP = 0.7
    for _ in range(20):
        moved = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                ca, cb = clusters[i], clusters[j]
                if ca['y'] < cb['y'] + cb['h'] and cb['y'] < ca['y'] + ca['h']:
                    if ca['x'] + ca['w'] + _MIN_GAP > cb['x'] and ca['x'] < cb['x']:
                        push = ca['x'] + ca['w'] + _MIN_GAP - cb['x']
                        cb['x'] += push; moved = True
                    elif cb['x'] + cb['w'] + _MIN_GAP > ca['x'] and cb['x'] < ca['x']:
                        push = cb['x'] + cb['w'] + _MIN_GAP - ca['x']
                        ca['x'] += push; moved = True
                if ca['x'] < cb['x'] + cb['w'] and cb['x'] < ca['x'] + ca['w']:
                    if ca['y'] + ca['h'] + _MIN_GAP > cb['y'] and ca['y'] < cb['y']:
                        push = ca['y'] + ca['h'] + _MIN_GAP - cb['y']
                        cb['y'] += push; moved = True
                    elif cb['y'] + cb['h'] + _MIN_GAP > ca['y'] and cb['y'] < ca['y']:
                        push = cb['y'] + cb['h'] + _MIN_GAP - ca['y']
                        ca['y'] += push; moved = True
        if not moved:
            break

    fig, ax = plt.subplots(figsize=(15, 8), dpi=150)
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title('002 Zenn Auto Article Bot — アーキテクチャ図',
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

    out = os.path.join(_BASE, 'images', '002_architecture.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white', format='png')
    plt.close(fig)
    print(f'saved → {out}')


if __name__ == '__main__':
    draw()
