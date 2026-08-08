# 004_portfolio 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-08-02

### ローカルNode.jsバージョンを固定

- `.nvmrc`を追加し、動作確認済みのNode.js v24.18.0をローカル開発バージョンとして固定

## 2026-03-15

### 初版リリース（v1）

- Astro SSR + Lambda + CloudFront + S3

## 2026-03-20

### API Gateway切替（v1.1）

- API Gateway HTTP API に切り替え（Function URL SCP問題の回避）

## 2026-04-01

### カスタムドメイン（v1.2）

- カスタムドメイン `www.zer0-infra.com` の設定完了

## 2026-04-10

### Templatesページ追加（v1.3）

- Templatesページ（VS Codeエクスプローラー風UIと22テンプレート）を追加

## 2026-04-19

### 全62テンプレート公開（v1.4）

- 全62テンプレート公開完了。全カテゴリ（compute/database/messaging/monitoring/network/security/storage）対応

## 2026-05-30

### シンタックスハイライト（v1.5）

- YAMLビューアーにVS Code Dark Modernシンタックスハイライトを追加

### Templatesページ UI改善（v1.6）

- GitHub風パンくず・行番号・モバイルフルスクリーン化

## 2026-05-31

### テンプレート実デプロイ検証①（v1.7）

- cfn-dynamodb-basic.yaml バグ修正（SSEType AES256 非対応→デフォルト暗号化に変更）
- 全62テンプレート実デプロイ検証完了

### テンプレート実デプロイ検証②（v1.8）

- Advanced全31テンプレート実デプロイ検証完了
- cfn-elasticache.yaml バグ修正（EngineVersion 7.2未提供→7.1）。cfn-ecs-service.yaml CREATE_COMPLETE確認

## 2026-06-02

### ZIP構造・命名統一（v1.9）

- ZIPダウンロードにadvanced/beginnerサブフォルダ構造を追加
- 全62テンプレートの論理ID・物理名にシーケンス番号（01）を統一付与
- EC2/RDS/NATにInstanceSuffix/DbSuffix/NatSuffixパラメータを追加

## 2026-06-03

### 全プロパティのパラメータ化（v2.0）

- Advanced全20テンプレートに設定可能な全プロパティをParameterとして追加（公式CFnドキュメント準拠で網羅性を担保）
- CWアラーム・CW Logs・ALB/NLB・NAT・VPC・SG・IAM Role・KMS・S3・EFS・EBS の各テンプレートを網羅的に拡張

### ALBバグ修正・デプロイ検証（v2.1）

- cfn-alb.yaml バグ修正（AccessLogsEnabled=false 時に access_logs.s3.bucket が空文字のまま渡り AWS が拒否する問題）
- Advanced 全20テンプレートのデプロイ検証完了（グループC: ALB/NLB/EFS/EBS、グループD: NAT Gateway）

## 2026-06-04

### アラーム自動更新テンプレート（v2.2）

- 新テンプレート cfn-cw-alarm-auto-update.yaml・同-basic.yaml を追加（EC2/FSxリストア後のCloudWatch Alarm ID自動更新。Lambda+EventBridge構成）
- monitoring フォルダを用途別（logs/ / alarms/ / automation/）に再編。AWS実機検証済み

## 2026-06-05

### automationカテゴリ昇格ほか（v2.3）

- automation を独立した8番目のカテゴリに昇格。デスクトップツリーを difficulty-first に統一（ja/en）
- sync_to_public.sh の --exclude=templates/ バグを修正
- breadcrumb 順序・yv-copy SVG 喪失・mob-code-view クラス欠落・lambda.mjs CSP ハッシュ同期を修正

## 2026-06-10

### プロジェクト説明の同期（v2.4）

- プロジェクト説明文（projects.ts）を各Botの最新仕様に同期（001/003 の投稿頻度・003 のカテゴリ構成・006 の監視間隔）
- ルートREADMEのプロジェクト一覧（001/003の投稿頻度）も同様に修正

