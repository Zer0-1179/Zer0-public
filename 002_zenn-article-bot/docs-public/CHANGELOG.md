# 002_Zenn_Auto_Article_Bot 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-04-01

### 初版リリース（v1）

- EventBridge Scheduler + Lambda + Bedrock Haiku による月2回Zenn記事自動生成

## 2026-04-10

### 構成図の自動生成（v1.1）

- matplotlib アーキテクチャ図自動生成を追加

## 2026-04-20

### 図挿入マーカー方式（v1.2）

- `{DIAGRAM_N}` マーカー方式を導入

## 2026-04-28

### 公式ドキュメント取得（v1.3）

- AWS公式ドキュメント自動取得（Step 2.5）を追加

## 2026-05-05

### 失敗時アラート体制（v1.4）

- DLQ（SQS）+ CloudWatch Alarm + SNS Topicを追加。Lambda失敗時のアラート体制を整備

## 2026-05-21

### 出力クリーンアップ（v1.5）

- `output/` 自動クリーンアップ（最新5件保持）を追加

## 2026-06-01

### 検証機能追加・バグ修正5件（v1.6）

- CFn `validate_template` 検証機能を追加
- バグ修正5件（重複トピック・TemplateBody上限・HTMLエスケープ・CFn例外取得・マーカー自動除去）
- 処理時間計測・Bedrockコスト概算ログを追加

## 2026-06-15

### コードレビューによるバグ修正3件（v1.7）

- PNG未生成時のマーカー除去が機能していなかった不具合を修正（単一波括弧 `{DIAGRAM_N}` に対応）
- 見出しなし記事のフォールバック挿入 `IndexError` を修正
- SSMカウンター破損・書込失敗時のガードを追加
- 構成図クラスター枠を点線→実線に統一。回帰テスト3件追加（計7件）

## 2026-06-16

### 記事の構築手順をCLI中心に変更（v1.8）

- 記事内構築手順をCFnテンプレート→AWS CLI中心に変更
- プロンプト改修（AWS CLIコマンド変数化・コード例更新）
- CFn `validate_template` を廃止しCLIコマンド存在チェックに置換。`cfn` boto3クライアントを削除

### コードレビュー反映（v1.9）

- `cloudformation:ValidateTemplate` IAM権限を削除（CLAUDE.md step5対応・CFnスタック再デプロイ済み）

## 2026-06-18

### トピック拡充・モデル変更（v2.0）

- サブトピック6件を追加（ec2_ssm/ec2_ebs/lambda_layers/s3_lifecycle/vpc_endpoint/cloudwatch_insights）
- トピック重複除外数を5→28に拡大。記事生成モデルをHaiku→Opus 4.8に変更
- 動的タイトル生成（`TITLE:` 行をフロントマターに反映）を追加
- CFnパラメータ・IAMポリシー・Lambda env varsを更新

## 2026-06-27

### IAM最小権限化（v2.1）

- コードレビューMEDIUM 3件: 未使用の `ses:SendRawEmail`・未使用の Opus モデル ARN（Bedrock Resource）・未使用の `aws-marketplace` Statement を削除
- テンプレート Description の "Claude Opus" 誤記を修正。CFnスタック再デプロイ完了

## 2026-07-01

### 構成図生成の安定化（v2.2）

- diagram_generator.py: `try/finally` で `plt.close(fig)` を保証（figureリーク防止）、`plt.tight_layout()` を削除
- lambda_function.py: 孤立 `{DIAGRAM_N}` マーカーのクリーンアップを追加
- 005 のコードレビュー結果を 002 へ横展開

## 2026-07-03

### 第2巡Fableレビュー修正（v2.3）

- HIGH: Bedrock IAM ARNを2リージョン明示に修正（ap-northeast-3ルーティング時のAccessDenied対策）
- HIGH: Bedrock応答content空時のIndexErrorを安全抽出関数で修正
- MEDIUM: `RECENT_TOPICS_LIMIT` を28→20に修正（重複除外の恒久ロック解消）

### 構成図6トピック追加（v2.4）

- v2.0で追加した6サブトピックが構成図未対応で画像なしのまま記事生成されていた問題を修正
- 各2枚・計12枚の構成図関数を追加し、SSM/EBS/PrivateLink/S3 Glacierの公式アイコンを `aws_icons/` にローカル同梱
- 本番Lambda実行でPNG生成を確認済み

## 2026-07-05

### Fableブラッシュアップ（v2.5）

- dry_run実装（S3/SES/SSM書込スキップ）
- 構成図タイトルを記事プロンプトに注入し本文と整合。切り口4種のランダム変化を追加
- トピック選定をBedrock→random.choiceに変更（`BEDROCK_MODEL_ID`廃止）
- 記事品質チェックを実質化（文字数/Markdown対応/CLI体裁/構成図枚数）
- メール通知にタイトル/見出し一覧/コスト概算/stop_reason等を追加
- Bedrockリトライ設定（adaptive・最大4回）を追加。構成図エッジラベルへ白背景bboxを付与。構造化サマリーログを追加
- CFnから未使用`BedrockModelId`パラメータを削除・スタック再デプロイ・本番Lambdaでdry_run実行検証済み

### 文字数チェックの見直し（v2.6）

- v2.5導入の文字数チェックが実態と乖離していた問題を修正
- 過去ログ確認で実測6,500〜9,500文字が常態と判明（ハンズオンの完全なコード例要求・内容充実優先の方針上、正常な挙動）
- 想定文字数を2,000〜3,500→4,000〜8,000文字に修正（プロンプト・README・仕様書）
- 品質チェックのレンジ判定を「3,000文字未満（内容不足の兆候）のみ検出」する片側チェックに変更
- 上限超過は許容する方針とし、ユニットテストで回帰防止

### 軽微問題の自動修正機能（v2.7）

- `_auto_fix_article()`を追加し、Bedrock再呼び出し不要・コストゼロで直せる軽微な問題を記事保存前に自動修正
- 対象: 古いランタイム表記・コードブロック外h1見出し・言語指定なしコードブロック・記事全体で`--region`皆無時の単一行コマンド補完
- 品質チェックはこれで直らない内容面の問題のみを検出しメール警告する2段構成に整理
- メールに「自動修正」欄を追加。ユニットテスト6件追加（計21件）
