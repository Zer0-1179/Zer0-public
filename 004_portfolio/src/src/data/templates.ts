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
];

export function getTemplateBySlug(slug: string) {
  return templates.find((t) => t.slug === slug);
}
