# 003 X Poster Bot (@Zer0_0326)

> AI活用術・会社員あるある系コンテンツを6カテゴリで日替わりローテーションしながら毎日22:00に自動投稿するBot。曜日別投稿ロジック・Google Trends連動・直近7投稿での重複回避で飽きさせないコンテンツ設計を実現。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20EventBridge-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Cost](https://img.shields.io/badge/月額-~%240.38-green)](https://aws.amazon.com/pricing)

## 概要

| 項目       | 内容                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| 投稿頻度   | 毎日 22:00 JST + 日曜 10:00 JST（trend）の計2スロット                                                   |
| カテゴリ数 | 6カテゴリ（shigoto/fukugyo/jitsuwa/question/suji/nichijo）+ 固定2スロット（url_reaction/trend）         |
| 重複防止   | 直近7投稿で同カテゴリが連続しないようSSMで履歴管理                                                      |
| 曜日別制御 | 水曜: question 固定 / 火・金: url_reaction / 日曜: trend                                                |
| AI生成     | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / temperature=0.95） |
| 月額コスト | ~$0.38（約57円）                                                                                        |

## アーキテクチャ

![アーキテクチャ図](images/003_architecture.png)

```text
EventBridge Scheduler（22:00 JST / 日曜 10:00 JST）
  └─▶ Lambda（Python 3.14）
        ├─ 曜日判定 → カテゴリ選択（SSM 履歴参照）
        ├─ カテゴリ別データ取得
        │   ├─ url_reaction: Zenn/Qiita RSS から AI記事取得
        │   └─ trend: Google Trends RSS から急上昇ワード取得
        ├─ Bedrock Claude Haiku（カテゴリ別プロンプトで生成）
        ├─ SSM 投稿履歴更新（used_categories / history）
        └─ X API v2（POST）
```

## 投稿カテゴリ

| カテゴリ       | 内容                                                   | 曜日                    |
| -------------- | ------------------------------------------------------ | ----------------------- |
| `shigoto`      | 仕事×AIあるある                                        | ランダム                |
| `fukugyo`      | 副業の現実                                             | ランダム                |
| `jitsuwa`      | 「実は〜してる」告白系                                 | ランダム                |
| `question`     | 問いかけ・議論系                                       | **水曜固定** + ランダム |
| `suji`         | 「〇つのこと」リスト型                                 | ランダム                |
| `nichijo`      | 日常のどうでもいいこと（通勤・食事・会社の謎ルール等） | ランダム                |
| `url_reaction` | Zenn/Qiita 記事感想（URL付き）                         | 火・金固定              |
| `trend`        | Google Trends トレンド連動                             | 日曜固定                |

## 実装のこだわり

### 1. カテゴリローテーション設計

単純なランダム選択では同じカテゴリが連続するケースが発生する。SSM Parameter Store に直近7件の投稿カテゴリを記録し、**現在候補から直近履歴を除外**することで均等なローテーションを実現。フォロワーに同じトーンの投稿が続かないようコンテンツの多様性を担保。

### 2. 曜日別固定スロットの設計思想

- **水曜 `question`**: 週の中間でエンゲージメント（リプライ・引用RT）を狙う問いかけ投稿
- **火・金 `url_reaction`**: ビジネスデーの終わりに技術記事の感想を届け、学習意欲の高いフォロワーへリーチ
- **日曜 `trend`**: 週末の話題と AI を絡めてバズりやすいコンテンツを投入

### 3. Bedrock システムプロンプトの導入

カテゴリ別の「一行目フック必須」「体言止め禁止」「絵文字の使用箇所制限」を**システムプロンプト**として設定。temperature=0.95 の高い多様性設定と組み合わせ、毎回異なる表現ながらも口調が崩れない投稿を生成。

### 4. `url_reaction` の記事概要拡張

当初 150 文字の記事概要では Bedrock が感想の根拠を生成しにくい問題があった。Zenn/Qiita の記事本文冒頭を 300 文字に拡張し、具体的な感想付きで投稿できるよう改善。

### 5. ハッシュタグの動的ローテーション

`#AI活用` / `#生成AI` / `#ChatGPT` など10個のハッシュタグプールから投稿ごとに選択し、特定タグへの依存を避ける。アルゴリズムの変動に対してリスク分散。

## 技術スタック

| レイヤー         | 技術                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| 実行基盤         | AWS Lambda（Python 3.14）                                                                               |
| スケジューリング | Amazon EventBridge Scheduler（JST対応・2スロット）                                                      |
| AI生成           | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / temperature=0.95） |
| 状態管理         | SSM Parameter Store（8パラメータで履歴管理）                                                            |
| 外部データ       | Zenn RSS / Qiita RSS / Google Trends RSS                                                                |
| 投稿先           | X API v2                                                                                                |
| IaC              | CloudFormation                                                                                          |

## ディレクトリ構成

```text
003_x-poster_zer0-0326/
├── src/
│   ├── lambda_function.py              # メインロジック
│   ├── cfn-x-poster-zer0-0326.yaml
│   └── deploy.sh                       # デプロイスクリプト
├── scripts/
│   └── test_invoke.sh                  # テストスクリプト（DRY_RUN対応）
└── images/
    └── 003_architecture.png
```

## デプロイ

```bash
# 初回: X APIキーをSSMに登録 → CFn + コードを一括デプロイ
bash src/setup_ssm.sh
bash src/deploy.sh

# コードのみ更新
bash src/deploy.sh

# DRY_RUN テスト（実投稿なし）
bash scripts/test_invoke.sh
# mode指定（random / trend）
bash scripts/test_invoke.sh trend
```

## 運用コマンド

```bash
# 最新ログ確認
aws logs tail /aws/lambda/x-poster-zer0-0326 --follow --region ap-northeast-1

# カテゴリ履歴リセット（同カテゴリ連続投稿が起きた場合）
aws ssm delete-parameter --name "/ai_bot/history/used_categories" --region ap-northeast-1
```

## SSMパラメータ

| パラメータ名                          | 種別         | 管理           |
| ------------------------------------- | ------------ | -------------- |
| `/ai_bot/twitter_api_key`             | SecureString | setup_ssm.sh   |
| `/ai_bot/twitter_api_secret`          | SecureString | setup_ssm.sh   |
| `/ai_bot/twitter_access_token`        | SecureString | setup_ssm.sh   |
| `/ai_bot/twitter_access_token_secret` | SecureString | setup_ssm.sh   |
| `/ai_bot/history/used_categories`     | String       | Lambda自動更新 |
| `/ai_bot/history/{category}`          | String       | Lambda自動更新 |
| `/ai_bot/history/url_reaction_urls`   | String       | Lambda自動更新 |

## トラブルシューティング

| 症状                   | 原因                           | 対処                                                        |
| ---------------------- | ------------------------------ | ----------------------------------------------------------- |
| 投稿されない           | DRY_RUN=true のまま            | Lambda 環境変数 `DRY_RUN` を `false` に更新                 |
| 同カテゴリが連続投稿   | SSM履歴破損                    | `/ai_bot/history/used_categories` を削除してリセット        |
| X API 403 Forbidden    | APIクレジット不足              | developer.x.com でクレジット残高確認・チャージ              |
| X API 401 Unauthorized | アクセストークン期限切れ       | `bash src/setup_ssm.sh` で4キーを再登録                     |
| Bedrock エラー         | モデルアクセス未承認           | AWS Console → Bedrock → モデルアクセスで Haiku 4.5 を有効化 |
| url_reaction 記事が0件 | Zenn/Qiita RSSフィード取得失敗 | CloudWatch Logs で HTTP ステータス確認                      |

## コスト内訳

| サービス                               | 月額                 |
| -------------------------------------- | -------------------- |
| Lambda 実行（~35回/月）                | ~$0.001              |
| Bedrock Claude Haiku（~400 tokens/回） | ~$0.04               |
| X API（$0.01/件 × 34件/月）            | ~$0.34               |
| EventBridge・SSM                       | ~$0                  |
| **合計**                               | **~$0.38（約57円）** |

## 変更履歴

| 日付       | バージョン | 内容                                                                                                    |
| ---------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| 2026-04-15 | v1         | 初版リリース。EventBridge Scheduler + Lambda + Bedrock Haiku による毎日22:00 X自動投稿                  |
| 2026-04-20 | v1.1       | 6カテゴリローテーション（shigoto/fukugyo/jitsuwa/question/suji/url_reaction）実装。SSMで直近7件履歴管理 |
| 2026-04-25 | v1.2       | 曜日別固定スロット追加。水曜=question固定、火・金=url_reaction固定                                      |
| 2026-05-01 | v1.3       | Google Trends RSS連動の `trend` カテゴリ（日曜10:00）追加。Tier1/2/3優先度でキーワード選択              |
| 2026-05-10 | v1.4       | url_reaction の記事概要を150→300文字に拡張。Bedrockが具体的な感想を生成しやすくなるよう改善             |
| 2026-05-29 | v1.5       | スタック名・Lambda関数名を `x-poster-zer0-0326` にリネーム。DRY_RUNテスト済み                           |
