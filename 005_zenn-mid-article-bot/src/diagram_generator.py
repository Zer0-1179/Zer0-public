"""
中級者向けAWSアーキテクチャ図を生成するモジュール。
複合サービス構成に対応したフルシステム構成図（図1）と
データフロー図（図2）の2種類を各トピックで生成する。
matplotlib + AWS公式アイコン（PNGバンドル）使用。Graphviz依存なし。
"""
import matplotlib
matplotlib.use('Agg')

import os
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_SCRIPT_DIR, 'aws_icons')


def _setup_font():
    import matplotlib.font_manager as fm
    bundled = os.path.join(_SCRIPT_DIR, 'fonts', 'NotoSansCJK-Regular.ttc')
    system_candidates = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    ]
    for path in [bundled] + system_candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            plt.rcParams['font.family'] = 'Noto Sans CJK JP'
            return
    for name in ['Noto Sans CJK JP', 'Noto Sans JP', 'IPAGothic']:
        if any(f.name == name for f in fm.fontManager.ttflist):
            plt.rcParams['font.family'] = name
            return


_setup_font()


# ─── アイコン自動生成 ──────────────────────────────────────────────────────────

# サービスカテゴリ別カラー: (bg_color, text_color, short_label)
_ICON_FALLBACK: dict[str, tuple[str, str, str]] = {
    # Compute
    'ec2':               ('#ED7100', '#FFFFFF', 'EC2'),
    'ecs':               ('#ED7100', '#FFFFFF', 'ECS'),
    'ecr':               ('#ED7100', '#FFFFFF', 'ECR'),
    'fargate':           ('#ED7100', '#FFFFFF', 'FG'),
    'lambda':            ('#ED7100', '#FFFFFF', 'λ'),
    'compute_optimizer': ('#ED7100', '#FFFFFF', 'CO'),
    'autoscaling':       ('#ED7100', '#FFFFFF', 'ASG'),
    # Storage
    's3':                ('#7AA116', '#FFFFFF', 'S3'),
    'backup':            ('#7AA116', '#FFFFFF', 'Bkp'),
    # Database
    'rds':               ('#C7131F', '#FFFFFF', 'RDS'),
    'dynamodb':          ('#C7131F', '#FFFFFF', 'DDB'),
    'dynamodb_streams':  ('#C7131F', '#FFFFFF', 'DDS'),
    'dax':               ('#C7131F', '#FFFFFF', 'DAX'),
    'elasticache':       ('#C7131F', '#FFFFFF', 'EC$'),
    'opensearch':        ('#0D8EFF', '#FFFFFF', 'OS'),
    # Networking
    'vpc':               ('#8C4FFF', '#FFFFFF', 'VPC'),
    'alb':               ('#8C4FFF', '#FFFFFF', 'ALB'),
    'cloudfront':        ('#8C4FFF', '#FFFFFF', 'CF'),
    'route53':           ('#8C4FFF', '#FFFFFF', 'R53'),
    'api_gateway':       ('#8C4FFF', '#FFFFFF', 'APIG'),
    'igw':               ('#8C4FFF', '#FFFFFF', 'IGW'),
    'nat':               ('#8C4FFF', '#FFFFFF', 'NAT'),
    'waf':               ('#8C4FFF', '#FFFFFF', 'WAF'),
    # Security & Identity
    'iam':               ('#DD344C', '#FFFFFF', 'IAM'),
    'iam_role':          ('#DD344C', '#FFFFFF', 'Role'),
    'acm':               ('#DD344C', '#FFFFFF', 'ACM'),
    'cognito':           ('#DD344C', '#FFFFFF', 'Cog'),
    'guardduty':         ('#DD344C', '#FFFFFF', 'GD'),
    'security_hub':      ('#DD344C', '#FFFFFF', 'SHub'),
    'shield':            ('#DD344C', '#FFFFFF', 'Shld'),
    'secrets_manager':   ('#DD344C', '#FFFFFF', 'SM'),
    'control_tower':     ('#DD344C', '#FFFFFF', 'CT'),
    'organizations':     ('#DD344C', '#FFFFFF', 'Org'),
    # Developer Tools
    'codepipeline':      ('#C7131F', '#FFFFFF', 'CP'),
    'codebuild':         ('#C7131F', '#FFFFFF', 'CB'),
    'codecommit':        ('#C7131F', '#FFFFFF', 'CC'),
    'codedeploy':        ('#C7131F', '#FFFFFF', 'CD'),
    # Analytics & Data
    'kinesis':           ('#8C4FFF', '#FFFFFF', 'KDS'),
    'athena':            ('#8C4FFF', '#FFFFFF', 'Ath'),
    'glue':              ('#8C4FFF', '#FFFFFF', 'Glue'),
    'quicksight':        ('#8C4FFF', '#FFFFFF', 'QS'),
    'lake_formation':    ('#8C4FFF', '#FFFFFF', 'LF'),
    # Management & Governance
    'cloudwatch':        ('#E7157B', '#FFFFFF', 'CW'),
    'cloudwatch_alarm':  ('#E7157B', '#FFFFFF', 'CWA'),
    'cloudtrail':        ('#E7157B', '#FFFFFF', 'CTr'),
    'cloudformation':    ('#E7157B', '#FFFFFF', 'CFn'),
    'config':            ('#E7157B', '#FFFFFF', 'Cfg'),
    'service_catalog':   ('#E7157B', '#FFFFFF', 'SC'),
    'xray':              ('#E7157B', '#FFFFFF', 'X-Ray'),
    'eventbridge':       ('#E7157B', '#FFFFFF', 'EB'),
    # Messaging
    'sns':               ('#E7157B', '#FFFFFF', 'SNS'),
    'sqs':               ('#E7157B', '#FFFFFF', 'SQS'),
    'ses':               ('#E7157B', '#FFFFFF', 'SES'),
    # Workflow
    'step_functions':    ('#E7157B', '#FFFFFF', 'SF'),
    # Cost
    'cost_explorer':     ('#E7157B', '#FFFFFF', 'CE'),
    'budgets':           ('#E7157B', '#FFFFFF', 'Bgts'),
    # ML / AI
    'sagemaker':         ('#01A88D', '#FFFFFF', 'SM'),
    'bedrock':           ('#01A88D', '#FFFFFF', 'BR'),
    'rekognition':       ('#01A88D', '#FFFFFF', 'Rek'),
    'comprehend':        ('#01A88D', '#FFFFFF', 'Comp'),
    'textract':          ('#01A88D', '#FFFFFF', 'Txt'),
    # Other
    'user':              ('#555555', '#FFFFFF', '人'),
}


def _ensure_icon(name: str) -> None:
    """アイコンPNGが存在しない場合、フォールバック定義から自動生成する。"""
    path = os.path.join(_ICON_DIR, f'{name}.png')
    if os.path.exists(path):
        return
    os.makedirs(_ICON_DIR, exist_ok=True)
    bg, fg, label = _ICON_FALLBACK.get(name, ('#999999', '#FFFFFF', name[:4].upper()))
    import matplotlib.pyplot as _plt
    from matplotlib.patches import FancyBboxPatch as _FBP
    fig, ax = _plt.subplots(figsize=(0.8, 0.8), dpi=100)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.add_patch(_FBP((0.06, 0.06), 0.88, 0.88, boxstyle='round,pad=0.05',
                      facecolor=bg, edgecolor='none', zorder=1))
    fs = 18 if len(label) <= 3 else (14 if len(label) <= 5 else 11)
    ax.text(0.5, 0.5, label, ha='center', va='center', fontsize=fs,
            color=fg, fontweight='bold', zorder=2)
    _plt.savefig(path, dpi=100, bbox_inches='tight',
                 facecolor='none', format='png', pad_inches=0)
    _plt.close(fig)
    print(f'[diagram_generator] アイコン自動生成: {name}.png')


# ─── 描画ヘルパー ──────────────────────────────────────────────────────────────

def _load_icon(name: str):
    if not name:
        return None
    _ensure_icon(name)
    path = os.path.join(_ICON_DIR, f'{name}.png')
    if os.path.exists(path):
        try:
            return mpimg.imread(path)
        except Exception:
            return None
    return None