## 2026-06-15

### 全テンプレートレビュー（v2.5）

- 全62テンプレートをOpusでレビューし品質改善
- バグ修正: cfn-alb/cfn-sg-egress/ingress の重複Descriptionキー・cfn-kms-basic のSidスペース・cfn-efs の DeletionPolicy 未設定・cfn-rds prd の Retain→Snapshot
- ProjectName の Description 追加等の横断改善

### フロントエンド・Lambdaレビュー（v2.6）

- en/index.astro の RSS link パース不完全を修正
- Footer.astro 外部リンクに `rel="noreferrer"` を追加。AvatarPicker.astro に 1 MB サイズ上限チェックを追加
- i18n キー追加で ja/en のハードコード文字列を置換

### ログ保持期間の短縮（v2.7）

- `infra/cfn-portfolio.yaml` の Lambda CloudWatch Logs 保持期間を 7 日→3 日に短縮（ログ保管コスト削減）
- システム仕様書の CloudWatch Logs 行に保持期間 3 日を明記

## 2026-06-27

### S3ライフサイクル設定（v2.8）

- `zer0-portfolio-s3` に旧バージョン 7 日後削除（直近 3 世代保持）＋未完了マルチパート 7 日後中断ルールを CFn で追加
- 既存の不要旧バージョン 2,448 件（約 12 GB）を一括削除

### fetchタイムアウト追加（v2.9）

- ja/en articles.astro の RSS フェッチに 5 秒、`lambda.mjs` の GitHub Raw 取得 2 箇所に 10 秒のタイムアウトを追加
- 仕様書の CSP 記述を実 CFn（`connect-src`・`'nonce-fallback'`）に一致させた

## 2026-06-28

### フォントサイズ拡大（v3.0）

- `global.css` に `html { font-size: 18px; }` を追加。デフォルト 16px → 18px（+12.5%）
- `text-sm` 実質 16px・`text-base` 実質 18px となり視認性を向上

## 2026-07-03

### 第2巡Fableレビュー修正（v3.1）

- HIGH: ResponseHeadersPolicy が Content-Type を text/html に強制上書きし sitemap.xml 等が壊れるバグを修正
- MEDIUM: テンプレートDLアイコンのインラインonclickをイベントリスナー方式に修正
- S3配信3ビヘイビアにセキュリティヘッダーを追加。本番実機検証済み

### CSP nonce機構の実装（v3.2）

- 生成した nonce が未消費でハッシュのみに依存していた問題を修正
- 全6箇所のインラインスクリプトに nonce を付与し、`middleware.ts` の CSP を nonce ベースに簡素化。本番でnonce一致を実機検証済み

## 2026-07-04

### 非公開トレード実績ページ追加（v3.3）

- /ja/cryptobot-stats を新設。Basic認証（SSM SecureString）で保護
- 006 CryptoBotの非公開statsバケットをSSR Lambdaが直接読み込みSVG描画（新規API Gateway追加なし）
- 本番でBasic認証・空表示・実データ表示を実機検証済み

### 管理者Cookie方式に変更（v3.4）

- Basic認証を廃止し、007と同じ?admin=トークン→Cookie(365日,HttpOnly)方式に統一
- Nav.astroに管理者限定リンク「CryptoBot実績」を追加（Cookie保持時のみ表示）。本番で全パターン実機検証済み

## 2026-07-05

### Fableブラッシュアップ実装7件（v3.5）

- 問い合わせフォームは現状維持。GitHub導線をサブディレクトリへ修正
- StatsBar/Hero数字強化（テンプレート64本配布・EN版hero.sub資格数抜け修正）。Articles自動生成の透明性表記
- hreflang/JSON-LD/OG画像/sitemap lastmodのSEOパック。テンプレートdeep link+検証済みバッジ
- CloudWatch構造化ログでPV/DL計測（追加コストゼロ）。本番デプロイ・実機検証済み

