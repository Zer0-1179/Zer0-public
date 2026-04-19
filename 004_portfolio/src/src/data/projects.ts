export type Project = {
  slug: string;
  number: string;
  nameJa: string;
  nameEn: string;
  descJa: string;
  descEn: string;
  longDescJa: string;
  longDescEn: string;
  pointsJa: string[];
  pointsEn: string[];
  architecture: string;
  githubUrl?: string;
  tags: string[];
  services: string[];
  emoji: string;
  featured: boolean;
};

export const projects: Project[] = [
  {
    slug: 'aws-x-poster',
    number: '001',
    nameJa: 'AWSニュース自動投稿Bot',
    nameEn: 'AWS News Auto-Poster',
    descJa: 'AWSの最新記事をRSSで取得し、Bedrockで口調を変換してXに毎日2回自動投稿するサーバーレスBot。',
    descEn: 'Serverless bot that fetches AWS news via RSS, converts tone with Bedrock, and auto-posts to X twice daily.',
    longDescJa: '複数のRSSフィード（AWS公式・クラスメソッド・Zenn・Qiita）から14日以内の記事を取得し、段階的フィルタで重複を排除。Amazon Bedrockで @Zer0_Infra の口調に変換してXに自動投稿する。時間帯別の投稿スタイル分岐や動的ハッシュタグ生成など、品質を保つための仕組みを実装。',
    longDescEn: 'Fetches articles from multiple RSS feeds (AWS official, Classmethod, Zenn, Qiita) within 14 days, removes duplicates with staged filters. Converts tone to match @Zer0_Infra style using Amazon Bedrock and auto-posts to X. Implements time-based posting style branching and dynamic hashtag generation.',
    pointsJa: [
      '4つのRSSフィードを並列取得し、14日以内・未投稿の記事のみを段階的フィルタで絞り込み',
      '朝投稿と夜投稿でBedrockへのプロンプトを切り替え、時間帯に合ったトーンを自動選択',
      'SSM Parameter Storeで投稿済みURLを管理し、重複投稿を完全排除',
      '動的ハッシュタグ生成で毎投稿に適切なタグを自動付与',
    ],
    pointsEn: [
      'Fetches 4 RSS feeds in parallel, filters to articles within 14 days using staged deduplication',
      'Switches Bedrock prompts between morning and evening to match appropriate tone',
      'Tracks posted URLs in SSM Parameter Store to prevent duplicate posts',
      'Dynamically generates relevant hashtags for each post',
    ],
    architecture: '/images/001_architecture.png',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public',
    tags: ['Serverless', 'Bedrock', 'EventBridge', 'X API'],
    services: ['Lambda', 'Amazon Bedrock', 'EventBridge', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '🤖',
    featured: true,
  },
  {
    slug: 'zenn-article-bot',
    number: '002',
    nameJa: 'Zenn初級記事自動生成Bot',
    nameEn: 'Zenn Beginner Article Bot',
    descJa: 'AWS初学者向けの技術記事とアーキテクチャ図を毎週木曜に自動生成してS3に保存するシステム。',
    descEn: 'Auto-generates AWS beginner tech articles and architecture diagrams every Thursday and saves them to S3.',
    longDescJa: '22種類のAWSサービスからランダムにトピックを選択し、Bedrockで3,000〜5,000文字のZenn記事を生成。matplotlibでAWS公式アイコンを使ったアーキテクチャ図PNG×2枚を同時生成。Zenn Markdownフォーマット完全対応。',
    longDescEn: 'Randomly selects from 22 AWS service topics and generates 3,000-5,000 character Zenn articles with Bedrock. Simultaneously generates 2 architecture diagram PNGs using AWS official icons with matplotlib. Full Zenn Markdown format support.',
    pointsJa: [
      '22トピックから重複なく選択するロジックをSSMで管理し、同じ内容の繰り返しを防止',
      'matplotlibとAWS公式アイコン素材を組み合わせ、図解PNG×2枚を記事と同時生成',
      'Zenn Markdownの見出し・コードブロック・画像埋め込みに完全対応したプロンプト設計',
      'SESで生成完了通知メールを自動送信、S3へのアップロードまで全自動',
    ],
    pointsEn: [
      'Manages topic history in SSM to prevent repeating the same subject across 22 topics',
      'Generates 2 architecture diagram PNGs alongside each article using matplotlib and official AWS icons',
      'Prompt designed to produce valid Zenn Markdown with headers, code blocks, and image embeds',
      'Sends completion notification via SES; fully automated from generation to S3 upload',
    ],
    architecture: '/images/002_architecture.png',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public',
    tags: ['SAM', 'Bedrock', 'S3', 'SES', 'matplotlib'],
    services: ['Lambda', 'Amazon Bedrock', 'S3', 'SES', 'SSM Parameter Store', 'SAM'],
    emoji: '📝',
    featured: true,
  },
  {
    slug: 'x-ai-bot',
    number: '003',
    nameJa: 'AI活用術自動投稿Bot',
    nameEn: 'AI Tips Auto-Poster',
    descJa: 'AI活用術・会社員あるある系コンテンツを6カテゴリでローテーションしながら毎日自動投稿するBot。',
    descEn: 'Bot that auto-posts AI usage tips and office worker content daily across 6 rotating categories.',
    longDescJa: '仕事×AI・副業・共感・問いかけ・記事感想・Googleトレンド連動の6カテゴリを直近7投稿で重複しないよう管理。火・金はZenn/QiitaのAI記事感想をURL付きで投稿、日曜はGoogle Trendsと連動。カテゴリ別プロンプト設計で一貫した世界観を表現。',
    longDescEn: 'Manages 6 categories (Work×AI, Side hustle, Empathy, Questions, Article reactions, Google Trends) without repeating within 7 posts. Tue/Fri: AI article reactions with URLs; Sun: Google Trends-linked posts. Category-specific prompts maintain consistent voice.',
    pointsJa: [
      '6カテゴリの投稿履歴をSSMで管理し、直近7件で同カテゴリが連続しないようローテーション',
      '火・金曜はZenn/QiitaのRSSからAI関連記事を取得してURL付き感想ツイートを自動生成',
      '日曜はGoogle Trends APIと連動し、トレンドワードに合わせた投稿を自動作成',
      'カテゴリごとに専用プロンプトを設計し、読者に一貫したキャラクターとして認識させる',
    ],
    pointsEn: [
      'Tracks category history in SSM to prevent the same category appearing in 7 consecutive posts',
      'Tue/Fri: fetches AI articles from Zenn/Qiita RSS and auto-generates reaction posts with URLs',
      'Sun: integrates with Google Trends API to generate trend-aware posts',
      'Per-category prompt design maintains a consistent author persona for followers',
    ],
    architecture: '/images/003_architecture.png',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public',
    tags: ['Serverless', 'Bedrock', 'EventBridge', 'X API'],
    services: ['Lambda', 'Amazon Bedrock', 'EventBridge Scheduler', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '💡',
    featured: true,
  },
  {
    slug: 'portfolio',
    number: '004',
    nameJa: 'ポートフォリオサイト',
    nameEn: 'Portfolio Site',
    descJa: 'Astro SSR + Lambda + CloudFrontで構築した日英2言語対応の動的ポートフォリオサイト。（このサイト）',
    descEn: 'Dynamic bilingual portfolio site built with Astro SSR + Lambda + CloudFront. (This site)',
    longDescJa: 'AstroのSSRモードとAPI Gateway + AWS Lambdaを組み合わせた動的サイト。CloudFrontをCDNとして使用し、静的アセットはS3から配信。月額ほぼ$0の低コスト運用を実現。日英2言語対応。',
    longDescEn: 'Dynamic site combining Astro SSR with API Gateway + AWS Lambda. CloudFront as CDN, static assets served from S3. Nearly $0/month operation cost. Bilingual Japanese/English support.',
    pointsJa: [
      'Organizations SCPによりLambda Function URLが403ブロックされる問題をAPI Gateway HTTP APIへの切り替えで解決',
      'CloudFrontで静的アセット（JS/CSS/画像）はS3から直接配信し、SSRリクエストのみLambdaへルーティング',
      'Zenn・note両方のRSSをサーバーサイドで並列取得し、最新記事をリアルタイム表示',
      'i18n設計で日本語・英語の2言語を単一コードベースで管理',
    ],
    pointsEn: [
      'Resolved 403 block on Lambda Function URL caused by Organizations SCP by switching to API Gateway HTTP API',
      'CloudFront routes static assets (JS/CSS/images) directly from S3; only SSR requests hit Lambda',
      'Server-side parallel RSS fetching from Zenn and note for real-time article display',
      'Single codebase manages both Japanese and English via i18n routing',
    ],
    architecture: '/images/004_architecture.png',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public',
    tags: ['Astro', 'SSR', 'CloudFront', 'Lambda'],
    services: ['Lambda', 'API Gateway', 'CloudFront', 'S3', 'CloudFormation'],
    emoji: '🌐',
    featured: true,
  },
  {
    slug: 'zenn-mid-article-bot',
    number: '005',
    nameJa: 'Zenn中級記事自動生成Bot',
    nameEn: 'Zenn Mid-Level Article Bot',
    descJa: 'AWS中級者向けの複合アーキテクチャ記事を毎月2回自動生成するシステム。16トピック対応。',
    descEn: 'Auto-generates intermediate AWS architecture articles twice monthly. Covers 16 topics.',
    longDescJa: '複合アーキテクチャ系8種＋ユースケース別8種の16トピックから重複なく選択。4,000〜6,000文字の記事にアーキテクチャ図2枚を添付。設計上の考慮ポイント（コスト・セキュリティ・スケーラビリティ）を追加セクション化し初級記事と差別化。',
    longDescEn: 'Selects from 16 non-repeating topics (8 composite architectures + 8 use cases). Attaches 2 architecture diagrams to 4,000-6,000 character articles. Differentiated from beginner articles with dedicated sections on design considerations (cost, security, scalability).',
    pointsJa: [
      '複合アーキテクチャ8種・ユースケース8種の計16トピックをSSMで履歴管理し重複を排除',
      '初級記事との差別化として「コスト最適化・セキュリティ・スケーラビリティ」の考慮点セクションを追加',
      'アーキテクチャ図をメイン構成図と詳細図の2種類生成し、記事の理解度を向上',
      '002の初級Botと設計を分離することで、読者層に応じた記事品質を独立してチューニング可能',
    ],
    pointsEn: [
      'Tracks 16-topic history (8 architectures + 8 use cases) in SSM to prevent repeats',
      'Adds dedicated sections on cost, security, and scalability to differentiate from beginner articles',
      'Generates 2 diagrams per article: an overview and a detailed view for better comprehension',
      'Decoupled from the beginner bot (002) to allow independent prompt tuning per audience level',
    ],
    architecture: '/images/005_architecture.png',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public',
    tags: ['SAM', 'Bedrock', 'S3', 'SES', 'matplotlib'],
    services: ['Lambda', 'Amazon Bedrock', 'S3', 'SES', 'SSM Parameter Store', 'SAM'],
    emoji: '🏗️',
    featured: true,
  },
];

export function getProjectBySlug(slug: string) {
  return projects.find((p) => p.slug === slug);
}
