"""
diagrams パッケージに同梱されているAWS公式アイコンを
aws_icons/ ディレクトリにコピーするスクリプト。

既存の自動生成アイコン（テキストラベル付き色付き四角）を
公式SVG/PNGに置き換える。
"""
import os
import shutil

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_SCRIPT_DIR, 'aws_icons')

# diagrams パッケージのリソースディレクトリ（モジュールから自動検出）
try:
    import diagrams as _diagrams
    _DIAGRAMS_BASE = os.path.dirname(os.path.dirname(_diagrams.__file__))
    _DIAGRAMS_RES = os.path.join(_DIAGRAMS_BASE, 'resources', 'aws')
except ImportError:
    _DIAGRAMS_RES = '/usr/local/lib/python3.12/dist-packages/resources/aws'

# 内部名 -> (カテゴリ, ファイル名) のマッピング
ICON_MAP: dict[str, tuple[str, str]] = {
    # Compute
    'ec2':               ('compute',    'ec2.png'),
    'ecs':               ('compute',    'elastic-container-service.png'),
    'ecr':               ('compute',    'ec2-container-registry.png'),
    'fargate':           ('compute',    'fargate.png'),
    'lambda':            ('compute',    'lambda.png'),
    'autoscaling':       ('compute',    'ec2-auto-scaling.png'),
    'compute_optimizer': ('compute',    'compute-optimizer.png'),
    # Storage
    's3':                ('storage',    'simple-storage-service-s3.png'),
    'backup':            ('storage',    'backup.png'),
    # Database
    'rds':               ('database',   'rds.png'),
    'dynamodb':          ('database',   'dynamodb.png'),
    'dynamodb_streams':  ('database',   'dynamodb-streams.png'),
    'dax':               ('database',   'dynamodb-dax.png'),
    'elasticache':       ('database',   'elasticache.png'),
    'opensearch':        ('analytics',  'amazon-opensearch-service.png'),
    # Networking
    'vpc':               ('network',    'vpc.png'),
    'alb':               ('network',    'elb-application-load-balancer.png'),
    'cloudfront':        ('network',    'cloudfront.png'),
    'route53':           ('network',    'route-53.png'),
    'api_gateway':       ('network',    'api-gateway.png'),
    'igw':               ('network',    'internet-gateway.png'),
    'nat':               ('network',    'nat-gateway.png'),
    'waf':               ('security',   'waf.png'),
    # Security & Identity
    'iam':               ('security',   'identity-and-access-management-iam.png'),
    'iam_role':          ('security',   'identity-and-access-management-iam-role.png'),
    'acm':               ('security',   'certificate-manager.png'),
    'cognito':           ('security',   'cognito.png'),
    'guardduty':         ('security',   'guardduty.png'),
    'security_hub':      ('security',   'security-hub.png'),
    'shield':            ('security',   'shield.png'),
    'secrets_manager':   ('security',   'secrets-manager.png'),
    'control_tower':     ('management', 'control-tower.png'),
    'organizations':     ('management', 'organizations.png'),
    # Developer Tools
    'codepipeline':      ('devtools',   'codepipeline.png'),
    'codebuild':         ('devtools',   'codebuild.png'),
    'codecommit':        ('devtools',   'codecommit.png'),
    'codedeploy':        ('devtools',   'codedeploy.png'),
    # Analytics & Data
    'kinesis':           ('analytics',  'kinesis-data-streams.png'),
    'athena':            ('analytics',  'athena.png'),
    'glue':              ('analytics',  'glue.png'),
    'quicksight':        ('analytics',  'quicksight.png'),
    'lake_formation':    ('analytics',  'lake-formation.png'),
    # Management & Governance
    'cloudwatch':        ('management', 'cloudwatch.png'),
    'cloudwatch_alarm':  ('management', 'cloudwatch-alarm.png'),
    'cloudtrail':        ('management', 'cloudtrail.png'),
    'cloudformation':    ('management', 'cloudformation.png'),
    'config':            ('management', 'config.png'),
    'service_catalog':   ('management', 'service-catalog.png'),
    'xray':              ('devtools',   'x-ray.png'),
    'eventbridge':       ('integration','eventbridge.png'),
    # Messaging
    'sns':               ('integration','simple-notification-service-sns.png'),
    'sqs':               ('integration','simple-queue-service-sqs.png'),
    'ses':               ('integration','simple-notification-service-sns.png'),  # SESはfallback
    # Workflow
    'step_functions':    ('integration','step-functions.png'),
    # Cost
    'cost_explorer':     ('cost',       'cost-explorer.png'),
    'budgets':           ('cost',       'budgets.png'),
    # ML / AI
    'sagemaker':         ('ml',         'sagemaker.png'),
    'bedrock':           ('ml',         'bedrock.png'),
    'rekognition':       ('ml',         'rekognition.png'),
    'comprehend':        ('ml',         'comprehend.png'),
    'textract':          ('ml',         'textract.png'),
    # Management (追加)
    'ssm':               ('management', 'systems-manager-parameter-store.png'),
    # General
    'user':              ('general',    'user.png'),
}


def main():
    os.makedirs(_ICON_DIR, exist_ok=True)
    ok = 0
    skip = 0
    not_found = []

    for name, (category, filename) in ICON_MAP.items():
        src = os.path.join(_DIAGRAMS_RES, category, filename)
        dst = os.path.join(_ICON_DIR, f'{name}.png')

        if not os.path.exists(src):
            not_found.append(f'{name}: {src}')
            continue

        shutil.copy2(src, dst)
        ok += 1
        print(f'  ✓ {name:25s} <- {category}/{filename}')

    print(f'\n完了: {ok} アイコンをコピー')
    if not_found:
        print(f'\n⚠ ソースが見つからなかった ({len(not_found)} 件):')
        for m in not_found:
            print(f'  {m}')


if __name__ == '__main__':
    main()