### インラインscript構文エラーの緊急修正（v3.6）

- HIGH: 全5箇所のnonce付きインラインscript（Nav/templates×4）がTypeScript構文（!非nullアサーション・as型キャスト等）のままブラウザへ送信され、SyntaxErrorでハンバーガーメニュー等が機能停止していた
- 動的nonce属性がAstroのTS変換をバイパスすると判明。esbuildで全script blockを再変換しプレーンJSへ修正。本番で構文検証・実機確認済み

### 職務経歴レビュー反映（v3.7）

- DEA資格年2021→2024に訂正。個人開発(7システム運用中)をタイムラインに追加しProjectsへ導線
- 直近案件を「PL下で技術支援」に是正、表現重複を解消
- モバイルCookie問題も修正: SameSite Lax化+有効トークン直接アクセス時はリダイレクトせず描画(Fable推奨案)。本番実機検証済み

## 2026-07-06

### モバイルメニュー表示修正（v3.8）

- HIGH: モバイルメニューのnavItems.mapが`label`を見ず`t(key)`のみ表示していたため、翻訳辞書に存在しない管理者リンク（nav.cryptobot）が空文字（見えないリンク）になっていた
- デスクトップ側と同じ`label ?? t(key)`に統一し表示を修正。本番でモバイルメニューのHTML出力を確認済み

## 2026-07-08

### ユーザー向けテキスト総点検（v3.9）

- StatsBarの日本語ラベル「日 Bot無停止自動運用」が数字要素と分離した単位「日」で不自然だった問題を修正（`104+日` / `Bot無停止自動運用` に変更）
- 併せてFableで全ユーザー向けテキストをレビューし8件修正
- ArticleCardの日付が英語ページでも`ja-JP`ロケール表示だった問題を修正（lang判定で`en-US`に出し分け）
- en/articles.astroのBotリンク区切り「・」→「/」。テンプレートページのコピー完了トースト表記ゆれを統一（「コピー済！」→「コピーしました！」）
- section.projects.subの見出し語重複を解消。projects.tsの助詞抜け・用語ゆれ2箇所、templates.tsの日英説明ズレ1箇所を修正
- en/about.astroの職務経歴タイトルが日本語版の「構築」を欠いていた問題を修正。本番デプロイ・全ページ疎通確認済み

### スクロール入場アニメーション追加（v3.10）

- 実績カードにレイヤーせり上がり(stagger)、Hero見出しに精密製図線(clip-path)、StatsBar数値にカウントアップを実装
- JS未実行時は常時フル表示・prefers-reduced-motion対応。BaseLayoutに共通IntersectionObserverスクリプトを新設

### アニメーション横展開（v3.11）

- reveal-io（フェード＋stagger）をTemplatesカテゴリバッジ・ArticleCard一覧(ホーム/articles.astro)・Aboutの職務経歴タイムラインに追加
- ファイルブラウザ系(templates一覧)は対象外(操作性優先のため見送り)

## 2026-07-13

### ブランドfavicon追加・404修正（v3.12）

- 独自ブランドfavicon一式(favicon-16/32.png・apple-touch-icon.png・favicon.ico)を既存のsvg「Z」デザインから生成し追加
- CloudFrontに該当パス用CacheBehaviorが無く本番404になっていたため、CFnテンプレートに5パターン追加して解消

## 2026-07-21

### CryptoBot実績ページに「現在のポジション」表示を追加

- 006 CryptoBotで「TP1部分利確後、次はいつ利確するのか分からず不安」というフィードバックを受け、非公開ページ`/ja/cryptobot-stats`に保有中ポジションの状況（確保済み利益ライン・これまでの高値/安値・含み損益）を表示するセクションを新設
- データソースは006 Executorが30分毎に書き出す非公開S3オブジェクト`positions.json`（stats.jsonと同じバケット）。cfn-portfolio.yamlのIAMポリシーにGetObject/ListBucket権限を追加
- 手動決済分のトレード履歴（+138.5円／+120.5円）もstats.jsonに反映し、累計損益+584.8円で表示されることを確認
- 既存の「最終更新」表示がSSR実行環境(UTC)でレンダリングされ実際の時刻より9時間ずれていたバグを発見（`toLocaleString('ja-JP')`にtimeZone未指定）。`timeZone: 'Asia/Tokyo'`を明示して修正

