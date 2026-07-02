"""
中級者向けAWSアーキテクチャ図を生成するモジュール。
複合サービス構成に対応したフルシステム構成図（図1）と
データフロー図（図2）の2種類を各トピックで生成する。
matplotlib + AWS公式アイコン（PNGバンドル）使用。Graphviz依存なし。
"""
import matplotlib
matplotlib.use('Agg')

import functools
import os
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = '/tmp/aws_icons'
_OFFICIAL_ICON_DIR = os.path.join(_SCRIPT_DIR, '..', '..', 'images', 'AWS-icon')

_SVC = 'Architecture-Service-Icons_07312025'
_GRP = 'Architecture-Group-Icons_07312025'

_OFFICIAL_ICON_MAP: dict[str, str] = {
    # ── サービスアイコン（64px） ──
    'eventbridge': f'{_SVC}/Arch_App-Integration/64/Arch_Amazon-EventBridge_64.png',
    'lambda':      f'{_SVC}/Arch_Compute/64/Arch_AWS-Lambda_64.png',
    'bedrock':     f'{_SVC}/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock_64.png',
    'ssm':         f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Systems-Manager_64.png',
    'cloudwatch':  f'{_SVC}/Arch_Management-Governance/64/Arch_Amazon-CloudWatch_64.png',
    'sqs':         f'{_SVC}/Arch_App-Integration/64/Arch_Amazon-Simple-Queue-Service_64.png',
    's3':          f'{_SVC}/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.png',
    'ses':         f'{_SVC}/Arch_Business-Applications/64/Arch_Amazon-Simple-Email-Service_64.png',
    'cloudfront':  f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-CloudFront_64.png',
    'acm':         f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Certificate-Manager_64.png',
    'api_gateway': f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-API-Gateway_64.png',
    'dynamodb':    f'{_SVC}/Arch_Database/64/Arch_Amazon-DynamoDB_64.png',
    # ── Compute ──
    'ec2':              f'{_SVC}/Arch_Compute/64/Arch_Amazon-EC2_64.png',
    'ecs':              f'{_SVC}/Arch_Containers/64/Arch_Amazon-Elastic-Container-Service_64.png',
    'ecr':              f'{_SVC}/Arch_Containers/64/Arch_Amazon-Elastic-Container-Registry_64.png',
    'compute_optimizer':f'{_SVC}/Arch_Compute/64/Arch_AWS-Compute-Optimizer_64.png',
    # ── Storage ──
    'backup':           f'{_SVC}/Arch_Storage/64/Arch_AWS-Backup_64.png',
    # ── Database ──
    'rds':              f'{_SVC}/Arch_Database/64/Arch_Amazon-RDS_64.png',
    'opensearch':       f'{_SVC}/Arch_Analytics/64/Arch_Amazon-OpenSearch-Service_64.png',
    # ── Networking ──
    'alb':              f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Elastic-Load-Balancing_64.png',
    'route53':          f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-Route-53_64.png',
    'waf':              f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-WAF_64.png',
    # ── Security & Identity ──
    'iam':              f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Identity-and-Access-Management_64.png',
    'guardduty':        f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_Amazon-GuardDuty_64.png',
    'security_hub':     f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Security-Hub_64.png',
    'shield':           f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Shield_64.png',
    'secrets_manager':  f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Secrets-Manager_64.png',
    'control_tower':    f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Control-Tower_64.png',
    'organizations':    f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Organizations_64.png',
    # ── Developer Tools ──
    'codepipeline':     f'{_SVC}/Arch_Developer-Tools/64/Arch_AWS-CodePipeline_64.png',
    'codebuild':        f'{_SVC}/Arch_Developer-Tools/64/Arch_AWS-CodeBuild_64.png',
    'codecommit':       f'{_SVC}/Arch_Developer-Tools/64/Arch_AWS-CodeCommit_64.png',
    'codedeploy':       f'{_SVC}/Arch_Developer-Tools/64/Arch_AWS-CodeDeploy_64.png',
    'xray':             f'{_SVC}/Arch_Developer-Tools/64/Arch_AWS-X-Ray_64.png',
    # ── Analytics ──
    'kinesis':          f'{_SVC}/Arch_Analytics/64/Arch_Amazon-Kinesis_64.png',
    'athena':           f'{_SVC}/Arch_Analytics/64/Arch_Amazon-Athena_64.png',
    'glue':             f'{_SVC}/Arch_Analytics/64/Arch_AWS-Glue_64.png',
    'lake_formation':   f'{_SVC}/Arch_Analytics/64/Arch_AWS-Lake-Formation_64.png',
    'quicksight':       f'{_SVC}/Arch_Analytics/64/Arch_Amazon-QuickSight_64.png',
    'sagemaker':        f'{_SVC}/Arch_Analytics/64/Arch_Amazon-SageMaker_64.png',
    # ── Management & Governance ──
    'cloudtrail':       f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-CloudTrail_64.png',
    'cloudformation':   f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-CloudFormation_64.png',
    'config':           f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Config_64.png',
    'service_catalog':  f'{_SVC}/Arch_Management-Governance/64/Arch_AWS-Service-Catalog_64.png',
    # ── Messaging ──
    'sns':              f'{_SVC}/Arch_App-Integration/64/Arch_Amazon-Simple-Notification-Service_64.png',
    'step_functions':   f'{_SVC}/Arch_App-Integration/64/Arch_AWS-Step-Functions_64.png',
    # ── Cost Management ──
    'cost_explorer':    f'{_SVC}/Arch_Cloud-Financial-Management/64/Arch_AWS-Cost-Explorer_64.png',
    'budgets':          f'{_SVC}/Arch_Cloud-Financial-Management/64/Arch_AWS-Budgets_64.png',
    # ── グループアイコン（クラスター枠用・32px） ──
    'vpc':            f'{_GRP}/Virtual-private-cloud-VPC_32.png',
    'region':         f'{_GRP}/Region_32.png',
    'public_subnet':  f'{_GRP}/Public-subnet_32.png',
    'private_subnet': f'{_GRP}/Private-subnet_32.png',
    'aws_cloud':      f'{_GRP}/AWS-Cloud_32.png',
    'aws_cloud_logo': f'{_GRP}/AWS-Cloud-logo_32.png',
}


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


