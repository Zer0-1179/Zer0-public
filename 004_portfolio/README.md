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

![アーキテクチャ図](images/004_architecture.png)

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
│   ├── public/images/           # アーキテクチャ図（001〜007）
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
    └── 004_architecture.png
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

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                              |
| ---------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-03-15 | v1         | 初版リリース。Astro SSR + Lambda + CloudFront + S3                                                                                                                                                                                                                                |
| 2026-03-20 | v1.1       | API Gateway HTTP API に切り替え（Function URL SCP問題の回避）                                                                                                                                                                                                                     |
| 2026-04-01 | v1.2       | カスタムドメイン `www.zer0-infra.com` 設定完了                                                                                                                                                                                                                                    |
| 2026-04-10 | v1.3       | Templatesページ（VS Codeエクスプローラー風UIと22テンプレート）追加                                                                                                                                                                                                                |
| 2026-04-19 | v1.4       | 全62テンプレート公開完了。全カテゴリ（compute/database/messaging/monitoring/network/security/storage）対応                                                                                                                                                                        |
| 2026-05-30 | v1.5       | YAMLビューアーにVS Code Dark Modernシンタックスハイライト追加                                                                                                                                                                                                                     |
| 2026-05-30 | v1.6       | Templatesページ UI改善。GitHub風パンくず・行番号・モバイルフルスクリーン化                                                                                                                                                                                                        |
| 2026-05-31 | v1.7       | cfn-dynamodb-basic.yaml バグ修正（SSEType AES256 非対応→デフォルト暗号化に変更）。全62テンプレート実デプロイ検証完了                                                                                                                                                              |
| 2026-05-31 | v1.8       | Advanced全31テンプレート実デプロイ検証完了。cfn-elasticache.yaml バグ修正（EngineVersion 7.2未提供→7.1）。cfn-ecs-service.yaml CREATE_COMPLETE確認                                                                                                                                |
| 2026-06-02 | v1.9       | ZIPダウンロードにadvanced/beginnerサブフォルダ構造追加。全62テンプレートの論理ID・物理名にシーケンス番号（01）統一付与。EC2/RDS/NATにInstanceSuffix/DbSuffix/NatSuffixパラメータ追加                                                                                              |
| 2026-06-03 | v2.0       | Advanced全20テンプレートに設定可能な全プロパティをParameterとして追加（公式CFnドキュメント準拠で網羅性を担保）。CWアラーム・CW Logs・ALB/NLB・NAT・VPC・SG・IAM Role・KMS・S3・EFS・EBS の各テンプレートを網羅的に拡張                                                            |
| 2026-06-03 | v2.1       | cfn-alb.yaml バグ修正（AccessLogsEnabled=false 時に access_logs.s3.bucket が空文字のまま渡り AWS が拒否する問題を修正）。Advanced 全20テンプレートのデプロイ検証完了（グループC: ALB/NLB/EFS/EBS、グループD: NAT Gateway）                                                        |
| 2026-06-04 | v2.2       | 新テンプレート cfn-cw-alarm-auto-update.yaml・同-basic.yaml 追加（EC2/FSxリストア後のCloudWatch Alarm ID自動更新。Lambda+EventBridge構成）。monitoring フォルダを用途別（logs/ / alarms/ / automation/）に再編。AWS実機検証済み                                                   |
| 2026-06-05 | v2.3       | automation を独立した8番目のカテゴリに昇格。デスクトップツリーを difficulty-first に統一（ja/en）。sync_to_public.sh の --exclude=templates/ バグ修正。ほか breadcrumb 順序・yv-copy SVG 喪失・mob-code-view クラス欠落・lambda.mjs CSP ハッシュ同期を修正                        |
| 2026-06-10 | v2.4       | プロジェクト説明文（projects.ts）を各Botの最新仕様に同期（001/003 の投稿頻度・003 のカテゴリ構成・006 の監視間隔）。ルートREADMEのプロジェクト一覧（001/003の投稿頻度）も同様に修正                                                                                               |
| 2026-06-15 | v2.5       | 全62テンプレートをOpusでレビューし品質改善。バグ修正: cfn-alb/cfn-sg-egress/ingress の重複Descriptionキー・cfn-kms-basic のSidスペース・cfn-efs の DeletionPolicy 未設定・cfn-rds prd の Retain→Snapshot。ProjectName の Description 追加等の横断改善                             |
| 2026-06-15 | v2.6       | フロントエンド・Lambdaコードレビュー。①en/index.astro の RSS link パース不完全を修正 ②Footer.astro 外部リンクに `rel="noreferrer"` 追加 ③AvatarPicker.astro に 1 MB サイズ上限チェック追加 ④i18n キー追加で ja/en のハードコード文字列を置換                                      |
| 2026-06-15 | v2.7       | `infra/cfn-portfolio.yaml` の Lambda CloudWatch Logs 保持期間を 7 日→3 日に短縮（ログ保管コスト削減）。システム仕様書の CloudWatch Logs 行に保持期間 3 日を明記                                                                                                                   |
| 2026-06-27 | v2.8       | S3 ライフサイクル設定追加: `zer0-portfolio-s3` に旧バージョン 7 日後削除（直近 3 世代保持）＋未完了マルチパート 7 日後中断ルールを CFn で追加。既存の不要旧バージョン 2,448 件（約 12 GB）を一括削除。                                                                            |
| 2026-06-27 | v2.9       | fetch タイムアウト追加: ja/en articles.astro の RSS フェッチに 5 秒、`lambda.mjs` の GitHub Raw 取得 2 箇所に 10 秒のタイムアウトを追加。仕様書の CSP 記述を実 CFn（`connect-src`・`'nonce-fallback'`）に一致させた。                                                             |
| 2026-06-28 | v3.0       | フォントサイズ全体拡大: `global.css` に `html { font-size: 18px; }` を追加。デフォルト 16px → 18px（+12.5%）。`text-sm` 実質 16px・`text-base` 実質 18px となり視認性を向上。                                                                                                     |
| 2026-07-03 | v3.1       | **第2巡Fableレビュー HIGH修正**: ResponseHeadersPolicy が Content-Type を text/html に強制上書きし sitemap.xml 等が壊れるバグを修正。MEDIUM: テンプレートDLアイコンのインラインonclickをイベントリスナー方式に修正。S3配信3ビヘイビアにセキュリティヘッダー追加。本番実機検証済み |
| 2026-07-03 | v3.2       | **CSP nonce機構を実装**: 生成した nonce が未消費でハッシュのみに依存していた問題を修正。全6箇所のインラインスクリプトに nonce を付与し、`middleware.ts` の CSP を nonce ベースに簡素化。本番でnonce一致を実機検証済み                                                             |
| 2026-07-04 | v3.3       | **非公開トレード実績ページ追加**: /ja/cryptobot-stats を新設。Basic認証（SSM SecureString）で保護し、006 CryptoBotの非公開statsバケットをSSR Lambdaが直接読み込みSVG描画（新規API Gateway追加なし）。本番でBasic認証・空表示・実データ表示を実機検証済み                          |
| 2026-07-04 | v3.4       | **管理者Cookie方式に変更**: Basic認証を廃止し、007と同じ?admin=トークン→Cookie(365日,HttpOnly)方式に統一。Nav.astroに管理者限定リンク「CryptoBot実績」を追加（Cookie保持時のみ表示）。本番で全パターン実機検証済み                                                              |
| 2026-07-05 | v3.5       | Fableブラッシュアップ実装7件: 問い合わせフォームは現状維持、GitHub導線をサブディレクトリへ修正、StatsBar/Hero数字強化（テンプレート64本配布・EN版hero.sub資格数抜け修正）、Articles自動生成の透明性表記、hreflang/JSON-LD/OG画像/sitemap lastmodのSEOパック、テンプレートdeep link+検証済みバッジ、CloudWatch構造化ログでPV/DL計測（追加コストゼロ）。本番デプロイ・実機検証済み |
| 2026-07-05 | v3.6       | HIGH緊急修正: 全5箇所のnonce付きインラインscript（Nav/templates×4）がTypeScript構文（!非nullアサーション・as型キャスト等）のままブラウザへ送信され、SyntaxErrorでハンバーガーメニュー等が機能停止していた。動的nonce属性がAstroのTS変換をバイパスすると判明。esbuildで全script blockを再変換しプレーンJSへ修正。本番で構文検証・実機確認済み |
