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
| SSM Parameter Store | `/portfolio/cryptobot-stats-auth`（SecureString、CryptoBot実績ページの管理者認証値） |
| ACM 証明書  | us-east-1（www.zer0-infra.com）                         |

## 変更履歴

直近1日分のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

### 2026-08-20

#### CryptoBot非公開実績ページの勝率表示バグを修正

- `cryptobot-stats.astro`が決済レコード単位（TP1部分利確とトレーリングSL/損切りを別々の1件）で勝率を計算しており、正味は勝ちポジションでも小幅マイナスのレコードで1勝1敗に水増しされ、勝率が実態より低く表示される不具合があった
- 006側`stats.json`に`position_id`が出力されるよう修正した上で、astro側もポジション単位で正味損益を再集計するよう変更。表示ラベル「トレード数」も実態に合わせ「決済ポジション数」に変更
- 本番デプロイ後、実データで「決済ポジション数10件・勝率90.0%（9勝1敗）」が正しく表示されることを確認

#### プロジェクト詳細ページの構成図にライトボックス（拡大縮小）機能を追加

- サービス数増加で構成図が見づらいとの要望を受け、`ImageLightbox.astro`を新規作成。クリックで全画面表示→再クリックで2倍ズーム、Esc・背景クリック・閉じるボタンで閉じられる
- ja/en両方のプロジェクト詳細ページの「全体構成図」に適用。デプロイ後、本番ビルド限定の不具合2件（CSP nonce未付与でブロック／nonce付与でTypeScript変換バイパスにより構文エラー）が発覚しユーザー報告を受けて修正
- さらに「クリック2倍ズームだと同じ位置しか見えない」という指摘を受け、ホイールで連続ズーム（1〜5倍）＋拡大時ドラッグでパン移動できる方式に変更。実機（ヘッドレスChromium）でズーム・パンのCSS transform実測値とコンソールエラー無しを確認して本番デプロイ

#### サイト全体のユーザビリティ調査・改善

- 全ページ・コンポーネントを調査し改善候補をリスト化、優先度高4件（ナビ現在地表示・フォーカスリング・スキップリンク・404ページのクイックリンク）を実装
- 検証中、本番（Lambda経由）ではAstroの`mode:'middleware'`により未マッチルートが自動的に404.astroへフォールバックしない既存の潜在バグを発見。`lambda.mjs`に内部リライトのフォールバックを追加し修正（今回まで本番でカスタム404が実質表示されていなかった）。詳細は[CHANGELOG.md](./CHANGELOG.md)参照
