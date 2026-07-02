# 005 Zenn Article Bot（中級）

> 複合アーキテクチャ×ユースケース別の16トピックから毎月2回、10,000〜15,000文字の中級 AWS 技術記事を Bedrock Claude Sonnet で自動生成するシステム。002（初級Bot）の上位互換として設計。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20S3-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Zenn](https://img.shields.io/badge/Zenn-zenn.dev%2Fzer0__infra-3EA8FF)](https://zenn.dev/zer0_infra)
[![Cost](https://img.shields.io/badge/月額-~%242.8-green)](https://aws.amazon.com/pricing)

## 概要

| 項目             | 内容                                                                     |
| ---------------- | ------------------------------------------------------------------------ |
| 生成頻度         | 毎月1日・15日 21:00 JST                                                  |
| 対応トピック     | 16種類（複合アーキテクチャ8 + ユースケース別8）                          |
| 記事ボリューム   | 10,000〜15,000文字（初級Botの約3倍）                                     |
| 差別化セクション | コスト最適化・セキュリティ設計・スケーラビリティの考慮点を追加           |
| 生成画像         | アーキテクチャ図 PNG × 2枚（AWS公式アイコン使用）                        |
| 使用モデル       | Amazon Bedrock **Claude Sonnet 4.6**（`jp.anthropic.claude-sonnet-4-6`） |
| 月額コスト       | ~$2.8（約420円）                                                         |

## アーキテクチャ

![アーキテクチャ図](images/005_architecture.png)

```text
EventBridge（毎月1日・15日 21:00 JST）
  └─▶ Lambda（Python 3.14 / 512MB / 900秒）
        ├─ Bedrock Claude Haiku（トピック選択: ~10 tokens）
        ├─ SSM からトピック履歴取得（直近4件除外）
        ├─ Bedrock Claude Sonnet（記事本文生成: ~12,000 tokens出力）
        ├─ diagram_generator.py（matplotlib + AWS公式アイコン）
        ├─ S3 PUT（MD + PNG × 2）
        ├─ SSM PUT（トピック履歴更新）
        └─ SES（生成完了メール通知）
```

## 初級Bot（002）との比較

| 項目           | 002（初級）          | 005（中級）                                  |
| -------------- | -------------------- | -------------------------------------------- |
| ターゲット     | AWS 入門者           | AWS 実務経験者                               |
| 文字数         | 3,000〜5,500 文字    | 10,000〜15,000 文字                          |
| 使用モデル     | Claude Haiku 4.5     | Claude Sonnet 4.6                            |
| トピック数     | 22種（単一サービス） | 16種（複合アーキテクチャ）                   |
| 追加セクション | なし                 | コスト最適化・セキュリティ・スケーラビリティ |
| 月額コスト     | ~$0.16               | ~$2.8                                        |
| Lambda メモリ  | 256MB                | 512MB                                        |

## 対応トピック（16種）

| 複合アーキテクチャ（8種）  | ユースケース別（8種） |
| -------------------------- | --------------------- |
| サーバーレス Web API       | CI/CD パイプライン    |
| マイクロサービス（ECS）    | ML モデル提供基盤     |
| イベント駆動アーキテクチャ | ログ収集・分析基盤    |
| データレイク構成           | コンテナ移行          |
| マルチリージョン冗長化     | セキュリティ監視      |
| ハイブリッドクラウド       | コスト最適化          |
| エッジコンピューティング   | 災害復旧（DR）        |
| 機械学習パイプライン       | モバイルバックエンド  |

## 実装のこだわり

### 1. 2段階 Bedrock 呼び出し設計

記事生成に Claude Sonnet（高精度・高コスト）を使いつつ、**トピック選択には Claude Haiku**（低コスト）を使い分け。トピック選択は数トークンの判断で十分なため、コストを抑えながら記事品質を最大化。月額コストを約30%削減。

### 2. 512MB メモリ設定の根拠

中級記事では matplotlib で生成する構成図が複合アーキテクチャのため複雑化し、256MB では OOM エラーが発生。プロファイリングにより 380〜420MB が実使用量であることを確認し、512MB に設定。

### 3. 初級Botとのコードベース分離

002 と 005 は別 Lambda・別 CloudFormation スタック・別デプロイスクリプトとして完全分離。一方のバグ修正が他方に影響しない設計。プロンプトも読者層に応じて独立してチューニング可能。

### 4. Function URL（AWS_IAM 認証）対応

本番から独立したテスト経路として Lambda Function URL（AWS_IAM 認証）を追加。EventBridge を停止せず、AWS CLI の署名付きリクエストで任意のタイミングでテスト実行できる。

## ディレクトリ構成

```text
005_Zenn_Mid_Article_Bot/
├── src/
│   ├── lambda_function.py    # メインロジック
│   ├── diagram_generator.py  # matplotlib 図生成エンジン
│   ├── deploy.sh             # デプロイスクリプト
│   └── tests/
│       └── test_lambda.py    # ユニットテスト（5件）
├── cfn-mid-article-generator.yaml
└── images/
    └── 005_architecture.png
```

> **Note**: `src/fonts/NotoSansCJK-Regular.ttc`（図解PNGの日本語描画用フォント、約19MB）はファイルサイズの都合上このリポジトリには含まれていません。ローカルでデプロイする場合は [Noto Sans CJK](https://github.com/notofonts/noto-cjk) から取得し `src/fonts/` に配置してください。

## デプロイ

```bash
# 初回デプロイ（CloudFormation + Lambda）
SENDER_EMAIL=your@email.com RECIPIENT_EMAIL=your@email.com ./src/deploy.sh

# Layer も更新する場合
DEPLOY_LAYER=1 SENDER_EMAIL=your@email.com RECIPIENT_EMAIL=your@email.com ./src/deploy.sh
```

## テスト / 動作確認

```bash
# ユニットテスト（5件）
cd src && python -m pytest tests/ -v

# Function URL でテスト実行（AWS_IAM 認証）
aws lambda invoke --function-name zenn-mid-article-generator \
  --payload '{"dry_run": true}' /tmp/out.json --region ap-northeast-1
```

## コスト内訳

| サービス                                             | 月額                 |
| ---------------------------------------------------- | -------------------- |
| Lambda 実行（2回/月 × ~120秒 × 512MB）               | ~$0.002              |
| Bedrock Claude Sonnet（~12,000 tokens/回）           | ~$2.7                |
| Bedrock Claude Haiku（トピック選択 / ~10 tokens/回） | ~$0.001              |
| S3 ストレージ・PUT                                   | ~$0.01               |
| SES 送信（2通/月）                                   | ~$0                  |
| **合計**                                             | **~$2.8（約420円）** |

## 変更履歴

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                                                       |
| ---------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-20 | v1         | 初版リリース。Claude Sonnet + 512MB Lambda + 16トピック体制                                                                                                                                                                                                                                                |
| 2026-04-28 | v1.1       | 2段階Bedrock呼び出し（トピック選択にHaiku使用）。月額コスト約30%削減                                                                                                                                                                                                                                       |
| 2026-05-05 | v1.2       | `{DIAGRAM_N}` マーカー方式導入。Bedrockが図挿入位置と説明文を記事本文内に自然配置するよう改善                                                                                                                                                                                                              |
| 2026-05-10 | v1.3       | AWS公式ドキュメント自動取得（primary_serviceのdocs.aws.amazon.com・最大6,000文字）を根拠情報として付与                                                                                                                                                                                                     |
| 2026-05-20 | v1.4       | Lambda Function URL（AWS_IAM認証）追加。EventBridgeスケジュールを止めずに任意タイミングでテスト実行可能に                                                                                                                                                                                                  |
| 2026-06-01 | v1.5       | CFn `validate_template` 検証機能追加・バグ修正5件（重複トピック・TemplateBody上限・HTMLエスケープ・CFn例外取得・マーカー自動除去）・処理時間計測・Bedrockコスト概算ログ追加                                                                                                                                |
| 2026-06-15 | v1.6       | コードレビュー反映。/tmp 記事フォルダの自動削除（最新5件保持）を002と同様に追加しウォームスタート時のディスク逼迫を防止・トピック選択の部分一致フォールバック追加・Bedrockパラメータ/単価/サイズ上限のマジックナンバーを定数化                                                                             |
| 2026-06-15 | v1.7       | バグ修正2件：① PNG未生成時のDIAGRAMマーカー除去正規表現を `\{\{?DIAGRAM_\d+\}\}?` に修正（`str.format()` 後の単一波括弧も除去対象に）② 見出しなし記事で `_embed_image_placeholders` が画像を無言スキップする問題を修正（末尾追記＋WARNING ログに変更）                                                     |
| 2026-06-16 | v1.8       | 記事内構築手順をCFnテンプレート→AWS CLI中心に変更。プロンプト改修（変数定義セクション必須・コマンドコメントルール・クリーンアップセクション追加）・CFnバリデーション廃止→CLIコマンド存在チェックに置換・`cfn` Lambdaクライアント削除                                                                       |
| 2026-06-16 | v1.9       | コードレビュー反映。①bashブロック例のバックスラッシュをPython行継続から保護（`\\`）②例外ハンドラのCFn表記を修正③CLIバリデーターをbashブロック限定awsチェック＋クリーンアップ同義語対応（後片付け/リソース削除）に改善④`cloudformation:ValidateTemplate` IAM権限を両スタックから削除（CLAUDE.md step5対応） |
| 2026-06-27 | v2.0       | IAM最小権限化（コードレビュー反映）：①未使用の `ses:SendRawEmail` を削除②未使用の `aws-marketplace:ViewSubscriptions`/`Subscribe`（`Resource:"*"`）Statement を削除③Bedrock の `inference-profile/*` ワイルドカードを廃止し、test_mode で使う Haiku 推論プロファイル ARN（`jp.anthropic.claude-haiku-4-5-20251001-v1:0`）を明示追加。CFnスタック再デプロイ済み |
| 2026-07-01 | v2.1       | Opus 4.8 コードレビュー（10件）反映。diagram_generator.py 大幅改善：①`_outer_cluster()` に `skip_autopad` フラグ追加（auto-padding ループで外枠座標が破壊される問題を解消）②`_draw_diagram()` 処理順序を再構築（auto-padding → ylim → figsize → try/finally描画）③曲線矢印 16件を直線（rad=0.0）に統一（CLAUDE.md 規約対応）④`microservices_base_1`/`realtime_notify_1`/`realtime_notify_2`/`bedrock_rag_2` の垂直間隔修正⑤`data_lake_1` athena/qs の xlim 超過修正（x=13.0→12.5）⑥`plt.tight_layout()` 削除（bbox_inches='tight' 競合解消）⑦`try/finally` で `plt.close(fig)` を保証（figure リーク防止）⑧`_load_icon()` に `@functools.lru_cache(maxsize=128)` 追加。lambda_function.py：孤立 `{DIAGRAM_N}` マーカークリーンアップ追加（図生成失敗時の残留マーカーを除去） |
| 2026-07-02 | v2.2       | Opus 4.8 で個別記事（log_analytics）を技術精査。①`diagram_generator.py` の `_diagram_log_analytics_1`/`_2` がトピック定義の services リストに存在しない要素（VPC Flow Logs・Lambda異常検知・SNS・EventBridge）を含み、本文と矛盾していた問題を修正（本文と整合する構成に再設計）②生成済み記事側で発覚したAWS技術的誤り2件を修正：CloudWatch LogsサブスクリプションのgzipエンベロープをFirehoseがそのまま処理できない問題（展開Lambda追加）、Athenaがダイナミックパーティショニングの新規パーティションを認識できない問題（Glueテーブルへパーティション射影を追加）。Lambda本体（diagram_generator.py）を再デプロイ済み |
| 2026-07-02 | v2.3       | 記事生成後の**AI技術レビュー自動化**を追加。`review_technical_accuracy()` を新設し、Bedrock（`ReviewModelId`、デフォルトSonnet 4.6・生成モデルと独立して切替可能）に構造化出力（json_schema）で記事の技術的正確性（サービス間データフォーマット互換性・IAM信頼ポリシーの実効性・パーティション認識タイミング・動作確認手順の妥当性等）を検証させ、結果をメール本文に新セクション「🔍 AI技術レビュー」として掲載（記事本体は汚さず参考情報として提示のみ、自動修正はしない）。test_modeではコスト・速度優先でスキップ。`output_config.effort: "medium"` を指定しないとadaptive thinkingだけでmax_tokensを使い切り出力ゼロになる実障害を実機で確認したため対処済み（`REVIEW_MAX_TOKENS=12000`）。副次的に、Haiku 4.5のJP推論プロファイルが `ap-northeast-3` にルーティングされ既存IAMポリシーでは権限不足だった潜在バグも発見・修正（ワイルドカードリージョンARNを追加）。002には未適用（初級記事はコスト重視の設計方針のため対象外） |