### モバイルでトレード履歴が見えない問題を修正

- 累積損益推移チャートの各点詳細がSVG `<title>`のホバー依存で、タッチ操作のスマートフォンでは表示できなかった
- 「テーブル表示」の`<details>`をデフォルト展開に変更し、チャート下部の案内文もモバイル/デスクトップで出し分け、どの端末でも詳細が見える状態にした

## 2026-07-30

### お問い合わせページのSNSリンク表記を修正

- SNSバッジ（GitHub/X (Twitter)/Zenn/note/Credly）の幅が文字数依存で行ごとにバラバラになり、ハンドル名・説明文の開始位置がずれていた問題を修正。バッジ幅を固定し中央揃えにして全行の開始位置を統一（ja/en両方）
- X (Twitter)の説明文「AWS・AI活用術を毎日発信」が実態と不一致だった（001のEventBridgeルールは月・木の週2回のみ）。今後スケジュールが変わっても陳腐化しないよう「AWS・AI活用術を定期的に発信」に変更
- 過去のQRコードセクション削除時に取り残されていた未使用の翻訳キー`contact.qr`/`contact.qr.sub`（ja/en）を削除

### CryptoBot実績ページのトレーリングSL説明文を改善

- 「TP1後、次はいつ決済されるか分からない」というフィードバックが再度あり、既存の説明文（ATR倍率ベースの技術的な表現）だけでは伝わりにくいと判明
- トレーリングSL欄の冒頭に「◯◯円まで戻す（下がる）と、残り70%が自動決済されます」という具体的な価格ベースの一文を追加し、実データ（SOL/JPYショート）で表示を確認

## 2026-08-08

### touring-appプロジェクトページに利用実績グラフを追加

- ユーザーから007バイクツーリングPWAの利用回数を問われ、007側に集計バッチ(`zer0-touring-stats`)を新設。その出力(`stats.json`)を表示する新規`TouringStatsChart.astro`コンポーネントを追加
- `[slug].astro`(ja/en)でslug==='touring-app'のときSSR時にstats.jsonをfetchし、累計呼び出し回数と日別バーチャート(直近90日)・表形式の詳細(`<details>`)を表示。dataviz skillのガイドライン（thin marks・アクセントカラー単色・アクセシブルなtable view）に準拠
- SSR時のfetchが失敗する場合（007側未デプロイ・一時的な障害等）はセクション自体を非表示にする設計とし、006 CryptoBot実績ページと同様stats.json欠落時もページ全体は壊れないことを確認
- x軸ラベルの先頭・末尾がviewBox外にはみ出て見切れる不具合、および「累計呼び出し回数回」の表記重複をローカル確認で発見し修正

## 2026-08-09

### S3の_astro/フォルダに蓄積していた不要ファイルを削除・再発防止

- ユーザーに「他に問題ないか」と問われ調査した結果、`scripts/deploy.sh`の`_astro/`同期コマンドに`--delete`が付いておらず、コンテンツハッシュ付きファイル名のため再ビルドのたびに新規ファイル扱いになり古いバンドルが無期限に蓄積していたと判明
- 2026-05-31〜08-08分の74ファイル（現在参照されているのは1件のみ）をS3から削除。`deploy.sh`に`--delete`を追加して再発防止
- 削除後、全主要ページ(ja/en)・現在のCSS参照先が正しいことを確認。スクリーンショットで見た目上の欠落もフェードインアニメーション中のタイミングと判明し実害なしと確認済み