def _draw_diagram(
    title: str,
    nodes: list,
    edges: list,
    output_path: str,
    figsize: tuple = (14, 7),
    xlim: tuple = (0, 14),
    ylim: tuple = None,
    clusters: list = None,
):
    """
    nodes   : [{'id': str, 'icon': str|None, 'label': str, 'x': float, 'y': float}]
    edges   : [(from_id, to_id) | (from_id, to_id, label)]
    clusters: [{'label': str, 'x': float, 'y': float, 'w': float, 'h': float, 'color': str}]
    ylim    : None で自動計算（ノード・クラスターの範囲から余白付きで決定）
    """
    # ylim 自動計算
    if ylim is None:
        ys = [n['y'] for n in nodes]
        y_lo = min(ys)
        y_hi = max(ys)
        for c in (clusters or []):
            y_lo = min(y_lo, c['y'])
            y_hi = max(y_hi, c['y'] + c['h'])
        y_lo = max(0.0, y_lo - 1.3)   # アイコン下端 + ラベル分
        y_hi = y_hi + 0.8              # アイコン上端 + クラスターラベル分
        if y_hi - y_lo < 4.0:          # 最低幅を確保
            mid = (y_lo + y_hi) / 2
            y_lo, y_hi = mid - 2.0, mid + 2.0
        ylim = (y_lo, y_hi)

    # ── クラスター枠がノードと重ならないよう自動パディング調整 ──────────────
    # ルール: アイコン端(HALF=0.55)から枠まで水平0.45・上0.55・下1.05以上確保
    _ICON_HALF   = 0.55
    _PAD_H       = _ICON_HALF + 0.45   # 水平マージン（アイコン端＋余白）
    _PAD_TOP     = _ICON_HALF + 0.55   # 上マージン（クラスターラベル分含む）
    _PAD_BOT     = _ICON_HALF + 1.05   # 下マージン（ノードラベルが下に伸びる分含む）

    node_cx = {n['id']: (n['x'], n['y']) for n in nodes}
    for cl in (clusters or []):
        for node in nodes:
            nx, ny = node['x'], node['y']
            # ノードがこのクラスターの範囲内かチェック（元の座標で判定）
            if not (cl['x'] - 0.1 <= nx <= cl['x'] + cl['w'] + 0.1 and
                    cl['y'] - 0.1 <= ny <= cl['y'] + cl['h'] + 0.1):
                continue
            # 左端
            if nx - cl['x'] < _PAD_H:
                diff = _PAD_H - (nx - cl['x'])
                cl['x'] -= diff
                cl['w'] += diff
            # 右端
            if (cl['x'] + cl['w']) - nx < _PAD_H:
                cl['w'] += _PAD_H - ((cl['x'] + cl['w']) - nx)
            # 上端
            if (cl['y'] + cl['h']) - ny < _PAD_TOP:
                cl['h'] += _PAD_TOP - ((cl['y'] + cl['h']) - ny)
            # 下端（ノードラベルが下に伸びる）
            if ny - cl['y'] < _PAD_BOT:
                diff = _PAD_BOT - (ny - cl['y'])
                cl['y'] -= diff
                cl['h'] += diff

    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=10, color='#232F3E')

    ICON_SZ = 0.45  # クラスターアイコンの一辺サイズ
    for cluster in (clusters or []):
        has_icon = bool(cluster.get('icon'))
        rect = FancyBboxPatch(
            (cluster['x'], cluster['y']),
            cluster['w'], cluster['h'],
            boxstyle='round,pad=0.15',
            facecolor=cluster.get('color', '#EAF4FB'),
            edgecolor=cluster.get('edgecolor', '#8AAFCC'),
            linewidth=cluster.get('linewidth', 2.0 if has_icon else 1.5),
            linestyle=cluster.get('linestyle', '-' if has_icon else '--'),
            zorder=1,
        )
        ax.add_patch(rect)
        icon_img = _load_icon(cluster['icon']) if has_icon else None
        ix = cluster['x'] + 0.15
        iy = cluster['y'] + cluster['h'] - ICON_SZ - 0.05
        if icon_img is not None:
            ax.imshow(
                icon_img,
                extent=[ix, ix + ICON_SZ, iy, iy + ICON_SZ],
                aspect='auto', zorder=6, interpolation='bilinear',
            )
            tx = ix + ICON_SZ + 0.12
        else:
            tx = cluster['x'] + 0.2
        ty = cluster['y'] + cluster['h'] - (ICON_SZ / 2) - 0.05 if has_icon else cluster['y'] + cluster['h']
        ax.text(
            tx, ty,
            cluster['label'],
            ha='left', va='center' if has_icon else 'bottom',
            fontsize=7.5, color='#4A7FA5', style='italic',
            zorder=6,
        )

    node_map = {n['id']: n for n in nodes}

    SHRINK = 42
    for edge in edges:
        from_id, to_id = edge[0], edge[1]
        edge_label = edge[2] if len(edge) > 2 else ''
        n1, n2 = node_map[from_id], node_map[to_id]
        rad = edge[3] if len(edge) > 3 else 0.0
        ax.annotate(
            '',
            xy=(n2['x'], n2['y']),
            xytext=(n1['x'], n1['y']),
            arrowprops=dict(
                arrowstyle='->', color='#555555', lw=1.5,
                shrinkA=SHRINK, shrinkB=SHRINK,
                connectionstyle=f'arc3,rad={rad}',
            ),
            zorder=3,
        )
        if edge_label:
            mx = (n1['x'] + n2['x']) / 2
            my = (n1['y'] + n2['y']) / 2
            if rad != 0.0:
                # 弧の視覚的中点 = 弦の中点 + 0.5 * rad * 垂直方向ベクトル
                dx = n2['x'] - n1['x']
                dy = n2['y'] - n1['y']
                mx += 0.5 * rad * (-dy)
                my += 0.5 * rad * dx
            offset_y = 0.18 if rad >= 0 else -0.25
            ax.text(mx, my + offset_y, edge_label, ha='center', va='bottom',
                    fontsize=7, color='#555555', zorder=5,
                    bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=1.5))

    HALF = 0.55
    for node in nodes:
        x, y = node['x'], node['y']
        img = _load_icon(node.get('icon'))
        if img is not None:
            ax.imshow(
                img,
                extent=[x - HALF, x + HALF, y - HALF, y + HALF],
                aspect='auto', zorder=4, interpolation='bilinear',
            )
        else:
            rect = FancyBboxPatch(
                (x - HALF, y - HALF), HALF * 2, HALF * 2,
                boxstyle='round,pad=0.1',
                facecolor=node.get('color', '#E8E8E8'),
                edgecolor='#AAAAAA', zorder=4,
            )
            ax.add_patch(rect)
            ax.text(x, y, node.get('short', '?'), ha='center', va='center',
                    fontsize=8, color='#232F3E', fontweight='bold', zorder=5)

        ax.text(x, y - HALF - 0.2, node['label'],
                ha='center', va='top', fontsize=8,
                color='#232F3E', fontweight='bold', zorder=5,
                bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=1.0))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', format='png')
    plt.close(fig)


# ─── serverless_ec ─────────────────────────────────────────────────────────────

