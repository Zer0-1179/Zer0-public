# 002 Zenn Article Bot（初級）

> AWS初学者向け技術記事を毎月2回、Bedrock Claude で 3,000〜5,500文字自動生成し、matplotlib + AWS公式アイコンでアーキテクチャ図PNG×2枚を同時生成してS3に保存するシステム。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20S3-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Zenn](https://img.shields.io/badge/Zenn-zenn.dev%2Fzer0__infra-3EA8FF)](https://zenn.dev/zer0_infra)
[![Cost](https://img.shields.io/badge/月額-~%240.16-green)](https://aws.amazon.com/pricing)

## 概要

| 項目           | 内容                                                      |
| -------------- | --------------------------------------------------------- |
| 生成頻度       | 毎月第1・第3木曜 21:00 JST                                |
| 対応トピック   | 22種類のAWSサービス（EC2/S3/Lambda/RDS 等）               |
| 記事ボリューム | 3,000〜5,500文字 + Zenn Markdown 完全対応                 |
| 生成画像       | アーキテクチャ図 PNG × 2枚（AWS公式アイコン使用）         |
| 重複防止       | SSM で直近5件を記録、同一トピック連続生成を防止           |
| 出力先         | Amazon S3（`zer0-dev-s3/zenn-articles/`）+ SES メール通知 |
| 月額コスト     | ~$0.16（約24円）                                          |

## アーキテクチャ

![アーキテクチャ図](images/002_architecture.png)

```text
EventBridge Scheduler（第1・第3木曜 21:00 JST）
  └─▶ Lambda（Python 3.14 / 256MB / 900秒）
        ├─ SSM からトピック履歴取得（直近5件除外）
        ├─ Bedrock Claude Haiku（記事本文生成 ~8,000 tokens出力）
        ├─ diagram_generator.py
        │   ├─ matplotlib + AWS公式アイコン（64px PNG）
        │   └─ PNG 生成 × 2枚（メイン構成図 + 詳細図）
        ├─ S3 PUT（MD + PNG × 2）
        ├─ SSM PUT（トピック履歴更新）
        └─ SES（生成完了メール通知）
```

## 技術スタック

| レイヤー     | 技術                                                        |
| ------------ | ----------------------------------------------------------- |
| 実行基盤     | AWS Lambda（Python 3.14 / 256MB / 900秒）                   |
| AI生成       | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / max_tokens: 8,192） |
| 図生成       | matplotlib（Graphviz・diagrams 依存ゼロ）                   |
| アイコン     | AWS公式アイコン 64px PNG（Lambda Layer に同梱）             |
| 状態管理     | SSM Parameter Store（トピック履歴 + 記事カウンター）        |
| ストレージ   | Amazon S3（ライフサイクル90日自動削除設定済み）             |
| 通知         | Amazon SES                                                  |
| IaC          | CloudFormation                                              |
| Lambda Layer | matplotlib / numpy / Pillow（50MB 以内 / 直接アップロード） |

## 実装のこだわり

### 1. Lambda 環境での図生成（Graphviz 不使用）

`diagrams` や `graphviz` はシステムバイナリが必要なため Lambda では動作しない。**matplotlib のみで AWS公式アイコンを配置・矢印描画するカスタムエンジン**（`diagram_generator.py`）を自前実装。ノード間の矢印衝突回避・クラスター枠の自動パディング調整・日本語フォントの動的ロードまで独自で実装している。

### 2. Zenn Markdown 完全対応

単純な Markdown ではなく、Zenn 独自の記法（`:::message`・`:::details`・コードタイトル付きブロック）をプロンプトに組み込み。Few-shot で出力フォーマットを固定し、Bedrock がフォーマット違反を起こさないよう制御。

### 3. AWSサービス名の自動最新化

古い名称（例: `SageMaker` → `SageMaker AI`、`Kinesis Data Streams` → `Managed Streaming for Apache Kafka`）を辞書で管理し生成記事内を自動置換。Bedrock の学習データが古くても公式名称での出力を保証。

### 4. `output/` 自動クリーンアップ

記事保存のたびに `_cleanup_old_articles()` が実行され、最新5件（`OUTPUT_KEEP_MAX=5`）を超えた古いフォルダを自動削除。ローカル容量の肥大化を防ぎ、S3 側も90日ライフサイクルで自動削除。

## 対応トピック（22種）

| カテゴリ           | トピック                              |
| ------------------ | ------------------------------------- |
| コンピューティング | EC2、Lambda、ECS、Fargate             |
| ストレージ         | S3、EBS、EFS                          |
| データベース       | RDS、DynamoDB、ElastiCache            |
| ネットワーク       | VPC、CloudFront、Route53、API Gateway |
| セキュリティ       | IAM、KMS、WAF、Shield                 |
| 運用監視           | CloudWatch、Systems Manager           |
| AI/ML              | Bedrock                               |

## ディレクトリ構成

```text
002_Zenn_Auto_Article_Bot/
├── src/
│   ├── lambda_function.py    # メインロジック
│   ├── diagram_generator.py  # matplotlib 図生成エンジン
│   ├── deploy.sh             # デプロイスクリプト
│   └── tests/
│       └── test_lambda.py    # ユニットテスト（4件）
├── scripts/
│   ├── build_layer.sh        # Lambda Layer ビルド
│   └── download_article.sh   # S3 から生成記事をローカルに取得
├── cloudformation-article-generator.yaml
└── images/
    └── 002_architecture.png
```

## デプロイ

```bash
# 初回デプロイ（CloudFormation + Lambda）
SENDER_EMAIL=your@email.com RECIPIENT_EMAIL=your@email.com ./src/deploy.sh

# Layer も更新する場合
DEPLOY_LAYER=1 SENDER_EMAIL=your@email.com RECIPIENT_EMAIL=your@email.com ./src/deploy.sh
```

## テスト / 動作確認

```bash
# ユニットテスト（4件）
cd src && python -m pytest tests/ -v

# Lambda 手動実行（DRY_RUN: S3保存・SES送信をスキップ）
aws lambda invoke --function-name zenn-article-generator \
  --payload '{"dry_run": true}' /tmp/out.json --region ap-northeast-1

# S3 から生成記事をローカルに取得
bash scripts/download_article.sh
```

## コスト内訳

| サービス                                 | 月額                 |
| ---------------------------------------- | -------------------- |
| Lambda 実行（2回/月 × ~90秒 × 256MB）    | ~$0.001              |
| Bedrock Claude Haiku（~8,000 tokens/回） | ~$0.12               |
| S3 ストレージ・PUT                       | ~$0.01               |
| SES 送信（2通/月）                       | ~$0                  |
| **合計**                                 | **~$0.16（約24円）** |
