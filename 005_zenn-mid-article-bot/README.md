# 005 Zenn Article Bot（中級）

> 複合アーキテクチャ×ユースケース別の16トピックから毎月2回、15,000〜30,000文字の中級 AWS 技術記事を Bedrock Claude Sonnet で自動生成するシステム。002（初級Bot）の上位互換として設計。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20S3-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Zenn](https://img.shields.io/badge/Zenn-zenn.dev%2Fzer0__infra-3EA8FF)](https://zenn.dev/zer0_infra)
[![Cost](https://img.shields.io/badge/月額-~%242.8-green)](https://aws.amazon.com/pricing)

## 概要

| 項目             | 内容                                                                     |
| ---------------- | ------------------------------------------------------------------------ |
| 生成頻度         | 毎月1日・15日 21:00 JST                                                  |
| 対応トピック     | 16種類（複合アーキテクチャ8 + ユースケース別8）                          |
| 記事ボリューム   | 15,000〜30,000文字（初級Botの約3倍）                                     |
| 差別化セクション | コスト最適化・セキュリティ設計・スケーラビリティの考慮点を追加           |
| 生成画像         | アーキテクチャ図 PNG × 1枚（AWS公式アイコン使用）                        |
| 使用モデル       | Amazon Bedrock **Claude Sonnet 4.6**（`jp.anthropic.claude-sonnet-4-6`） |
| 月額コスト       | ~$2.8（約420円）                                                         |

## アーキテクチャ

![アーキテクチャ図](images/005_architecture.png)

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
| Bedrock Claude Sonnet（~12,000 tokens/回）           | ~$2.7                |
| Bedrock Claude Haiku（トピック選択 / ~10 tokens/回） | ~$0.001              |
| S3 ストレージ・PUT                                   | ~$0.01               |
| SES 送信（2通/月）                                   | ~$0                  |
| **合計**                                             | **~$2.8（約420円）** |

## 変更履歴

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                                                          |
| ---------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-20 | v1         | 初版リリース。Claude Sonnet + 512MB Lambda + 16トピック体制                                                                                                                                                                                                                                                   |
| 2026-04-28 | v1.1       | 2段階Bedrock呼び出し（トピック選択にHaiku使用）。月額コスト約30%削減                                                                                                                                                                                                                                          |
| 2026-05-05 | v1.2       | `{DIAGRAM_N}` マーカー方式導入。Bedrockが図挿入位置と説明文を記事本文内に自然配置するよう改善                                                                                                                                                                                                                 |
| 2026-05-10 | v1.3       | AWS公式ドキュメント自動取得（primary_serviceのdocs.aws.amazon.com・最大6,000文字）を根拠情報として付与                                                                                                                                                                                                        |
| 2026-05-20 | v1.4       | Lambda Function URL（AWS_IAM認証）追加。EventBridgeスケジュールを止めずに任意タイミングでテスト実行可能に                                                                                                                                                                                                     |
| 2026-06-01 | v1.5       | CFn `validate_template` 検証機能追加・バグ修正5件（重複トピック・TemplateBody上限・HTMLエスケープ・CFn例外取得・マーカー自動除去）・処理時間計測・Bedrockコスト概算ログ追加                                                                                                                                   |
| 2026-06-15 | v1.6       | コードレビュー反映。/tmp 記事フォルダの自動削除（最新5件保持）を002と同様に追加しウォームスタート時のディスク逼迫を防止・トピック選択の部分一致フォールバック追加・Bedrockパラメータ/単価/サイズ上限のマジックナンバーを定数化                                                                                |
| 2026-06-15 | v1.7       | バグ修正2件：① PNG未生成時のDIAGRAMマーカー除去正規表現を `\{\{?DIAGRAM_\d+\}\}?` に修正（`str.format()` 後の単一波括弧も除去対象に）② 見出しなし記事で `_embed_image_placeholders` が画像を無言スキップする問題を修正（末尾追記＋WARNING ログに変更）                                                        |
| 2026-06-16 | v1.8       | 記事内構築手順をCFnテンプレート→AWS CLI中心に変更。プロンプト改修（変数定義セクション必須・コマンドコメントルール・クリーンアップセクション追加）・CFnバリデーション廃止→CLIコマンド存在チェックに置換・`cfn` Lambdaクライアント削除                                                                          |
| 2026-06-16 | v1.9       | コードレビュー反映。①bashブロック例のバックスラッシュをPython行継続から保護（`\\`）②例外ハンドラのCFn表記を修正③CLIバリデーターをbashブロック限定awsチェック＋クリーンアップ同義語対応（後片付け/リソース削除）に改善④`cloudformation:ValidateTemplate` IAM権限を両スタックから削除（CLAUDE.md step5対応）    |
| 2026-06-27 | v2.0       | IAM最小権限化。未使用の`ses:SendRawEmail`・`aws-marketplace:*`権限を削除し、Bedrockの`inference-profile/*`ワイルドカードをHaiku明示ARNに置き換え。CFn再デプロイ済み                                                                                                                                           |
| 2026-07-01 | v2.1       | Opus 4.8コードレビュー（10件）反映。diagram_generator.pyのauto-padding座標破壊・曲線矢印・垂直間隔・figureリーク等のバグを修正、`_load_icon()`にlru_cache追加。孤立DIAGRAMマーカーのクリーンアップも追加                                                                                                      |
| 2026-07-02 | v2.2       | Opus 4.8でlog_analytics記事を精査。構成図が本文のservicesリストと食い違う問題と、CloudTrail経由データのgzipエンベロープ未展開・Athenaパーティション未登録という実バグ2件を発見・修正                                                                                                                          |
| 2026-07-02 | v2.3       | 記事生成後のAI技術レビュー自動化を追加。Bedrockに構造化出力で技術的正確性を検証させ、指摘をメールに掲載（自動修正なし）。Haiku推論プロファイルのリージョン起因IAM不足バグも副次的に発見・修正                                                                                                                 |
| 2026-07-02 | v2.4       | v2.3のレビュー・自動修正機能を撤回（1回書き直し方式の自動修正が新たな矛盾を生む実例を確認）。代わりに全16トピックのサービス数を5→3に削減し、構成図生成をservicesリストから自動生成する汎用方式に刷新                                                                                                          |
| 2026-07-02 | v2.5       | Opusによるコード監査を反映。security_hardening の primary_service 誤り（waf→guardduty）を修正、未使用の secondary_service フィールドと IAM s3:DeleteObject を削除、構成図がサービス数4以上でxlim外にクリップされるバグを修正、Lambda Runtime記述をpython3.14に統一                                            |
| 2026-07-02 | v2.6       | 構成図をほぼ同一内容の2枚から1枚に統合。記事プロンプトの{DIAGRAM_2}マーカー・設計上の考慮ポイント節の図指示を削除し、コスト・セキュリティ・スケーラビリティを図なしで直接解説する構成に変更                                                                                                                   |
| 2026-07-02 | v2.7       | 記事品質改善2点。①primary_serviceの公式ドキュメントURLをコード側で「参考」節に確定挿入（LLMのURL生成なし）②「はじめに」に「この記事でわかること」3行サマリーを追加                                                                                                                                            |
| 2026-07-02 | v2.8       | Fableコードレビュー反映。構成図の矢印を方向性主張なしの直線に変更（実際と逆向きの表示を修正）・Sonnet5切替時のKeyError修正・S3失敗時のBedrockコスト重複回避・microservices_base等の細部修正                                                                                                                   |
| 2026-07-02 | v2.9       | Fableレビュー続き。壊れていたテスト2件を修正しHIGHバグを検出：`generate_article`のtextブロック抽出がthinking打ち切り時にStopIterationでクラッシュする問題を修正、BedrockクライアントのReadTimeout自動リトライを無効化（コスト二重発生防止）、CFnのBedrock ARNリージョンワイルドカードを明示化、回帰テスト追加 |
| 2026-07-06 | v3.0       | Fableブラッシュアップ実施。トピック重複除外を12件に拡張し再登場時はタイトルに周回数を付与、記事品質の機械チェック追加(検出のみ)、メールに見出しアウトライン・レビューチェックリスト追加、根拠ドキュメントを3サービス全件取得、MD+PNGをメール添付、14トピックで構成図矢印を安全に復活                                            |
| 2026-07-06 | v3.1       | deploy.shがaws_icons/・fonts/をLambda ZIPに同梱しておらず、本番の構成図は日本語が文字化けしアイコンも自作の色付きボックスに全滅していた重大な既存バグを発見・修正。両ディレクトリをzip対象に追加し実機確認済み                                                                                             |
