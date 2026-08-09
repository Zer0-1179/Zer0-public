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

_BASE     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    'acm':         f'{_SVC}/Arch_Security-Identity-Compliance/64/Arch_AWS-Certificate-Manager_64.png',
    'api_gateway': f'{_SVC}/Arch_Networking-Content-Delivery/64/Arch_Amazon-API-Gateway_64.png',
    'dynamodb':    f'{_SVC}/Arch_Database/64/Arch_Amazon-DynamoDB_64.png',
    'region':      f'{_GRP}/Region_32.png',
    'aws_cloud_logo': f'{_GRP}/AWS-Cloud-logo_32.png',
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
    # --- 配置グリッド(2026-08-09、ユーザー指摘によるルール化) ---
    # 横方向は水平間隔3.5(CLAUDE.md規定の最低値)刻みのグリッドに統一し、
    # 既存の縦列(ssm/cw/apigw/s3mail、x=9.5)を基準点にする:
    #   GRID = {..., 6.0, 9.5, 13.0, 16.5, 20.0, ...}  (各差分=3.5)
    # acm/lambda(collector)はGRID[6.0]、ssm/cw/apigw/s3mail/cf/s3lpはGRID[9.5]、
    # lambda_wlはGRID[13.0]、lambda_swはGRID[16.5]、ses_out/lambda_fwはGRID[20.0]
    # に統一。ebのみap-northeast-1枠の左パディング制約(枠x=3.3+パディング0.9)で
    # グリッドに乗せられない例外(詳細は配置コメント参照)。
    # ddb_wl(14.75)はlambda_wl/lambda_swの中間点で、両者からの距離を揃えるための
    # 意図的な非グリッド配置。
    nodes = [
        # --- レーン1: 収集Bot(既存)  y=12.0 ---
        {'id': 'eb',      'icon': 'eventbridge', 'label': 'Amazon EventBridge\n毎日 6:00 JST',    'x': 4.2,  'y': 12.0},
        {'id': 'lambda',  'icon': 'lambda',      'label': 'AWS Lambda\ncollector',                'x': 6.0,  'y': 12.0},
        {'id': 'dlq',     'icon': 'sqs',         'label': 'Amazon SQS (DLQ)',                     'x': 6.0,  'y': 9.7},
        {'id': 'ssm',     'icon': 'ssm',         'label': 'AWS Systems Manager\n設定値',           'x': 9.5,  'y': 10.6},
        {'id': 'cw',      'icon': 'cloudwatch',  'label': 'Amazon CloudWatch\nLogs',              'x': 9.5,  'y': 8.5},
        {'id': 'site',    'icon': 'user',        'label': '横浜市 入札サイト\n(公開情報)',        'x': 24.5, 'y': 12.0},

        # --- レーン2: LP事前登録(新規)  y=6.5 ---
        {'id': 'browser', 'icon': 'user',        'label': 'LP利用者\n(ブラウザ)',                 'x': 0.8,  'y': 6.5},
        # S3はCloudFrontの真下・ssm/cw/apigw/s3mailと同じグリッド列(x=9.5)に配置し、
        # cf→s3lpが一直線の垂直線になるようにする。'lambda'→'site'(GET収集、
        # y=12.0でregionの全幅を横断)と交差しないよう、2行ラベル(matplotlibの
        # get_window_extent実測で高さ約0.34、下端y≈13.36)がその上に来るy=14.3に
        # 置く(region上端をその分押し上げてある)。
        {'id': 's3lp',    'icon': 's3',          'label': 'Amazon S3\nLP静的サイト',              'x': 9.5,  'y': 14.3},
        {'id': 'apigw',   'icon': 'api_gateway', 'label': 'Amazon API Gateway\n事前登録API',      'x': 9.5,  'y': 6.5},
        # lambda_wlはapigw/ses_outと同じy=6.5に揃え、apigw→lambda_wl→ses_outが
        # 一直線の水平線になるようにする。lambda_sw(下記Stripe節)はそのままだと
        # 同じ経路上で衝突するため、下トラック(y=4.8)へ分離しapigwから迂回させて
        # ddb_wl/ses_outへ接続する。
        {'id': 'lambda_wl','icon': 'lambda',     'label': 'AWS Lambda\nlp-waitlist',              'x': 13.0, 'y': 6.5},
        {'id': 'ddb_wl',  'icon': 'dynamodb',    'label': 'Amazon DynamoDB\nlp-waitlist',         'x': 14.75,'y': 2.4},

        # --- エッジ/グローバルサービス(2026-08-09、region枠の外・AWS Cloud内) ---
        # CloudFrontはグローバルサービス、ACMもCloudFront証明書はus-east-1発行のため
        # 両方ともap-northeast-1リージョンに属さない。AWS Cloud直下・region枠の外の
        # 専用クラスターに切り出し、region枠との二重内包(冗長)を解消する。
        # acmはlambda(collector)と同じグリッド列(x=6.0)、cfはssm/cw/apigw等と
        # 同じ列(x=9.5、グリッド間隔3.5)に統一。
        {'id': 'acm', 'icon': 'acm',        'label': 'AWS Certificate Manager\n(us-east-1) SSL/TLS証明書', 'x': 6.0,  'y': 17.8},
        {'id': 'cf',  'icon': 'cloudfront', 'label': 'Amazon CloudFront\nnyusatsu.zer0-infra.com',        'x': 9.5,  'y': 18.5},

        # --- レーン3: 問合せメール転送(新規)  y=1.0 ---
        {'id': 'inquirer','icon': 'user',        'label': '問合せ送信者\n(外部)',                 'x': 0.8,  'y': 1.0},
        {'id': 'ses_in',  'icon': 'ses',         'label': 'Amazon SES (受信)\nnyusatsu@zer0-infra.com', 'x': 5.0,  'y': 1.0},
        {'id': 's3mail',  'icon': 's3',          'label': 'Amazon S3\n受信メール(一時)',          'x': 9.5,  'y': 1.0},
        # mail-forwarderはses_outと同じグリッド列(x=20.0)に揃え、
        # lambda_fw→ses_outが一直線の垂直線になるようにする。
        {'id': 'lambda_fw','icon': 'lambda',     'label': 'AWS Lambda\nmail-forwarder',           'x': 20.0, 'y': 1.0},

        # --- 共有: SES送信・通知先(右端の専用縦帯) ---
        {'id': 'ses_out', 'icon': 'ses',         'label': 'Amazon SES (送信)\ninfo.zer0-infra.com', 'x': 20.0, 'y': 6.5},
        {'id': 'recv',    'icon': 'user',        'label': '通知先/転送先\nメール',                'x': 24.5, 'y': 6.5},

        # --- Stripe Webhook突合(v0.19、新規)。既存のapigw/ddb_wl(レーン2)を共有し、
        # stripe自体は左側の外部クラスターにbrowser/inquirerと並べて配置、
        # lambda_swはapigwの下トラックとして、lambda_wl(上トラック)と対称に配置する。 ---
        {'id': 'stripe',    'icon': 'user',   'label': 'Stripe\n(決済)',         'x': 0.8,  'y': 3.75},
        {'id': 'lambda_sw', 'icon': 'lambda', 'label': 'AWS Lambda\nstripe-webhook', 'x': 16.5, 'y': 4.8},
    ]

    # --- 矢印の始点・終点の考え方(2026-08-09、ユーザー確認済み) ---
    # 「自分自身の送信元・送信先ノードのラベル文字」に矢印がかかるのは問題ない
    # (むしろ「そのノードの文字から矢印が出ている」ように見えるのが望ましい)。
    # 直線を優先し、経由点による回避は入れない。回避が必要なのは「無関係な
    # 他ノードのラベル」を横切ってしまう場合のみ(例: lambda→ses_outの迂回帯は
    # ssm/cwという別ノードのラベルを踏まないためのもの)。
    edges = [
        ('eb',        'lambda',   ''),
        ('lambda',    'site',     'GET収集'),
        ('lambda',    'ssm',      '設定取得'),
        ('lambda',    'cw',       ''),
        ('lambda',    'dlq',      ''),
        # ssm/cw列(x=9.5)とlambda_wl(x=13.0)を避けるため、GET収集線(y=12.0)の
        # 下側・ssmアイコン上端(y=11.15)の上側の専用帯(y=11.6)を通り、
        # ses_out直上(x=20.0)から下りる迂回ルートを取る(直線区間のみで構成)。
        # 第1区間の終点x=8.6は、lambda→ssm斜め線(y=11.6上でx=7.0)との交差、および
        # 「設定取得」エッジラベル(x≈7.5〜8.0, 上端y≈11.6)への重なりを回避するため
        # (いずれも無関係な別ノード・別エッジのラベルなので回避対象)。
        ('lambda',    'ses_out',  '', [(8.6, 11.6), (20.0, 11.6)]),

        # browser→cfは外部クラスター左端の専用縦帯(x=-0.45、stripe→apigwの
        # x=-0.3とは0.15離して並走)を通り、region枠の外(エッジ/グローバル
        # クラスター、y=18.5)まで直接立ち上げる。
        ('browser',   'cf',       'HTTPS', [(-0.45, 6.5), (-0.45, 18.5)]),
        # s3lpをcfと同じグリッド列(x=9.5)に置いているため一直線になる。
        ('cf',        's3lp',     ''),
        # cf/acmをregion外へ退避させたことでy=6.5〜7.3が完全に空いたため、
        # browser→apigwは迂回なしの直線で引ける(2026-08-09に単純化)。
        ('browser',   'apigw',    '事前登録\nfetch'),
        ('apigw',     'lambda_wl',''),
        ('lambda_wl', 'ddb_wl',   ''),
        ('lambda_wl', 'ses_out',  '登録通知'),
        ('acm',       'cf',       '証明書'),

        ('inquirer',  'ses_in',   'メール送信'),
        ('ses_in',    's3mail',   ''),
        ('s3mail',    'lambda_fw',''),
        # ses_outと同じグリッド列(x=20.0)に置いているため一直線になる。
        ('lambda_fw', 'ses_out',  '転送'),

        ('ses_out',   'recv',     ''),

        # Stripe Webhook突合(v0.19)。cf/acm退避でy=3.75〜6.5の経路も空いたため、
        # stripe→apigwは迂回なしの直線で引ける(2026-08-09に単純化)。
        ('stripe',    'apigw',    ''),
        # apigw→lambda_sw(下トラック)はlambda_wl→ddb_wl/ses_out(上トラック、
        # 無関係な別エッジ)と交差しないよう、いったんddb_wlのラベル下端より
        # 低い専用帯(y=1.2)まで下りてから右へ進み、lambda_swへ合流する。
        ('apigw',     'lambda_sw','', [(10.3, 1.2), (16.5, 1.2)]),
        ('lambda_sw', 'ddb_wl',   ''),
        ('lambda_sw', 'ses_out',  ''),
    ]

    clusters = [
        # AWS Cloud全体を示す外枠(ソラコム松下氏のAWS Summit Japan 2025セッション
        # 「AWS アーキテクチャ作図入門」のチェックリストに準拠)。region枠と
        # エッジ/グローバルクラスターの両方を覆う。座標はこの2つの内側クラスター
        # の確定値をもとに手計算(auto-paddingの対象外)。
        {
            'label': 'AWS Cloud', 'icon': 'aws_cloud_logo',
            'x': 2.95, 'y': -1.0, 'w': 19.5, 'h': 21.5,
            'color': '#FFFFFF', 'edgecolor': '#879196',
            'linestyle': '-', 'linewidth': 1.5,
        },
        {
            'label': 'ap-northeast-1', 'icon': 'region',
            # 左端をx=3.3に調整(旧値3.6)。ebノードがこの枠に収まるよう
            # x=4.2へ配置し直したため、パディング0.9(旧ノードでは未収容だった)。
            # 上端をy=15.0まで拡大。s3lp(y=14.3)の2行ラベル(実測高さ約0.34)を
            # 'lambda'→'site'(GET収集、y=12.0で全幅横断)と交差しない高さに
            # 置くための拡張。
            'x': 3.3, 'y': -0.65, 'w': 18.8, 'h': 15.65,
            'color': '#F0F7EE', 'edgecolor': '#6BAE75',
            'linestyle': '-', 'linewidth': 2.0,
        },
        # エッジ/グローバルサービス(2026-08-09新設)。CloudFront・ACM(us-east-1)は
        # 特定リージョンに属さないため、ap-northeast-1枠の外・AWS Cloud内に
        # 独立クラスターとして配置し、region枠との二重内包(冗長)を解消する。
        # 「リージョン/VPC/サブネット」のような公式グループアイコンが存在する
        # 概念ではないため、外部(非AWS)クラスターと同様アイコンなしとする
        # (ただしAWS所属を示すため水色系で外部クラスターの淡灰色と区別する)。
        # 下端(y=16.2)とregion枠上端(y=15.0)の数値上の隙間は1.2だが、
        # FancyBboxPatchのboxstyle='round,pad=0.15'により両クラスターとも
        # 実際の描画は指定座標より0.15ずつ外側へ膨らむため、視覚的な隙間は
        # 1.2-0.15-0.15=0.9(CLAUDE.mdの「0.8以上」を満たす最小限の計算)。
        {
            'label': 'エッジ/グローバルサービス', 'icon': None,
            'x': 5.0, 'y': 16.2, 'w': 6.2, 'h': 3.4,
            'color': '#EAF4FB', 'edgecolor': '#8AAFCC',
            'linestyle': '-', 'linewidth': 2.0,
        },
        {
            'label': '外部（非AWS）', 'icon': None,
            'x': -0.6, 'y': -0.65, 'w': 2.6, 'h': 8.25,
            'color': '#F5F5F5', 'edgecolor': '#AAAAAA',
            'linestyle': '-', 'linewidth': 1.5,
        },
        {
            'label': '外部（非AWS）', 'icon': None,
            'x': 23.0, 'y': 4.6, 'w': 2.8, 'h': 8.6,
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

    fig, ax = plt.subplots(figsize=(24, 19.7), dpi=150)
    ax.set_xlim(-1.2, 26.2)
    ax.set_ylim(-1.5, 21.0)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title('008 入札情報ウォッチ（清掃業界向け・横浜市パイロット） — アーキテクチャ図',
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

    # 「直線が自ノードのラベル文字を自然に貫通する接続」だけ、矢印の始点/終点を
    # ラベル寄りにする(2026-08-09、ユーザー確認済み)。判定基準は「その接続を
    # 中心点どうしの直線で結んだ場合に、自分自身のラベル矩形を通過するか」。
    # 通過しない接続(横方向・斜め浅めなど)は通常通りアイコン基準のまま変更しない。
    # - LABEL_START_EDGES: 出発直後に自分のラベルを貫通する接続。始点をラベル
    #   下端の実測座標(get_window_extent)にし、shrinkAを実質0にする。
    # - LABEL_END_EDGES: 到着直前に自分のラベルを貫通する接続(例:
    #   lambda_fw→ses_outはses_outの真下から近づくため、標準shrinkB=42だと
    #   矢頭がアイコン下端とラベル上端の間の隙間で浮いてしまっていた)。
    #   shrinkBを縮小し、アイコンの陰(zorderが線より前面)で自然に隠れる形にする。
    # waypoint経由の接続は「waypointを含めた最初/最後の区間」で判定する必要が
    # あり、apigw→lambda_swは出発直後(apigw自身)・到着直前(lambda_sw自身)の
    # 両方でラベルを貫通していた(直線判定のみのチェックで見落としていた分、
    # 2026-08-09に追加)。
    # lambda_swは apigw→lambda_sw(着信、真下から)と lambda_sw→ddb_wl(発信、
    # 同じく真下寄り)の両方が同じノードの直下corridorを使うため、両方を
    # ラベル起点にすると線同士が重なってしまう。lambda_sw→ddb_wlは自ラベルの
    # 境界をわずかに掠める程度(ボーダーライン)だったため、こちらはアイコン基準
    # のまま残し、着信側(apigw→lambda_sw)を優先してラベル寄りにする。
    LABEL_START_EDGES = {('lambda', 'dlq'), ('cf', 's3lp'), ('lambda_wl', 'ddb_wl'), ('apigw', 'lambda_sw')}
    LABEL_END_EDGES = {('lambda_fw', 'ses_out'), ('apigw', 'lambda_sw')}
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    label_bottom = {}
    for n in nodes:
        x, y = n['x'], n['y']
        t = ax.text(x, y - HALF - 0.2, n['label'],
                    ha='center', va='top', fontsize=7.5,
                    color='#232F3E', fontweight='bold', zorder=4.5)
        fig.canvas.draw()
        bbox = t.get_window_extent(renderer=renderer)
        (_, y0), (_, _) = inv.transform([(bbox.x0, bbox.y0), (bbox.x1, bbox.y1)])
        label_bottom[n['id']] = y0

    for n in nodes:
        x, y = n['x'], n['y']
        img = _load(n['icon'])
        if img is not None:
            ax.imshow(img, extent=[x - HALF, x + HALF, y - HALF, y + HALF],
                      aspect='auto', zorder=4, interpolation='bilinear')

    SHRINK = 42
    for edge in edges:
        from_id, to_id = edge[0], edge[1]
        label = edge[2] if len(edge) > 2 else ''
        waypoints = edge[3] if len(edge) > 3 else []
        n1, n2 = node_map[from_id], node_map[to_id]
        use_label_start = (from_id, to_id) in LABEL_START_EDGES
        use_label_end = (from_id, to_id) in LABEL_END_EDGES
        start_pt = (n1['x'], label_bottom[from_id]) if use_label_start else (n1['x'], n1['y'])
        # 途中に経由点(waypoints)がある場合は直線区間を複数つなぎ、矢頭は最終区間のみに描く。
        pts = [start_pt] + waypoints + [(n2['x'], n2['y'])]
        n_seg = len(pts) - 1
        for i in range(n_seg):
            shrink_a = (0 if use_label_start else SHRINK) if i == 0 else 0
            shrink_b = (3 if use_label_end else SHRINK) if i == n_seg - 1 else 0
            ax.annotate(
                '', xy=pts[i + 1], xytext=pts[i],
                arrowprops=dict(
                    arrowstyle='->' if i == n_seg - 1 else '-',
                    color='#555555', lw=1.5,
                    shrinkA=shrink_a,
                    shrinkB=shrink_b,
                    connectionstyle='arc3,rad=0.0',
                ),
                zorder=3,
            )
        if label:
            mi = n_seg // 2
            mp1, mp2 = pts[mi], pts[mi + 1]
            mx = (mp1[0] + mp2[0]) / 2
            my = (mp1[1] + mp2[1]) / 2
            ax.text(mx, my + 0.18, label, ha='center', va='bottom',
                    fontsize=7, color='#666666',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                              edgecolor='none', alpha=0.9),
                    zorder=5)

    out = os.path.join(_BASE, 'images', '008_architecture.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white', format='png')
    plt.close(fig)
    print(f'saved → {out}')


if __name__ == '__main__':
    draw()
