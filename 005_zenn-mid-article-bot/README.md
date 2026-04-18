# 005_Zenn_Mid_Article_Bot

AWS中級者向けZenn技術記事を毎月2回（1日・15日）自動生成するサーバーレスシステム。

複数AWSサービスを組み合わせた「複合アーキテクチャ」記事と「ユースケース別ソリューション」記事をミックスして生成します。

---

## 概要

| 項目             | 内容                                              |
| ---------------- | ------------------------------------------------- |
| 対象読者         | AWSの基本サービスを知っている中級者               |
| 記事タイプ       | 複合アーキテクチャ / ユースケース別ソリューション |
| 実行スケジュール | 毎月1日・15日 21:00 JST                           |
| 記事ボリューム   | 10,000〜15,000文字 + アーキテクチャ図2枚          |
| トピック数       | 16テーマ（約8ヶ月分）                             |
| 重複防止         | 直近4記事を除外                                   |

---

## アーキテクチャ

```
EventBridge (月2回: 1日・15日 21:00 JST)
    ↓
Lambda (ZennMidArticleGenerator)
    ├─ Step 1: SSM から直近4トピックを取得（除外リスト）
    ├─ Step 2: Bedrock でトピック選択（16種類からランダム）
    ├─ Step 3: Bedrock で中級者向け記事を生成（10,000〜15,000文字）
    ├─ Step 4: matplotlib でアーキテクチャ図を2枚生成（AWS公式アイコン使用）
    ├─ Step 5: S3 に保存（zenn-mid-articles/ プレフィックス）
    ├─ Step 6: SSM にトピックを保存
    └─ Step 7: SES でメール通知
    ↓
手動: download_article.sh → output/ → Zennに投稿
```

---

## トピック一覧

### 複合アーキテクチャ系（8記事）

| ID                      | テーマ                         | 使用サービス                                  |
| ----------------------- | ------------------------------ | --------------------------------------------- |
| `serverless_ec`         | サーバーレスECバックエンド     | API GW + Lambda + DynamoDB + SQS + SNS        |
| `static_web_hosting`    | 静的Webホスティング最適解      | S3 + CloudFront + Route 53 + ACM + WAF        |
| `container_platform`    | コンテナアプリ本番運用         | ECS Fargate + ALB + ECR + CloudWatch          |
| `event_driven_pipeline` | イベント駆動データパイプライン | Kinesis + Lambda + S3 + Athena                |
| `microservices_base`    | マイクロサービス観測性基盤     | API GW + Lambda + DynamoDB + SQS + X-Ray      |
| `multi_region_dr`       | マルチリージョンDR構成         | Route 53 + ALB + EC2 + RDS                    |
| `realtime_notify`       | リアルタイム通知システム       | SNS + SQS + Lambda + SES + EventBridge        |
| `bedrock_rag`           | Bedrock RAGアーキテクチャ      | Bedrock + S3 + OpenSearch Serverless + Lambda |

### ユースケース別ソリューション（8記事）

| ID                   | テーマ                     | 使用サービス                                        |
| -------------------- | -------------------------- | --------------------------------------------------- |
| `cicd_pipeline`      | CI/CDパイプライン構築      | CodePipeline + CodeBuild + CodeDeploy + ECR         |
| `ml_pipeline`        | 機械学習パイプライン自動化 | SageMaker AI + Step Functions + Lambda              |
| `log_analytics`      | ログ集約・分析基盤         | CloudTrail + Kinesis Firehose + S3 + Athena         |
| `cost_optimization`  | AWSコスト最適化実践        | Cost Explorer + Budgets + Savings Plans + Lambda    |
| `security_hardening` | セキュリティ強化設計       | WAF + GuardDuty + Security Hub + Config             |
| `backup_dr`          | バックアップ・DR設計       | AWS Backup + S3 Cross-Region + RDS                  |
| `multi_account`      | マルチアカウント管理       | Organizations + Control Tower + IAM Identity Center |
| `data_lake`          | データレイク構築           | S3 + Glue + Athena + Lake Formation + QuickSight    |

---

## ディレクトリ構成

```
005_Zenn_Mid_Article_Bot/
├── README.md
├── build_layer.sh          # Lambda Layer（matplotlib）ビルド
├── download_article.sh     # S3→ローカル記事取得スクリプト
├── src/
│   ├── lambda_function.py  # メインハンドラ（トピック選択・記事生成・図挿入・保存）
│   ├── diagram_generator.py# アーキテクチャ図生成（16トピック×2枚 = 32パターン、AWS公式アイコン使用）
│   ├── template.yaml       # SAM CloudFormationテンプレート
│   ├── deploy.sh           # デプロイスクリプト
│   ├── requirements.txt
│   ├── aws_icons/          # AWS公式アーキテクチャアイコンPNG（62枚）
│   ├── install_aws_icons.py# diagrams パッケージから公式アイコンをコピーするスクリプト
│   └── fonts/              # Noto Sans CJK JP フォント
└── output/                 # 生成記事の保存先
    └── NNN_YYYYMMDD_HHMMSS_TOPIC_ID/
        ├── YYYYMMDD_HHMMSS_TOPIC_ID.md
        └── images/
            ├── YYYYMMDD_HHMMSS_TOPIC_ID_diagram_1.png
            └── YYYYMMDD_HHMMSS_TOPIC_ID_diagram_2.png
```

---

## 記事テンプレート構造（中級者向け）

002プロジェクト（初級者向け）との主な違い：

