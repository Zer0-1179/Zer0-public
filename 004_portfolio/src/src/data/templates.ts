export type Category = {
  slug: string;
  labelJa: string;
  labelEn: string;
  descJa: string;
  descEn: string;
};

const CATEGORY_META: Category[] = [
  { slug: 'network',    labelJa: 'ネットワーク',      labelEn: 'Network',    descJa: 'VPC・サブネット・ALB・NLBなど',          descEn: 'VPC, Subnet, ALB, NLB, and more' },
  { slug: 'compute',   labelJa: 'コンピューティング', labelEn: 'Compute',    descJa: 'Lambda・EC2・ECS・Batchなど',            descEn: 'Lambda, EC2, ECS, Batch, and more' },
  { slug: 'storage',   labelJa: 'ストレージ',        labelEn: 'Storage',    descJa: 'S3・EFS・EBSなど',                      descEn: 'S3, EFS, EBS, and more' },
  { slug: 'database',  labelJa: 'データベース',       labelEn: 'Database',   descJa: 'RDS・DynamoDB・ElastiCacheなど',         descEn: 'RDS, DynamoDB, ElastiCache, and more' },
  { slug: 'security',  labelJa: 'セキュリティ',       labelEn: 'Security',   descJa: 'KMS・IAM・WAF・Secrets Managerなど',    descEn: 'KMS, IAM, WAF, Secrets Manager, and more' },
  { slug: 'messaging', labelJa: 'メッセージング',     labelEn: 'Messaging',  descJa: 'SQS・SNS・EventBridgeなど',             descEn: 'SQS, SNS, EventBridge, and more' },
  { slug: 'monitoring',labelJa: 'モニタリング',       labelEn: 'Monitoring', descJa: 'CloudWatch・CloudTrailなど',             descEn: 'CloudWatch, CloudTrail, and more' },
];

export type Template = {
  slug: string;
  filename: string;
  nameJa: string;
  nameEn: string;
  descJa: string;
  descEn: string;
  descShortJa: string;
  descShortEn: string;
  services: string[];
  tagsJa: string[];
  tagsEn: string[];
  categoryJa: string;
  categoryEn: string;
  updatedAt: string;
};

