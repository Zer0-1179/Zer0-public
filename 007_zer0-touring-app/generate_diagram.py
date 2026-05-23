"""007_Zer0_TouringApp アーキテクチャ図生成スクリプト"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

# ── 日本語フォント設定 ──
for _fp in [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
]:
    if os.path.exists(_fp):
        font_manager.fontManager.addfont(_fp)
        matplotlib.rcParams['font.family'] = 'Noto Sans CJK JP'
        break

# ── アイコンパス ──
_BASE = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_BASE, '..', 'images', 'AWS-icon')
_SVC = 'Architecture-Service-Icons_07312025'
_GRP = 'Architecture-Group-Icons_07312025'

ICONS = {
    'cloudfront':  f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-CloudFront_64.png',
    's3':          f'{_SVC}/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.png',
    'api_gw':      f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-API-Gateway_64.png',
    'lambda':      f'{_SVC}/Arch_Compute/64/Arch_AWS-Lambda_64.png',
    'bedrock':     f'{_SVC}/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock_64.png',
    'acm':         f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Certificate-Manager_64.png',
    'cloudwatch':  f'{_SVC}/Arch_Management-Governance/64/Arch_Amazon-CloudWatch_64.png',
    'region':      f'{_GRP}/Region_32.png',
    'aws_cloud':   f'{_GRP}/AWS-Cloud_32.png',
    'user':        None,  # ローカル aws_icons/user.png
}

_USER_PNG = os.path.join(_BASE, '..', '002_Zenn_Auto_Article_Bot', 'src', 'aws_icons', 'user.png')


def _load(key):
    if key == 'user':
        return mpimg.imread(_USER_PNG) if os.path.exists(_USER_PNG) else None
    path = os.path.join(_ICON_DIR, ICONS[key])
    return mpimg.imread(path) if os.path.exists(path) else None


def _cluster_icon(key):
    path = os.path.join(_ICON_DIR, ICONS[key])
    return mpimg.imread(path) if os.path.exists(path) else None


def draw():
    # ── レイアウト ──
    # xlim=14, ylim=8  figsize=(14,8)
    # 外部サービス: OpenMeteo(1.5,6.0)  Browser(1.5,3.5)  Wikipedia(1.5,1.5)
    # Edge/Global:  ACM(4.5,5.5)  CF(4.5,3.5)
    # ap-northeast-1: S3(7.5,5.5)  APIGW(7.5,3.5)  Lambda(10.5,3.5)
    #                 Bedrock(13.5,3.5)  CW(10.5,1.5)
    HALF = 0.55

    nodes = [
        {'id': 'openmeteo', 'icon': 'user',       'label': 'Open-Meteo\n（天気API）',              'x': 1.5,  'y': 6.0},
        {'id': 'browser',   'icon': 'user',       'label': 'スマホ\n（ブラウザ）',                 'x': 1.5,  'y': 3.5},
        {'id': 'wikipedia', 'icon': 'user',       'label': 'Wikipedia\n（写真API）',               'x': 1.5,  'y': 1.5},
        {'id': 'acm',       'icon': 'acm',        'label': 'ACM\n(SSL証明書)',                     'x': 4.5,  'y': 5.5},
        {'id': 'cf',        'icon': 'cloudfront', 'label': 'CloudFront\ntouring.zer0-infra.com',   'x': 4.5,  'y': 3.5},
        {'id': 's3',        'icon': 's3',         'label': 'S3\nzer0-touring-s3',                 'x': 7.5,  'y': 5.5},
        {'id': 'apigw',     'icon': 'api_gw',     'label': 'API Gateway\n(HTTP API)',              'x': 7.5,  'y': 3.5},
        {'id': 'lambda',    'icon': 'lambda',     'label': 'Lambda\nzer0-touring-suggest',         'x': 10.5, 'y': 3.5},
        {'id': 'bedrock',   'icon': 'bedrock',    'label': 'Bedrock\nClaude Haiku',               'x': 13.5, 'y': 3.5},
        {'id': 'cw',        'icon': 'cloudwatch', 'label': 'CloudWatch\nLogs',                    'x': 10.5, 'y': 1.5},
    ]

    edges = [
        ('browser',  'openmeteo', '天気取得'),
        ('browser',  'wikipedia', ''),
        ('browser',  'cf',        ''),
        ('acm',      'cf',        'HTTPS'),
        ('cf',       's3',        '/* 静的HTML'),
        ('cf',       'apigw',     '/api/*'),
        ('apigw',    'lambda',    ''),
        ('lambda',   'bedrock',   ''),
        ('lambda',   'cw',        ''),
    ]

    clusters = [
        {
            'label': '外部サービス', 'icon': None,
            'x': 0.4, 'y': 0.5, 'w': 2.3, 'h': 6.2,
            'color': '#F5F5F5', 'edgecolor': '#AAAAAA',
            'linestyle': '--', 'linewidth': 1.5,
        },
        {
            'label': 'Edge / Global', 'icon': 'aws_cloud',
            'x': 3.3, 'y': 2.3, 'w': 2.6, 'h': 4.1,
            'color': '#EAF4FB', 'edgecolor': '#8AAFCC',
            'linestyle': '-', 'linewidth': 2.0,
        },
        {
            'label': 'ap-northeast-1', 'icon': 'region',
            'x': 6.2, 'y': 0.3, 'w': 8.1, 'h': 6.5,
            'color': '#F0F7EE', 'edgecolor': '#6BAE75',
            'linestyle': '-', 'linewidth': 2.0,
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

    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title('007 Zer0 Touring App — アーキテクチャ図',
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
            img = _cluster_icon(cl['icon'])
            ix = cl['x'] + 0.15
            iy = cl['y'] + cl['h'] - ICON_SZ - 0.05
            if img is not None:
                ax.imshow(img, extent=[ix, ix + ICON_SZ, iy, iy + ICON_SZ],
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

    out = os.path.join(_BASE, '..', 'images', '007_architecture.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white', format='png')
    plt.close(fig)
    print(f'saved → {out}')


if __name__ == '__main__':
    draw()
