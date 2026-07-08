"""008_Nyusatsu_Notify_Bot アーキテクチャ図生成スクリプト"""
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
    'ssm':         f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Systems-Manager_64.png',
    'cloudwatch':  f'{_SVC}/Arch_Management-Governance/64/Arch_Amazon-CloudWatch_64.png',
    'sqs':         f'{_SVC}/Arch_App-Integration/64/Arch_Amazon-Simple-Queue-Service_64.png',
    'ses':         f'{_SVC}/Arch_Business-Applications/64/Arch_Amazon-Simple-Email-Service_64.png',
    's3':          f'{_SVC}/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.png',
    'cloudfront':  f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-CloudFront_64.png',
    'api_gateway': f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-API-Gateway_64.png',
    'dynamodb':    f'{_SVC}/Arch_Database/64/Arch_Amazon-DynamoDB_64.png',
    'region':      f'{_GRP}/Region_32.png',
}

_USER_PNG = os.path.join(_BASE, '..', '002_Zenn_Auto_Article_Bot', 'src', 'aws_icons', 'user.png')


def _load(key):
    if key == 'user':
        return mpimg.imread(_USER_PNG) if os.path.exists(_USER_PNG) else None
    path = os.path.join(_ICON_DIR, ICONS[key])
    return mpimg.imread(path) if os.path.exists(path) else None


def draw():
    HALF = 0.55

    # 3本の独立した横方向レーン(収集Bot/LP事前登録/問合せ転送)を縦に並べ、
    # 各レーンのLambdaから共有のSES送信ノード(ses_out)へは、他レーンのノード
    # が存在しない右側の専用縦帯(x=19.5付近)を通って合流させる。
    nodes = [
        # --- レーン1: 収集Bot(既存)  y=12.0 ---
        {'id': 'eb',      'icon': 'eventbridge', 'label': 'EventBridge\n毎日 6:00 JST',          'x': 2.0,  'y': 12.0},
        {'id': 'lambda',  'icon': 'lambda',      'label': 'Lambda\ncollector',                   'x': 6.0,  'y': 12.0},
        {'id': 'dlq',     'icon': 'sqs',         'label': 'SQS (DLQ)',                           'x': 6.0,  'y': 9.7},
        {'id': 'ssm',     'icon': 'ssm',         'label': 'SSM\n設定値',                          'x': 9.5,  'y': 10.6},
        {'id': 'cw',      'icon': 'cloudwatch',  'label': 'CloudWatch\nLogs',                    'x': 9.5,  'y': 8.5},
        {'id': 'site',    'icon': 'user',        'label': '横浜市 入札サイト\n(公開情報)',        'x': 24.5, 'y': 12.0},

        # --- レーン2: LP事前登録(新規)  y=6.5 ---
        {'id': 'browser', 'icon': 'user',        'label': 'LP利用者\n(ブラウザ)',                 'x': 0.8,  'y': 6.5},
        {'id': 'cf',      'icon': 'cloudfront',  'label': 'CloudFront\nnyusatsu.zer0-infra.com',  'x': 5.0,  'y': 6.5},
        {'id': 's3lp',    'icon': 's3',          'label': 'S3\nLP静的サイト',                     'x': 5.0,  'y': 4.2},
        {'id': 'apigw',   'icon': 'api_gateway', 'label': 'API Gateway\n事前登録API',             'x': 9.5,  'y': 6.5},
        {'id': 'lambda_wl','icon': 'lambda',     'label': 'Lambda\nlp-waitlist',                  'x': 13.5, 'y': 6.5},
        {'id': 'ddb_wl',  'icon': 'dynamodb',    'label': 'DynamoDB\nlp-waitlist',                'x': 13.5, 'y': 3.8},

        # --- レーン3: 問合せメール転送(新規)  y=1.0 ---
        {'id': 'inquirer','icon': 'user',        'label': '問合せ送信者\n(外部)',                 'x': 0.8,  'y': 1.0},
        {'id': 'ses_in',  'icon': 'ses',         'label': 'SES 受信\nnyusatsu@zer0-infra.com',    'x': 5.0,  'y': 1.0},
        {'id': 's3mail',  'icon': 's3',          'label': 'S3\n受信メール(一時)',                 'x': 9.5,  'y': 1.0},
        {'id': 'lambda_fw','icon': 'lambda',     'label': 'Lambda\nmail-forwarder',               'x': 13.5, 'y': 1.0},

        # --- 共有: SES送信・通知先(右端の専用縦帯) ---
        {'id': 'ses_out', 'icon': 'ses',         'label': 'SES 送信\ninfo.zer0-infra.com',        'x': 20.5, 'y': 6.5},
        {'id': 'recv',    'icon': 'user',        'label': '通知先/転送先\nメール',                'x': 24.5, 'y': 6.5},
    ]

    edges = [
        ('eb',        'lambda',   ''),
        ('lambda',    'site',     'GET収集'),
        ('lambda',    'ssm',      '設定取得'),
        ('lambda',    'cw',       ''),
        ('lambda',    'dlq',      ''),
        ('lambda',    'ses_out',  ''),

        ('browser',   'cf',       'HTTPS'),
        ('cf',        's3lp',     ''),
        ('browser',   'apigw',    '事前登録\nfetch'),
        ('apigw',     'lambda_wl',''),
        ('lambda_wl', 'ddb_wl',   ''),
        ('lambda_wl', 'ses_out',  '登録通知'),

        ('inquirer',  'ses_in',   'メール送信'),
        ('ses_in',    's3mail',   ''),
        ('s3mail',    'lambda_fw',''),
        ('lambda_fw', 'ses_out',  '転送'),

        ('ses_out',   'recv',     ''),
    ]

    clusters = [
        {
            'label': 'ap-northeast-1', 'icon': 'region',
            'x': 3.6, 'y': -0.4, 'w': 18.5, 'h': 13.4,
            'color': '#F0F7EE', 'edgecolor': '#6BAE75',
            'linestyle': '-', 'linewidth': 2.0,
        },
        {
            'label': '外部（非AWS）', 'icon': None,
            'x': -0.6, 'y': -0.4, 'w': 2.6, 'h': 8.0,
            'color': '#F5F5F5', 'edgecolor': '#AAAAAA',
            'linestyle': '-', 'linewidth': 1.5,
        },
        {
            'label': '外部（非AWS）', 'icon': None,
            'x': 23.0, 'y': 4.6, 'w': 2.9, 'h': 8.6,
            'color': '#F5F5F5', 'edgecolor': '#AAAAAA',
            'linestyle': '-', 'linewidth': 1.5,
        },
    ]

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

    fig, ax = plt.subplots(figsize=(24, 13), dpi=150)
    ax.set_xlim(-1.2, 26.2)
    ax.set_ylim(-1.2, 13.6)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title('008 入札情報通知Bot（清掃業界向け・横浜市パイロット） — アーキテクチャ図',
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
                              edgecolor='none', alpha=0.9),
                    zorder=5)

    for n in nodes:
        x, y = n['x'], n['y']
        img = _load(n['icon'])
        if img is not None:
            ax.imshow(img, extent=[x - HALF, x + HALF, y - HALF, y + HALF],
                      aspect='auto', zorder=4, interpolation='bilinear')
        ax.text(x, y - HALF - 0.2, n['label'],
                ha='center', va='top', fontsize=7.5,
                color='#232F3E', fontweight='bold', zorder=4.5)

    out = os.path.join(_BASE, 'images', '008_architecture.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white', format='png')
    plt.close(fig)
    print(f'saved → {out}')


if __name__ == '__main__':
    draw()