export const templates: Template[] = [
  {
    slug: 's3-bucket',
    filename: 'cfn-s3-bucket.yaml',
    nameJa: 'S3バケット',
    nameEn: 'S3 Bucket',
    descJa: 'dev/prd環境に応じてバージョニング・ライフサイクル・DeletionPolicyを自動切替。パブリックアクセス完全ブロック済み。ProjectNameとEnvを指定するだけで即デプロイ可能。',
    descEn: 'Auto-switches versioning, lifecycle, and DeletionPolicy based on dev/prd env. Full public access block enabled. Deploy instantly with just ProjectName and Env.',
    descShortJa: 'dev/prd切替・バージョニング・ライフサイクル・パブリックアクセスブロック設定済み',
    descShortEn: 'dev/prd env switch, versioning, lifecycle, and public access block pre-configured',
    services: ['S3'],
    tagsJa: ['初級', 'ストレージ', 'env切替'],
    tagsEn: ['Beginner', 'Storage', 'env switch'],
    categoryJa: 'ストレージ',
    categoryEn: 'Storage',
    updatedAt: '2026-05-26',
  },
  {
    slug: 'kms-key',
    filename: 'cfn-kms-key.yaml',
    nameJa: 'KMSキー',
    nameEn: 'KMS Key',
    descJa: 'S3・EBS・RDS・EFS・CloudWatch Logs・SSM・SQS・Secrets Managerなど主要サービスで共用できる汎用KMSキー。エイリアス自動作成・年次自動ローテーション有効済み。他スタックからImportValueで参照可能。',
    descEn: 'General-purpose KMS key reusable across S3, EBS, RDS, EFS, CloudWatch Logs, SSM, SQS, and Secrets Manager. Alias auto-created, annual key rotation enabled. Exportable ARN for cross-stack reference.',
    descShortJa: '主要サービス共用・エイリアス自動作成・年次ローテーション・クロススタック参照対応',
    descShortEn: 'Reusable across major services, alias auto-created, annual rotation, cross-stack reference ready',
    services: ['KMS'],
    tagsJa: ['初級', 'セキュリティ', '暗号化'],
    tagsEn: ['Beginner', 'Security', 'Encryption'],
    categoryJa: 'セキュリティ',
    categoryEn: 'Security',
    updatedAt: '2026-05-26',
  },
  {
    slug: 'sqs-queue',
    filename: 'cfn-sqs-queue.yaml',
    nameJa: 'SQSキュー + DLQ',
    nameEn: 'SQS Queue + DLQ',
    descJa: 'メインキューとDead Letter Queueをセットで作成。env別保持期間・可視性タイムアウト・最大受信回数を設定済み。SQS管理SSEをデフォルト有効、カスタムKMSキーにも対応。',
    descEn: 'Creates a main queue and Dead Letter Queue together. Pre-configured with env-based retention, visibility timeout, and max receive count. SQS managed SSE enabled by default with optional custom KMS key.',
    descShortJa: 'DLQ付き・env別保持期間・SSEデフォルト有効',
    descShortEn: 'DLQ included, env-based retention, SSE enabled by default',
    services: ['SQS'],
    tagsJa: ['初級', 'メッセージング', 'DLQ'],
    tagsEn: ['Beginner', 'Messaging', 'DLQ'],
    categoryJa: 'メッセージング',
    categoryEn: 'Messaging',
    updatedAt: '2026-05-26',
  },
  {
    slug: 'cloudwatch-logs',
    filename: 'cfn-cloudwatch-logs.yaml',
    nameJa: 'CloudWatch ロググループ',
    nameEn: 'CloudWatch Log Group',
    descJa: 'env別の保持期間設定済みロググループ。カスタム名にも対応し、Lambda・EC2・ECSなど任意のサービスのログ出力先として利用可能。KMS暗号化オプション付き。',
    descEn: 'Log group with env-based retention pre-configured. Supports custom names for use with Lambda, EC2, ECS, or any service. Optional KMS encryption.',
    descShortJa: 'env別保持期間・カスタム名対応・KMS暗号化オプション',
    descShortEn: 'env-based retention, custom name support, optional KMS encryption',
    services: ['CloudWatch Logs'],
    tagsJa: ['初級', 'モニタリング', 'ログ'],
    tagsEn: ['Beginner', 'Monitoring', 'Logging'],
    categoryJa: 'モニタリング',
    categoryEn: 'Monitoring',
    updatedAt: '2026-05-26',
  },
  {
    slug: 'iam-role-lambda',
    filename: 'cfn-iam-role-lambda.yaml',
    nameJa: 'IAMロール（Lambda用）',
    nameEn: 'IAM Role for Lambda',
    descJa: 'Lambda実行ロールの単体テンプレート。CloudWatch Logsへの書き込み権限を標準装備。追加マネージドポリシーを2つまでパラメータで指定可能。他スタックからImportValueで参照できる。',
    descEn: 'Standalone Lambda execution role. CloudWatch Logs write access included. Attach up to two additional managed policies via parameters. Exportable ARN for cross-stack reference.',
    descShortJa: 'CWLogs権限付き・追加ポリシー2つまで指定可・クロススタック参照対応',
    descShortEn: 'CWLogs access included, up to 2 additional policies, cross-stack reference ready',
    services: ['IAM'],
    tagsJa: ['初級', 'セキュリティ', 'Lambda'],
    tagsEn: ['Beginner', 'Security', 'Lambda'],
    categoryJa: 'セキュリティ',
    categoryEn: 'Security',
    updatedAt: '2026-05-26',
  },
  {
    slug: 'scheduled-lambda',
    filename: 'cfn-scheduled-lambda.yaml',
    nameJa: 'スケジュール実行Lambda',
    nameEn: 'Scheduled Lambda',
    descJa: 'EventBridgeで定期実行するLambda関数一式。SSM Parameter StoreとAmazon Bedrockへのアクセス権限付きIAMロール・DLQ・CloudWatch Logsを含む。2スケジュール設定に対応。',
    descEn: 'Lambda function set triggered by EventBridge on a schedule. Includes IAM role with SSM and Bedrock access, DLQ, and CloudWatch Logs. Supports two schedule configurations.',
    descShortJa: 'EventBridge定期実行・SSM/Bedrock権限付きIAM・DLQ・CloudWatch Logs一式',
    descShortEn: 'EventBridge schedule, IAM with SSM/Bedrock access, DLQ, and CloudWatch Logs included',
    services: ['Lambda', 'EventBridge', 'SSM', 'Bedrock'],
    tagsJa: ['初級', 'コンピューティング', '定期実行'],
    tagsEn: ['Beginner', 'Compute', 'Scheduled'],
    categoryJa: 'コンピューティング',
    categoryEn: 'Compute',
    updatedAt: '2026-05-26',
  },
];

export function categorySlug(template: Template): string {
  return template.categoryEn.toLowerCase().replace(/\s+/g, '-');
}

export function getCategoryBySlug(slug: string): Category | undefined {
  const fromMeta = CATEGORY_META.find((c) => c.slug === slug);
  if (fromMeta) return fromMeta;
  const tmpl = templates.find((t) => categorySlug(t) === slug);
  if (!tmpl) return undefined;
  return { slug, labelJa: tmpl.categoryJa, labelEn: tmpl.categoryEn, descJa: '', descEn: '' };
}

export function getTemplatesByCategory(slug: string): Template[] {
  return templates.filter((t) => categorySlug(t) === slug);
}

export function getCategoriesWithTemplates(): Category[] {
  const usedSlugs = [...new Set(templates.map(categorySlug))];
  const ordered = CATEGORY_META.filter((c) => usedSlugs.includes(c.slug));
  const extra = usedSlugs
    .filter((s) => !CATEGORY_META.find((c) => c.slug === s))
    .map((s) => getCategoryBySlug(s)!);
  return [...ordered, ...extra];
}

export function getTemplateBySlug(slug: string) {
  return templates.find((t) => t.slug === slug);
}
