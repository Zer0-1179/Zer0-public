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
    slug: 'scheduled-lambda',
    filename: 'cfn-scheduled-lambda.yaml',
    nameJa: 'スケジュール実行Lambda',
    nameEn: 'Scheduled Lambda',
    descJa: 'EventBridgeで2スケジュール定期実行するLambda構成。SSM Parameter Store・Amazon Bedrockへのアクセス権限込み。ProjectNameを変えるだけで使い回せる汎用テンプレート。',
    descEn: 'Lambda triggered by two EventBridge schedules. Includes IAM permissions for SSM Parameter Store and Amazon Bedrock. Ready to deploy by changing ProjectName.',
    services: ['Lambda', 'EventBridge', 'SSM Parameter Store', 'Amazon Bedrock', 'CloudWatch Logs', 'IAM'],
    tagsJa: ['サーバーレス', 'Bot', '定期実行'],
    tagsEn: ['Serverless', 'Bot', 'Scheduled'],
  },
];

export function getTemplateBySlug(slug: string) {
  return templates.find((t) => t.slug === slug);
}