| 項目             | 002（初級）              | 005（中級）                                                    |
| ---------------- | ------------------------ | -------------------------------------------------------------- |
| 文字数           | 3,000〜5,000文字         | 10,000〜15,000文字                                             |
| ハンズオン       | コンソール操作           | CloudFormation/SAMコード重視                                   |
| 追加セクション   | なし                     | 設計上の考慮ポイント（コスト・セキュリティ・スケーラビリティ） |
| 追加セクション   | なし                     | 月額コスト目安テーブル                                         |
| アーキテクチャ図 | 図1: 構成図、図2: 関連図 | 図1: 全体アーキテクチャ構成図、図2: データフロー・詳細構成図  |
| 図の挿入方式     | 固定位置                 | `{DIAGRAM_N}` マーカー方式（Bedrockが文脈に合った位置に配置） |
| サービス数       | 1サービス中心            | 3〜6サービス組み合わせ                                         |

---

## セットアップ

### 前提条件

- AWS CLI 設定済み（`aws configure`）
- SAM CLI インストール済み（`sam --version`）
- Python 3.14
- `diagrams` パッケージインストール済み（`pip install diagrams`）
- SESでメールアドレス検証済み

### デプロイ手順

```bash
# 1. リポジトリに移動
cd ~/Zer0/005_Zenn_Mid_Article_Bot

# 2. AWS公式アイコンをセットアップ（初回・diagrams更新時に実行）
cd src
python3 install_aws_icons.py

# 3. 環境変数を設定
export SENDER_EMAIL="your-verified@example.com"
export RECIPIENT_EMAIL="notify@example.com"

# 4. デプロイ（Lambda Layer ビルド + SAM デプロイ）
./deploy.sh
```

### ローカル動作確認

```bash
cd ~/Zer0/005_Zenn_Mid_Article_Bot/src

# 依存パッケージをインストール（初回のみ）
pip install matplotlib boto3 diagrams

# AWS公式アイコンをセットアップ（初回のみ）
python3 install_aws_icons.py

# 実行（AWS認証情報が必要: Bedrock/SSM/SESアクセス権限）
SES_SENDER_EMAIL=your@email.com SES_RECIPIENT_EMAIL=notify@email.com python3 lambda_function.py
```

成功時の出力例（所要時間: 約90〜120秒）：
```
[20260501_210000] Zenn中級記事自動生成を開始します
Step 1: 直近トピックをSSMから取得中...
  除外トピック: ['data_lake', 'cicd_pipeline', 'multi_account', 'log_analytics']
Step 2: Bedrockでトピックを選択中...
  選択されたトピック: AWSコスト最適化の実践戦略 (cost_optimization)
  記事タイプ: usecase
  使用サービス: Cost Explorer, AWS Budgets, Savings Plans, Lambda, CloudWatch
Step 3: 記事を生成中（10,000〜15,000文字）...
  記事生成完了: 14,256文字
Step 4: ローカルに保存中（記事MD + 構成図PNG）...
  PNG生成完了: /path/to/output/.../images/..._diagram_1.png
  PNG生成完了: /path/to/output/.../images/..._diagram_2.png
  MD保存完了: /path/to/output/.../20260501_210000_cost_optimization.md
  PNG生成完了: 2枚
Step 6: SSMにトピックを保存中...
Step 7: メール通知を送信中...
[20260501_210000] 処理が正常に完了しました
```

---

## 運用フロー

```
毎月1日 or 15日 21:00 JST
    ↓ EventBridgeが自動実行
    ↓ 約60〜90秒後にメール通知が届く
    ↓
メールを確認 → "次のアクション" の手順に従う
    ↓
bash ~/Zer0/005_Zenn_Mid_Article_Bot/download_article.sh
    ↓
output/NNN_YYYYMMDD_HHMMSS_TOPIC_ID/ に記事が保存される
    ↓
Zennエディタで新規記事を作成
    ↓
MDファイルの内容を貼り付け
    ↓
:::message ブロック内の指示に従いPNGをアップロード・URLを差し替え
（図1は ## アーキテクチャ概要 内、図2は ## 設計上の考慮ポイント 内に配置済み）
    ↓
published: false → true に変更して公開
```

---

## AWSリソース一覧

| リソース                 | 名前                                         |
| ------------------------ | -------------------------------------------- |
| Lambda関数               | `ZennMidArticleGenerator`                    |
| EventBridgeルール (1日)  | `ZennMidArticleMonthly1st`                   |
| EventBridgeルール (15日) | `ZennMidArticleMonthly15th`                  |
| Lambda Layer             | `matplotlib-aws-icons-mid`                   |
| S3プレフィックス         | `zer0-dev-s3/zenn-mid-articles/`             |
| SSMパラメータ            | `/mid-article-bot/recent-topics`             |
| CloudFormationスタック   | `zenn-mid-article-generator`                 |
| IAMロール                | `ZennMidArticleGeneratorRole-ap-northeast-1` |
| CloudWatch Logs          | `/aws/lambda/ZennMidArticleGenerator`        |

---

## Lambda手動実行（テスト）

```bash
# Lambda直接実行
aws lambda invoke \
  --function-name ZennMidArticleGenerator \
  --region ap-northeast-1 \
  response.json && cat response.json

# ログ確認
aws logs tail /aws/lambda/ZennMidArticleGenerator \
  --region ap-northeast-1 \
  --since 10m
```

---

## 関連プロジェクト

- **002_Zenn_Auto_Article_Bot**: AWS初級者向け単一サービス記事（毎週木曜自動生成）
- **005_Zenn_Mid_Article_Bot** (本プロジェクト): AWS中級者向け複合アーキテクチャ記事（毎月2回）
