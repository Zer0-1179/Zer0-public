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

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-03-15 | v1         | 初版リリース。Astro SSR + Lambda + CloudFront + S3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-03-20 | v1.1       | API Gateway HTTP API に切り替え（Function URL SCP問題の回避）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-04-01 | v1.2       | カスタムドメイン `www.zer0-infra.com` 設定完了                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 2026-04-10 | v1.3       | Templatesページ（VS Codeエクスプローラー風UIと22テンプレート）追加                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-04-19 | v1.4       | 全62テンプレート公開完了。全カテゴリ（compute/database/messaging/monitoring/network/security/storage）対応                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-30 | v1.5       | YAMLビューアーにVS Code Dark Modernシンタックスハイライト追加                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-30 | v1.6       | Templatesページ UI改善。GitHub風パンくず・行番号・モバイルフルスクリーン化                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-31 | v1.7       | cfn-dynamodb-basic.yaml バグ修正（SSEType AES256 非対応→デフォルト暗号化に変更）。全62テンプレート実デプロイ検証完了                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-05-31 | v1.8       | Advanced全31テンプレート実デプロイ検証完了。cfn-elasticache.yaml バグ修正（EngineVersion 7.2未提供→7.1）。cfn-ecs-service.yaml CREATE_COMPLETE確認                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-06-02 | v1.9       | ZIPダウンロードにadvanced/beginnerサブフォルダ構造追加。全62テンプレートの論理ID・物理名にシーケンス番号（01）統一付与。EC2/RDS/NATにInstanceSuffix/DbSuffix/NatSuffixパラメータ追加                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-06-03 | v2.0       | Advanced全20テンプレートに設定可能な全プロパティをParameterとして追加。公式CFnドキュメント準拠で網羅性を担保。主な追加: CWアラームにInsufficientDataAction/DatapointsToAlarm/ActionsEnabled/Tags、CW LogsにLogGroupClass/DeletionProtectionEnabled、ALBにIpAddressType/LoadBalancerAttributes/TargetGroupAttributes、NLBにcross-zone/preserve_client_ip、NATにprivate NAT対応（ConnectivityType）、VPCにInstanceTenancy、SGにIpProtocol拡張/CidrIpv6、IAM RoleにMaxSessionDuration/PermissionsBoundary/Path、KMSにMultiRegion/RotationPeriodInDays、S3にLoggingConfiguration/AccelerateConfiguration、EFSにLifecyclePolicies（IA/Archive/Primary）、EBSにSnapshotId/MultiAttachEnabled/AutoEnableIO |
| 2026-06-03 | v2.1       | cfn-alb.yaml バグ修正（AccessLogsEnabled=false 時に access_logs.s3.bucket が空文字のまま渡り AWS が拒否する問題を修正）。Advanced 全20テンプレートのデプロイ検証完了（グループC: ALB/NLB/EFS/EBS、グループD: NAT Gateway）                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-06-04 | v2.2       | 新テンプレート追加 + monitoring フォルダ再編。新テンプレート: cfn-cw-alarm-auto-update.yaml・cfn-cw-alarm-auto-update-basic.yaml（EC2/FSxリストア後のCloudWatch Alarm ID自動更新。Lambda+EventBridge構成。上級版はConditionsでEC2/FSx監視を個別ON/OFF可能）。monitoring フォルダを advanced/beginner から用途別（logs/ / alarms/ / automation/）に再編。AWS実機検証済み（2026-06-03）                                                                                                                                                                                                                                                                                                               |
| 2026-06-05 | v2.3       | automation を monitoring から独立した8番目のカテゴリに昇格（advanced/automation/ + beginner/automation/）。デスクトップツリーを difficulty-first（advanced/beginner → カテゴリ → ファイル）に統一（ja/en 両言語）。カテゴリページ（ja/en）の難易度グループ表示を修正。sync_to_public.sh の --exclude=templates/ バグ修正（Astro テンプレートページが GitHub に未同期だった問題を解消）。バグ修正: breadcrumb 順序（difficulty → category → filename）・yv-copy SVG 喪失・mob-code-view flex クラス欠落・lambda.mjs CSP ハッシュ同期                                                                                                                                                                 |
| 2026-06-10 | v2.4       | プロジェクト説明文（projects.ts）を各Botの最新仕様に同期。001: 投稿頻度を毎日→毎週月・木20時に修正、003: 投稿頻度を毎日→月・木・日に修正しカテゴリ構成を7カテゴリ→6カテゴリ+固定2枠（url_reaction/trend）に修正、006: 証拠金維持率の監視間隔を4時間毎→30分毎（Executor）に修正。ルートREADMEのプロジェクト一覧（001/003の投稿頻度）も同様に修正                                                                                                                                                                                                                                                                                                                                                     |
| 2026-06-15 | v2.5       | 全62テンプレートをOpusでレビューし品質改善。バグ修正: cfn-alb/cfn-sg-egress/cfn-sg-ingress の重複Descriptionキー（コンソール誤表示）・cfn-kms-basic のSidにスペース含みデプロイ失敗・cfn-efs の DeletionPolicy 未設定（データ消失リスク）・cfn-rds の prd DeletionPolicy を Retain→Snapshot。全ファイルへの横断改善: ProjectNameパラメータのDescription追加・セクションコメント説明文のCLAUDE.md標準文統一                                                                                                                                                                                                                                                                                          |
| 2026-06-15 | v2.6       | フロントエンド・Lambdaコードレビュー。修正①en/index.astro の RSS link パース不完全（`<link href="...">` 形式未対応）を ja/index.astro と統一。②Footer.astro の外部リンクに `rel="noreferrer"` 追加（リファラー漏洩防止）。③AvatarPicker.astro に 1 MB サイズ上限チェックを追加（localStorage 容量超過エラー防止）。④i18n に `section.projects.link` / `section.articles.link` キーを追加し ja/en index.astro のハードコード文字列を置換（一貫性向上）                                                                                                                                                                                                                                               |
| 2026-06-15 | v2.7       | `infra/cfn-portfolio.yaml` の Lambda CloudWatch Logs 保持期間を 7 日→3 日に短縮（ログ保管コスト削減）。システム仕様書の CloudWatch Logs 行に保持期間 3 日を明記                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-06-27 | v2.8       | S3 ライフサイクル設定追加: `zer0-portfolio-s3` に旧バージョン 7 日後削除（直近 3 世代保持）＋未完了マルチパート 7 日後中断ルールを CFn で追加。既存の不要旧バージョン 2,448 件（約 12 GB）を一括削除。 |
| 2026-06-27 | v2.9       | fetch タイムアウト追加: `ja/articles.astro`・`en/articles.astro` の RSS フェッチに 5 秒タイムアウト（`AbortSignal.timeout`）追加。`lambda.mjs` の GitHub Raw 取得 2 箇所に 10 秒タイムアウト追加。Lambda がスロー上流でブロックされるリスクを解消。仕様書の CSP 記述を実 CFn（`connect-src`・`'nonce-fallback'` 追記）に一致させた。 |
| 2026-06-28 | v3.0       | フォントサイズ全体拡大: `global.css` に `html { font-size: 18px; }` を追加。デフォルト 16px → 18px（+12.5%）。`text-sm` 実質 16px・`text-base` 実質 18px となり視認性を向上。 |
