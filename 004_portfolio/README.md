# 004_portfolio

AWS Lambda + API Gateway + CloudFront + S3 で構築した、Astro SSR 動的ポートフォリオサイト。日英2言語対応。

**サイトURL**: https://du7bbiecctrzb.cloudfront.net/ja/

---

## 概要

| 項目           | 内容                                                  |
| -------------- | ----------------------------------------------------- |
| フレームワーク | Astro 6.x（SSRモード）                                |
| 言語対応       | 日本語（`/ja/`）・英語（`/en/`）                      |
| ホスティング   | AWS Lambda + API Gateway HTTP API + CloudFront + S3   |
| 月額コスト     | ほぼ $0（Lambda/CloudFront 無料枠内）                 |
| IaC            | CloudFormation                                        |
| デプロイ       | `bash deploy.sh`（ビルド→Lambda更新→S3同期→CF無効化） |

---

## アーキテクチャ

```
ユーザー
  ↓ HTTPS
CloudFront (E33SJ6UEA95L47)
  ├─ /_astro/* → S3 (zer0-portfolio-s3) ← 静的アセット（長期キャッシュ）
  └─ /* → API Gateway HTTP API (Zer0-portfolio-api)
               ↓
           Lambda (Zer0-portfolio-ssr, Node.js 24.x)
               ↓
           Astro SSR (serverless-http + express + @astrojs/node)
```

### リクエストフロー

1. ブラウザが CloudFront にリクエスト
2. `/_astro/*`（CSS/JS）→ S3 から直接配信（`Cache-Control: immutable`）
3. それ以外のパス → API Gateway → Lambda → Astro SSR でレンダリング → HTML レスポンス

### 静的アセット vs SSR の分離

| パス                     | オリジン           | キャッシュ戦略                               |
| ------------------------ | ------------------ | -------------------------------------------- |
| `/_astro/*`              | S3                 | `public, max-age=31536000, immutable`（1年） |
| `/ja/*`, `/en/*`, その他 | API Gateway→Lambda | キャッシュ無効（毎回SSR）                    |

---

## ページ構成

| パス                                         | 内容                                            |
| -------------------------------------------- | ----------------------------------------------- |
| `/`                                          | `/ja/` へリダイレクト（デフォルトロケール）     |
| `/ja/`・`/en/`                               | トップページ（Hero・Stats・Projects・Articles） |
| `/ja/about`・`/en/about`                     | プロフィール・スキルスタック                    |
| `/ja/projects`・`/en/projects`               | プロジェクト一覧（5件）                         |
| `/ja/projects/[slug]`・`/en/projects/[slug]` | プロジェクト詳細                                |
| `/ja/articles`・`/en/articles`               | 最新記事（Zenn・note RSS取得）                  |
| `/ja/contact`・`/en/contact`                 | SNSリンク・名刺用QRコード                       |

---

## ディレクトリ構成

```
004_portfolio/
├── README.md
├── deploy.sh                # アプリデプロイスクリプト（通常使用）
├── lambda-deployment.zip    # デプロイ用zipキャッシュ（自動生成）
├── infra/
│   ├── cloudformation.yaml  # インフラ定義（S3/Lambda/API GW/CloudFront）
│   └── deploy-infra.sh      # インフラ構築スクリプト（初回のみ）
└── src/
    ├── astro.config.mjs     # Astro設定（SSR・i18n・Tailwind）
    ├── tailwind.config.mjs  # Tailwindカラー設定（ネイビー系）
    ├── package.json
    ├── lambda.mjs           # LambdaエントリーポイントI
    ├── .env                 # 環境変数（NOTE_RSS_URL・SITE_URL）
    ├── public/
    │   ├── favicon.svg
    │   └── 404.html
    └── src/
        ├── components/      # 共通コンポーネント
        │   ├── Nav.astro
        │   ├── Hero.astro
        │   ├── Footer.astro
        │   ├── StatsBar.astro
        │   ├── ProjectCard.astro
        │   └── ArticleCard.astro
        ├── layouts/
        │   └── BaseLayout.astro
        ├── pages/
        │   ├── index.astro          # /ja/ へリダイレクト
        │   ├── ja/                  # 日本語ページ群
        │   │   ├── index.astro
        │   │   ├── about.astro
        │   │   ├── articles.astro
        │   │   ├── contact.astro
        │   │   └── projects/
        │   │       ├── index.astro
        │   │       └── [slug].astro
        │   └── en/                  # 英語ページ群（jaと同構成）
        ├── data/
        │   ├── projects.ts          # プロジェクト定義データ
        │   └── links.ts             # SNSリンク・サイトURL
        └── i18n/
            ├── ui.ts                # 日英翻訳文字列定義
            └── utils.ts             # 言語判定ユーティリティ
```