def _diagram_serverless_ec_1(output_path: str):
    """図1: フルシステム構成図 API GW → Lambda → DynamoDB/SQS/SNS"""
    clusters = [
        {'label': 'フロントエンド', 'x': 0.2, 'y': 2.8, 'w': 2.2, 'h': 1.8, 'color': '#F0F8FF'},
        {'label': 'API層', 'x': 2.6, 'y': 2.8, 'w': 2.2, 'h': 1.8, 'color': '#FFF8E1'},
        {'label': 'ビジネスロジック', 'x': 5.0, 'y': 1.8, 'w': 2.2, 'h': 3.8, 'color': '#F0FFF0'},
        {'label': 'データ層', 'x': 7.4, 'y': 2.8, 'w': 2.2, 'h': 1.8, 'color': '#FFF0F0'},
        {'label': '非同期通知', 'x': 9.8, 'y': 2.8, 'w': 3.6, 'h': 2.0, 'color': '#F5F0FF'},
    ]
    nodes = [
        {'id': 'client', 'icon': 'user',        'label': 'クライアント', 'x': 1.3, 'y': 3.8},
        {'id': 'apigw',  'icon': 'api_gateway',  'label': 'API Gateway',  'x': 3.7, 'y': 3.8},
        {'id': 'fn',     'icon': 'lambda',       'label': 'Lambda',       'x': 6.1, 'y': 4.8},
        {'id': 'fn2',    'icon': 'lambda',       'label': 'Lambda\n(非同期)', 'x': 6.1, 'y': 2.8},
        {'id': 'ddb',    'icon': 'dynamodb',     'label': 'DynamoDB',     'x': 8.5, 'y': 3.8},
        {'id': 'sqs',    'icon': 'sqs',          'label': 'SQS',          'x': 10.6, 'y': 3.8},
        {'id': 'sns',    'icon': 'sns',          'label': 'SNS',          'x': 12.4, 'y': 3.8},
    ]
    edges = [
        ('client', 'apigw', 'HTTPS'),
        ('apigw', 'fn', '同期呼び出し'),
        ('fn', 'ddb', 'CRUD'),
        ('fn', 'fn2', 'イベント'),
        ('fn2', 'sqs', 'キュー投入'),
        ('fn2', 'sns', '通知発行'),
    ]
    _draw_diagram('サーバーレスECバックエンド ① – フルシステム構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_serverless_ec_2(output_path: str):
    """図2: データフロー（注文処理シーケンス）"""
    nodes = [
        {'id': 'client', 'icon': 'user',        'label': 'クライアント',  'x': 1.5, 'y': 3.5},
        {'id': 'apigw',  'icon': 'api_gateway',  'label': 'API Gateway',   'x': 4.0, 'y': 3.5},
        {'id': 'fn',     'icon': 'lambda',       'label': 'Order Lambda',  'x': 6.5, 'y': 3.5},
        {'id': 'ddb',    'icon': 'dynamodb',     'label': 'DynamoDB\n(Orders)', 'x': 9.0, 'y': 5.0},
        {'id': 'sqs',    'icon': 'sqs',          'label': 'SQS\n(order-queue)', 'x': 9.0, 'y': 3.5},
        {'id': 'fn2',    'icon': 'lambda',       'label': 'Notify Lambda', 'x': 11.5, 'y': 3.5},
        {'id': 'sns',    'icon': 'sns',          'label': 'SNS\n(顧客通知)',    'x': 9.0, 'y': 2.0},
    ]
    edges = [
        ('client', 'apigw', 'POST /orders'),
        ('apigw', 'fn', 'invoke'),
        ('fn', 'ddb', '1. 注文保存'),
        ('fn', 'sqs', '2. キュー投入'),
        ('sqs', 'fn2', '3. トリガー'),
        ('fn2', 'sns', '4. 通知発行'),
    ]
    _draw_diagram('サーバーレスECバックエンド ② – 注文処理データフロー',
                  nodes, edges, output_path)


# ─── static_web_hosting ────────────────────────────────────────────────────────

def _diagram_static_web_hosting_1(output_path: str):
    """図1: S3 + CloudFront + Route53 + WAF 全体構成"""
    clusters = [
        {'label': 'エッジ層 (グローバル)', 'x': 3.5, 'y': 2.0, 'w': 5.5, 'h': 4.2, 'color': '#EAF4FB'},
        {'label': 'オリジン (ap-northeast-1)', 'x': 9.2, 'y': 2.5, 'w': 3.5, 'h': 3.0, 'color': '#F0FFF0'},
    ]
    nodes = [
        {'id': 'user',  'icon': 'user',       'label': 'ユーザー',         'x': 1.5, 'y': 4.0},
        {'id': 'r53',   'icon': 'route53',    'label': 'Route 53',         'x': 4.5, 'y': 4.0},
        {'id': 'waf',   'icon': 'waf',        'label': 'WAF',              'x': 7.2, 'y': 5.3},
        {'id': 'cf',    'icon': 'cloudfront', 'label': 'CloudFront',       'x': 7.2, 'y': 3.5},
        {'id': 's3',    'icon': 's3',         'label': 'S3 (静的ファイル)', 'x': 11.0, 'y': 4.0},
        {'id': 'acm',   'icon': 'acm',        'label': 'ACM\n(SSL証明書)', 'x': 5.8, 'y': 2.7},
    ]
    edges = [
        ('user', 'r53', 'example.com'),
        ('r53', 'waf', 'ALIASレコード'),
        ('waf', 'cf', 'フィルタリング'),
        ('cf', 's3', 'OAC経由'),
        ('acm', 'cf', 'HTTPS証明書', 0.3),
    ]
    _draw_diagram('静的Webホスティング ① – CloudFront + S3 + Route53 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_static_web_hosting_2(output_path: str):
    """図2: デプロイパイプライン & キャッシュ無効化フロー"""
    nodes = [
        {'id': 'dev',   'icon': 'user',        'label': '開発者',          'x': 1.5, 'y': 3.5},
        {'id': 'pipe',  'icon': 'codepipeline','label': 'CodePipeline',    'x': 4.0, 'y': 3.5},
        {'id': 'build', 'icon': 'codebuild',   'label': 'CodeBuild\n(ビルド)', 'x': 6.5, 'y': 3.5},
        {'id': 's3',    'icon': 's3',          'label': 'S3\n(デプロイ先)',     'x': 9.0, 'y': 3.5},
        {'id': 'cf',    'icon': 'cloudfront',  'label': 'CloudFront\n(キャッシュ)', 'x': 11.5, 'y': 3.5},
        {'id': 'fn',    'icon': 'lambda',      'label': 'Lambda\n(無効化)',      'x': 9.0, 'y': 1.5},
    ]
    edges = [
        ('dev', 'pipe', 'git push'),
        ('pipe', 'build', 'ビルド開始'),
        ('build', 's3', 'アップロード'),
        ('s3', 'fn', 'S3イベント'),
        ('fn', 'cf', 'キャッシュ無効化'),
    ]
    _draw_diagram('静的Webホスティング ② – CI/CDデプロイ & キャッシュ無効化フロー',
                  nodes, edges, output_path)


# ─── container_platform ───────────────────────────────────────────────────────

def _diagram_container_platform_1(output_path: str):
    """図1: ECS Fargate + ALB + ECR 本番構成"""
    clusters = [
        {'label': 'VPC', 'x': 3.5, 'y': 0.5, 'w': 9.8, 'h': 6.0, 'color': '#F0F8FF'},
        {'label': 'パブリックサブネット', 'x': 3.8, 'y': 0.8, 'w': 2.5, 'h': 5.2, 'color': '#E8F5E9'},
        {'label': 'プライベートサブネット (ECS)', 'x': 6.5, 'y': 0.8, 'w': 6.5, 'h': 5.2, 'color': '#FFF8E1'},
    ]
    nodes = [
        {'id': 'user',  'icon': 'user',    'label': 'ユーザー',     'x': 1.5, 'y': 3.5},
        {'id': 'alb',   'icon': 'alb',     'label': 'ALB',          'x': 5.0, 'y': 3.5},
        {'id': 'ecs1',  'icon': 'ecs',     'label': 'ECS Task #1',  'x': 8.5, 'y': 4.5},
        {'id': 'ecs2',  'icon': 'ecs',     'label': 'ECS Task #2',  'x': 8.5, 'y': 2.5},
        {'id': 'rds',   'icon': 'rds',     'label': 'RDS',          'x': 11.5, 'y': 3.5},
        {'id': 'ecr',   'icon': 'ecr',     'label': 'ECR',          'x': 8.5, 'y': 6.0},
        {'id': 'sm',    'icon': 'secrets_manager', 'label': 'Secrets\nManager', 'x': 11.5, 'y': 1.5},
    ]
    edges = [
        ('user', 'alb', 'HTTPS'),
        ('alb', 'ecs1', 'ルーティング'),
        ('alb', 'ecs2', 'ルーティング'),
        ('ecs1', 'rds', 'DB接続'),
        ('ecs2', 'rds', 'DB接続'),
        ('ecr', 'ecs1', 'イメージPull', 0.2),
        ('ecs1', 'sm', 'シークレット取得', 0.2),
    ]
    _draw_diagram('コンテナ本番運用 ① – ECS Fargate + ALB + ECR 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_container_platform_2(output_path: str):
    """図2: CI/CD + CloudWatch モニタリングフロー"""
    nodes = [
        {'id': 'dev',  'icon': 'user',        'label': '開発者',       'x': 1.5, 'y': 3.5},
        {'id': 'pipe', 'icon': 'codepipeline','label': 'CodePipeline', 'x': 4.0, 'y': 3.5},
        {'id': 'ecr',  'icon': 'ecr',         'label': 'ECR',          'x': 6.5, 'y': 3.5},
        {'id': 'ecs',  'icon': 'ecs',         'label': 'ECS Service',  'x': 9.0, 'y': 3.5},
        {'id': 'cw',   'icon': 'cloudwatch',  'label': 'CloudWatch',   'x': 9.0, 'y': 1.5},
        {'id': 'sns',  'icon': 'sns',         'label': 'SNS\n(アラート)', 'x': 11.5, 'y': 1.5},
        {'id': 'alb',  'icon': 'alb',         'label': 'ALB\n(ヘルスチェック)', 'x': 11.5, 'y': 3.5},
    ]
    edges = [
        ('dev', 'pipe', 'git push'),
        ('pipe', 'ecr', 'docker push'),
        ('ecr', 'ecs', 'デプロイ'),
        ('ecs', 'cw', 'メトリクス送信'),
        ('cw', 'sns', 'アラーム発火'),
        ('alb', 'ecs', 'ヘルスチェック'),
    ]
    _draw_diagram('コンテナ本番運用 ② – CI/CD + CloudWatch モニタリングフロー',
                  nodes, edges, output_path)


# ─── event_driven_pipeline ────────────────────────────────────────────────────

def _diagram_event_driven_pipeline_1(output_path: str):
    """図1: Kinesis → Lambda → S3 → Athena パイプライン"""
    nodes = [
        {'id': 'src',   'icon': 'user',     'label': 'データソース',      'x': 1.5, 'y': 3.5},
        {'id': 'kds',   'icon': 'kinesis',  'label': 'Kinesis\nData Streams', 'x': 4.0, 'y': 3.5},
        {'id': 'fn',    'icon': 'lambda',   'label': 'Lambda\n(変換)',    'x': 6.5, 'y': 3.5},
        {'id': 'kfh',   'icon': 'kinesis',  'label': 'Kinesis\nFirehose',  'x': 4.0, 'y': 1.5},
        {'id': 's3r',   'icon': 's3',       'label': 'S3\n(Raw層)',        'x': 9.0, 'y': 3.5},
        {'id': 's3p',   'icon': 's3',       'label': 'S3\n(Parquet層)',    'x': 9.0, 'y': 1.5},
        {'id': 'glue',  'icon': 'glue',     'label': 'Glue\nCatalog',     'x': 11.5, 'y': 2.5},
        {'id': 'athena','icon': 'athena',   'label': 'Athena',             'x': 11.5, 'y': 4.5},
    ]
    edges = [
        ('src', 'kds', 'PutRecord'),
        ('kds', 'fn', 'トリガー'),
        ('fn', 's3r', '生データ保存'),
        ('kds', 'kfh', 'Firehose連携', 0.3),
        ('kfh', 's3p', 'Parquet変換'),
        ('s3p', 'glue', 'クロール'),
        ('glue', 'athena', 'スキーマ提供'),
        ('s3r', 'athena', 'SQLクエリ', 0.15),
    ]
    _draw_diagram('イベント駆動パイプライン ① – Kinesis + Lambda + S3 + Athena',
                  nodes, edges, output_path)


def _diagram_event_driven_pipeline_2(output_path: str):
    """図2: データフロー（リアルタイム分析〜バッチ集計）"""
    nodes = [
        {'id': 'app',   'icon': 'user',      'label': 'アプリ\n(ログ送信)',   'x': 1.5, 'y': 4.0},
        {'id': 'kds',   'icon': 'kinesis',   'label': 'Kinesis\nData Streams','x': 4.0, 'y': 4.0},
        {'id': 'fn',    'icon': 'lambda',    'label': 'Lambda\n(リアルタイム)','x': 6.5, 'y': 5.2},
        {'id': 'ddb',   'icon': 'dynamodb',  'label': 'DynamoDB\n(カウンタ)', 'x': 9.0, 'y': 5.2},
        {'id': 'kfh',   'icon': 'kinesis',   'label': 'Firehose\n(バッファ)', 'x': 6.5, 'y': 2.8},
        {'id': 's3',    'icon': 's3',        'label': 'S3\n(データレイク)',   'x': 9.0, 'y': 2.8},
        {'id': 'athena','icon': 'athena',    'label': 'Athena\n(バッチ分析)', 'x': 11.5, 'y': 2.8},
    ]
    edges = [
        ('app', 'kds', 'イベント送信'),
        ('kds', 'fn', 'リアルタイム処理'),
        ('fn', 'ddb', 'カウンタ更新'),
        ('kds', 'kfh', 'バッファ転送'),
        ('kfh', 's3', 'Parquet保存'),
        ('s3', 'athena', 'バッチクエリ'),
    ]
    _draw_diagram('イベント駆動パイプライン ② – リアルタイム + バッチ分析フロー',
                  nodes, edges, output_path)


# ─── microservices_base ───────────────────────────────────────────────────────

def _diagram_microservices_base_1(output_path: str):
    """図1: マイクロサービス全体構成 + X-Ray"""
    nodes = [
        {'id': 'client', 'icon': 'user',       'label': 'クライアント',  'x': 1.5, 'y': 3.5},
        {'id': 'apigw',  'icon': 'api_gateway','label': 'API Gateway',   'x': 4.0, 'y': 3.5},
        {'id': 'fn1',    'icon': 'lambda',     'label': 'Order\nService', 'x': 7.0, 'y': 5.0},
        {'id': 'fn2',    'icon': 'lambda',     'label': 'User\nService',  'x': 7.0, 'y': 3.5},
        {'id': 'fn3',    'icon': 'lambda',     'label': 'Notify\nService','x': 7.0, 'y': 2.0},
        {'id': 'ddb',    'icon': 'dynamodb',   'label': 'DynamoDB',       'x': 10.5, 'y': 4.3},
        {'id': 'sqs',    'icon': 'sqs',        'label': 'SQS',            'x': 10.5, 'y': 2.8},
        {'id': 'xray',   'icon': 'xray',       'label': 'X-Ray\n(トレース)', 'x': 4.0, 'y': 1.0},
    ]
    edges = [
        ('client', 'apigw', 'HTTPS'),
        ('apigw', 'fn1', 'ルーティング'),
        ('apigw', 'fn2', 'ルーティング'),
        ('apigw', 'fn3', 'ルーティング'),
        ('fn1', 'ddb', 'Read/Write'),
        ('fn1', 'sqs', 'メッセージ投入'),
        ('sqs', 'fn3', 'トリガー'),
        ('fn1', 'xray', 'トレース送信', 0.3),
        ('fn2', 'xray', 'トレース送信', 0.2),
    ]
    _draw_diagram('マイクロサービス基盤 ① – API Gateway + Lambda + X-Ray 構成',
                  nodes, edges, output_path)


def _diagram_microservices_base_2(output_path: str):
    """図2: X-Ray サービスマップ & 分散トレーシングフロー"""
    nodes = [
        {'id': 'apigw',  'icon': 'api_gateway', 'label': 'API Gateway',    'x': 2.0, 'y': 3.5},
        {'id': 'fn1',    'icon': 'lambda',      'label': 'Order Lambda',   'x': 5.0, 'y': 5.0},
        {'id': 'ddb',    'icon': 'dynamodb',    'label': 'DynamoDB',        'x': 8.0, 'y': 5.0},
        {'id': 'sqs',    'icon': 'sqs',         'label': 'SQS',             'x': 8.0, 'y': 3.5},
        {'id': 'fn2',    'icon': 'lambda',      'label': 'Notify Lambda',  'x': 11.0, 'y': 3.5},
        {'id': 'xray',   'icon': 'xray',        'label': 'X-Ray\nService Map', 'x': 5.0, 'y': 1.5},
    ]
    edges = [
        ('apigw', 'fn1', 'トレースID付与'),
        ('fn1', 'ddb', 'サブセグメント'),
        ('fn1', 'sqs', 'サブセグメント'),
        ('sqs', 'fn2', 'トレース継続'),
        ('fn1', 'xray', 'セグメント送信', 0.3),
        ('fn2', 'xray', 'セグメント送信', 0.2),
    ]
    _draw_diagram('マイクロサービス基盤 ② – X-Ray 分散トレーシングフロー',
                  nodes, edges, output_path)


# ─── multi_region_dr ──────────────────────────────────────────────────────────

def _diagram_multi_region_dr_1(output_path: str):
    """図1: マルチリージョン DR アーキテクチャ"""
    clusters = [
        {'label': 'プライマリリージョン (ap-northeast-1)', 'x': 3.0, 'y': 3.2, 'w': 4.5, 'h': 3.2, 'color': '#E8F5E9'},
        {'label': 'DRリージョン (ap-southeast-1)', 'x': 7.8, 'y': 3.2, 'w': 4.5, 'h': 3.2, 'color': '#FFF8E1'},
    ]
    nodes = [
        {'id': 'user',    'icon': 'user',    'label': 'ユーザー',       'x': 1.5, 'y': 4.8},
        {'id': 'r53',     'icon': 'route53', 'label': 'Route 53\n(フェイルオーバー)', 'x': 1.5, 'y': 3.0},
        {'id': 'alb1',    'icon': 'alb',     'label': 'ALB (Primary)',  'x': 4.5, 'y': 5.5},
        {'id': 'ec2p',    'icon': 'ec2',     'label': 'EC2 (Active)',   'x': 4.5, 'y': 4.0},
        {'id': 'rdsp',    'icon': 'rds',     'label': 'RDS\nMulti-AZ', 'x': 4.5, 'y': 2.5},
        {'id': 'alb2',    'icon': 'alb',     'label': 'ALB (DR)',       'x': 9.5, 'y': 5.5},
        {'id': 'ec2dr',   'icon': 'ec2',     'label': 'EC2 (Standby)', 'x': 9.5, 'y': 4.0},
        {'id': 'rdsdr',   'icon': 'rds',     'label': 'RDS\nRead Replica', 'x': 9.5, 'y': 2.5},
    ]
    edges = [
        ('user', 'r53', 'DNS解決'),
        ('r53', 'alb1', 'Primary'),
        ('r53', 'alb2', 'Failover', 0.2),
        ('alb1', 'ec2p', 'ルーティング'),
        ('ec2p', 'rdsp', 'Read/Write'),
        ('rdsp', 'rdsdr', 'レプリケーション'),
        ('alb2', 'ec2dr', 'ルーティング'),
        ('ec2dr', 'rdsdr', 'Read'),
    ]
    _draw_diagram('マルチリージョンDR ① – Route 53 フェイルオーバー構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_multi_region_dr_2(output_path: str):
    """図2: フェイルオーバー判定フロー"""
    nodes = [
        {'id': 'r53',   'icon': 'route53',    'label': 'Route 53\nヘルスチェック', 'x': 2.0, 'y': 3.5},
        {'id': 'check', 'icon': 'cloudwatch', 'label': 'CloudWatch\nAlarm',       'x': 5.0, 'y': 3.5},
        {'id': 'sns',   'icon': 'sns',        'label': 'SNS\n(障害通知)',          'x': 8.0, 'y': 5.0},
        {'id': 'alb1',  'icon': 'alb',        'label': 'Primary ALB\n(Unhealthy)', 'x': 8.0, 'y': 3.5},
        {'id': 'alb2',  'icon': 'alb',        'label': 'DR ALB\n(Active)',         'x': 11.0, 'y': 3.5},
        {'id': 'user',  'icon': 'user',       'label': 'ユーザー\n(自動切替)',      'x': 11.0, 'y': 1.5},
    ]
    edges = [
        ('r53', 'check', 'ヘルスチェック失敗'),
        ('check', 'sns', 'アラーム発火'),
        ('check', 'alb1', '障害検知'),
        ('r53', 'alb2', 'フェイルオーバー'),
        ('alb2', 'user', 'トラフィック切替'),
    ]
    _draw_diagram('マルチリージョンDR ② – 自動フェイルオーバーフロー',
                  nodes, edges, output_path)


# ─── realtime_notify ──────────────────────────────────────────────────────────

def _diagram_realtime_notify_1(output_path: str):
    """図1: SNS + SQS + Lambda + SES 通知基盤"""
    nodes = [
        {'id': 'src',   'icon': 'user',    'label': 'イベントソース', 'x': 1.5, 'y': 3.5},
        {'id': 'eb',    'icon': 'eventbridge', 'label': 'EventBridge', 'x': 4.0, 'y': 3.5},
        {'id': 'sns',   'icon': 'sns',     'label': 'SNS Topic',  'x': 6.5, 'y': 3.5},
        {'id': 'sqs1',  'icon': 'sqs',     'label': 'SQS\n(メール通知)', 'x': 9.5, 'y': 5.0},
        {'id': 'sqs2',  'icon': 'sqs',     'label': 'SQS\n(Slack通知)', 'x': 9.5, 'y': 3.5},
        {'id': 'sqs3',  'icon': 'sqs',     'label': 'SQS\n(DB保存)',    'x': 9.5, 'y': 2.0},
        {'id': 'fn1',   'icon': 'lambda',  'label': 'Lambda\n(SES送信)', 'x': 12.0, 'y': 5.0},
        {'id': 'fn2',   'icon': 'lambda',  'label': 'Lambda\n(Webhook)', 'x': 12.0, 'y': 3.5},
    ]
    edges = [
        ('src', 'eb', 'イベント発火'),
        ('eb', 'sns', 'ルーティング'),
        ('sns', 'sqs1', 'サブスクリプション'),
        ('sns', 'sqs2', 'サブスクリプション'),
        ('sns', 'sqs3', 'サブスクリプション'),
        ('sqs1', 'fn1', 'トリガー'),
        ('sqs2', 'fn2', 'トリガー'),
    ]
    _draw_diagram('リアルタイム通知システム ① – SNS + SQS + Lambda 構成',
                  nodes, edges, output_path)


def _diagram_realtime_notify_2(output_path: str):
    """図2: デッドレターキュー & リトライフロー"""
    nodes = [
        {'id': 'sqs',   'icon': 'sqs',    'label': 'SQS\n(メインキュー)',   'x': 2.5, 'y': 4.0},
        {'id': 'fn',    'icon': 'lambda', 'label': 'Lambda\n(処理)',        'x': 5.5, 'y': 4.0},
        {'id': 'ok',    'icon': 'ses',    'label': 'SES\n(送信成功)',        'x': 8.5, 'y': 5.2},
        {'id': 'fail',  'icon': 'sqs',    'label': 'DLQ\n(失敗メッセージ)', 'x': 8.5, 'y': 2.8},
        {'id': 'cw',    'icon': 'cloudwatch', 'label': 'CloudWatch\n(アラーム)', 'x': 11.5, 'y': 2.8},
        {'id': 'notify','icon': 'sns',    'label': 'SNS\n(障害通知)',        'x': 11.5, 'y': 4.5},
    ]
    edges = [
        ('sqs', 'fn', 'メッセージ取得'),
        ('fn', 'ok', '成功'),
        ('fn', 'fail', '3回失敗後\nDLQ転送'),
        ('fail', 'cw', 'DLQメトリクス'),
        ('cw', 'notify', 'アラーム発火'),
    ]
    _draw_diagram('リアルタイム通知システム ② – DLQ & リトライフロー',
                  nodes, edges, output_path)


# ─── bedrock_rag ──────────────────────────────────────────────────────────────

def _diagram_bedrock_rag_1(output_path: str):
    """図1: Bedrock RAG フルシステム構成"""
    clusters = [
        {'label': 'ドキュメント取り込みパイプライン', 'x': 0.5, 'y': 4.5, 'w': 6.0, 'h': 2.0, 'color': '#F0F8FF'},
        {'label': '検索・回答生成', 'x': 0.5, 'y': 0.5, 'w': 13.0, 'h': 3.8, 'color': '#F0FFF0'},
    ]
    nodes = [
        {'id': 'docs',   'icon': 's3',       'label': 'S3\n(ドキュメント)',   'x': 2.0, 'y': 5.5},
        {'id': 'embed',  'icon': 'bedrock',  'label': 'Bedrock\n(Embedding)', 'x': 5.0, 'y': 5.5},
        {'id': 'oss',    'icon': 'opensearch','label': 'OpenSearch\nServerless', 'x': 8.5, 'y': 5.5},
        {'id': 'user',   'icon': 'user',     'label': 'ユーザー',             'x': 1.5, 'y': 2.5},
        {'id': 'apigw',  'icon': 'api_gateway', 'label': 'API Gateway',      'x': 4.0, 'y': 2.5},
        {'id': 'fn',     'icon': 'lambda',   'label': 'Lambda\n(RAGロジック)', 'x': 6.5, 'y': 2.5},
        {'id': 'search', 'icon': 'opensearch','label': 'ベクトル検索',         'x': 9.0, 'y': 2.5},
        {'id': 'claude', 'icon': 'bedrock',  'label': 'Bedrock\nClaude',     'x': 11.5, 'y': 2.5},
    ]
    edges = [
        ('docs', 'embed', 'チャンキング'),
        ('embed', 'oss', 'ベクトル格納'),
        ('user', 'apigw', '質問'),
        ('apigw', 'fn', 'invoke'),
        ('fn', 'search', 'クエリ埋め込み'),
        ('search', 'oss', 'ANN検索', 0.2),
        ('fn', 'claude', '文脈+質問'),
        ('claude', 'fn', '回答生成', 0.3),
    ]
    _draw_diagram('Bedrock RAG ① – フルシステム構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_bedrock_rag_2(output_path: str):
    """図2: RAG クエリ処理フロー"""
    nodes = [
        {'id': 'user',   'icon': 'user',       'label': 'ユーザー\n(質問入力)',     'x': 1.5, 'y': 3.5},
        {'id': 'fn',     'icon': 'lambda',     'label': 'Lambda\n(RAGロジック)',   'x': 4.5, 'y': 3.5},
        {'id': 'embed',  'icon': 'bedrock',    'label': 'Bedrock\nEmbedding API', 'x': 7.5, 'y': 5.0},
        {'id': 'oss',    'icon': 'opensearch', 'label': 'OpenSearch\n(ベクトルDB)', 'x': 7.5, 'y': 3.5},
        {'id': 'claude', 'icon': 'bedrock',    'label': 'Bedrock\nClaude',        'x': 7.5, 'y': 2.0},
        {'id': 'out',    'icon': 'user',       'label': '回答返却',               'x': 11.0, 'y': 3.5},
    ]
    edges = [
        ('user', 'fn', '1. 質問送信'),
        ('fn', 'embed', '2. クエリ埋め込み'),
        ('embed', 'oss', '3. ベクトル検索'),
        ('oss', 'fn', '4. 関連文書取得'),
        ('fn', 'claude', '5. プロンプト構築\n(文脈+質問)'),
        ('claude', 'fn', '6. 回答生成'),
        ('fn', 'out', '7. 回答返却'),
    ]
    _draw_diagram('Bedrock RAG ② – クエリ処理データフロー',
                  nodes, edges, output_path)


# ─── cicd_pipeline ────────────────────────────────────────────────────────────

def _diagram_cicd_pipeline_1(output_path: str):
    """図1: CodePipeline + CodeBuild + CodeDeploy + ECS"""
    nodes = [
        {'id': 'dev',    'icon': 'user',        'label': '開発者',         'x': 1.5, 'y': 3.5},
        {'id': 'cc',     'icon': 'codecommit',  'label': 'CodeCommit\n(or GitHub)', 'x': 4.0, 'y': 3.5},
        {'id': 'pipe',   'icon': 'codepipeline','label': 'CodePipeline',   'x': 6.5, 'y': 3.5},
        {'id': 'build',  'icon': 'codebuild',   'label': 'CodeBuild\n(テスト/ビルド)', 'x': 9.0, 'y': 5.0},
        {'id': 'ecr',    'icon': 'ecr',         'label': 'ECR\n(イメージ登録)', 'x': 9.0, 'y': 3.5},
        {'id': 'deploy', 'icon': 'codedeploy',  'label': 'CodeDeploy\n(B/Gデプロイ)', 'x': 9.0, 'y': 2.0},
        {'id': 'ecs',    'icon': 'ecs',         'label': 'ECS Fargate',    'x': 11.5, 'y': 2.0},
    ]
    edges = [
        ('dev', 'cc', 'git push'),
        ('cc', 'pipe', 'Webhook/Poll'),
        ('pipe', 'build', 'Stage: Build'),
        ('build', 'ecr', 'docker push'),
        ('pipe', 'deploy', 'Stage: Deploy'),
        ('ecr', 'ecs', 'イメージPull'),
        ('deploy', 'ecs', 'Blue/Green\nデプロイ'),
    ]
    _draw_diagram('CI/CDパイプライン ① – CodePipeline + CodeBuild + CodeDeploy 構成',
                  nodes, edges, output_path)


def _diagram_cicd_pipeline_2(output_path: str):
    """図2: Blue/Green デプロイフロー"""
    nodes = [
        {'id': 'alb',   'icon': 'alb',   'label': 'ALB',              'x': 2.0, 'y': 3.5},
        {'id': 'blue',  'icon': 'ecs',   'label': 'ECS (Blue)\n[現行]', 'x': 5.5, 'y': 5.0},
        {'id': 'green', 'icon': 'ecs',   'label': 'ECS (Green)\n[新版]', 'x': 5.5, 'y': 2.0},
        {'id': 'cd',    'icon': 'codedeploy', 'label': 'CodeDeploy',   'x': 9.0, 'y': 3.5},
        {'id': 'shift', 'icon': 'cloudwatch', 'label': 'CloudWatch\n(ヘルス監視)', 'x': 11.5, 'y': 3.5},
    ]
    edges = [
        ('alb', 'blue', '100%トラフィック'),
        ('cd', 'green', '新バージョンデプロイ'),
        ('cd', 'alb', '10%→50%→100%\nトラフィック切替'),
        ('shift', 'alb', 'ヘルスチェック成功\n→切替続行'),
        ('shift', 'cd', '失敗→自動ロールバック', 0.2),
    ]
    _draw_diagram('CI/CDパイプライン ② – Blue/Green デプロイフロー',
                  nodes, edges, output_path)


# ─── ml_pipeline ──────────────────────────────────────────────────────────────

def _diagram_ml_pipeline_1(output_path: str):
    """図1: SageMaker + Step Functions MLパイプライン"""
    nodes = [
        {'id': 'raw',   'icon': 's3',         'label': 'S3\n(生データ)',      'x': 1.5, 'y': 3.5},
        {'id': 'sf',    'icon': 'step_functions', 'label': 'Step Functions\n(オーケストレーション)', 'x': 4.5, 'y': 3.5},
        {'id': 'proc',  'icon': 'sagemaker',  'label': 'SageMaker AI\n(前処理Job)',  'x': 7.5, 'y': 5.5},
        {'id': 'train', 'icon': 'sagemaker',  'label': 'SageMaker AI\n(Training Job)', 'x': 7.5, 'y': 3.5},
        {'id': 'eval',  'icon': 'lambda',     'label': 'Lambda\n(精度評価)',   'x': 7.5, 'y': 1.5},
        {'id': 'reg',   'icon': 'sagemaker',  'label': 'SageMaker AI\n(Model Registry)', 'x': 10.5, 'y': 4.5},
        {'id': 'ep',    'icon': 'sagemaker',  'label': 'SageMaker AI\n(Endpoint)',  'x': 10.5, 'y': 2.5},
    ]
    edges = [
        ('raw', 'sf', 'トリガー'),
        ('sf', 'proc', 'Step1: 前処理'),
        ('sf', 'train', 'Step2: 学習'),
        ('sf', 'eval', 'Step3: 評価'),
        ('proc', 'train', 'データ渡し'),
        ('train', 'reg', 'モデル登録'),
        ('eval', 'ep', '承認→デプロイ'),
    ]
    _draw_diagram('MLパイプライン ① – SageMaker AI + Step Functions 構成',
                  nodes, edges, output_path)


def _diagram_ml_pipeline_2(output_path: str):
    """図2: モデル更新 & A/Bテストフロー"""
    nodes = [
        {'id': 'eb',    'icon': 'eventbridge', 'label': 'EventBridge\n(週次スケジュール)', 'x': 2.0, 'y': 3.5},
        {'id': 'sf',    'icon': 'step_functions', 'label': 'Step Functions', 'x': 4.5, 'y': 3.5},
        {'id': 'train', 'icon': 'sagemaker',  'label': 'SageMaker AI\n(再学習)',     'x': 7.0, 'y': 3.5},
        {'id': 'ab',    'icon': 'sagemaker',  'label': 'SageMaker AI\n(A/Bテスト)', 'x': 9.5, 'y': 3.5},
        {'id': 'cw',    'icon': 'cloudwatch', 'label': 'CloudWatch\n(精度監視)',     'x': 9.5, 'y': 1.5},
        {'id': 'ep',    'icon': 'sagemaker',  'label': 'Endpoint\n(本番切替)',       'x': 12.0, 'y': 3.5},
    ]
    edges = [
        ('eb', 'sf', '定期実行'),
        ('sf', 'train', '再学習'),
        ('train', 'ab', '新モデル追加'),
        ('ab', 'cw', 'メトリクス監視'),
        ('cw', 'ep', '精度向上確認→\n本番100%切替'),
    ]
    _draw_diagram('MLパイプライン ② – 定期再学習 & A/Bテストフロー',
                  nodes, edges, output_path)


# ─── log_analytics ────────────────────────────────────────────────────────────

def _diagram_log_analytics_1(output_path: str):
    """図1: ログ集約 + Athena 分析基盤"""
    nodes = [
        {'id': 'ct',    'icon': 'cloudtrail', 'label': 'CloudTrail',     'x': 1.5, 'y': 5.5},
        {'id': 'cwl',   'icon': 'cloudwatch', 'label': 'CloudWatch\nLogs','x': 1.5, 'y': 3.5},
        {'id': 'vpc',   'icon': 'vpc',        'label': 'VPC Flow Logs',  'x': 1.5, 'y': 1.5},
        {'id': 'kfh',   'icon': 'kinesis',    'label': 'Kinesis\nFirehose', 'x': 4.5, 'y': 3.5},
        {'id': 's3',    'icon': 's3',         'label': 'S3\n(ログ保存)',  'x': 7.5, 'y': 3.5},
        {'id': 'glue',  'icon': 'glue',       'label': 'Glue\nCatalog',  'x': 10.0, 'y': 5.0},
        {'id': 'athena','icon': 'athena',     'label': 'Athena\n(SQL分析)', 'x': 10.0, 'y': 2.0},
    ]
    edges = [
        ('ct', 'kfh', 'CloudWatch\nLogs経由'),
        ('cwl', 'kfh', 'サブスクリプション'),
        ('vpc', 'kfh', 'Firehose連携'),
        ('kfh', 's3', 'Parquet変換'),
        ('s3', 'glue', 'クロール'),
        ('glue', 'athena', 'スキーマ提供'),
        ('s3', 'athena', 'データソース'),
    ]
    _draw_diagram('ログ分析基盤 ① – CloudTrail + Kinesis Firehose + Athena',
                  nodes, edges, output_path)


def _diagram_log_analytics_2(output_path: str):
    """図2: セキュリティ監査クエリフロー"""
    nodes = [
        {'id': 's3',    'icon': 's3',        'label': 'S3\n(CloudTrailログ)', 'x': 2.0, 'y': 3.5},
        {'id': 'athena','icon': 'athena',    'label': 'Athena\n(SQLクエリ)',   'x': 5.0, 'y': 3.5},
        {'id': 'check', 'icon': 'lambda',   'label': 'Lambda\n(異常検知)',    'x': 8.0, 'y': 3.5},
        {'id': 'sns',   'icon': 'sns',       'label': 'SNS\n(アラート通知)',   'x': 11.0, 'y': 4.5},
        {'id': 'eb',    'icon': 'eventbridge','label': 'EventBridge\n(定期実行)', 'x': 5.0, 'y': 1.5},
    ]
    edges = [
        ('eb', 'athena', '毎時実行'),
        ('s3', 'athena', 'データ読み取り'),
        ('athena', 'check', 'クエリ結果'),
        ('check', 'sns', '不審操作検知'),
    ]
    _draw_diagram('ログ分析基盤 ② – 自動セキュリティ監査フロー',
                  nodes, edges, output_path)


# ─── cost_optimization ────────────────────────────────────────────────────────

def _diagram_cost_optimization_1(output_path: str):
    """図1: コスト最適化アーキテクチャ全体像"""
    nodes = [
        {'id': 'ce',    'icon': 'cost_explorer', 'label': 'Cost Explorer\n(分析)',     'x': 2.0, 'y': 5.5},
        {'id': 'bgt',   'icon': 'budgets',       'label': 'AWS Budgets\n(予算アラート)', 'x': 2.0, 'y': 3.5},
        {'id': 'co',    'icon': 'compute_optimizer', 'label': 'Compute\nOptimizer',   'x': 2.0, 'y': 1.5},
        {'id': 'sns',   'icon': 'sns',           'label': 'SNS\n(通知)',               'x': 5.5, 'y': 3.5},
        {'id': 'fn',    'icon': 'lambda',        'label': 'Lambda\n(自動停止)',        'x': 8.5, 'y': 3.5},
        {'id': 'ec2',   'icon': 'ec2',           'label': 'EC2\n(停止対象)',           'x': 11.5, 'y': 5.0},
        {'id': 'rds',   'icon': 'rds',           'label': 'RDS\n(停止対象)',           'x': 11.5, 'y': 2.0},
    ]
    edges = [
        ('bgt', 'sns', 'コスト超過アラーム'),
        ('sns', 'fn', 'トリガー'),
        ('fn', 'ec2', '開発環境\n自動停止'),
        ('fn', 'rds', '深夜帯\n自動停止'),
        ('ce', 'fn', 'コスト分析', 0.2),
        ('co', 'fn', '最適化推奨', 0.2),
    ]
    _draw_diagram('コスト最適化 ① – 自動コスト管理アーキテクチャ',
                  nodes, edges, output_path)


def _diagram_cost_optimization_2(output_path: str):
    """図2: コスト削減施策のフロー"""
    nodes = [
        {'id': 'tags',  'icon': 'iam',     'label': 'タグ戦略\n(Environment/Project)', 'x': 2.0, 'y': 3.5},
        {'id': 'ce',    'icon': 'cost_explorer', 'label': 'Cost Explorer\n(タグ別分析)', 'x': 5.0, 'y': 3.5},
        {'id': 'sp',    'icon': 'ec2',     'label': 'Savings Plans\n(コミットメント)',  'x': 8.0, 'y': 5.0},
        {'id': 'spot',  'icon': 'ec2',     'label': 'Spot Instances\n(バッチ処理)',    'x': 8.0, 'y': 3.5},
        {'id': 'life',  'icon': 's3',      'label': 'S3 Lifecycle\n(Glacier移行)',    'x': 8.0, 'y': 2.0},
        {'id': 'report','icon': 'cloudwatch', 'label': 'コスト\n月次レポート',          'x': 11.0, 'y': 3.5},
    ]
    edges = [
        ('tags', 'ce', 'コスト可視化'),
        ('ce', 'sp', 'Savings Plans\n適用判断'),
        ('ce', 'spot', 'Spot活用判断'),
        ('ce', 'life', 'ストレージ最適化'),
        ('sp', 'report', 'コスト削減額'),
        ('spot', 'report', 'コスト削減額'),
        ('life', 'report', 'コスト削減額'),
    ]
    _draw_diagram('コスト最適化 ② – コスト削減施策フロー',
                  nodes, edges, output_path)


# ─── security_hardening ───────────────────────────────────────────────────────

def _diagram_security_hardening_1(output_path: str):
    """図1: 多層防御セキュリティアーキテクチャ"""
    clusters = [
        {'label': 'レイヤー1: エッジ保護', 'x': 0.5, 'y': 5.0, 'w': 13.0, 'h': 1.8, 'color': '#FFF0F0'},
        {'label': 'レイヤー2: 脅威検知', 'x': 0.5, 'y': 2.8, 'w': 13.0, 'h': 1.8, 'color': '#FFF8E1'},
        {'label': 'レイヤー3: 対応・修復', 'x': 0.5, 'y': 0.6, 'w': 13.0, 'h': 1.8, 'color': '#F0FFF0'},
    ]
    nodes = [
        {'id': 'waf',   'icon': 'waf',        'label': 'WAF',           'x': 2.5, 'y': 5.8},
        {'id': 'shield','icon': 'shield',     'label': 'Shield\nAdvanced','x': 7.0, 'y': 5.8},
        {'id': 'cf',    'icon': 'cloudfront', 'label': 'CloudFront',    'x': 11.5, 'y': 5.8},
        {'id': 'gd',    'icon': 'guardduty',  'label': 'GuardDuty',     'x': 2.5, 'y': 3.6},
        {'id': 'sh',    'icon': 'security_hub','label': 'Security Hub', 'x': 7.0, 'y': 3.6},
        {'id': 'config','icon': 'config',     'label': 'AWS Config',    'x': 11.5, 'y': 3.6},
        {'id': 'fn',    'icon': 'lambda',     'label': 'Lambda\n(自動修復)', 'x': 4.0, 'y': 1.4},
        {'id': 'sns',   'icon': 'sns',        'label': 'SNS\n(通知)',    'x': 10.0, 'y': 1.4},
    ]
    edges = [
        ('waf', 'cf', 'DDoS/SQLi防御'),
        ('gd', 'sh', '脅威検知→集約'),
        ('config', 'sh', 'コンプライアンス'),
        ('sh', 'fn', 'EventBridge連携'),
        ('fn', 'sns', '修復完了通知'),
    ]
    _draw_diagram('セキュリティ強化 ① – 多層防御アーキテクチャ',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_security_hardening_2(output_path: str):
    """図2: セキュリティインシデント対応フロー"""
    nodes = [
        {'id': 'gd',    'icon': 'guardduty', 'label': 'GuardDuty\n(脅威検知)',    'x': 2.0, 'y': 3.5},
        {'id': 'eb',    'icon': 'eventbridge','label': 'EventBridge\n(イベント)', 'x': 5.0, 'y': 3.5},
        {'id': 'fn',    'icon': 'lambda',    'label': 'Lambda\n(自動対応)',       'x': 8.0, 'y': 3.5},
        {'id': 'iam',   'icon': 'iam',       'label': 'IAM\n(権限無効化)',        'x': 11.0, 'y': 5.0},
        {'id': 'sg',    'icon': 'vpc',       'label': 'Security Group\n(隔離)',   'x': 11.0, 'y': 3.5},
        {'id': 'sns',   'icon': 'sns',       'label': 'SNS\n(担当者通知)',        'x': 11.0, 'y': 2.0},
    ]
    edges = [
        ('gd', 'eb', '高深刻度アラート'),
        ('eb', 'fn', 'トリガー'),
        ('fn', 'iam', '1. IAMキー無効化'),
        ('fn', 'sg', '2. EC2隔離'),
        ('fn', 'sns', '3. 担当者通知'),
    ]
    _draw_diagram('セキュリティ強化 ② – インシデント自動対応フロー',
                  nodes, edges, output_path)


# ─── backup_dr ────────────────────────────────────────────────────────────────

def _diagram_backup_dr_1(output_path: str):
    """図1: AWS Backup 統合バックアップ構成"""
    nodes = [
        {'id': 'policy','icon': 'backup',    'label': 'AWS Backup\n(バックアッププラン)', 'x': 2.0, 'y': 3.5},
        {'id': 'ec2',   'icon': 'ec2',       'label': 'EC2\n(スナップショット)',          'x': 5.5, 'y': 5.5},
        {'id': 'rds',   'icon': 'rds',       'label': 'RDS\n(自動スナップショット)',       'x': 5.5, 'y': 3.5},
        {'id': 'ddb',   'icon': 'dynamodb',  'label': 'DynamoDB\n(PITR)',                'x': 5.5, 'y': 1.5},
        {'id': 'vault1','icon': 'backup',    'label': 'Backup Vault\n(東京)',            'x': 9.0, 'y': 3.5},
        {'id': 'vault2','icon': 'backup',    'label': 'Backup Vault\n(大阪・Cross-Region)', 'x': 12.0, 'y': 3.5},
    ]
    edges = [
        ('policy', 'ec2', 'バックアップ'),
        ('policy', 'rds', 'バックアップ'),
        ('policy', 'ddb', 'バックアップ'),
        ('ec2', 'vault1', 'Vault保存'),
        ('rds', 'vault1', 'Vault保存'),
        ('ddb', 'vault1', 'Vault保存'),
        ('vault1', 'vault2', 'Cross-Region\nコピー'),
    ]
    _draw_diagram('バックアップ・DR ① – AWS Backup 統合管理構成',
                  nodes, edges, output_path)


def _diagram_backup_dr_2(output_path: str):
    """図2: DR 復元フロー"""
    nodes = [
        {'id': 'incident','icon': 'cloudwatch','label': '障害検知\n(CloudWatch)', 'x': 1.5, 'y': 3.5},
        {'id': 'vault',  'icon': 'backup',    'label': 'Backup Vault\n(DRリージョン)', 'x': 4.5, 'y': 3.5},
        {'id': 'rds',    'icon': 'rds',       'label': 'RDS復元\n(スナップショット)', 'x': 7.5, 'y': 5.0},
        {'id': 'ec2',    'icon': 'ec2',       'label': 'EC2復元\n(AMI)',             'x': 7.5, 'y': 3.5},
        {'id': 'cfn',    'icon': 'cloudformation', 'label': 'CloudFormation\n(インフラ再構築)', 'x': 7.5, 'y': 2.0},
        {'id': 'r53',    'icon': 'route53',   'label': 'Route 53\n(フェイルオーバー)', 'x': 10.5, 'y': 3.5},
    ]
    edges = [
        ('incident', 'vault', '復元開始'),
        ('vault', 'rds', 'RDS復元'),
        ('vault', 'ec2', 'EC2復元'),
        ('cfn', 'ec2', 'インフラ展開', 0.2),
        ('rds', 'r53', 'DNS切替'),
        ('ec2', 'r53', 'DNS切替'),
    ]
    _draw_diagram('バックアップ・DR ② – DRリージョン復元フロー',
                  nodes, edges, output_path)


# ─── multi_account ────────────────────────────────────────────────────────────

def _diagram_multi_account_1(output_path: str):
    """図1: AWS Organizations + Control Tower マルチアカウント構成"""
    clusters = [
        {'label': 'Root OU', 'x': 0.5, 'y': 0.5, 'w': 13.0, 'h': 6.0, 'color': '#F5F5FF'},
        {'label': 'Security OU', 'x': 1.0, 'y': 3.5, 'w': 3.0, 'h': 2.5, 'color': '#FFF0F0'},
        {'label': 'Production OU', 'x': 5.0, 'y': 3.5, 'w': 3.5, 'h': 2.5, 'color': '#F0FFF0'},
        {'label': 'Development OU', 'x': 9.5, 'y': 3.5, 'w': 3.5, 'h': 2.5, 'color': '#FFF8E1'},
    ]
    nodes = [
        {'id': 'mgmt',  'icon': 'organizations', 'label': 'Management\nAccount', 'x': 7.0, 'y': 1.5},
        {'id': 'ct',    'icon': 'control_tower', 'label': 'Control Tower',       'x': 4.0, 'y': 1.5},
        {'id': 'sso',   'icon': 'iam',           'label': 'IAM Identity\nCenter','x': 10.0, 'y': 1.5},
        {'id': 'log',   'icon': 'cloudtrail',    'label': 'Log Archive\nAccount','x': 1.8, 'y': 4.8},
        {'id': 'audit', 'icon': 'security_hub',  'label': 'Audit\nAccount',      'x': 3.2, 'y': 4.8, 'color': '#FFE0E0'},
        {'id': 'prod',  'icon': 'ec2',           'label': 'Production\nAccount', 'x': 6.5, 'y': 4.5},
        {'id': 'dev',   'icon': 'ec2',           'label': 'Dev\nAccount',        'x': 11.0, 'y': 4.5},
    ]
    edges = [
        ('ct', 'mgmt', 'ガードレール適用'),
        ('sso', 'prod', 'シングルサインオン'),
        ('sso', 'dev', 'シングルサインオン'),
        ('prod', 'log', 'CloudTrail集約'),
        ('dev', 'log', 'CloudTrail集約'),
    ]
    _draw_diagram('マルチアカウント ① – Organizations + Control Tower 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_multi_account_2(output_path: str):
    """図2: アカウント払い出しフロー（Account Factory）"""
    nodes = [
        {'id': 'req',   'icon': 'user',          'label': '申請者\n(新アカウント要求)', 'x': 1.5, 'y': 3.5},
        {'id': 'sc',    'icon': 'service_catalog','label': 'Service Catalog\n(Account Factory)', 'x': 4.5, 'y': 3.5},
        {'id': 'ct',    'icon': 'control_tower',  'label': 'Control Tower\n(自動プロビジョニング)', 'x': 7.5, 'y': 3.5},
        {'id': 'acc',   'icon': 'organizations',  'label': '新AWSアカウント\n(OU配置済み)',         'x': 10.5, 'y': 3.5},
        {'id': 'scp',   'icon': 'iam',            'label': 'SCP適用\n(ガードレール)',               'x': 10.5, 'y': 1.5},
    ]
    edges = [
        ('req', 'sc', 'セルフサービス申請'),
        ('sc', 'ct', 'Account Factory\nトリガー'),
        ('ct', 'acc', 'アカウント作成\n(完全自動)'),
        ('ct', 'scp', 'SCP自動適用'),
    ]
    _draw_diagram('マルチアカウント ② – Account Factory 自動払い出しフロー',
                  nodes, edges, output_path)


# ─── data_lake ────────────────────────────────────────────────────────────────

def _diagram_data_lake_1(output_path: str):
    """図1: S3 + Glue + Athena + Lake Formation データレイク（メダリオンアーキテクチャ）"""
    # Bronze/Silver/Gold クラスターを縦帯として配置し、処理ノードはクラスター間に配置
    clusters = [
        {'label': 'Bronze層 (Raw)', 'x': 1.5, 'y': 2.5, 'w': 2.5, 'h': 3.0, 'color': '#FFF0E0'},
        {'label': 'Silver層 (Cleansed)', 'x': 5.5, 'y': 2.5, 'w': 2.5, 'h': 3.0, 'color': '#FFF8E1'},
        {'label': 'Gold層 (Curated)', 'x': 9.5, 'y': 2.5, 'w': 2.5, 'h': 3.0, 'color': '#E8F5E9'},
    ]
    nodes = [
        {'id': 'src',    'icon': 'user',          'label': 'データソース\n(API/DB/ログ)', 'x': 0.8, 'y': 4.0},
        {'id': 'raw',    'icon': 's3',            'label': 'S3 (Raw)',         'x': 2.8, 'y': 4.0},
        {'id': 'glue',   'icon': 'glue',          'label': 'Glue ETL\n(変換)', 'x': 4.7, 'y': 4.0},
        {'id': 'clean',  'icon': 's3',            'label': 'S3 (Parquet)',     'x': 6.8, 'y': 4.0},
        {'id': 'lf',     'icon': 'lake_formation','label': 'Lake Formation\n(権限管理)', 'x': 8.7, 'y': 4.0},
        {'id': 'curate', 'icon': 's3',            'label': 'S3 (Curated)',     'x': 10.8, 'y': 4.0},
        {'id': 'athena', 'icon': 'athena',        'label': 'Athena',           'x': 13.0, 'y': 5.0},
        {'id': 'qs',     'icon': 'quicksight',    'label': 'QuickSight\n(BI)', 'x': 13.0, 'y': 3.0},
    ]
    edges = [
        ('src', 'raw', 'Ingestion'),
        ('raw', 'glue', 'クロール'),
        ('glue', 'clean', 'ETL変換'),
        ('clean', 'lf', 'カタログ登録'),
        ('lf', 'curate', '集計・加工'),
        ('curate', 'athena', 'SQLクエリ'),
        ('athena', 'qs', 'BIダッシュボード'),
    ]
    _draw_diagram('データレイク ① – S3 + Glue + Athena + Lake Formation 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_data_lake_2(output_path: str):
    """図2: Glue ETLジョブ & データカタログ更新フロー"""
    nodes = [
        {'id': 'eb',    'icon': 'eventbridge','label': 'EventBridge\n(日次スケジュール)', 'x': 2.0, 'y': 3.5},
        {'id': 'glue',  'icon': 'glue',      'label': 'Glue Job\n(ETL処理)',            'x': 5.0, 'y': 3.5},
        {'id': 's3in',  'icon': 's3',        'label': 'S3 Input\n(Raw Parquet)',         'x': 5.0, 'y': 5.5},
        {'id': 's3out', 'icon': 's3',        'label': 'S3 Output\n(Curated)',            'x': 8.0, 'y': 3.5},
        {'id': 'cat',   'icon': 'glue',      'label': 'Glue Catalog\n(スキーマ更新)',   'x': 8.0, 'y': 1.5},
        {'id': 'athena','icon': 'athena',    'label': 'Athena\n(即時クエリ可能)',       'x': 11.0, 'y': 3.5},
    ]
    edges = [
        ('eb', 'glue', 'ジョブ起動'),
        ('s3in', 'glue', 'データ読み取り'),
        ('glue', 's3out', '変換後保存'),
        ('glue', 'cat', 'パーティション更新'),
        ('cat', 'athena', 'スキーマ反映'),
        ('s3out', 'athena', 'データソース'),
    ]
    _draw_diagram('データレイク ② – Glue ETLジョブ & データカタログ更新フロー',
                  nodes, edges, output_path)


# ─── ディスパッチテーブル ──────────────────────────────────────────────────────

_DIAGRAM_FUNCTIONS: dict[str, tuple] = {
    "serverless_ec":         (_diagram_serverless_ec_1,         _diagram_serverless_ec_2),
    "static_web_hosting":    (_diagram_static_web_hosting_1,    _diagram_static_web_hosting_2),
    "container_platform":    (_diagram_container_platform_1,    _diagram_container_platform_2),
    "event_driven_pipeline": (_diagram_event_driven_pipeline_1, _diagram_event_driven_pipeline_2),
    "microservices_base":    (_diagram_microservices_base_1,    _diagram_microservices_base_2),
    "multi_region_dr":       (_diagram_multi_region_dr_1,       _diagram_multi_region_dr_2),
    "realtime_notify":       (_diagram_realtime_notify_1,       _diagram_realtime_notify_2),
    "bedrock_rag":           (_diagram_bedrock_rag_1,           _diagram_bedrock_rag_2),
    "cicd_pipeline":         (_diagram_cicd_pipeline_1,         _diagram_cicd_pipeline_2),
    "ml_pipeline":           (_diagram_ml_pipeline_1,           _diagram_ml_pipeline_2),
    "log_analytics":         (_diagram_log_analytics_1,         _diagram_log_analytics_2),
    "cost_optimization":     (_diagram_cost_optimization_1,     _diagram_cost_optimization_2),
    "security_hardening":    (_diagram_security_hardening_1,    _diagram_security_hardening_2),
    "backup_dr":             (_diagram_backup_dr_1,             _diagram_backup_dr_2),
    "multi_account":         (_diagram_multi_account_1,         _diagram_multi_account_2),
    "data_lake":             (_diagram_data_lake_1,             _diagram_data_lake_2),
}


def generate_diagrams(topic_id: str, base_path: str) -> list[str]:
    """
    指定トピックの構成図2枚を生成し、PNGパスのリストを返す。
    base_path: 拡張子なしのパス（例: /tmp/20260501_210000_serverless_ec_diagram）
    """
    funcs = _DIAGRAM_FUNCTIONS.get(topic_id)
    if funcs is None:
        print(f"警告: トピック '{topic_id}' の図定義が見つかりません")
        return []

    paths = []
    for i, func in enumerate(funcs, start=1):
        out_path = f"{base_path}_{i}.png"
        try:
            func(out_path)
            paths.append(out_path)
            print(f"  PNG生成完了: {out_path}")
        except Exception as e:
            print(f"  PNG生成エラー (図{i}): {e}")

    return paths