_PAD_H_OUTER   = 1.1   # 外枠 水平余白（auto-paddingの閾値1.0より大きく設定）
_PAD_TOP_OUTER = 1.2   # 外枠 上余白（クラスターアイコン・ラベル含む、閾値1.1より大）
_PAD_BOT_OUTER = 2.0   # 外枠 下余白（ノードラベルが下に伸びる分、閾値1.6より大）


def _outer_cluster(
    nodes: list,
    inner_clusters: list = None,
    label: str = 'ap-northeast-1',
    icon: str = 'region',
    color: str = '#F0F4F8',
    edgecolor: str = '#4A7FA5',
) -> dict:
    """全ノードと内部クラスターを包む最外枠クラスターを auto-padding が発火しない座標で生成する。"""
    xs = [n['x'] for n in nodes]
    ys = [n['y'] for n in nodes]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    for c in (inner_clusters or []):
        x_min = min(x_min, c['x'])
        x_max = max(x_max, c['x'] + c['w'])
        y_min = min(y_min, c['y'])
        y_max = max(y_max, c['y'] + c['h'])
    cx = max(0.4, x_min - _PAD_H_OUTER)
    cy = y_min - _PAD_BOT_OUTER
    cw = x_max + _PAD_H_OUTER - cx
    ch = y_max + _PAD_TOP_OUTER - cy
    return {'label': label, 'icon': icon, 'x': cx, 'y': cy, 'w': cw, 'h': ch,
            'color': color, 'edgecolor': edgecolor, 'linewidth': 2.0,
            'skip_autopad': True}


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

_BUNDLED_ICON_DIR = os.path.join(_SCRIPT_DIR, 'aws_icons')


