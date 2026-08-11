# 004 Portfolio Site

> Astro SSR + Lambda + CloudFront で構築した日英2言語対応の動的ポートフォリオサイト。月額ほぼ$0のサーバーレス構成で Zenn/note の RSS をサーバーサイドで動的取得して表示。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20CloudFront%20%7C%20S3-orange)](https://aws.amazon.com)
[![Astro](https://img.shields.io/badge/Astro-SSR-FF5D01)](https://astro.build)
[![Site](https://img.shields.io/badge/サイト-www.zer0--infra.com-blue)](https://www.zer0-infra.com)
[![Cost](https://img.shields.io/badge/月額-~%240-green)](https://aws.amazon.com/pricing)

## 概要

| 項目           | 内容                                                   |
| -------------- | ------------------------------------------------------ |
| URL            | `https://www.zer0-infra.com`                           |
| フレームワーク | Astro（SSR / `output: 'server'` / Node.js adapter）    |
| 対応言語       | 日本語（`/ja/`）・英語（`/en/`）                       |
| ホスティング   | CloudFront + S3（静的） + API Gateway + Lambda（SSR）  |
| 動的コンテンツ | Zenn・note の RSS をリクエスト時にサーバーサイドで取得 |
| IaC            | CloudFormation（全リソース管理）                       |
| 月額コスト     | ~$0（Lambda・CloudFront 無料枠内）                     |

## アーキテクチャ

![アーキテクチャ図](../images/004_architecture.png)

```text
[ブラウザ] HTTPS
  └─▶ CloudFront（www.zer0-infra.com）
        ├─ /_astro/* → S3（CSS/JS/画像 / 長期キャッシュ）
        └─ /* → API Gateway → Lambda（Astro SSR）
                  └─ リクエスト時に Zenn/note RSS を並列取得
```

## 技術スタック

| レイヤー       | 技術                                                           |
| -------------- | -------------------------------------------------------------- |
| フレームワーク | Astro 6.x（SSR / `@astrojs/node` adapter）                     |
| スタイリング   | Tailwind CSS v4（`@tailwindcss/vite` プラグイン）              |
| 実行基盤       | AWS Lambda（Node.js 24.x / 256MB / 30秒）                      |
| API            | Amazon API Gateway HTTP API                                    |
| CDN            | Amazon CloudFront（静的: 1年キャッシュ / SSR: キャッシュ無効） |
| ストレージ     | Amazon S3（OAC 署名付きアクセス）                              |
| IaC            | CloudFormation                                                 |
| デプロイ       | `scripts/deploy.sh`（6ステップ自動化）                         |

## 実装のこだわり

### 1. Organizations SCP による Lambda Function URL 問題の解決

AWS Organizations の SCP（Service Control Policy）により Lambda Function URL が 403 ブロックされる環境だった。当初は Function URL で実装していたが、本番デプロイ時に初めて制約を発見。**API Gateway HTTP API に切り替え**ることで解決。この経験から「組織レベルのポリシーと Lambda 呼び出し方式の関係」を深く理解。

### 2. 静的アセット vs SSR の分離キャッシュ戦略

| パス        | オリジン | キャッシュ       | 理由                                 |
| ----------- | -------- | ---------------- | ------------------------------------ |
| `/_astro/*` | S3       | 1年（immutable） | ハッシュ付きファイル名のため変更不要 |
| `/images/*` | S3       | 1日              | 更新頻度が低い                       |
| `/*`（SSR） | API GW   | 無効             | Zenn/note RSS をリクエスト毎に取得   |

### 3. Zenn・note RSS の並列サーバーサイド取得

`Promise.allSettled()` で Zenn・note 両方の RSS フィードを並列取得。片方が失敗しても残りを表示できるよう Settled（成功・失敗両対応）で処理。クライアントサイドでの取得を避け、CORS 問題を排除。

### 4. i18n 設計（日英2言語）

Astro の `i18n` ルーティングを使用し、`/ja/` と `/en/` で全ページを提供。翻訳キー管理・言語切替 URL 生成・デフォルトロケールリダイレクトを単一コードベースで実装。

### 5. デプロイ自動化（6ステップ）

`scripts/deploy.sh` が以下を全自動化：

1. CloudFormation Outputs からリソース情報取得
2. Astro ビルド（SSR 用 Lambda コード生成）
3. Lambda ZIP 作成 + S3 アップロード
4. Lambda コード更新（`update-function-code`）
5. S3 静的アセット同期（キャッシュ設定付き）
6. CloudFront キャッシュ無効化 + 10ページの疎通確認

## ディレクトリ構成

```text
004_portfolio/
├── src/                         # Astro プロジェクト
│   ├── src/
│   │   ├── components/          # ProjectCard, ArticleCard 等
│   │   ├── data/projects.ts     # プロジェクト定義データ
│   │   ├── layouts/             # BaseLayout
│   │   └── pages/ja/, pages/en/ # 日英ページ
│   ├── public/images/           # アーキテクチャ図（001〜008）
│   ├── lambda.mjs               # CloudFront→Lambda ブリッジ
│   ├── astro.config.mjs
│   └── package.json
├── infra/
│   ├── cfn-portfolio.yaml
│   ├── certificate.yaml         # ACM（us-east-1）
│   └── deploy-infra.sh
├── scripts/
│   └── deploy.sh                # 6ステップ自動デプロイ
└── images/
    ├── 004_architecture.drawio  # 構成図（draw.ioで手動編集する一次情報源）
    └── 004_architecture.png     # 上記からエクスポートした画像（本ドキュメントで表示）
```

## セットアップ / デプロイ

```bash
# ローカル開発
cd src && npm install && npm run dev

# 初回インフラ構築（ACM証明書は us-east-1 先行デプロイ）
bash infra/deploy-infra.sh

# コード更新デプロイ（Lambda + S3 + CloudFront 無効化まで自動）
bash scripts/deploy.sh
```

## CFnテンプレート機能

実運用プロジェクトで使用している CloudFormation テンプレートを汎用化して公開。

- **64テンプレート** / 8カテゴリ（automation / compute / database / messaging / monitoring / network / security / storage）
- **GitHub 風 UI**: パンくず・行番号・ファイルサイズ・VS Code Dark Modern シンタックスハイライト
- **モバイル対応**: フルスクリーン3ステップ操作（カテゴリ → ファイル → コードビュー）
- **Env パラメータ**: `stg / dev / prd` の3環境対応。`prd` のみ DeletionPolicy=Retain・削除保護が有効
- **配信**: GitHub raw URL（AWS インフラ非経由）— `sync_to_public.sh` で自動 push

## AWSリソース一覧

| リソース    | 名前/ID                                                 |
| ----------- | ------------------------------------------------------- |
| CloudFront  | E33SJ6UEA95L47 / `https://du7bbiecctrzb.cloudfront.net` |
| S3 バケット | zer0-portfolio-s3                                       |
| Lambda      | Zer0-portfolio-ssr                                      |
| API Gateway | Zer0-portfolio-api                                      |
| ACM 証明書  | us-east-1（www.zer0-infra.com）                         |

## 変更履歴

直近1日分のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

### 2026-08-11

#### Fableコードレビューで検出した6件を修正

- **middleware.tsの単一障害点を解消**: SSM `GetParameter`呼び出しにtry/catchが無く、SSM側の一時障害・スロットリングが起きると全ページ(ja/en問わず)が500エラーになる作りだった。障害時は古いキャッシュ、無ければ管理者機能のみ無効化(`isAdmin=false`)してリクエスト自体は通すよう修正
- **deploy.shのLambda環境変数がSITE_URLのみで丸ごと置換される問題を修正**: `update-function-configuration --environment`はマージでなく置換の仕様のため、将来手動追加したenv varが次回デプロイで消える罠があった。既存の環境変数を`get-function-configuration`で取得しSITE_URLだけ上書きしてから渡す方式に変更
- **sitemap.xmlのlastmodが37日間ハードコードのまま放置されていた問題を修正**: 「デプロイ毎に手動更新」という運用が形骸化し検索エンジンへの更新シグナルが機能していなかった。`astro.config.mjs`の`vite.define`でビルド時刻を`__BUILD_DATE__`として焼き込み、以後は自動更新される
- **CloudFrontのDefaultCacheBehaviorから未使用のPUT/POST/PATCH/DELETEを削除**: `lambda.mjs`は`app.get`のみでこれらのメソッドのハンドラを持たないため、不要な攻撃面を減らす目的でAllowedMethodsをGET/HEAD/OPTIONSのみに縮小
- **未使用コンポーネントAvatarPicker.astroを削除**: どこからもimportされていないデッドコードで、かつCSP nonceが未付与の`<script>`タグを持っていた(将来使われるとv3.6と同じCSPブロック不具合が再発するリスクがあった)
- **cryptobot-stats.astroの古いコメントを修正**: 「Basic認証」という記述がv3.4のトークン方式への移行後も残っており保守者を誤誘導する状態だったため、現行方式を反映
- 検証: `npm run build`成功→`astro dev`で管理者トークン認証の3パターン(直接描画/Cookie発行/Cookie経由アクセス)・sitemap自動lastmod・保護ページ401を確認→CFn更新(AllowedMethods)→本番デプロイ→本番で同項目を再検証(200/401/lastmod一致)。S3・Lambda Layerに不要リソースなし
