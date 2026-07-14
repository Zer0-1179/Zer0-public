# 004_portfolio 変更履歴

### 2026-03-15

- **v1**: 初版リリース。Astro SSR + Lambda + CloudFront + S3

### 2026-03-20

- **v1.1**: API Gateway HTTP API に切り替え（Function URL SCP問題の回避）

### 2026-04-01

- **v1.2**: カスタムドメイン `www.zer0-infra.com` 設定完了

### 2026-04-10

- **v1.3**: Templatesページ（VS Codeエクスプローラー風UIと22テンプレート）追加

### 2026-04-19

- **v1.4**: 全62テンプレート公開完了。全カテゴリ（compute/database/messaging/monitoring/network/security/storage）対応

### 2026-05-30

- **v1.5**: YAMLビューアーにVS Code Dark Modernシンタックスハイライト追加
- **v1.6**: Templatesページ UI改善。GitHub風パンくず・行番号・モバイルフルスクリーン化

### 2026-05-31

- **v1.7**: cfn-dynamodb-basic.yaml バグ修正（SSEType AES256 非対応→デフォルト暗号化に変更）。全62テンプレート実デプロイ検証完了
- **v1.8**: Advanced全31テンプレート実デプロイ検証完了。cfn-elasticache.yaml バグ修正（EngineVersion 7.2未提供→7.1）。cfn-ecs-service.yaml CREATE_COMPLETE確認

### 2026-06-02

- **v1.9**: ZIPダウンロードにadvanced/beginnerサブフォルダ構造追加。全62テンプレートの論理ID・物理名にシーケンス番号（01）統一付与。EC2/RDS/NATにInstanceSuffix/DbSuffix/NatSuffixパラメータ追加

### 2026-06-03

- **v2.0**: Advanced全20テンプレートに設定可能な全プロパティをParameterとして追加（公式CFnドキュメント準拠で網羅性を担保）。CWアラーム・CW Logs・ALB/NLB・NAT・VPC・SG・IAM Role・KMS・S3・EFS・EBS の各テンプレートを網羅的に拡張
- **v2.1**: cfn-alb.yaml バグ修正（AccessLogsEnabled=false 時に access_logs.s3.bucket が空文字のまま渡り AWS が拒否する問題を修正）。Advanced 全20テンプレートのデプロイ検証完了（グループC: ALB/NLB/EFS/EBS、グループD: NAT Gateway）

### 2026-06-04

- **v2.2**: 新テンプレート cfn-cw-alarm-auto-update.yaml・同-basic.yaml 追加（EC2/FSxリストア後のCloudWatch Alarm ID自動更新。Lambda+EventBridge構成）。monitoring フォルダを用途別（logs/ / alarms/ / automation/）に再編。AWS実機検証済み

### 2026-06-05

- **v2.3**: automation を独立した8番目のカテゴリに昇格。デスクトップツリーを difficulty-first に統一（ja/en）。sync_to_public.sh の --exclude=templates/ バグ修正。ほか breadcrumb 順序・yv-copy SVG 喪失・mob-code-view クラス欠落・lambda.mjs CSP ハッシュ同期を修正

### 2026-06-10

- **v2.4**: プロジェクト説明文（projects.ts）を各Botの最新仕様に同期（001/003 の投稿頻度・003 のカテゴリ構成・006 の監視間隔）。ルートREADMEのプロジェクト一覧（001/003の投稿頻度）も同様に修正

### 2026-06-15

- **v2.5**: 全62テンプレートをOpusでレビューし品質改善。バグ修正: cfn-alb/cfn-sg-egress/ingress の重複Descriptionキー・cfn-kms-basic のSidスペース・cfn-efs の DeletionPolicy 未設定・cfn-rds prd の Retain→Snapshot。ProjectName の Description 追加等の横断改善
- **v2.6**: フロントエンド・Lambdaコードレビュー。①en/index.astro の RSS link パース不完全を修正 ②Footer.astro 外部リンクに `rel="noreferrer"` 追加 ③AvatarPicker.astro に 1 MB サイズ上限チェック追加 ④i18n キー追加で ja/en のハードコード文字列を置換
- **v2.7**: `infra/cfn-portfolio.yaml` の Lambda CloudWatch Logs 保持期間を 7 日→3 日に短縮（ログ保管コスト削減）。システム仕様書の CloudWatch Logs 行に保持期間 3 日を明記

### 2026-06-27

- **v2.8**: S3 ライフサイクル設定追加: `zer0-portfolio-s3` に旧バージョン 7 日後削除（直近 3 世代保持）＋未完了マルチパート 7 日後中断ルールを CFn で追加。既存の不要旧バージョン 2,448 件（約 12 GB）を一括削除。
- **v2.9**: fetch タイムアウト追加: ja/en articles.astro の RSS フェッチに 5 秒、`lambda.mjs` の GitHub Raw 取得 2 箇所に 10 秒のタイムアウトを追加。仕様書の CSP 記述を実 CFn（`connect-src`・`'nonce-fallback'`）に一致させた。

### 2026-06-28