@functools.lru_cache(maxsize=128)
def _load_icon(name: str):
    if not name:
        return None
    # 1. ローカル開発環境: 公式July 2025 PNGを使用
    if name in _OFFICIAL_ICON_MAP:
        path = os.path.join(_OFFICIAL_ICON_DIR, _OFFICIAL_ICON_MAP[name])
        if os.path.exists(path):
            try:
                return mpimg.imread(path)
            except Exception:
                pass
    # 2. Lambda: ZIPにバンドルされたアイコンを使用（/var/task/aws_icons/）
    bundled = os.path.join(_BUNDLED_ICON_DIR, f'{name}.png')
    if os.path.exists(bundled):
        try:
            return mpimg.imread(bundled)
        except Exception:
            pass
    # 3. 未登録アイコン: /tmp/aws_icons/ に色付きテキストボックスを生成
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
    figsize: tuple = None,
    xlim: tuple = (0, 14),
    ylim: tuple = None,
    clusters: list = None,
):
    """
    nodes   : [{'id': str, 'icon': str|None, 'label': str, 'x': float, 'y': float}]
    edges   : [(from_id, to_id) | (from_id, to_id, label)]
    clusters: [{'label': str, 'x': float, 'y': float, 'w': float, 'h': float, 'color': str}]
    ylim    : None で自動計算（ノード・クラスターの範囲から余白付きで決定）
    figsize : None で xlim/ylim の比率から自動計算
    """
    # ── クラスター枠がノードと重ならないよう自動パディング調整 ──────────────
    # ルール: アイコン端(HALF=0.55)から枠まで水平0.45・上0.55・下1.05以上確保
    # skip_autopad=True の外枠クラスターは対象外（_outer_cluster が正確に計算済み）
    _ICON_HALF   = 0.55
    _PAD_H       = _ICON_HALF + 0.45   # 水平マージン（アイコン端＋余白）
    _PAD_TOP     = _ICON_HALF + 0.55   # 上マージン（クラスターラベル分含む）
    _PAD_BOT     = _ICON_HALF + 1.05   # 下マージン（ノードラベルが下に伸びる分含む）

    for cl in (clusters or []):
        if cl.get('skip_autopad'):
            continue
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

    # ylim 自動計算（auto-padding 後のクラスター座標を使用）
    if ylim is None:
        ys = [n['y'] for n in nodes]
        y_lo = min(ys)
        y_hi = max(ys)
        for c in (clusters or []):
            y_lo = min(y_lo, c['y'])
            y_hi = max(y_hi, c['y'] + c['h'])
        y_lo = y_lo - 0.4              # アイコン下端 + ラベル分（クランプなし）
        y_hi = y_hi + 0.8              # アイコン上端 + クラスターラベル分
        if y_hi - y_lo < 4.0:          # 最低幅を確保
            mid = (y_lo + y_hi) / 2
            y_lo, y_hi = mid - 2.0, mid + 2.0
        ylim = (y_lo, y_hi)

    # figsize 自動計算（xlim/ylim 比率に合わせる）
    if figsize is None:
        xlim_range = xlim[1] - xlim[0]
        ylim_range = ylim[1] - ylim[0]
        if xlim_range <= 0:
            xlim_range = 14.0
        fig_w = 14.0
        fig_h = round(fig_w * ylim_range / xlim_range, 1)
        figsize = (fig_w, fig_h)

    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    try:
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
                linestyle=cluster.get('linestyle', '-'),
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

        plt.savefig(output_path, dpi=150, bbox_inches='tight',
                    facecolor='white', format='png')
    finally:
        plt.close(fig)


# ─── サービス名 → アイコンキー変換（トピックのservicesリストと構造的に一致させる） ──

