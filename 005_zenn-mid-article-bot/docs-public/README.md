# 005 Zenn Article Bot（中級）

> 複合アーキテクチャ×ユースケース別の24トピックから毎月2回、15,000〜30,000文字の中級 AWS 技術記事を Bedrock Claude Sonnet で自動生成するシステム。002（初級Bot）の上位互換として設計。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20S3-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Zenn](https://img.shields.io/badge/Zenn-zenn.dev%2Fzer0__infra-3EA8FF)](https://zenn.dev/zer0_infra)
[![Cost](https://img.shields.io/badge/月額-~%242.7-green)](https://aws.amazon.com/pricing)

## 概要

| 項目             | 内容                                                                     |
| ---------------- | ------------------------------------------------------------------------ |
| 生成頻度         | 毎月1日・15日 21:00 JST                                                  |
| 対応トピック     | 24種類（複合アーキテクチャ12 + ユースケース別12）                        |
| 記事ボリューム   | 15,000〜30,000文字（初級Botの約3倍）                                     |
| 差別化セクション | コスト最適化・セキュリティ設計・スケーラビリティの考慮点を追加           |
| 生成画像         | アーキテクチャ図 PNG × 1枚（AWS公式アイコン使用）                        |
| 使用モデル       | Amazon Bedrock **Claude Sonnet 4.6**（`jp.anthropic.claude-sonnet-4-6`） |
| 月額コスト       | ~$2.7（約410円）                                                         |

## アーキテクチャ

![アーキテクチャ図](../images/005_architecture.png)

```text
EventBridge（毎月1日・15日 21:00 JST）
  └─▶ Lambda（Python 3.14 / 512MB / 900秒）
        ├─ Bedrock Claude Haiku（トピック選択: ~10 tokens）
        ├─ SSM からトピック履歴取得（直近12件除外）
        ├─ Bedrock Claude Sonnet（記事本文生成: ~12,000 tokens出力）
        ├─ diagram_generator.py（matplotlib + AWS公式アイコン）
        ├─ S3 PUT（MD + PNG × 1）
        ├─ SSM PUT（トピック履歴更新）
        └─ SES（生成完了メール通知）
```

## 初級Bot（002）との比較

| 項目           | 002（初級）          | 005（中級）                                  |
| -------------- | -------------------- | -------------------------------------------- |
| ターゲット     | AWS 入門者           | AWS 実務経験者                               |
| 文字数         | 3,000〜5,500 文字    | 15,000〜30,000 文字                          |
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
| Bedrock Claude Sonnet（~12,000 tokens/回・記事本文生成のみ） | ~$2.7                |
| S3 ストレージ・PUT                                   | ~$0.01               |
| SES 送信（2通/月）                                   | ~$0                  |
| **合計**                                             | **~$2.7（約410円）** |

## 変更履歴

直近1日分のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

### 2026-07-16

#### トピックプール拡充 16→24種類（v3.4）

- v3.3でトピック選択の偏りは解消したが、固定16トピック×固定3サービスという構造上、S3が16トピック中7回・Lambdaが5回登場するなどサービス自体の偏りが残っていた
- VPC・EventBridge・CodeDeploy・Cognito・CloudWatch・WAF/Shield・Secrets Manager・Lake Formationなど、既存トピックで未使用のAWS公式アイコンを使った新規8トピックを追加（S3・Lambdaを含まない組み合わせで選定）
- 新サービス分の公式ドキュメントURLは全件WebFetchで実在確認してから`DOCS_URL_MAP`に登録（ハルシネーション防止の既存方針を踏襲）。QuickSightは2025〜2026年に「Amazon Quick」へ改称中で名称が安定しないため、今回は新トピックへの採用を見送り、プロンプトの命名最新化テーブルに改称情報のみ追記
- 8トピック全件をローカルでレンダリングし、アイコン解決漏れ（フォールバックの人物アイコンになっていないか）・日本語表示・レイアウト崩れがないことを目視確認
- 本番Lambdaへデプロイ済み（記事生成を伴う実機テストは前回同様見送り、整合性チェックスクリプトとローカル図生成で確認）
