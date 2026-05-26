export type Template = {
  slug: string;
  filename: string;
  nameJa: string;
  nameEn: string;
  descJa: string;
  descEn: string;
  services: string[];
  tagsJa: string[];
  tagsEn: string[];
};

export const templates: Template[] = [
  {
    slug: 's3-bucket',
    filename: 'cfn-s3-bucket.yaml',
    nameJa: 'S3バケット',
    nameEn: 'S3 Bucket',
    descJa: 'dev/prd環境に応じてバージョニング・ライフサイクル・DeletionPolicyを自動切替。パブリックアクセス完全ブロック済み。ProjectNameとEnvを指定するだけで即デプロイ可能。',
    descEn: 'Auto-switches versioning, lifecycle, and DeletionPolicy based on dev/prd env. Full public access block enabled. Deploy instantly with just ProjectName and Env.',
    services: ['S3'],
    tagsJa: ['初級', 'ストレージ', 'env切替'],
    tagsEn: ['Beginner', 'Storage', 'env switch'],
  },
  {
    slug: 'kms-key',
    filename: 'cfn-kms-key.yaml',
    nameJa: 'KMSキー',
    nameEn: 'KMS Key',
    descJa: 'S3・EBS・RDS・EFS・CloudWatch Logs・SSM・SQS・Secrets Managerなど主要サービスで共用できる汎用KMSキー。エイリアス自動作成・年次自動ローテーション有効済み。他スタックからImportValueで参照可能。',
    descEn: 'General-purpose KMS key reusable across S3, EBS, RDS, EFS, CloudWatch Logs, SSM, SQS, and Secrets Manager. Alias auto-created, annual key rotation enabled. Exportable ARN for cross-stack reference.',
    services: ['KMS'],
    tagsJa: ['初級', 'セキュリティ', '暗号化'],
    tagsEn: ['Beginner', 'Security', 'Encryption'],
  },
];

export function getTemplateBySlug(slug: string) {
  return templates.find((t) => t.slug === slug);
}
