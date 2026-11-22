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
  architectureSvg: string;
  githubUrl?: string;
  siteUrl?: string;
  tags: string[];
  services: string[];
  emoji: string;
  featured: boolean;
  monthlyCost: string;
  // 公開日時（ISO8601、タイムゾーン付き）。この日時より前は管理者（Astro.locals.isAdmin）にしか
  // 表示しない。一覧・トップ・統計・サイトマップ・詳細ページのすべてがgetVisibleProjects()を通す。
  publishAt?: string;
};

const baseProjects: Project[] = [
  {
    slug: 'aws-x-poster',
    number: '001',
    nameJa: 'AWSニュース自動投稿Bot',
    nameEn: 'AWS News Auto-Poster',
    descJa: 'AWSの最新記事をRSSで取得し、Bedrockで口調を変換してXに毎週月・木20時に自動投稿するサーバーレスBot。',
    descEn: 'Serverless bot that fetches AWS news via RSS, converts tone with Bedrock, and auto-posts to X every Monday and Thursday at 20:00 JST.',
    longDescJa: [
      "AWS公式の日本語RSSから、インフラ運用者の目線で新機能を紹介する投稿を、毎週月・木の20時（週2回）にXへ自動送信するBot。月額約$0.45（約70円）で運用。",
      "【記事の選定】What's New・AWSブログから14日以内の記事を取得し、EC2・VPC・CloudWatch等のインフラ系サービスに絞る。重複は「URL完全一致 → キーワード → AWSサービス名」の3段階で除く。",
      "【投稿文の生成】Amazon Bedrock（Claude Haiku）で、①@Zer0_Infra の口調に変換 ②記事本文と照らして事実を確認、の2段階で投稿文を作る。「何が楽になるか・何に注意するか」の目線でまとめ、ハッシュタグも内容に合わせて生成する。",
      "【リーチ対策】記事URLは本文に入れず、投稿直後のリプライにぶら下げて、リンク付き投稿のリーチ抑制を避ける。",
      "【投稿タイプ】通常の紹介に加え、スレッド形式のTips連投（thread_tips）もローテーションに入れている。",
    ].join('\n\n'),
    longDescEn: [
      "A bot that auto-posts AWS updates to X from an infrastructure operator's perspective, every Monday and Thursday at 20:00 JST (twice a week), for about $0.45 a month.",
      "[Article selection] Fetches articles within 14 days from AWS official Japanese RSS (What's New and the AWS Blog), narrows them to infrastructure services such as EC2, VPC and CloudWatch, and removes duplicates in 3 stages (exact URL → keywords → AWS service name).",
      "[Post generation] Amazon Bedrock (Claude Haiku) writes each post in 2 steps: (1) rewrite in the @Zer0_Infra voice, (2) fact-check against the article body, focusing on what gets easier and what to watch out for. Hashtags are generated to match the content.",
      "[Reach] The article URL goes in a reply right after the post instead of the body, avoiding reach throttling on link posts.",
      "[Post types] Besides regular updates, a thread-format Tips post type (thread_tips) is part of the rotation.",
    ].join('\n\n'),
    pointsJa: [
      'AWS公式RSSからインフラ系サービスの記事だけを抽出し、14日以内・未投稿の記事を3段階のフィルタ（URL→キーワード→サービス名）で絞り込み',
      '記事URLは本文に入れず投稿直後のリプライにぶら下げ、リンク入り投稿のリーチ抑制を回避',
      'SSM Parameter Storeで投稿済みURLと投稿タイプを管理し、重複投稿を防止',
      'スレッド形式Tips連投（thread_tips）を投稿タイプに追加し、保存・フォロー転換を狙う',
    ],
    pointsEn: [
      'Extracts only infrastructure-service articles from AWS official RSS, then filters to unposted articles within 14 days using 3-stage deduplication (URL → keywords → service name)',
      'Hangs the article URL as a reply (not in the body) to avoid reach throttling on link posts',
      'Tracks posted URLs in SSM Parameter Store to prevent duplicate posts',
      'Added a thread-format Tips post type (thread_tips) to drive saves and follows',
    ],
    architecture: '/images/001_architecture.png',
    architectureSvg: '/images/001_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/001_x-poster-zer0-infra',
    tags: ['Serverless', 'Bedrock', 'EventBridge', 'X API'],
    services: ['Lambda', 'Amazon Bedrock', 'EventBridge', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '🤖',
    featured: false,
    monthlyCost: '~$0.45',
  },
  {
    slug: 'zenn-article-bot',
    number: '002',
    nameJa: 'Zenn初級記事自動生成Bot',
    nameEn: 'Zenn Beginner Article Bot',
    descJa: 'AWSの新機能の発表を初学者向けに紹介する4,000文字程度の記事を、毎月2回（第1・第3木曜）自動生成してS3に保存するシステム。',
    descEn: 'Auto-generates ~4,000-character articles introducing new AWS features for beginners twice monthly (1st & 3rd Thursday) and saves them to S3.',
    longDescJa: [
      "AWSの新機能の発表を、初学者向けに紹介する4,000文字程度のZenn記事を、毎月2回（第1・第3木曜）自動生成するBot。",
      "【ネタ元】AWS公式「最新情報」RSS（日本語版）から新機能の発表を選ぶ。対象の発表が無いときだけ、定番サービスの解説記事（28トピック×切り口4種）で生成する。",
      "【記事の生成】Amazon Bedrockで、見出しを「はじめに・ポイント（小見出し5つ）・まとめ」に固定して書かせる。根拠は発表本文とリンク先の公式ドキュメントだけに絞り、出典リンクはコードで付ける。",
      "【重複防止】使用済みの発表URL（直近60件）とトピック（直近20件）をSSM Parameter Storeに記録し、同じ内容を繰り返さない。",
      "【品質チェック】文字数・Zenn記法を機械でチェックし、問題があれば通知メールで警告する。記事はS3に保存し、SESで完成を知らせる。月額約$0.04（約6円、実測）。",
    ].join('\n\n'),
    longDescEn: [
      "A bot that auto-generates ~4,000-character Zenn articles introducing new AWS features for beginners, twice a month (1st and 3rd Thursday).",
      "[Source] Picks a new-feature announcement from the AWS official \"What's New\" RSS (Japanese). Only when no suitable announcement exists does it fall back to a classic service explainer (28 topics × 4 angles).",
      "[Generation] Amazon Bedrock writes with fixed headings (Intro / five Key Points / Summary), grounded only in the announcement and the official docs it links to. The source link is added by code.",
      "[Deduplication] The last 60 announcement URLs and 20 topics are recorded in SSM Parameter Store so content is not repeated.",
      "[Quality checks] Length and Zenn syntax are checked automatically, and issues are flagged in the notification email. Articles are saved to S3 and announced via SES. About $0.04 a month (measured).",
    ].join('\n\n'),
    pointsJa: [
      'AWS公式「最新情報」RSSから新機能の発表を選び、発表本文と公式ドキュメントだけを根拠に記事を生成。出典リンクはコードで付与',
      '使用済みの発表URL・トピックをSSMで管理し、同じ内容の繰り返しを防止',
      '文字数指示をプロンプト冒頭に置き見出しを固定することで、LLMの記事の長さと構成を制御',
      '文字数・Zenn記法の機械チェックを行い、問題があれば通知メールで警告。S3への保存とSESでの完成通知まで全自動',
    ],
    pointsEn: [
      'Picks new-feature announcements from the AWS official What\'s New RSS and grounds each article only in the announcement and official docs; the source link is added by code',
      'Tracks used announcement URLs and topics in SSM to prevent repeating the same content',
      'Controls LLM article length and structure by putting the length rule first in the prompt and fixing the headings',
      'Automatically checks length and Zenn syntax and flags issues in the notification email; fully automated through S3 storage and SES notification',
    ],
    architecture: '/images/002_architecture.png',
    architectureSvg: '/images/002_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/002_zenn-article-bot',
    tags: ['CloudFormation', 'Bedrock', 'S3', 'SES'],
    services: ['Lambda', 'Amazon Bedrock', 'S3', 'SES', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '📝',
    featured: false,
    monthlyCost: '~$0.04',
  },
  {
    slug: 'x-ai-bot',
    number: '003',
    nameJa: 'AI活用術自動投稿Bot',
    nameEn: 'AI Tips Auto-Poster',
    descJa: '「コピペで使えるAI活用の具体」を会社員目線で発信するXBot。プロンプトレシピ・実録・比較・失敗談の4カテゴリ＋副業・問いかけ＋固定2枠で構成。反応が伸びず現在は投稿を一時停止中。',
    descEn: 'X bot posting practical AI tips (copy-paste ready) for office workers. 4 practical categories plus side hustle, Q&A, and 2 fixed slots. Currently paused due to low engagement.',
    longDescJa: [
      "「コピペで使えるAI活用の具体」を会社員目線で発信するXのBot。週3回（月・木20:00、日10:00）実行し、1回に1〜3件を投稿する。月額約$0.38（約57円）。全投稿に持ち帰れる具体を1つ入れる実用路線。反応が伸びず、現在は投稿を一時停止している。",
      "【カテゴリ】recipe・jissoku・hikaku・shippai・fukugyo・questionの6カテゴリを、直近4投稿で重複しないようにローテーションする。",
      "【曜日ごとの枠】木曜はquestion固定。月曜は50%の確率でZenn/QiitaのAI記事の感想をURL付きで投稿し、日曜はGoogle Trendsと連動する。生成はAmazon Bedrock（Claude Haiku 4.5、temperature 0.95）。",
      "【文体】カテゴリごとにプロンプトを分け、一貫したキャラクターとして発信する。",
    ].join('\n\n'),
    longDescEn: [
      "An X bot sharing copy-paste-ready AI tips from an office worker's perspective. It runs 3 times a week (Mon/Thu 20:00, Sun 10:00 JST), posting 1–3 items per run, for about $0.38 a month. Every post includes one practical takeaway. Currently paused due to low engagement.",
      "[Categories] Rotates six categories (recipe, jissoku, hikaku, shippai, fukugyo, question) without repeating within the last four posts.",
      "[Weekly slots] Thursday is always question. On Monday there is a 50% chance of a reaction post to a Zenn/Qiita AI article with its URL, and Sunday follows Google Trends. Generated with Amazon Bedrock (Claude Haiku 4.5, temperature 0.95).",
      "[Voice] Separate prompts per category keep a consistent persona.",
    ].join('\n\n'),
    pointsJa: [
      '6カテゴリの投稿履歴をSSMで管理し、直近4件で同カテゴリが連続しないようローテーション',
      '月曜は50%の確率でZenn/QiitaのRSSからAI関連記事を取得してURL付き感想ツイートを自動生成',
      '日曜はGoogle Trends APIと連動し、トレンドワードに合わせた投稿を自動作成',
      'カテゴリごとに専用プロンプトを設計し、読者に一貫したキャラクターとして認識させる',
    ],
    pointsEn: [
      'Tracks 6-category history in SSM to prevent the same category within 4 consecutive posts',
      'Mon: 50% chance to fetch AI articles from Zenn/Qiita RSS and auto-generate reaction posts with URLs',
      'Sun: integrates with Google Trends API to generate trend-aware posts',
      'Per-category prompt design maintains a consistent author persona for followers',
    ],
    architecture: '/images/003_architecture.png',
    architectureSvg: '/images/003_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/003_x-poster-zer0-0326',
    tags: ['Serverless', 'Bedrock', 'EventBridge', 'X API'],
    services: ['Lambda', 'Amazon Bedrock', 'EventBridge Scheduler', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '💡',
    featured: false,
    monthlyCost: '~$0.38',
  },
  {
    slug: 'portfolio',
    number: '004',
    nameJa: 'ポートフォリオサイト',
    nameEn: 'Portfolio Site',
    descJa: 'Astro SSR + Lambda + CloudFrontで構築した日英2言語対応の動的ポートフォリオサイト。（このサイト）',
    descEn: 'Dynamic bilingual portfolio site built with Astro SSR + Lambda + CloudFront. (This site)',
    longDescJa: [
      "AstroのSSRとAPI Gateway HTTP API + AWS Lambdaで動く、日英2言語対応の動的ポートフォリオサイト（このサイト）。",
      "【配信】CloudFrontをCDNにし、静的アセット（JS/CSS/画像）はS3から直接配信する。SSRのリクエストだけをLambdaへ送る。",
      "【動的コンテンツ】Zenn・noteのRSSをサーバー側で並列取得し、最新記事を表示する。",
      "【多言語】日本語・英語の2言語を1つのコードベースで管理する。",
      "【費用】月額ほぼ$0で運用している。",
    ].join('\n\n'),
    longDescEn: [
      "A bilingual (Japanese/English) dynamic portfolio site running on Astro SSR with API Gateway HTTP API + AWS Lambda (this site).",
      "[Delivery] CloudFront is the CDN; static assets (JS/CSS/images) are served straight from S3, and only SSR requests go to Lambda.",
      "[Dynamic content] Fetches Zenn and note RSS feeds in parallel on the server to show the latest articles.",
      "[i18n] Japanese and English are managed in a single codebase.",
      "[Cost] Runs for nearly $0 per month.",
    ].join('\n\n'),
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
    architectureSvg: '/images/004_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/004_portfolio',
    tags: ['Astro', 'SSR', 'CloudFront', 'Lambda'],
    services: ['Lambda', 'API Gateway', 'CloudFront', 'S3', 'CloudFormation'],
    emoji: '🌐',
    featured: true,
    monthlyCost: '$0',
  },
  {
    slug: 'zenn-mid-article-bot',
    number: '005',
    nameJa: 'Zenn中級記事自動生成Bot',
    nameEn: 'Zenn Mid-Level Article Bot',
    descJa: 'AWS中級者向けに、複数サービスを組み合わせた構成を短時間で試せるハンズオン記事を毎月2回自動生成するシステム。24トピック対応。定期生成は2027年1月まで一時停止中。',
    descEn: 'Auto-generates short hands-on articles on multi-service AWS architectures for intermediate users twice monthly. Covers 24 topics. Scheduled generation is paused until January 2027.',
    longDescJa: [
      "AWS中級者向けに、複数サービスを組み合わせた構成を短時間で試せるハンズオン記事を、毎月1日・15日に自動生成するBot。月額約$0.13（約20円、稼働時）。定期生成は2027年1月まで一時停止中。",
      "【トピック】複合アーキテクチャ系12種＋ユースケース別12種の24トピックから、重複しないように選ぶ。",
      "【記事の生成】Claude Sonnet 4.6で、文章1,000文字程度＋3〜4ステップのハンズオン（動作確認・クリーンアップ付き）を書かせる。",
      "【記事の長さ】「長い記事は読まれない」という判断から、構成と流れ・ハンズオンに絞った短い形式にしている。",
    ].join('\n\n'),
    longDescEn: [
      "A bot that auto-generates short hands-on articles on multi-service AWS architectures for intermediate users on the 1st and 15th of each month, for about $0.13 a month when running. Scheduled generation is paused until January 2027.",
      "[Topics] Picks without repetition from 24 topics: 12 composite architectures and 12 use cases.",
      "[Generation] Claude Sonnet 4.6 writes about 1,000 characters of prose plus a 3–4 step hands-on with verification and cleanup.",
      "[Length] Because long articles tend not to be read, the format stays short and focused on the architecture flow and the hands-on.",
    ].join('\n\n'),
    pointsJa: [
      'Claude Sonnet 4.6 で、文章1,000文字程度＋短いハンズオンの記事を生成',
      '複合アーキテクチャ12種・ユースケース12種の計24トピックをSSMで履歴管理し重複を排除',
      'コードを除いた文章の文字数を機械チェックし、長すぎ・短すぎを通知メールで警告',
      '002の初級Botと設計を完全分離し、読者層に応じたモデル・プロンプトを独立してチューニング可能',
    ],
    pointsEn: [
      'Uses Claude Sonnet 4.6 to generate ~1,000 characters of prose plus a short hands-on',
      'Tracks 24-topic history (12 architectures + 12 use cases) in SSM to prevent repeats',
      'Automatically checks prose length (excluding code) and flags too long or too short articles by email',
      'Fully decoupled from bot 002 to allow independent model and prompt tuning per audience',
    ],
    architecture: '/images/005_architecture.png',
    architectureSvg: '/images/005_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/005_zenn-mid-article-bot',
    tags: ['CloudFormation', 'Bedrock', 'S3', 'SES'],
    services: ['Lambda', 'Amazon Bedrock', 'S3', 'SES', 'SSM Parameter Store', 'CloudFormation'],
    emoji: '🏗️',
    featured: false,
    monthlyCost: '~$0.13',
  },
  {
    slug: 'cryptobot',
    number: '006',
    nameJa: '仮想通貨自動売買Bot',
    nameEn: 'Crypto Trading Bot',
    descJa: 'Binanceのシグナルを使いbitbank信用取引でBTC/ETH/SOLをロング・ショート両方向に4時間ごとに自動売買。トレーリングSLと動的サイジングで利益を追求するサーバーレスBot。',
    descEn: 'Serverless bot that trades BTC/ETH/SOL on bitbank margin (long & short) every 4 hours using Binance signals, trailing stop-loss, and dynamic position sizing.',
    longDescJa: [
      "Binanceのシグナルを使い、bitbankの信用取引（レバレッジ最大2倍）でBTC/ETH/SOLをロング・ショート両方向に自動売買するサーバーレスBot。分析は4時間ごと、注文の執行は30分ごと。AWS費用は無料枠内で$0。",
      "【エントリー】BTCの200EMAで市場の方向（ロング/ショート）を決め、Supertrendの転換・出来高の増加・遅いSupertrendとの方向一致がそろったときだけエントリーする。",
      "【利確・損切り】TP1（ATR×1.25）で30%を早めに利確し、残り70%はトレーリングSL（ATR×0.75）で含み益を守る。",
      "【取引方法】信用取引を使い、ロング・ショートの両方向で機会をとらえる。同時に持つのは最大2つ（1件＝資金の60%、各コイン1つまで）。",
      "【バックテスト】5年分・公式手数料込みで、勝率71.6%／PF 1.11／資本成長+9.7%（LUNA崩壊・FTX破綻を含む）。自動テストは137件。",
    ].join('\n\n'),
    longDescEn: [
      "A serverless bot that trades BTC/ETH/SOL both long and short with bitbank margin trading (up to 2x leverage), using Binance signals. Analysis runs every 4 hours and order execution every 30 minutes; AWS cost stays at $0 within the free tier.",
      "[Entry] BTC's 200EMA sets the market direction (long/short); it enters only when Supertrend flips, volume rises, and a slower Supertrend agrees on direction.",
      "[Exits] TP1 (ATR×1.25) takes 30% early, and the remaining 70% rides a trailing stop (ATR×0.75) to protect gains.",
      "[Trading] Margin trading captures opportunities in both directions, holding at most 2 positions at once (each 60% of capital, one per coin).",
      "[Backtest] Over 5 years with official fees: 71.6% win rate / PF 1.11 / +9.7% capital growth (including the LUNA and FTX crashes). 137 automated tests.",
    ].join('\n\n'),
    pointsJa: [
      'BTC 200EMAで市場方向を判定し、上昇相場はロング・下落相場はショートに自動切替',
      'Supertrend転換 + Volume増加 + ダブルSupertrend方向一致の3条件で偽シグナルを徹底排除',
      'TP1（ATR×1.25）で早期利確後にトレーリングSL（ATR×0.75）へ移行し含み益を最大限確保',
      '証拠金維持率を30分毎に監視し、危険水準で自動成行決済・24h未約定キャンセル・注文存在リトライで無人運用を実現',
    ],
    pointsEn: [
      'BTC 200EMA auto-selects direction: long in bull markets, short in bear markets',
      'Triple filter (Supertrend flip + volume spike + dual-Supertrend confirmation) eliminates false signals',
      'TP1 at ATR×1.25 for early profit; tight trailing stop at ATR×0.75 locks in gains on strong trends',
      'Monitors margin ratio every 30 min with auto emergency-close; 24h cancel, order-verify retry, and SSM state enable unattended operation',
    ],
    architecture: '/images/006_architecture.png',
    architectureSvg: '/images/006_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/006_zer0-cryptobot',
    tags: ['Trading Bot', 'Binance', 'bitbank', 'Supertrend'],
    services: ['Lambda', 'EventBridge Scheduler', 'SSM Parameter Store', 'SES', 'SQS', 'CloudFormation'],
    emoji: '📈',
    featured: true,
    monthlyCost: '$0',
  },
  {
    slug: 'touring-app',
    number: '007',
    nameJa: 'バイクツーリングPWA',
    nameEn: 'Bike Touring PWA',
    descJa: '現在地と天気からAIが日帰りツーリングコースを3つ提案するPWA。片道・往復時間・帰路提案・特徴タグ・Googleマップナビ・OGP付きURL短縮シェアまでをBedrock一括生成。',
    descEn: 'PWA suggesting 3 day-trip motorcycle routes from current location and weather. Bedrock generates one-way/round-trip times, return routes, feature tags, Google Maps navigation, and OGP-enabled short URL sharing in one shot.',
    longDescJa: [
      "現在地と天気から、AIが日帰りツーリングコースを3つ提案するPWA。",
      "【コース生成】GPS取得 → Open-Meteoの天気 → Bedrock（Claude Haiku）の3ステップで自動生成する。",
      "【コースの表示】初級（往復20〜49km）・中級（50〜99km）・上級（100〜300km）の3コースを、景観シルエット付きのカードでスワイプ表示する。距離と走行時間はGoogle Routes APIの実際の道路で計算する。",
      "【詳細画面】Wikipediaの写真、現在地と目的地の天気比較、7日間の週間予報（最高/最低気温）、行き・帰りの立ち寄りスポット、帰路の提案、Googleマップのナビ（waypointはジオコード座標で指定）。",
      "【シェア】POST /api/share でDynamoDBに保存し、Lambdaが /s/{id} にOGPタグ付きのHTMLを返すことで、SNSのプレビューに対応する。",
      "【費用と制限】DynamoDBでIPごと・1日3回のレート制限。Astro static + CloudFront + S3 + Lambda + DynamoDBのサーバーレス構成で、1回約$0.005（約0.7円）、月100回利用で約$0.40。",
    ].join('\n\n'),
    longDescEn: [
      "A PWA where AI suggests three day-trip motorcycle routes from your current location and the weather.",
      "[Route generation] Three steps: GPS → Open-Meteo weather → Bedrock (Claude Haiku).",
      "[Route display] Beginner (20–49 km round trip), intermediate (50–99 km) and advanced (100–300 km) routes appear as swipeable cards with landscape silhouettes; distance and riding time come from real roads via the Google Routes API.",
      "[Detail view] Wikipedia photos, current vs. destination weather, a 7-day forecast with highs and lows, outbound/return stops, return-route suggestions, and Google Maps navigation with geocoded waypoints.",
      "[Sharing] POST /api/share stores data in DynamoDB, and Lambda serves /s/{id} as OGP-tagged HTML for SNS previews.",
      "[Cost & limits] DynamoDB rate limiting at 3 requests per IP per day. A serverless Astro static + CloudFront + S3 + Lambda + DynamoDB stack at about $0.005 per request, or about $0.40 for 100 uses a month.",
    ].join('\n\n'),
    pointsJa: [
      'GPS・天気・AI生成の3ステップをリアルタイムのローディング画面で可視化し、待ち時間のストレスを軽減',
      'Bedrock Claude Haikuが特徴タグ・ルートサマリー・片道/往復時間・行き/帰り立ち寄りスポット・帰路提案を一括生成',
      'Astro static PWA + CloudFront + S3 + Lambda の構成で月額 ~$0.40、1リクエスト ~$0.005 の超低コスト運用',
      'URL短縮+OGP（Lambda /s/{id} でSNSプレビュー対応）・DynamoDB IP別レートリミット・Nominatim waypointジオコードなどスマホ向けUXを徹底実装',
    ],
    pointsEn: [
      'Real-time 3-step loading indicator (GPS → weather → AI) reduces perceived wait time',
      'Claude Haiku generates feature tags, route summary, one-way/round-trip times, outbound/return stops, and return-route suggestions in one call',
      'Astro static PWA + CloudFront + S3 + Lambda: ~$0.40/month, ~$0.005 per request',
      'URL shortening + OGP via Lambda /s/{id} for SNS previews; DynamoDB IP-based rate limiting; Nominatim waypoint geocoding with direction filter',
    ],
    architecture: '/images/007_architecture.png',
    architectureSvg: '/images/007_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/007_zer0-touring-app',
    siteUrl: 'https://touring.zer0-infra.com',
    tags: ['PWA', 'Bedrock', 'Astro', 'GPS'],
    services: ['Lambda', 'API Gateway', 'Amazon Bedrock', 'CloudFront', 'S3', 'DynamoDB', 'CloudFormation'],
    emoji: '🏍️',
    featured: true,
    monthlyCost: '~$0.40',
  },
  {
    slug: 'bid-watch',
    number: '008',
    nameJa: '入札情報ウォッチ',
    nameEn: 'Bid Info Watch',
    descJa: '横浜市の入札公告を自動収集し、清掃・ビルメンテナンス業向けにメール/LINEで通知するサブスクサービス。二重オプトイン・バウンス対応・Stripe決済連携まで実装したサービス。テスト運用を経て現在は一時停止中。',
    descEn: 'Auto-collects Yokohama city bid announcements and notifies cleaning/building-maintenance businesses via email/LINE. Subscription service with double opt-in, bounce handling, and Stripe billing. Currently paused after a pilot run.',
    longDescJa: [
      "横浜市の入札公告を毎日6時に集め、清掃・ビルメンテナンス業向けにメールまたはLINEで通知するサブスクサービス（月額3,000円を予定）。初期30万円＋年約77万円の大手サービスに手が届かない中小企業・個人事業主を想定した。個人運営のパイロットとして横浜市だけで実証し、現在は一時停止している。",
      "【収集】横浜市の入札サイトを毎日巡回し、清掃・ビルメンテナンス関連の11キーワードに合う案件を、対象業種の購読者へ通知する。",
      "【メール配信】二重オプトイン・ワンクリック配信停止・SESのバウンス/苦情での自動停止・honeypotで、到達性と法令対応を両立する。",
      "【LINE通知】LIFFで友だち追加とアカウント連携を1画面で完結させる。ブロックされたらWebhookで自動的に配信を止める。",
      "【決済】Stripe Webhookで決済状態と購読者情報を突き合わせる。特定商取引法に基づく表記・利用規約ページも整備した。",
    ].join('\n\n'),
    longDescEn: [
      "A subscription service (planned at ¥3,000/month) that collects Yokohama city bid announcements daily at 6:00 JST and notifies cleaning and building-maintenance businesses by email or LINE. Aimed at small firms priced out of the leading service (¥300,000 upfront plus about ¥770,000 a year). Run solo as a pilot in Yokohama only; currently paused.",
      "[Collection] Crawls the Yokohama city bid site daily and notifies subscribers of matches against 11 cleaning/maintenance keywords.",
      "[Email] Double opt-in, one-click unsubscribe, automatic unsubscribe on SES bounces/complaints, and a honeypot balance deliverability and compliance.",
      "[LINE] A LIFF flow completes friend-add and account linking on one screen, and a webhook stops delivery automatically when the user blocks the account.",
      "[Billing] Stripe webhooks reconcile payment status with subscriber records. Required Japanese commercial-law disclosures and terms pages are included.",
    ].join('\n\n'),
    pointsJa: [
      '二重オプトイン・ワンクリック配信停止・SESバウンス/苦情の自動配信停止で法令対応と到達性を両立',
      'LINE通知をメールと並列の選択肢として追加。LIFFで友だち追加とアカウント連携を1画面完結、ブロック時はWebhookで自動配信停止',
      'Stripe Webhookで決済完了/解約イベントを自前HMAC署名検証し、課金者と購読者情報を自動突合',
      '横浜市の入札サイトを日次巡回し、清掃・ビルメンテナンス関連の11キーワードでマッチした案件を抽出。詳細ページから参加資格・締切日数等の付加情報も取得して通知に反映',
    ],
    pointsEn: [
      'Double opt-in, one-click unsubscribe, and automatic unsubscribe on SES bounce/complaint balance compliance and deliverability',
      'Added LINE as a parallel notification channel; a LIFF flow combines friend-add and account linking in one screen, with webhook-driven auto-unsubscribe on block',
      'Stripe webhooks with self-verified HMAC signatures reconcile checkout/cancellation events against subscriber records automatically',
      'Daily crawler scans the Yokohama city bid site, filters matches against 11 cleaning/maintenance keywords, and enriches notifications with eligibility and deadline details pulled from detail pages',
    ],
    architecture: '/images/008_architecture.png',
    architectureSvg: '/images/008_architecture.svg',
    githubUrl: 'https://github.com/Zer0-1179/Zer0-public/tree/main/008_nyusatsu-notify-bot',
    tags: ['Subscription', 'LINE API', 'Stripe', 'SES'],
    services: ['Lambda', 'API Gateway', 'DynamoDB', 'EventBridge', 'SSM Parameter Store', 'SES', 'CloudFront', 'S3', 'CloudFormation'],
    emoji: '📋',
    featured: false,
    monthlyCost: '~$0.5',
  },
];

// 公開予約中のプロジェクトは projects-extra/ に1件1ファイルで置く。公開日時までは
// sync_to_public.sh のEMBARGO_RULESで公開リポジトリから除外されるため、ファイルが
// 無くてもビルドできるよう import.meta.glob で読み込む（無ければ空になる）。
const extraModules = import.meta.glob<{ default: Project; careerJa?: CareerItem; careerEn?: CareerItem }>(
  './projects-extra/*.ts',
  { eager: true },
);

// 自己紹介ページの職務経歴の1件。公開予約中のプロジェクトに付随する経歴も projects-extra/ に置く
export type CareerItem = {
  period: string;
  title: string;
  desc: string[];
  tags: string[];
  link?: { href: string; label: string };
  publishAt?: string;
};

// projects-extra/ の経歴のうち、表示してよいもの（管理者は予約中も含む）を新しい順で返す
export function getExtraCareer(lang: 'ja' | 'en', isAdmin: boolean): (CareerItem & { scheduledAt: string | null })[] {
  return Object.values(extraModules)
    .map((m) => (lang === 'ja' ? m.careerJa : m.careerEn))
    .filter((c): c is CareerItem => !!c)
    .filter((c) => isAdmin || !c.publishAt || Date.now() >= new Date(c.publishAt).getTime())
    .sort((a, b) => b.period.localeCompare(a.period))
    .map((c) => ({
      ...c,
      scheduledAt: c.publishAt && Date.now() < new Date(c.publishAt).getTime()
        ? new Date(c.publishAt).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
        : null,
    }));
}

// 並び順は番号の昇順（追加は末尾、途中挿入しない）
export const projects: Project[] = [
  ...baseProjects,
  ...Object.values(extraModules).map((m) => m.default),
].sort((a, b) => a.number.localeCompare(b.number));

export function isPublished(p: Project, now: Date = new Date()): boolean {
  return !p.publishAt || now.getTime() >= new Date(p.publishAt).getTime();
}

// 管理者には公開予約中のものも含めて全件、それ以外には公開済みのものだけを返す
export function getVisibleProjects(isAdmin: boolean): Project[] {
  return isAdmin ? projects : projects.filter((p) => isPublished(p));
}

export function getProjectBySlug(slug: string, isAdmin = false) {
  return getVisibleProjects(isAdmin).find((p) => p.slug === slug);
}

// '~$0.7'・'$0' などの表記から数値を足し合わせ、'~$2.1' の形で返す
export function sumMonthlyCost(list: Project[]): string {
  const total = list.reduce((acc, p) => acc + (parseFloat(p.monthlyCost.replace(/[^0-9.]/g, '')) || 0), 0);
  return `~$${total.toFixed(1)}`;
}

// 管理者向けの「公開予約」表示（例: 2026/12/05 17:00）。日本時間で表示する
export function formatPublishAt(p: Project): string | null {
  if (!p.publishAt || isPublished(p)) return null;
  return new Date(p.publishAt).toLocaleString('ja-JP', {
    timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}
