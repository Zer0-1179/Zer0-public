"""
各AWSトピックのアーキテクチャ図を生成するモジュール。
matplotlib + AWS公式アイコン（PNGバンドル）を使用。
Graphviz / diagrams への依存なし。Lambda環境で動作。
各トピックにつき2枚のPNGを生成する。
"""
import matplotlib
matplotlib.use('Agg')  # Lambda環境ではGUIバックエンド不可のため必須

import os
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

# アイコンディレクトリ（関数コードと同梱）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_SCRIPT_DIR, 'aws_icons')

# 日本語フォント設定
def _setup_font():
    import matplotlib.font_manager as fm

    # 1. 同梱フォント（Lambda環境・ローカル共通）
    bundled = os.path.join(_SCRIPT_DIR, 'fonts', 'NotoSansCJK-Regular.ttc')
    # 2. システムフォントのフォールバックパス
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

    # 3. フォントキャッシュから検索（最終フォールバック）
    for name in ['Noto Sans CJK JP', 'Noto Sans JP', 'IPAGothic']:
        if any(f.name == name for f in fm.fontManager.ttflist):
            plt.rcParams['font.family'] = name
            return

_setup_font()


# ─── 描画ヘルパー ──────────────────────────────────────────────────────────────

def _load_icon(name: str):
    if not name:
        return None
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
    figsize: tuple = (13, 6),
    xlim: tuple = (0, 13),
    ylim: tuple = (0, 6),
    clusters: list = None,
):
    """
    nodes   : [{'id': str, 'icon': str|None, 'label': str, 'x': float, 'y': float}]
    edges   : [(from_id, to_id) | (from_id, to_id, label)]
    clusters: [{'label': str, 'x': float, 'y': float, 'w': float, 'h': float, 'color': str}]
    """
    # ── クラスター枠がノードと重ならないよう自動パディング調整 ──────────────
    _ICON_HALF = 0.55
    _PAD_H     = _ICON_HALF + 0.45
    _PAD_TOP   = _ICON_HALF + 0.55
    _PAD_BOT   = _ICON_HALF + 1.05

    for cl in (clusters or []):
        for node in nodes:
            nx, ny = node['x'], node['y']
            if not (cl['x'] - 0.1 <= nx <= cl['x'] + cl['w'] + 0.1 and
                    cl['y'] - 0.1 <= ny <= cl['y'] + cl['h'] + 0.1):
                continue
            if nx - cl['x'] < _PAD_H:
                diff = _PAD_H - (nx - cl['x']); cl['x'] -= diff; cl['w'] += diff
            if (cl['x'] + cl['w']) - nx < _PAD_H:
                cl['w'] += _PAD_H - ((cl['x'] + cl['w']) - nx)
            if (cl['y'] + cl['h']) - ny < _PAD_TOP:
                cl['h'] += _PAD_TOP - ((cl['y'] + cl['h']) - ny)
            if ny - cl['y'] < _PAD_BOT:
                diff = _PAD_BOT - (ny - cl['y']); cl['y'] -= diff; cl['h'] += diff

    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=10, color='#232F3E')

    # クラスター（破線囲み枠）
    for cluster in (clusters or []):
        rect = FancyBboxPatch(
            (cluster['x'], cluster['y']),
            cluster['w'], cluster['h'],
            boxstyle='round,pad=0.15',
            facecolor=cluster.get('color', '#EAF4FB'),
            edgecolor='#8AAFCC',
            linewidth=1.5,
            linestyle='--',
            zorder=1,
        )
        ax.add_patch(rect)
        ax.text(
            cluster['x'] + cluster['w'] / 2,
            cluster['y'] + cluster['h'] - 0.1,
            cluster['label'],
            ha='center', va='top',
            fontsize=8, color='#4A7FA5', style='italic',
        )

    node_map = {n['id']: n for n in nodes}

    # エッジ（矢印）
    SHRINK = 42
    for edge in edges:
        from_id, to_id = edge[0], edge[1]
        edge_label = edge[2] if len(edge) > 2 else ''
        n1, n2 = node_map[from_id], node_map[to_id]
        ax.annotate(
            '',
            xy=(n2['x'], n2['y']),
            xytext=(n1['x'], n1['y']),
            arrowprops=dict(
                arrowstyle='->', color='#555555', lw=1.5,
                shrinkA=SHRINK, shrinkB=SHRINK,
                connectionstyle='arc3,rad=0.0',
            ),
            zorder=3,
        )
        if edge_label:
            mx = (n1['x'] + n2['x']) / 2
            my = (n1['y'] + n2['y']) / 2
            ax.text(mx, my + 0.18, edge_label, ha='center', va='bottom',
                    fontsize=7, color='#666666', zorder=4)

    # ノード（アイコン + ラベル）
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
            ax.text(x, y, node.get('short', ''), ha='center', va='center',
                    fontsize=8, color='#232F3E', fontweight='bold', zorder=5)

        ax.text(x, y - HALF - 0.2, node['label'],
                ha='center', va='top', fontsize=8,
                color='#232F3E', fontweight='bold', zorder=5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', format='png')
    plt.close(fig)


# ─── EC2 ─────────────────────────────────────────────────────────────────────

def _diagram_ec2_1(output_path: str):
    """図1: ユーザー → ALB → EC2×2 → RDS"""
    nodes = [
        {'id': 'user',  'icon': 'user',  'label': 'ユーザー', 'x': 1.5, 'y': 3.0},
        {'id': 'alb',   'icon': 'alb',   'label': 'ALB',      'x': 4.0, 'y': 3.0},
        {'id': 'ec2_1', 'icon': 'ec2',   'label': 'EC2 #1',   'x': 7.0, 'y': 4.2},
        {'id': 'ec2_2', 'icon': 'ec2',   'label': 'EC2 #2',   'x': 7.0, 'y': 1.8},
        {'id': 'rds',   'icon': 'rds',   'label': 'RDS',      'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('user', 'alb'),
        ('alb', 'ec2_1'),
        ('alb', 'ec2_2'),
        ('ec2_1', 'rds'),
        ('ec2_2', 'rds'),
    ]
    _draw_diagram('Amazon EC2 ① – ALB + EC2 冗長構成', nodes, edges, output_path)


def _diagram_ec2_2(output_path: str):
    """図2: CloudWatch → Auto Scaling → EC2 スケールアウト"""
    nodes = [
        {'id': 'cw',  'icon': 'cloudwatch',       'label': 'CloudWatch',   'x': 1.5, 'y': 3.0},
        {'id': 'al',  'icon': 'cloudwatch_alarm',  'label': 'Alarm',        'x': 4.0, 'y': 3.0},
        {'id': 'asg', 'icon': 'autoscaling',       'label': 'Auto Scaling', 'x': 7.0, 'y': 3.0},
        {'id': 'e1',  'icon': 'ec2',               'label': 'EC2 #1',       'x': 10.5,'y': 4.5},
        {'id': 'e2',  'icon': 'ec2',               'label': 'EC2 #2',       'x': 10.5,'y': 3.0},
        {'id': 'e3',  'icon': 'ec2',               'label': 'EC2 #3 (new)', 'x': 10.5,'y': 1.5},
    ]
    edges = [
        ('cw', 'al', 'CPU > 70%'),
        ('al', 'asg', 'スケール指示'),
        ('asg', 'e1'),
        ('asg', 'e2'),
        ('asg', 'e3', '追加起動'),
    ]
    _draw_diagram('Amazon EC2 ② – CloudWatch + Auto Scaling 自動スケール構成',
                  nodes, edges, output_path)


# ─── S3 ─────────────────────────────────────────────────────────────────────

def _diagram_s3_1(output_path: str):
    """図1: 開発者 → S3 → CloudFront → ユーザー"""
    nodes = [
        {'id': 'dev',  'icon': 'user',       'label': '開発者',      'x': 1.5, 'y': 3.0},
        {'id': 's3',   'icon': 's3',          'label': 'S3 バケット', 'x': 4.5, 'y': 3.0},
        {'id': 'cf',   'icon': 'cloudfront',  'label': 'CloudFront',  'x': 7.5, 'y': 3.0},
        {'id': 'user', 'icon': 'user',        'label': 'ユーザー',    'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('dev', 's3', 'アップロード'),
        ('s3', 'cf', 'オリジン'),
        ('cf', 'user', 'CDN配信'),
    ]
    _draw_diagram('Amazon S3 ① – 静的ウェブホスティング + CloudFront 構成',
                  nodes, edges, output_path)


def _diagram_s3_2(output_path: str):
    """図2: S3 イベント通知 → Lambda → DynamoDB"""
    nodes = [
        {'id': 'user', 'icon': 'user',     'label': 'ユーザー',    'x': 1.5, 'y': 3.0},
        {'id': 's3',   'icon': 's3',       'label': 'S3 バケット', 'x': 4.5, 'y': 3.0},
        {'id': 'fn',   'icon': 'lambda',   'label': 'Lambda',      'x': 7.5, 'y': 3.0},
        {'id': 'ddb',  'icon': 'dynamodb', 'label': 'DynamoDB',    'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('user', 's3', 'PUT Object'),
        ('s3', 'fn', 'イベント通知'),
        ('fn', 'ddb', 'メタデータ保存'),
    ]
    _draw_diagram('Amazon S3 ② – S3 イベント通知 + Lambda 連携構成',
                  nodes, edges, output_path)


# ─── IAM ─────────────────────────────────────────────────────────────────────

def _diagram_iam_1(output_path: str):
    """図1: ユーザー → IAMユーザー/ロール → AWSリソース"""
    nodes = [
        {'id': 'user',     'icon': 'user',     'label': 'ユーザー',     'x': 1.5, 'y': 3.0},
        {'id': 'iam_user', 'icon': 'iam',       'label': 'IAM ユーザー', 'x': 4.5, 'y': 4.2},
        {'id': 'iam_role', 'icon': 'iam_role',  'label': 'IAM ロール',   'x': 4.5, 'y': 1.8},
        {'id': 'ec2',      'icon': 'ec2',       'label': 'EC2',          'x': 8.0, 'y': 4.5},
        {'id': 's3',       'icon': 's3',        'label': 'S3',           'x': 8.0, 'y': 3.0},
        {'id': 'rds',      'icon': 'rds',       'label': 'RDS',          'x': 8.0, 'y': 1.5},
    ]
    edges = [
        ('user', 'iam_user'),
        ('user', 'iam_role'),
        ('iam_user', 'ec2'),
        ('iam_user', 's3'),
        ('iam_role', 's3'),
        ('iam_role', 'rds'),
    ]
    _draw_diagram('AWS IAM ① – ユーザー / ロール / ポリシー 構成', nodes, edges, output_path)


def _diagram_iam_2(output_path: str):
    """図2: EC2 が IAM ロールで S3・DynamoDB にアクセス"""
    nodes = [
        {'id': 'ec2',  'icon': 'ec2',      'label': 'EC2 (App)',   'x': 2.0, 'y': 3.0},
        {'id': 'role', 'icon': 'iam_role', 'label': 'IAM ロール',  'x': 5.5, 'y': 3.0},
        {'id': 's3',   'icon': 's3',       'label': 'S3',          'x': 9.5, 'y': 4.3},
        {'id': 'ddb',  'icon': 'dynamodb', 'label': 'DynamoDB',    'x': 9.5, 'y': 1.7},
    ]
    edges = [
        ('ec2', 'role', 'AssumeRole'),
        ('role', 's3', 'GetObject / PutObject'),
        ('role', 'ddb', 'Query / PutItem'),
    ]
    _draw_diagram('AWS IAM ② – EC2 インスタンスプロファイル（ロール）によるリソースアクセス',
                  nodes, edges, output_path)


# ─── VPC ─────────────────────────────────────────────────────────────────────

def _diagram_vpc_1(output_path: str):
    """図1: Internet → IGW → パブリック → プライベートサブネット"""
    nodes = [
        {'id': 'inet', 'icon': 'user', 'label': 'Internet',         'x': 1.0, 'y': 3.0},
        {'id': 'igw',  'icon': 'igw',  'label': 'Internet Gateway', 'x': 3.5, 'y': 3.0},
        {'id': 'alb',  'icon': 'alb',  'label': 'ALB',              'x': 6.0, 'y': 3.0},
        {'id': 'ec2',  'icon': 'ec2',  'label': 'EC2 (Web)',        'x': 8.5, 'y': 3.0},
        {'id': 'rds',  'icon': 'rds',  'label': 'RDS (DB)',         'x': 11.0,'y': 3.0},
    ]
    edges = [('inet', 'igw'), ('igw', 'alb'), ('alb', 'ec2'), ('ec2', 'rds')]
    clusters = [
        {'label': 'パブリックサブネット', 'x': 4.8, 'y': 1.8, 'w': 4.2, 'h': 2.4,
         'color': '#E8F4FB'},
        {'label': 'プライベートサブネット', 'x': 9.6, 'y': 1.8, 'w': 2.8, 'h': 2.4,
         'color': '#FEF9E7'},
    ]
    _draw_diagram('Amazon VPC ① – パブリック / プライベートサブネット 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_vpc_2(output_path: str):
    """図2: プライベートサブネット → NAT GW → インターネット"""
    nodes = [
        {'id': 'ec2',  'icon': 'ec2',  'label': 'EC2 (Private)', 'x': 2.0, 'y': 3.0},
        {'id': 'nat',  'icon': 'nat',  'label': 'NAT Gateway',   'x': 5.5, 'y': 3.0},
        {'id': 'igw',  'icon': 'igw',  'label': 'Internet GW',   'x': 9.0, 'y': 3.0},
        {'id': 'inet', 'icon': 'user', 'label': 'Internet',       'x': 12.0,'y': 3.0},
    ]
    edges = [
        ('ec2', 'nat', 'アウトバウンド'),
        ('nat', 'igw'),
        ('igw', 'inet'),
    ]
    clusters = [
        {'label': 'プライベートサブネット', 'x': 0.7, 'y': 1.8, 'w': 3.0, 'h': 2.4,
         'color': '#FEF9E7'},
        {'label': 'パブリックサブネット',   'x': 4.2, 'y': 1.8, 'w': 3.0, 'h': 2.4,
         'color': '#E8F4FB'},
    ]
    _draw_diagram('Amazon VPC ② – NAT Gateway 経由のアウトバウンド通信構成',
                  nodes, edges, output_path, clusters=clusters)


# ─── RDS ─────────────────────────────────────────────────────────────────────

def _diagram_rds_1(output_path: str):
    """図1: EC2 → RDS Primary / Standby（Multi-AZ）"""
    nodes = [
        {'id': 'ec2',     'icon': 'ec2', 'label': 'EC2 (App)',    'x': 2.5, 'y': 3.0},
        {'id': 'primary', 'icon': 'rds', 'label': 'RDS Primary',  'x': 6.5, 'y': 4.2},
        {'id': 'standby', 'icon': 'rds', 'label': 'RDS Standby',  'x': 6.5, 'y': 1.8},
    ]
    edges = [
        ('ec2', 'primary', '読み書き'),
        ('primary', 'standby', '同期レプリケーション'),
    ]
    clusters = [
        {'label': 'AZ-a', 'x': 5.0, 'y': 3.3, 'w': 3.0, 'h': 1.8, 'color': '#EAF7EA'},
        {'label': 'AZ-b', 'x': 5.0, 'y': 0.9, 'w': 3.0, 'h': 1.8, 'color': '#FEF3E7'},
    ]
    _draw_diagram('Amazon RDS ① – Multi-AZ 冗長構成',
                  nodes, edges, output_path, figsize=(10, 6), xlim=(0, 10), clusters=clusters)


def _diagram_rds_2(output_path: str):
    """図2: Primary → Read Replica（読み取り分離）"""
    nodes = [
        {'id': 'app_w',   'icon': 'ec2', 'label': 'App (Write)',       'x': 1.5, 'y': 4.2},
        {'id': 'app_r',   'icon': 'ec2', 'label': 'App (Read)',        'x': 1.5, 'y': 1.8},
        {'id': 'primary', 'icon': 'rds', 'label': 'RDS Primary',       'x': 5.5, 'y': 3.0},
        {'id': 'replica', 'icon': 'rds', 'label': 'Read Replica',      'x': 9.5, 'y': 3.0},
    ]
    edges = [
        ('app_w', 'primary', 'Write'),
        ('app_r', 'replica', 'Read'),
        ('primary', 'replica', '非同期レプリケーション'),
    ]
    _draw_diagram('Amazon RDS ② – リードレプリカ（読み取りスケールアウト）構成',
                  nodes, edges, output_path)


# ─── Lambda ──────────────────────────────────────────────────────────────────

def _diagram_lambda_1(output_path: str):
    """図1: EventBridge → Lambda → DynamoDB / S3"""
    nodes = [
        {'id': 'eb',  'icon': 'eventbridge', 'label': 'EventBridge', 'x': 2.0, 'y': 3.0},
        {'id': 'fn',  'icon': 'lambda',      'label': 'Lambda',      'x': 5.5, 'y': 3.0},
        {'id': 'ddb', 'icon': 'dynamodb',    'label': 'DynamoDB',    'x': 9.5, 'y': 4.2},
        {'id': 's3',  'icon': 's3',          'label': 'S3',          'x': 9.5, 'y': 1.8},
    ]
    edges = [
        ('eb', 'fn', 'スケジュール'),
        ('fn', 'ddb', 'Write'),
        ('fn', 's3', 'Put'),
    ]
    _draw_diagram('AWS Lambda ① – EventBridge トリガー + DynamoDB / S3 構成',
                  nodes, edges, output_path)


def _diagram_lambda_2(output_path: str):
    """図2: SQS → Lambda → DynamoDB（非同期処理）"""
    nodes = [
        {'id': 'ec2', 'icon': 'ec2',      'label': 'EC2 (Producer)', 'x': 1.5, 'y': 3.0},
        {'id': 'sqs', 'icon': 'sqs',      'label': 'SQS',            'x': 4.5, 'y': 3.0},
        {'id': 'fn',  'icon': 'lambda',   'label': 'Lambda',         'x': 7.5, 'y': 3.0},
        {'id': 'ddb', 'icon': 'dynamodb', 'label': 'DynamoDB',       'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('ec2', 'sqs', 'SendMessage'),
        ('sqs', 'fn', 'トリガー（バッチ）'),
        ('fn', 'ddb', 'PutItem'),
    ]
    _draw_diagram('AWS Lambda ② – SQS トリガーによる非同期処理構成',
                  nodes, edges, output_path)


# ─── CloudWatch ──────────────────────────────────────────────────────────────

def _diagram_cloudwatch_1(output_path: str):
    """図1: EC2/Lambda → CloudWatch → Alarm → SNS"""
    nodes = [
        {'id': 'ec2', 'icon': 'ec2',              'label': 'EC2',        'x': 1.2, 'y': 4.0},
        {'id': 'fn',  'icon': 'lambda',           'label': 'Lambda',     'x': 1.2, 'y': 2.0},
        {'id': 'cw',  'icon': 'cloudwatch',       'label': 'CloudWatch', 'x': 4.5, 'y': 3.0},
        {'id': 'al',  'icon': 'cloudwatch_alarm', 'label': 'Alarm',      'x': 7.5, 'y': 3.0},
        {'id': 'sns', 'icon': 'sns',              'label': 'SNS',        'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('ec2', 'cw', 'メトリクス'),
        ('fn', 'cw', 'メトリクス'),
        ('cw', 'al', '閾値評価'),
        ('al', 'sns', 'アラーム通知'),
    ]
    _draw_diagram('Amazon CloudWatch ① – メトリクス監視 + SNS 通知構成',
                  nodes, edges, output_path)


def _diagram_cloudwatch_2(output_path: str):
    """図2: CloudWatch Alarm → EventBridge → Lambda（自動修復）"""
    nodes = [
        {'id': 'ec2', 'icon': 'ec2',              'label': 'EC2 (障害)',   'x': 1.5, 'y': 3.0},
        {'id': 'cw',  'icon': 'cloudwatch',       'label': 'CloudWatch',  'x': 4.0, 'y': 3.0},
        {'id': 'al',  'icon': 'cloudwatch_alarm', 'label': 'Alarm',       'x': 6.5, 'y': 3.0},
        {'id': 'eb',  'icon': 'eventbridge',      'label': 'EventBridge', 'x': 9.0, 'y': 3.0},
        {'id': 'fn',  'icon': 'lambda',           'label': 'Lambda (修復)','x': 11.5,'y': 3.0},
    ]
    edges = [
        ('ec2', 'cw', 'ステータス異常'),
        ('cw', 'al', '検知'),
        ('al', 'eb', 'イベント発火'),
        ('eb', 'fn', '自動修復実行'),
    ]
    _draw_diagram('Amazon CloudWatch ② – Alarm + EventBridge + Lambda 自動修復構成',
                  nodes, edges, output_path)


# ─── ECS ─────────────────────────────────────────────────────────────────────

def _diagram_ecs_1(output_path: str):
    """図1: ALB → ECS Fargate × 2 → RDS"""
    nodes = [
        {'id': 'user',  'icon': 'user',    'label': 'ユーザー',    'x': 1.0, 'y': 3.0},
        {'id': 'alb',   'icon': 'alb',     'label': 'ALB',        'x': 3.5, 'y': 3.0},
        {'id': 'task1', 'icon': 'fargate', 'label': 'Fargate #1', 'x': 7.0, 'y': 4.2},
        {'id': 'task2', 'icon': 'fargate', 'label': 'Fargate #2', 'x': 7.0, 'y': 1.8},
        {'id': 'rds',   'icon': 'rds',     'label': 'RDS',        'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('user', 'alb'),
        ('alb', 'task1'),
        ('alb', 'task2'),
        ('task1', 'rds'),
        ('task2', 'rds'),
    ]
    clusters = [
        {'label': 'ECS Cluster', 'x': 5.6, 'y': 0.8, 'w': 2.8, 'h': 4.4,
         'color': '#EAF4FB'},
    ]
    _draw_diagram('Amazon ECS ① – Fargate + ALB + RDS 構成',
                  nodes, edges, output_path, clusters=clusters)


def _diagram_ecs_2(output_path: str):
    """図2: CloudWatch → Auto Scaling → ECS タスク増減"""
    nodes = [
        {'id': 'cw',    'icon': 'cloudwatch',       'label': 'CloudWatch',   'x': 1.5, 'y': 3.0},
        {'id': 'al',    'icon': 'cloudwatch_alarm',  'label': 'Alarm',        'x': 4.0, 'y': 3.0},
        {'id': 'asg',   'icon': 'autoscaling',       'label': 'Auto Scaling', 'x': 6.5, 'y': 3.0},
        {'id': 'task1', 'icon': 'fargate',           'label': 'Task #1',      'x': 10.0,'y': 4.5},
        {'id': 'task2', 'icon': 'fargate',           'label': 'Task #2',      'x': 10.0,'y': 3.0},
        {'id': 'task3', 'icon': 'fargate',           'label': 'Task #3 (new)','x': 10.0,'y': 1.5},
    ]
    edges = [
        ('cw', 'al', 'CPU > 60%'),
        ('al', 'asg', 'スケール指示'),
        ('asg', 'task1'),
        ('asg', 'task2'),
        ('asg', 'task3', '追加'),
    ]
    _draw_diagram('Amazon ECS ② – CloudWatch + Auto Scaling によるタスクスケールアウト',
                  nodes, edges, output_path)


# ─── DynamoDB ────────────────────────────────────────────────────────────────

def _diagram_dynamodb_1(output_path: str):
    """図1: Lambda → DynamoDB → Streams → Lambda"""
    nodes = [
        {'id': 'fn1',     'icon': 'lambda',           'label': 'Lambda (Write)',   'x': 1.5, 'y': 3.0},
        {'id': 'ddb',     'icon': 'dynamodb',         'label': 'DynamoDB',         'x': 5.0, 'y': 3.0},
        {'id': 'streams', 'icon': 'dynamodb_streams', 'label': 'DynamoDB Streams', 'x': 8.5, 'y': 3.0},
        {'id': 'fn2',     'icon': 'lambda',           'label': 'Lambda (Process)', 'x': 11.5,'y': 3.0},
    ]
    edges = [
        ('fn1', 'ddb', 'PutItem'),
        ('ddb', 'streams', '変更キャプチャ'),
        ('streams', 'fn2', 'トリガー'),
    ]
    _draw_diagram('Amazon DynamoDB ① – Streams + Lambda トリガー構成',
                  nodes, edges, output_path)


def _diagram_dynamodb_2(output_path: str):
    """図2: DynamoDB + DAX キャッシュ構成"""
    nodes = [
        {'id': 'fn',  'icon': 'lambda',   'label': 'Lambda (App)', 'x': 1.5, 'y': 3.0},
        {'id': 'dax', 'icon': 'dax',      'label': 'DAX (Cache)',  'x': 5.5, 'y': 3.0},
        {'id': 'ddb', 'icon': 'dynamodb', 'label': 'DynamoDB',     'x': 9.5, 'y': 3.0},
    ]
    edges = [
        ('fn', 'dax', 'マイクロ秒レスポンス'),
        ('dax', 'ddb', 'キャッシュミス時'),
    ]
    _draw_diagram('Amazon DynamoDB ② – DAX インメモリキャッシュ構成',
                  nodes, edges, output_path, figsize=(12, 5), xlim=(0, 12), ylim=(0, 5))


# ─── CloudFront ──────────────────────────────────────────────────────────────

def _diagram_cloudfront_1(output_path: str):
    """図1: ユーザー → CloudFront → S3 / ALB"""
    nodes = [
        {'id': 'user', 'icon': 'user',       'label': 'ユーザー',   'x': 1.5, 'y': 3.0},
        {'id': 'cf',   'icon': 'cloudfront', 'label': 'CloudFront', 'x': 5.0, 'y': 3.0},
        {'id': 's3',   'icon': 's3',         'label': 'S3 (静的)',  'x': 9.5, 'y': 4.5},
        {'id': 'alb',  'icon': 'alb',        'label': 'ALB (動的)', 'x': 9.5, 'y': 1.5},
    ]
    edges = [
        ('user', 'cf'),
        ('cf', 's3', '静的コンテンツ'),
        ('cf', 'alb', '動的コンテンツ'),
    ]
    _draw_diagram('Amazon CloudFront ① – S3 + ALB オリジン構成',
                  nodes, edges, output_path)


def _diagram_cloudfront_2(output_path: str):
    """図2: WAF + CloudFront + S3"""
    nodes = [
        {'id': 'user', 'icon': 'user',       'label': 'ユーザー',   'x': 1.5, 'y': 3.0},
        {'id': 'waf',  'icon': 'waf',        'label': 'AWS WAF',    'x': 4.5, 'y': 3.0},
        {'id': 'cf',   'icon': 'cloudfront', 'label': 'CloudFront', 'x': 7.5, 'y': 3.0},
        {'id': 's3',   'icon': 's3',         'label': 'S3',         'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('user', 'waf', 'HTTPリクエスト'),
        ('waf', 'cf', '悪意あるリクエストをブロック'),
        ('cf', 's3', 'オリジンフェッチ'),
    ]
    _draw_diagram('Amazon CloudFront ② – WAF 統合によるセキュアな配信構成',
                  nodes, edges, output_path)


# ─── API Gateway ─────────────────────────────────────────────────────────────

def _diagram_api_gateway_1(output_path: str):
    """図1: クライアント → API Gateway → Lambda → DynamoDB"""
    nodes = [
        {'id': 'client', 'icon': 'user',        'label': 'クライアント', 'x': 1.5, 'y': 3.0},
        {'id': 'apigw',  'icon': 'api_gateway', 'label': 'API Gateway',  'x': 4.5, 'y': 3.0},
        {'id': 'fn',     'icon': 'lambda',      'label': 'Lambda',       'x': 7.5, 'y': 3.0},
        {'id': 'ddb',    'icon': 'dynamodb',    'label': 'DynamoDB',     'x': 10.5,'y': 3.0},
    ]
    edges = [
        ('client', 'apigw', 'REST / HTTP'),
        ('apigw', 'fn', 'Lambda統合'),
        ('fn', 'ddb', 'CRUD'),
    ]
    _draw_diagram('Amazon API Gateway ① – Lambda + DynamoDB サーバーレス構成',
                  nodes, edges, output_path)


def _diagram_api_gateway_2(output_path: str):
    """図2: Cognito 認証付き API Gateway"""
    nodes = [
        {'id': 'client',  'icon': 'user',        'label': 'クライアント',  'x': 1.0, 'y': 3.0},
        {'id': 'cognito', 'icon': 'cognito',      'label': 'Cognito',       'x': 3.5, 'y': 3.0},
        {'id': 'apigw',   'icon': 'api_gateway',  'label': 'API Gateway',   'x': 6.5, 'y': 3.0},
        {'id': 'fn',      'icon': 'lambda',       'label': 'Lambda',        'x': 9.5, 'y': 3.0},
        {'id': 'ddb',     'icon': 'dynamodb',     'label': 'DynamoDB',      'x': 12.0,'y': 3.0},
    ]
    edges = [
        ('client', 'cognito', 'ログイン'),
        ('cognito', 'apigw', 'JWT トークン'),
        ('apigw', 'fn', '認証済みリクエスト'),
        ('fn', 'ddb', 'CRUD'),
    ]
    _draw_diagram('Amazon API Gateway ② – Cognito 認証統合構成',
                  nodes, edges, output_path, figsize=(14, 6), xlim=(0, 14))


# ─── SQS ─────────────────────────────────────────────────────────────────────

def _diagram_sqs_1(output_path: str):
    """図1: Producer → SQS → Consumer Lambda"""
    nodes = [
        {'id': 'producer', 'icon': 'ec2',    'label': 'Producer (EC2)',    'x': 1.5, 'y': 3.0},
        {'id': 'sqs',      'icon': 'sqs',    'label': 'SQS キュー',        'x': 5.5, 'y': 3.0},
        {'id': 'consumer', 'icon': 'lambda', 'label': 'Consumer (Lambda)', 'x': 9.5, 'y': 3.0},
    ]
    edges = [
        ('producer', 'sqs', 'SendMessage'),
        ('sqs', 'consumer', 'トリガー'),
    ]
    _draw_diagram('Amazon SQS ① – Producer / Consumer 非同期処理構成',
                  nodes, edges, output_path, figsize=(12, 5), xlim=(0, 12), ylim=(0, 5))


def _diagram_sqs_2(output_path: str):
    """図2: SQS + デッドレターキュー（DLQ）"""
    nodes = [
        {'id': 'producer', 'icon': 'ec2',    'label': 'Producer',  'x': 1.5, 'y': 3.0},
        {'id': 'sqs',      'icon': 'sqs',    'label': 'SQS (本キュー)', 'x': 4.5, 'y': 3.0},
        {'id': 'fn',       'icon': 'lambda', 'label': 'Lambda',    'x': 7.5, 'y': 4.5},
        {'id': 'dlq',      'icon': 'sqs',    'label': 'DLQ',       'x': 7.5, 'y': 1.5},
        {'id': 'alert',    'icon': 'sns',    'label': 'SNS (通知)', 'x': 10.5,'y': 1.5},
    ]
    edges = [
        ('producer', 'sqs', 'SendMessage'),
        ('sqs', 'fn', '正常処理'),
        ('sqs', 'dlq', '処理失敗（3回）'),
        ('dlq', 'alert', 'アラート通知'),
    ]
    _draw_diagram('Amazon SQS ② – デッドレターキュー（DLQ）による障害対応構成',
                  nodes, edges, output_path)


# ─── Bedrock ─────────────────────────────────────────────────────────────────

def _diagram_bedrock_1(output_path: str):
    """図1: ユーザー → API Gateway → Lambda → Bedrock"""
    nodes = [
        {'id': 'user',    'icon': 'user',        'label': 'ユーザー',          'x': 1.5, 'y': 3.0},
        {'id': 'apigw',   'icon': 'api_gateway', 'label': 'API Gateway',       'x': 4.5, 'y': 3.0},
        {'id': 'fn',      'icon': 'lambda',      'label': 'Lambda',            'x': 7.5, 'y': 3.0},
        {'id': 'bedrock', 'icon': 'bedrock',     'label': 'Bedrock (Claude)',   'x': 10.5, 'y': 3.0},
    ]
    edges = [
        ('user', 'apigw', 'プロンプト送信'),
        ('apigw', 'fn', 'リクエスト'),
        ('fn', 'bedrock', 'InvokeModel'),
    ]
    _draw_diagram('Amazon Bedrock ① – API Gateway + Lambda 経由のテキスト生成構成',
                  nodes, edges, output_path)


def _diagram_bedrock_2(output_path: str):
    """図2: Bedrock Knowledge Base + S3 RAG構成（ラベル重複回避レイアウト）"""
    nodes = [
        {'id': 'user',   'icon': 'user',    'label': 'ユーザー',          'x': 1.5, 'y': 3.0},
        {'id': 'fn',     'icon': 'lambda',  'label': 'Lambda',            'x': 4.5, 'y': 3.0},
        {'id': 'kb',     'icon': 'bedrock', 'label': 'Knowledge Base',    'x': 7.0, 'y': 4.5},
        {'id': 's3',     'icon': 's3',      'label': 'S3 (ドキュメント)', 'x': 7.0, 'y': 1.5},
        {'id': 'claude', 'icon': 'bedrock', 'label': 'Bedrock Claude',    'x': 12.0, 'y': 3.0},
    ]
    edges = [
        ('user', 'fn', '質問'),
        ('fn', 'kb', 'ベクター検索'),
        ('kb', 's3', '参照'),
        ('fn', 'claude', 'RAGプロンプト'),
    ]
    _draw_diagram('Amazon Bedrock ② – Knowledge Base を使った RAG 構成',
                  nodes, edges, output_path, figsize=(14, 6), xlim=(0, 14))


# ─── SageMaker ────────────────────────────────────────────────────────────────

def _diagram_sagemaker_1(output_path: str):
    """図1: データ → S3 → SageMaker Training Job → S3(モデル) → Endpoint"""
    nodes = [
        {'id': 'user',  'icon': 'user',      'label': 'データサイエンティスト', 'x': 1.5, 'y': 3.0},
        {'id': 's3in',  'icon': 's3',        'label': 'S3 (学習データ)',        'x': 4.5, 'y': 4.2},
        {'id': 'train', 'icon': 'sagemaker', 'label': 'Training Job',           'x': 7.5, 'y': 3.0},
        {'id': 's3out', 'icon': 's3',        'label': 'S3 (モデル)',            'x': 10.5, 'y': 4.2},
        {'id': 'ep',    'icon': 'sagemaker', 'label': 'Endpoint',               'x': 10.5, 'y': 1.8},
    ]
    edges = [
        ('user', 's3in', 'アップロード'),
        ('s3in', 'train', '入力'),
        ('train', 's3out', 'モデル保存'),
        ('s3out', 'ep', 'デプロイ'),
    ]
    _draw_diagram('Amazon SageMaker ① – 学習 → モデル保存 → エンドポイントデプロイ構成',
                  nodes, edges, output_path)


def _diagram_sagemaker_2(output_path: str):
    """図2: クライアント → API Gateway → Lambda → SageMaker Endpoint（推論API）"""
    nodes = [
        {'id': 'client', 'icon': 'user',        'label': 'クライアント',       'x': 1.5, 'y': 3.0},
        {'id': 'apigw',  'icon': 'api_gateway', 'label': 'API Gateway',        'x': 4.5, 'y': 3.0},
        {'id': 'fn',     'icon': 'lambda',      'label': 'Lambda',             'x': 7.5, 'y': 3.0},
        {'id': 'ep',     'icon': 'sagemaker',   'label': 'SageMaker Endpoint', 'x': 10.5, 'y': 3.0},
    ]
    edges = [
        ('client', 'apigw', 'REST API'),
        ('apigw', 'fn', 'プロキシ'),
        ('fn', 'ep', '推論リクエスト'),
    ]
    _draw_diagram('Amazon SageMaker ② – API Gateway 経由の推論エンドポイント公開構成',
                  nodes, edges, output_path)


# ─── Rekognition ──────────────────────────────────────────────────────────────

def _diagram_rekognition_1(output_path: str):
    """図1: S3アップロード → Lambda → Rekognition → DynamoDB（バッチ画像解析）"""
    nodes = [
        {'id': 'user',  'icon': 'user',        'label': 'ユーザー',    'x': 1.5, 'y': 3.0},
        {'id': 's3',    'icon': 's3',          'label': 'S3 (画像)',   'x': 4.5, 'y': 3.0},
        {'id': 'fn',    'icon': 'lambda',      'label': 'Lambda',      'x': 7.5, 'y': 4.2},
        {'id': 'rekog', 'icon': 'rekognition', 'label': 'Rekognition', 'x': 7.5, 'y': 1.8},
        {'id': 'ddb',   'icon': 'dynamodb',    'label': 'DynamoDB',    'x': 11.0, 'y': 3.0},
    ]
    edges = [
        ('user', 's3', '画像アップロード'),
        ('s3', 'fn', 'S3イベント'),
        ('fn', 'rekog', 'DetectLabels'),
        ('fn', 'ddb', '検出結果保存'),
    ]
    _draw_diagram('Amazon Rekognition ① – S3 + Lambda による画像解析パイプライン',
                  nodes, edges, output_path)


def _diagram_rekognition_2(output_path: str):
    """図2: モバイル → API Gateway → Lambda → Rekognition（リアルタイム顔認証）"""
    nodes = [
        {'id': 'client', 'icon': 'user',        'label': 'モバイルアプリ', 'x': 1.5, 'y': 3.0},
        {'id': 'apigw',  'icon': 'api_gateway', 'label': 'API Gateway',    'x': 4.5, 'y': 3.0},
        {'id': 'fn',     'icon': 'lambda',      'label': 'Lambda',         'x': 7.5, 'y': 3.0},
        {'id': 'rekog',  'icon': 'rekognition', 'label': 'Rekognition',    'x': 10.5, 'y': 3.0},
    ]
    edges = [
        ('client', 'apigw', '画像データ'),
        ('apigw', 'fn', 'プロキシ'),
        ('fn', 'rekog', 'CompareFaces'),
    ]
    _draw_diagram('Amazon Rekognition ② – API Gateway 経由のリアルタイム顔認証構成',
                  nodes, edges, output_path)


# ─── Textract ─────────────────────────────────────────────────────────────────

def _diagram_textract_1(output_path: str):
    """図1: S3 → Textract（非同期）→ SNS → Lambda → DynamoDB"""
    nodes = [
        {'id': 'user',     'icon': 'user',     'label': 'ユーザー',     'x': 1.5, 'y': 3.0},
        {'id': 's3',       'icon': 's3',       'label': 'S3 (PDF)',     'x': 4.5, 'y': 3.0},
        {'id': 'textract', 'icon': 'textract', 'label': 'Textract',     'x': 7.5, 'y': 3.0},
        {'id': 'fn',       'icon': 'lambda',   'label': 'Lambda',       'x': 10.5, 'y': 4.2},
        {'id': 'ddb',      'icon': 'dynamodb', 'label': 'DynamoDB',     'x': 10.5, 'y': 1.8},
    ]
    edges = [
        ('user', 's3', 'PDF/画像アップロード'),
        ('s3', 'textract', 'StartDocumentAnalysis'),
        ('textract', 'fn', 'SNS完了通知'),
        ('fn', 'ddb', '抽出データ保存'),
    ]
    _draw_diagram('Amazon Textract ① – S3 + Textract 非同期文書解析パイプライン',
                  nodes, edges, output_path)


def _diagram_textract_2(output_path: str):
    """図2: Textract → Lambda → Comprehend 感情分析 + S3保存"""
    nodes = [
        {'id': 's3in',      'icon': 's3',        'label': 'S3 (文書)',   'x': 1.5, 'y': 3.0},
        {'id': 'textract',  'icon': 'textract',  'label': 'Textract',    'x': 4.5, 'y': 3.0},
        {'id': 'fn',        'icon': 'lambda',    'label': 'Lambda',      'x': 7.5, 'y': 3.0},
        {'id': 'comprehend','icon': 'comprehend','label': 'Comprehend',  'x': 10.5, 'y': 4.2},
        {'id': 's3out',     'icon': 's3',        'label': 'S3 (結果)',   'x': 10.5, 'y': 1.8},
    ]
    edges = [
        ('s3in', 'textract', 'テキスト抽出'),
        ('textract', 'fn', '抽出テキスト'),
        ('fn', 'comprehend', '感情分析'),
        ('fn', 's3out', '結果保存'),
    ]
    _draw_diagram('Amazon Textract ② – Textract + Comprehend テキスト解析パイプライン',
                  nodes, edges, output_path)


# ─── Step Functions ───────────────────────────────────────────────────────────

def _diagram_step_functions_1(output_path: str):
    """図1: EventBridge → Step Functions → Lambda 順次実行 → DynamoDB"""
    nodes = [
        {'id': 'trigger', 'icon': 'eventbridge',    'label': 'EventBridge',   'x': 1.5, 'y': 3.0},
        {'id': 'sf',      'icon': 'step_functions', 'label': 'Step Functions', 'x': 4.5, 'y': 3.0},
        {'id': 'fn1',     'icon': 'lambda',         'label': 'Lambda ①',     'x': 8.0, 'y': 4.5},
        {'id': 'fn2',     'icon': 'lambda',         'label': 'Lambda ②',     'x': 8.0, 'y': 3.0},
        {'id': 'fn3',     'icon': 'lambda',         'label': 'Lambda ③',     'x': 8.0, 'y': 1.5},
        {'id': 'ddb',     'icon': 'dynamodb',       'label': 'DynamoDB',      'x': 11.5, 'y': 3.0},
    ]
    edges = [
        ('trigger', 'sf', 'スケジュール'),
        ('sf', 'fn1', 'Step 1'),
        ('sf', 'fn2', 'Step 2'),
        ('sf', 'fn3', 'Step 3'),
        ('fn1', 'ddb'),
        ('fn2', 'ddb'),
        ('fn3', 'ddb'),
    ]
    _draw_diagram('AWS Step Functions ① – 複数 Lambda の順次実行ワークフロー構成',
                  nodes, edges, output_path)


def _diagram_step_functions_2(output_path: str):
    """図2: Step Functions エラーハンドリング（Retry / Catch）→ SNS通知"""
    nodes = [
        {'id': 'sf',    'icon': 'step_functions', 'label': 'Step Functions',   'x': 2.0, 'y': 3.0},
        {'id': 'fn',    'icon': 'lambda',         'label': 'Lambda (Task)',     'x': 5.5, 'y': 3.0},
        {'id': 'retry', 'icon': 'lambda',         'label': 'Retry (3回)',       'x': 8.5, 'y': 4.5},
        {'id': 'catch', 'icon': 'sns',            'label': 'SNS (失敗通知)',    'x': 8.5, 'y': 1.5},
        {'id': 'sqs',   'icon': 'sqs',            'label': 'SQS (DLQ)',         'x': 11.5, 'y': 1.5},
    ]
    edges = [
        ('sf', 'fn', '実行'),
        ('fn', 'retry', 'エラー → Retry'),
        ('fn', 'catch', '最終失敗 → Catch'),
        ('catch', 'sqs', 'キューイング'),
    ]
    _draw_diagram('AWS Step Functions ② – エラーハンドリング（Retry / Catch）構成',
                  nodes, edges, output_path)


# ─── SNS ─────────────────────────────────────────────────────────────────────

def _diagram_sns_1(output_path: str):
    """図1: Publisher → SNS Topic → SQS / Lambda / Email（ファンアウト）"""
    nodes = [
        {'id': 'pub',   'icon': 'lambda', 'label': 'Publisher (Lambda)',  'x': 1.5, 'y': 3.0},
        {'id': 'sns',   'icon': 'sns',    'label': 'SNS Topic',           'x': 5.0, 'y': 3.0},
        {'id': 'sqs',   'icon': 'sqs',    'label': 'SQS キュー',          'x': 9.0, 'y': 4.5},
        {'id': 'fn',    'icon': 'lambda', 'label': 'Lambda',              'x': 9.0, 'y': 3.0},
        {'id': 'email', 'icon': 'ses',    'label': 'メール (SES)',        'x': 9.0, 'y': 1.5},
    ]
    edges = [
        ('pub', 'sns', 'Publish'),
        ('sns', 'sqs', 'サブスクライブ'),
        ('sns', 'fn', 'サブスクライブ'),
        ('sns', 'email', 'サブスクライブ'),
    ]
    _draw_diagram('Amazon SNS ① – Pub/Sub ファンアウトによる複数サブスクライバー通知構成',
                  nodes, edges, output_path)


def _diagram_sns_2(output_path: str):
    """図2: CloudWatch Alarm → SNS → Email + Lambda（障害通知と自動対応）"""
    nodes = [
        {'id': 'cw',    'icon': 'cloudwatch',       'label': 'CloudWatch',     'x': 1.5, 'y': 3.0},
        {'id': 'alarm', 'icon': 'cloudwatch_alarm', 'label': 'Alarm',          'x': 4.5, 'y': 3.0},
        {'id': 'sns',   'icon': 'sns',              'label': 'SNS Topic',      'x': 7.5, 'y': 3.0},
        {'id': 'email', 'icon': 'ses',              'label': 'メール通知',     'x': 10.5, 'y': 4.2},
        {'id': 'fn',    'icon': 'lambda',           'label': 'Lambda (自動対応)', 'x': 10.5, 'y': 1.8},
    ]
    edges = [
        ('cw', 'alarm', 'CPU > 80%'),
        ('alarm', 'sns', 'アラーム発火'),
        ('sns', 'email', '担当者に通知'),
        ('sns', 'fn', '自動対応実行'),
    ]
    _draw_diagram('Amazon SNS ② – CloudWatch Alarm + SNS による障害通知と自動対応構成',
                  nodes, edges, output_path)


# ─── ElastiCache ─────────────────────────────────────────────────────────────

def _diagram_elasticache_1(output_path: str):
    """図1: Lambda → ElastiCache (Redis) → RDS（キャッシュ構成）"""
    nodes = [
        {'id': 'user',  'icon': 'user',        'label': 'ユーザー',             'x': 1.5, 'y': 3.0},
        {'id': 'fn',    'icon': 'lambda',      'label': 'Lambda (App)',         'x': 4.5, 'y': 3.0},
        {'id': 'cache', 'icon': 'elasticache', 'label': 'ElastiCache (Redis)', 'x': 8.0, 'y': 4.2},
        {'id': 'rds',   'icon': 'rds',         'label': 'RDS',                  'x': 8.0, 'y': 1.8},
    ]
    edges = [
        ('user', 'fn', 'リクエスト'),
        ('fn', 'cache', 'キャッシュ参照'),
        ('fn', 'rds', 'キャッシュミス時'),
    ]
    _draw_diagram('Amazon ElastiCache ① – Lambda + Redis キャッシュ + RDS 構成',
                  nodes, edges, output_path)


def _diagram_elasticache_2(output_path: str):
    """図2: ALB → EC2 × 2 → ElastiCache（セッション共有）"""
    nodes = [
        {'id': 'user',  'icon': 'user',        'label': 'ユーザー',               'x': 1.5, 'y': 3.0},
        {'id': 'alb',   'icon': 'alb',         'label': 'ALB',                    'x': 4.0, 'y': 3.0},
        {'id': 'ec2a',  'icon': 'ec2',         'label': 'EC2 #1',                 'x': 7.0, 'y': 4.2},
        {'id': 'ec2b',  'icon': 'ec2',         'label': 'EC2 #2',                 'x': 7.0, 'y': 1.8},
        {'id': 'cache', 'icon': 'elasticache', 'label': 'ElastiCache (セッション)', 'x': 10.5, 'y': 3.0},
    ]
    edges = [
        ('user', 'alb'),
        ('alb', 'ec2a'),
        ('alb', 'ec2b'),
        ('ec2a', 'cache', 'セッション読み書き'),
        ('ec2b', 'cache', 'セッション読み書き'),
    ]
    _draw_diagram('Amazon ElastiCache ② – ALB + EC2 複数台構成でのセッション共有',
                  nodes, edges, output_path)


# ─── Route 53 ────────────────────────────────────────────────────────────────

def _diagram_route53_1(output_path: str):
    """図1: Route 53 フェイルオーバールーティング"""
    nodes = [
        {'id': 'user',    'icon': 'user',    'label': 'ユーザー',       'x': 1.5, 'y': 3.0},
        {'id': 'r53',     'icon': 'route53', 'label': 'Route 53',       'x': 4.5, 'y': 3.0},
        {'id': 'primary', 'icon': 'alb',    'label': 'Primary (AZ-a)', 'x': 8.5, 'y': 4.5},
        {'id': 'standby', 'icon': 'alb',    'label': 'Standby (AZ-b)', 'x': 8.5, 'y': 1.5},
    ]
    edges = [
        ('user', 'r53', 'DNS クエリ'),
        ('r53', 'primary', 'ヘルスチェックOK'),
        ('r53', 'standby', 'フェイルオーバー'),
    ]
    _draw_diagram('Amazon Route 53 ① – フェイルオーバールーティング構成',
                  nodes, edges, output_path)


def _diagram_route53_2(output_path: str):
    """図2: Route 53 → CloudFront → S3 / ALB（エイリアスレコード）"""
    nodes = [
        {'id': 'user', 'icon': 'user',       'label': 'ユーザー',   'x': 1.5, 'y': 3.0},
        {'id': 'r53',  'icon': 'route53',    'label': 'Route 53',   'x': 4.5, 'y': 3.0},
        {'id': 'cf',   'icon': 'cloudfront', 'label': 'CloudFront', 'x': 7.5, 'y': 3.0},
        {'id': 's3',   'icon': 's3',         'label': 'S3 (静的)',  'x': 11.0, 'y': 4.5},
        {'id': 'alb',  'icon': 'alb',        'label': 'ALB (動的)', 'x': 11.0, 'y': 1.5},
    ]
    edges = [
        ('user', 'r53', 'DNS解決'),
        ('r53', 'cf', 'エイリアスレコード'),
        ('cf', 's3', '静的コンテンツ'),
        ('cf', 'alb', '動的コンテンツ'),
    ]
    _draw_diagram('Amazon Route 53 ② – CloudFront + S3 / ALB オリジン構成',
                  nodes, edges, output_path)


# ─── Kinesis ─────────────────────────────────────────────────────────────────

def _diagram_kinesis_1(output_path: str):
    """図1: IoT/EC2 → Kinesis Data Streams → Lambda → DynamoDB（リアルタイム処理）"""
    nodes = [
        {'id': 'iot',  'icon': 'ec2',      'label': 'IoT / EC2 (Producer)',  'x': 1.5, 'y': 3.0},
        {'id': 'kds',  'icon': 'kinesis',  'label': 'Kinesis Data Streams',  'x': 5.0, 'y': 3.0},
        {'id': 'fn',   'icon': 'lambda',   'label': 'Lambda (Consumer)',     'x': 8.5, 'y': 3.0},
        {'id': 'ddb',  'icon': 'dynamodb', 'label': 'DynamoDB',              'x': 11.5, 'y': 3.0},
    ]
    edges = [
        ('iot', 'kds', 'PutRecord'),
        ('kds', 'fn', 'トリガー（シャード）'),
        ('fn', 'ddb', 'リアルタイム保存'),
    ]
    _draw_diagram('Amazon Kinesis ① – Data Streams + Lambda リアルタイム処理構成',
                  nodes, edges, output_path)


def _diagram_kinesis_2(output_path: str):
    """図2: アプリ → Kinesis Firehose → S3 → Athena 分析（データレイク）"""
    nodes = [
        {'id': 'app',    'icon': 'ec2',     'label': 'アプリ (Producer)',  'x': 1.5, 'y': 3.0},
        {'id': 'fh',     'icon': 'kinesis', 'label': 'Kinesis Firehose',   'x': 5.0, 'y': 3.0},
        {'id': 's3',     'icon': 's3',      'label': 'S3 (データレイク)', 'x': 8.5, 'y': 3.0},
        {'id': 'athena', 'icon': 'athena',  'label': 'Athena (分析)',      'x': 11.5, 'y': 3.0},
    ]
    edges = [
        ('app', 'fh', 'ログ/イベント'),
        ('fh', 's3', '自動バッファリング'),
        ('s3', 'athena', 'SQL クエリ'),
    ]
    _draw_diagram('Amazon Kinesis ② – Firehose + S3 + Athena データ分析パイプライン',
                  nodes, edges, output_path)


# ─── CloudTrail ──────────────────────────────────────────────────────────────

def _diagram_cloudtrail_1(output_path: str):
    """図1: AWS操作 → CloudTrail → S3（証跡）+ CloudWatch Logs"""
    nodes = [
        {'id': 'user', 'icon': 'user',       'label': '管理者 / 開発者',  'x': 1.5, 'y': 3.0},
        {'id': 'ct',   'icon': 'cloudtrail', 'label': 'CloudTrail',       'x': 5.0, 'y': 3.0},
        {'id': 's3',   'icon': 's3',         'label': 'S3 (証跡ログ)',    'x': 9.0, 'y': 4.2},
        {'id': 'cw',   'icon': 'cloudwatch', 'label': 'CloudWatch Logs',  'x': 9.0, 'y': 1.8},
    ]
    edges = [
        ('user', 'ct', 'AWSコンソール/CLI操作'),
        ('ct', 's3', 'ログ保存（証跡）'),
        ('ct', 'cw', 'リアルタイム配信'),
    ]
    _draw_diagram('AWS CloudTrail ① – 操作ログの S3 保存 + CloudWatch Logs 配信構成',
                  nodes, edges, output_path)


def _diagram_cloudtrail_2(output_path: str):
    """図2: CloudTrail → EventBridge → Lambda → SNS/IAM（セキュリティ自動対応）"""
    nodes = [
        {'id': 'ct',  'icon': 'cloudtrail',  'label': 'CloudTrail',         'x': 1.5, 'y': 3.0},
        {'id': 'eb',  'icon': 'eventbridge', 'label': 'EventBridge',        'x': 4.5, 'y': 3.0},
        {'id': 'fn',  'icon': 'lambda',      'label': 'Lambda (自動対応)',  'x': 7.5, 'y': 3.0},
        {'id': 'sns', 'icon': 'sns',         'label': 'SNS (セキュリティ通知)', 'x': 10.5, 'y': 4.2},
        {'id': 'iam', 'icon': 'iam',         'label': 'IAM (権限取消し)',   'x': 10.5, 'y': 1.8},
    ]
    edges = [
        ('ct', 'eb', '不審なAPI呼び出し'),
        ('eb', 'fn', 'ルールマッチ'),
        ('fn', 'sns', 'アラート通知'),
        ('fn', 'iam', '自動権限取消し'),
    ]
    _draw_diagram('AWS CloudTrail ② – EventBridge + Lambda によるセキュリティ自動対応構成',
                  nodes, edges, output_path)


# ─── パブリックインターフェース ───────────────────────────────────────────────────

_GENERATORS = {
    'ec2':         [_diagram_ec2_1,         _diagram_ec2_2],
    's3':          [_diagram_s3_1,          _diagram_s3_2],
    'iam':         [_diagram_iam_1,         _diagram_iam_2],
    'vpc':         [_diagram_vpc_1,         _diagram_vpc_2],
    'rds':         [_diagram_rds_1,         _diagram_rds_2],
    'lambda':      [_diagram_lambda_1,      _diagram_lambda_2],
    'cloudwatch':  [_diagram_cloudwatch_1,  _diagram_cloudwatch_2],
    'ecs':         [_diagram_ecs_1,         _diagram_ecs_2],
    'dynamodb':    [_diagram_dynamodb_1,    _diagram_dynamodb_2],
    'cloudfront':  [_diagram_cloudfront_1,  _diagram_cloudfront_2],
    'api_gateway':    [_diagram_api_gateway_1,    _diagram_api_gateway_2],
    'sqs':            [_diagram_sqs_1,            _diagram_sqs_2],
    # AI / ML 系
    'bedrock':        [_diagram_bedrock_1,        _diagram_bedrock_2],
    'sagemaker':      [_diagram_sagemaker_1,      _diagram_sagemaker_2],
    'rekognition':    [_diagram_rekognition_1,    _diagram_rekognition_2],
    'textract':       [_diagram_textract_1,       _diagram_textract_2],
    # その他主要サービス
    'step_functions': [_diagram_step_functions_1, _diagram_step_functions_2],
    'sns':            [_diagram_sns_1,            _diagram_sns_2],
    'elasticache':    [_diagram_elasticache_1,    _diagram_elasticache_2],
    'route53':        [_diagram_route53_1,        _diagram_route53_2],
    'kinesis':        [_diagram_kinesis_1,        _diagram_kinesis_2],
    'cloudtrail':     [_diagram_cloudtrail_1,     _diagram_cloudtrail_2],
}


def generate_diagrams(topic_id: str, base_path: str) -> list[str]:
    """
    指定トピックの構成図 PNG を生成してパスのリストを返す（最大2枚）。

    Args:
        topic_id : 'ec2' / 's3' / 'iam' など
        base_path: 出力先パスのベース（拡張子なし）
                   例: '/tmp/20240101_ec2_diagram'
                   → '/tmp/20240101_ec2_diagram_1.png'
                      '/tmp/20240101_ec2_diagram_2.png' を生成
    Returns:
        生成された PNG パスのリスト（失敗した図はスキップ）
    """
    generators = _GENERATORS.get(topic_id)
    if generators is None:
        print(f'[diagram_generator] 未対応トピック: {topic_id}')
        return []

    paths = []
    for i, generator in enumerate(generators, start=1):
        output_path = f'{base_path}_{i}.png'
        try:
            generator(output_path)
            if os.path.exists(output_path):
                paths.append(output_path)
        except Exception as e:
            print(f'[diagram_generator] {topic_id} 図{i} の生成に失敗: {e}')

    return paths
