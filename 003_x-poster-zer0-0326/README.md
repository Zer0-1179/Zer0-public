# 003 X Poster Bot (@Zer0_0326)

> 「コピペで使えるAI活用の具体」を会社員目線で毎週月・木20:00に自動投稿するBot。プロンプトレシピ・数字入り実録・比較・失敗談の実用4カテゴリ＋副業・問いかけで構成し、全投稿に保存したくなる持ち帰りを1つ入れる設計。曜日別投稿ロジック・Google Trends連動・重複回避つき。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20EventBridge-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Cost](https://img.shields.io/badge/月額-~%240.38-green)](https://aws.amazon.com/pricing)

## 概要

| 項目       | 内容                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| 投稿頻度   | 毎週月・木 20:00 JST + 日曜 10:00 JST（trend）の計2スロット                                             |
| カテゴリ数 | 6カテゴリ（recipe/jissoku/hikaku/shippai/fukugyo/question）+ 固定2スロット（url_reaction/trend）        |
| 重複防止   | 直近4投稿で同カテゴリが連続しないようSSMで履歴管理                                                      |
| 曜日別制御 | 月曜: url_reaction 50% / ローテーション 50% ・木曜: question固定 ・日曜: trend                          |
| AI生成     | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / temperature=0.95） |
| 月額コスト | ~$0.38（約57円）                                                                                        |

## アーキテクチャ

![アーキテクチャ図](images/003_architecture.png)

```text
EventBridge Scheduler（月・木 20:00 JST / 日曜 10:00 JST）
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

| カテゴリ       | 内容                                                                 | 曜日                                |
| -------------- | -------------------------------------------------------------------- | ----------------------------------- |
| `recipe`       | コピペで使えるプロンプトレシピ（12業務お題をローテーション）         | 月曜ローテーション枠（50%）         |
| `jissoku`      | AI活用のbefore/after実録（数字必須・盛らない）                       | 月曜ローテーション枠（50%）         |
| `hikaku`       | ツール・使い方の比較とどっち派（返信誘発）                           | 月曜ローテーション枠（50%）         |
| `shippai`      | AI活用の失敗談＋回避法（共感×実用）                                  | 月曜ローテーション枠（50%）         |
| `fukugyo`      | 副業×AIの現実（数字・やり方入り）                                    | 月曜ローテーション枠（50%）         |
| `question`     | 問いかけ・議論系                                                     | **木曜固定** + 月曜ローテーション枠 |
| `url_reaction` | Zenn/Qiita 記事からの「持ち帰り」1つ＋正直な反応（URLはリプライへ）  | 月曜固定枠（50%）                   |
| `trend`        | Google Trends トレンド連動                                           | 日曜固定                            |

## 実装のこだわり

### 1. カテゴリローテーション設計

単純なランダム選択では同じカテゴリが連続するケースが発生する。SSM Parameter Store に直近7件の投稿カテゴリを記録し、**現在候補から直近履歴を除外**することで均等なローテーションを実現。フォロワーに同じトーンの投稿が続かないようコンテンツの多様性を担保。

### 2. 曜日別固定スロットの設計思想

投稿頻度を毎日→週2回（月・木）に減らすにあたり、固定枠を「最もエンゲージメントが見込めるモード」に寄せつつ、**月曜は `url_reaction` と通常ローテーションを50%ずつ出し分けてコンテンツの予測可能性を下げる**設計に変更（固定一辺倒だと逆に「Bot感」が強まるため）。

- **木曜 `question`**: 調査の結果、最もインプレッションが伸びやすい曜日と判明。返信エンゲージメント最大化を狙う問いかけ投稿で固定
- **月曜 `url_reaction` / ローテーション 50%**: 週明けの情報収集ニーズに合わせて Zenn/Qiita 記事感想を投入しつつ、半分はローテーションプールから選び多様性を担保
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

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-15 | v1         | 初版リリース。EventBridge Scheduler + Lambda + Bedrock Haiku による毎日22:00 X自動投稿                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-04-20 | v1.1       | 6カテゴリローテーション（shigoto/fukugyo/jitsuwa/question/suji/url_reaction）実装。SSMで直近7件履歴管理                                                                                                                                                                                                                                                                                                                                                                                                           |
| 2026-04-25 | v1.2       | 曜日別固定スロット追加。水曜=question固定、火・金=url_reaction固定                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-05-01 | v1.3       | Google Trends RSS連動の `trend` カテゴリ（日曜10:00）追加。Tier1/2/3優先度でキーワード選択                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 2026-05-10 | v1.4       | url_reaction の記事概要を150→300文字に拡張。Bedrockが具体的な感想を生成しやすくなるよう改善                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-29 | v1.5       | スタック名・Lambda関数名を `x-poster-zer0-0326` にリネーム。DRY_RUNテスト済み                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-06-07 | v1.6       | 投稿頻度を毎日→毎週月・木に変更。曜日別ロジックを再設計（木=question固定、月=url_reaction/ローテーション50%出し分け）。エンゲージメント向上・Bot感の軽減が目的                                                                                                                                                                                                                                                                                                                                                    |
| 2026-06-08 | v1.7       | 夜投稿の時刻を 22:00 → 20:00 JST に変更。001（@Zer0_Infra）と投稿時刻を統一し管理をシンプル化                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-06-11 | v1.8       | 人間味改善：投稿ごとに文章フォーマット4種（改行ポエム調/通常文体/短文ひとこと/通常文+一言）を抽選してプロンプトに注入し、毎回同じポエム調になるのを解消。「…」・フィラーの使用回数制限、自虐オチ偏重の緩和、140字カットを文末境界で切るよう改善。url_reactionに「記事にないことを断定しない」ルール追加                                                                                                                                                                                                           |
| 2026-06-11 | v1.9       | リーチ最適化：url_reaction の記事URLを本文からリプライぶら下げに変更（リンク入り投稿のリーチ抑制対策）。約35%はハッシュタグなしで投稿（Bot感軽減）                                                                                                                                                                                                                                                                                                                                                                |
| 2026-06-11 | v2.0       | 投稿コンセプトを0から再設計：共感ポエム路線 → 「全投稿に持ち帰れる具体を1つ入れる」実用路線へ。新カテゴリ recipe（コピペで使えるプロンプトレシピ・12業務お題ローテーション）/ jissoku（数字入りbefore/after実録）/ hikaku（ツール比較・どっち派）/ shippai（失敗談＋回避法）を新設し、shigoto / jitsuwa / suji / nichijo を廃止（SSM履歴も削除）。url_reaction は「記事からの持ち帰り1つ＋正直な反応」に強化、fukugyo は数字・やり方必須に強化。カテゴリ履歴を直近4件に変更。テスト用 FORCE_CATEGORY 環境変数追加 |
| 2026-06-15 | v2.1       | コードレビュー反映：trend / url_reaction の固定スロットを used_categories（ローテーション重複回避ウィンドウ）に書き込まないよう修正（ローテーション枠が固定スロット投稿で圧迫されるバグを解消）。`save_url_history` の未使用引数 `used_urls` を削除。マジックナンバー（タグなし率 0.35 / 月曜url_reaction率 0.5 / 本文上限 100・140）を定数化 |