- **v3.0**: フォントサイズ全体拡大: `global.css` に `html { font-size: 18px; }` を追加。デフォルト 16px → 18px（+12.5%）。`text-sm` 実質 16px・`text-base` 実質 18px となり視認性を向上。

### 2026-07-03

- **v3.1**: **第2巡Fableレビュー HIGH修正**: ResponseHeadersPolicy が Content-Type を text/html に強制上書きし sitemap.xml 等が壊れるバグを修正。MEDIUM: テンプレートDLアイコンのインラインonclickをイベントリスナー方式に修正。S3配信3ビヘイビアにセキュリティヘッダー追加。本番実機検証済み
- **v3.2**: **CSP nonce機構を実装**: 生成した nonce が未消費でハッシュのみに依存していた問題を修正。全6箇所のインラインスクリプトに nonce を付与し、`middleware.ts` の CSP を nonce ベースに簡素化。本番でnonce一致を実機検証済み

### 2026-07-04

- **v3.3**: **非公開トレード実績ページ追加**: /ja/cryptobot-stats を新設。Basic認証（SSM SecureString）で保護し、006 CryptoBotの非公開statsバケットをSSR Lambdaが直接読み込みSVG描画（新規API Gateway追加なし）。本番でBasic認証・空表示・実データ表示を実機検証済み
- **v3.4**: **管理者Cookie方式に変更**: Basic認証を廃止し、007と同じ?admin=トークン→Cookie(365日,HttpOnly)方式に統一。Nav.astroに管理者限定リンク「CryptoBot実績」を追加（Cookie保持時のみ表示）。本番で全パターン実機検証済み

### 2026-07-05

- **v3.5**: Fableブラッシュアップ実装7件: 問い合わせフォームは現状維持、GitHub導線をサブディレクトリへ修正、StatsBar/Hero数字強化（テンプレート64本配布・EN版hero.sub資格数抜け修正）、Articles自動生成の透明性表記、hreflang/JSON-LD/OG画像/sitemap lastmodのSEOパック、テンプレートdeep link+検証済みバッジ、CloudWatch構造化ログでPV/DL計測（追加コストゼロ）。本番デプロイ・実機検証済み
- **v3.6**: HIGH緊急修正: 全5箇所のnonce付きインラインscript（Nav/templates×4）がTypeScript構文（!非nullアサーション・as型キャスト等）のままブラウザへ送信され、SyntaxErrorでハンバーガーメニュー等が機能停止していた。動的nonce属性がAstroのTS変換をバイパスすると判明。esbuildで全script blockを再変換しプレーンJSへ修正。本番で構文検証・実機確認済み
- **v3.7**: 職務経歴レビュー(Fable)反映: DEA資格年2021→2024に訂正、個人開発(7システム運用中)をタイムラインに追加しProjectsへ導線、直近案件を「PL下で技術支援」に是正、表現重複解消。モバイルCookie問題も修正: SameSite Lax化+有効トークン直接アクセス時はリダイレクトせず描画(Fable推奨案)。本番実機検証済み

### 2026-07-06

- **v3.8**: HIGH修正: モバイルメニューのnavItems.mapが`label`を見ず`t(key)`のみ表示していたため、翻訳辞書に存在しない管理者リンク（nav.cryptobot）が空文字（見えないリンク）になっていた。デスクトップ側と同じ`label ?? t(key)`に統一し表示を修正。本番でモバイルメニューのHTML出力を確認済み

### 2026-07-08

- **v3.9**: StatsBarの日本語ラベル「日 Bot無停止自動運用」が数字要素と分離した単位「日」で不自然だった問題を修正（`104+日` / `Bot無停止自動運用` に変更）。併せてFableで全ユーザー向けテキストをレビューし8件修正: ArticleCardの日付が英語ページでも`ja-JP`ロケール表示だった問題（lang判定で`en-US`に出し分け）、en/articles.astroのBotリンク区切り「・」→「/」、テンプレートページのコピー完了トースト表記ゆれ統一（「コピー済！」→「コピーしました！」）、section.projects.subの見出し語重複解消、projects.tsの助詞抜け・用語ゆれ2箇所、templates.tsの日英説明ズレ1箇所、en/about.astroの職務経歴タイトルが日本語版の「構築」を欠いていた問題。本番デプロイ・全ページ疎通確認済み
- **v3.10**: スクロール入場アニメーション追加: 実績カードにレイヤーせり上がり(stagger)、Hero見出しに精密製図線(clip-path)、StatsBar数値にカウントアップを実装。JS未実行時は常時フル表示・prefers-reduced-motion対応。BaseLayoutに共通IntersectionObserverスクリプトを新設
- **v3.11**: reveal-io（フェード＋stagger）を横展開: TemplatesカテゴリバッジならびにArticleCard一覧(ホーム/articles.astro)・Aboutの職務経歴タイムラインに追加。ファイルブラウザ系(templates一覧)は対象外(操作性優先のため見送り)

### 2026-07-13

- **v3.12**: 独自ブランドfavicon一式(favicon-16/32.png・apple-touch-icon.png・favicon.ico)を既存のsvg「Z」デザインから生成し追加。CloudFrontに新規ファイル用CacheBehaviorが無く本番404になっていた問題をCFnテンプレート更新で解消

