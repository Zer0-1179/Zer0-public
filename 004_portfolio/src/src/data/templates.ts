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

export function getTemplateBySlug(slug: string) {
  return templates.find((t) => t.slug === slug);
}