---

## AWSリソース

| リソース                         | 名前・ID                                             |
| -------------------------------- | ---------------------------------------------------- |
| CloudFormationスタック           | `Zer0-portfolio`                                     |
| S3バケット                       | `zer0-portfolio-s3`                                  |
| Lambda関数                       | `Zer0-portfolio-ssr`（Node.js 24.x, 256MB, 30s）     |
| API Gateway                      | `Zer0-portfolio-api`（HTTP API, `$default`ステージ） |
| CloudFrontディストリビューション | `E33SJ6UEA95L47`                                     |
| CloudFrontドメイン               | `https://du7bbiecctrzb.cloudfront.net`               |
| IAMロール                        | `Zer0-portfolio-lambda-role-{AccountId}`             |
| リージョン                       | `ap-northeast-1`（東京）                             |

---

## 環境変数・設定

### `src/.env`

```env
SITE_URL=https://du7bbiecctrzb.cloudfront.net
NOTE_RSS_URL=https://note.com/zer0_infra/rss
```

### Lambda環境変数（deploy.shが自動設定）

| 変数名     | 値                                     |
| ---------- | -------------------------------------- |
| `SITE_URL` | `https://du7bbiecctrzb.cloudfront.net` |

---

## セットアップ手順

### 初回（インフラ構築）

```bash
cd /root/Zer0/004_portfolio/infra
bash deploy-infra.sh
```

実行後、出力された `CloudFrontUrl` を `src/.env` の `SITE_URL` に設定する。

### デプロイ（コード更新時）

```bash
cd /root/Zer0/004_portfolio
bash deploy.sh
```

内部で以下を自動実行：

1. `npm run build`（Astroビルド → `dist/` 生成）
2. `lambda.mjs` + `dist/server/` + 本番依存をzipに梱包
3. zip を S3 にアップロード
4. Lambda コードを S3 から更新（`update-function-code`）
5. Lambda 環境変数を更新（`SITE_URL`）
6. `dist/client/_astro/` を S3 に同期（長期キャッシュヘッダー付き）
7. CloudFront キャッシュを全パス無効化

### DRY RUN（設定確認のみ）

```bash
bash deploy.sh --dry-run
```

---

## ローカル開発

```bash
cd src
npm install
npm run dev
# → http://localhost:4321/ja/ で確認
```

---

## 技術選定の理由

### Astro SSR + Lambda

- **SSG不採用の理由**: RSSフィード（Zenn・note）をリアルタイム取得するため動的レンダリングが必要
- **Lambda選択理由**: アクセス頻度が低いポートフォリオに最適（コールドスタートは許容、月額コストほぼ$0）
- **API Gateway HTTP API**: Lambda Function URL は Organizations SCP により `AuthType: NONE` でも403になるため HTTP API を採用

### CloudFront + S3 分離

- `/_astro/*`（ハッシュ付きビルド成果物）は S3 から長期キャッシュ配信
- SSRページは毎回 Lambda で動的生成（キャッシュ無効）

### i18n設計

- Astro の組み込み i18n ルーティングを使用（`/ja/`・`/en/` プレフィックス）
- 翻訳文字列は `src/i18n/ui.ts` で一元管理

---

## 注意事項

- **Lambda Function URL 非対応**: AWS Organizations の SCP により `AuthType: NONE` の Lambda Function URL が 403 になる。API Gateway HTTP API 経由が必要（このアカウント固有の制約）
- **コールドスタート**: Lambda の初回リクエストは数秒かかる場合がある（`MemorySize: 256MB` で緩和）
- **CloudFront伝播**: デプロイ後のキャッシュ無効化完了まで約1〜2分かかる

---

## 関連プロジェクト

- **001_X_Auto_Poster**: AWSニュース自動投稿Bot
- **002_Zenn_Auto_Article_Bot**: Zenn初級記事自動生成Bot
- **003_X_AI_Bot**: AI活用術自動投稿Bot
- **005_Zenn_Mid_Article_Bot**: Zenn中級記事自動生成Bot