_SERVICE_ICON_KEYWORDS: list[tuple] = [
    ("API Gateway", "api_gateway"),
    ("Lambda", "lambda"),
    ("DynamoDB", "dynamodb"),
    ("CloudFront", "cloudfront"),
    ("ACM", "acm"),
    ("ECS", "ecs"),
    ("ALB", "alb"),
    ("ECR", "ecr"),
    ("Kinesis", "kinesis"),
    ("X-Ray", "xray"),
    ("Route 53", "route53"),
    ("RDS", "rds"),
    ("SNS", "sns"),
    ("SQS", "sqs"),
    ("Bedrock", "bedrock"),
    ("OpenSearch", "opensearch"),
    ("CodePipeline", "codepipeline"),
    ("CodeBuild", "codebuild"),
    ("SageMaker", "sagemaker"),
    ("Step Functions", "step_functions"),
    ("CloudTrail", "cloudtrail"),
    ("Athena", "athena"),
    ("Cost Explorer", "cost_explorer"),
    ("Budgets", "budgets"),
    ("GuardDuty", "guardduty"),
    ("Security Hub", "security_hub"),
    ("Backup", "backup"),
    ("Control Tower", "control_tower"),
    ("Organizations", "organizations"),
    ("IAM Identity Center", "iam"),
    ("Glue", "glue"),
    ("S3", "s3"),
]

_SERVICE_LABEL_OVERRIDE: dict[str, str] = {
    "S3 Cross-Region Replication": "S3\n(レプリカ)",
    "IAM Identity Center": "IAM Identity\nCenter",
    "Amazon Bedrock": "Bedrock",
    "AWS Budgets": "Budgets",
    "AWS Backup": "Backup",
    "AWS Organizations": "Organizations",
    "AWS Glue": "Glue",
    "SageMaker AI": "SageMaker",
    "Kinesis Data Streams": "Kinesis\nData Streams",
    "OpenSearch Serverless": "OpenSearch\nServerless",
    "ECS Fargate": "ECS\nFargate",
}


def _icon_for_service(name: str) -> str:
    low = name.lower()
    for keyword, icon in _SERVICE_ICON_KEYWORDS:
        if keyword.lower() in low:
            return icon
    return "user"


def _label_for_service(name: str) -> str:
    return _SERVICE_LABEL_OVERRIDE.get(name, name)


def _diagram_generic(topic_name: str, services: list[str], variant: int, output_path: str):
    """トピックの services リストから直接ノードを組み立てる汎用フロー図。
    手作業のトピック別ハードコード図は、記事本文（services準拠）との不整合が
    繰り返し発生したため廃止し、この関数に一本化した。servicesと図が構造的に
    一致するため、本文と図が食い違うバグが原理的に起きない。
    """
    n = len(services)
    spacing = 4.2
    nodes = [
        {
            "id": f"n{i}",
            "icon": _icon_for_service(svc),
            "label": _label_for_service(svc),
            "x": 1.5 + i * spacing,
            "y": 3.5,
        }
        for i, svc in enumerate(services)
    ]
    edge_label = "データ連携" if variant == 1 else "アクセス制御・課金"
    edges = [(f"n{i}", f"n{i+1}", edge_label) for i in range(n - 1)]
    title = (
        f"{topic_name} ① – 構成概要"
        if variant == 1 else
        f"{topic_name} ② – コスト・セキュリティの制御ポイント"
    )
    # サービス数が変わってもノードが xlim の外にクリップされないよう、
    # ノード数に応じて右端の余白を動的に確保する（既定14はn=3までカバー）
    last_x = 1.5 + (n - 1) * spacing if n > 0 else 0
    xlim = (0, max(14.0, last_x + 2.5))
    _draw_diagram(title, nodes, edges, output_path, xlim=xlim, clusters=[_outer_cluster(nodes)])


def generate_diagrams(topic: dict, base_path: str) -> list[str]:
    """
    指定トピックの構成図2枚を生成し、PNGパスのリストを返す。
    topic     : AWS_TOPICS の要素（"name"・"services" を使用）
    base_path : 拡張子なしのパス（例: /tmp/20260501_210000_serverless_ec_diagram）
    """
    services = topic.get("services") or []
    if not services:
        print(f"警告: トピック '{topic.get('id')}' に services が定義されていません")
        return []

    paths = []
    for i in (1, 2):
        out_path = f"{base_path}_{i}.png"
        try:
            _diagram_generic(topic["name"], services, i, out_path)
            paths.append(out_path)
            print(f"  PNG生成完了: {out_path}")
        except Exception as e:
            print(f"  PNG生成エラー (図{i}): {e}")

    return paths
