# 003 X Poster Bot (@Zer0_0326)

> 「なんとか生きてる普通の会社員」目線のあるある系コンテンツを毎週月・木20:00に自動投稿するBot（2026-07-05にAI活用系から一般テーマへ全面転換）。言い回しレシピ・数字入り実録・比較・失敗談の実用4カテゴリ＋副業・問いかけで構成し、賛否が分かれる強い意見も辞さないバズ狙い設計。曜日別投稿ロジック・Google Trends連動・重複回避つき。

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
| 生成AI     | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / temperature=0.95） |
| 月額コスト | ~$0.38（約57円）                                                                                        |

## アーキテクチャ

![アーキテクチャ図](images/003_architecture.png)

```text
EventBridge Scheduler（月・木 20:00 JST / 日曜 10:00 JST・リトライ0回）
  └─▶ Lambda（Python 3.14・Timeout 90秒）失敗時 → SNS → メール通知
        ├─ 曜日判定 → カテゴリ選択（SSM 履歴参照）
        │   └─ recipe/jissoku: お題、question: テーマ軸もSSM履歴除外つきで選択
        ├─ カテゴリ別データ取得
        │   ├─ url_reaction: Yahoo!ニュースRSS（経済/国内/エンタメ）から記事取得
        │   └─ trend: Google Trends RSS から急上昇ワード取得（訃報・事件等はNGワードで除外、話題は問わない）
        ├─ Bedrock Claude Haiku（カテゴリ別プロンプトで生成、リトライ設定あり）
        ├─ SSM 投稿履歴更新（used_categories / history / recipe_tasks / question_themes）
        └─ X API v2（POST）
```

## 投稿カテゴリ

| カテゴリ       | 内容                                                                 | 曜日                                |
| -------------- | -------------------------------------------------------------------- | ----------------------------------- |
| `recipe`       | コピペで使える言い回し・テンプレのレシピ（12お題をローテーション）  | 月曜ローテーション枠（50%）         |
| `jissoku`      | 仕事・生活のbefore/after実録（数字必須・盛らない）                   | 月曜ローテーション枠（50%）         |
| `hikaku`       | 働き方・お金・生活の比較とどっち派（断定・返信誘発）                 | 月曜ローテーション枠（50%）         |
| `shippai`      | 仕事・お金・人間関係の失敗談＋回避法（共感×実用）                    | 月曜ローテーション枠（50%）         |
| `fukugyo`      | 副業の現実（数字・やり方入り）                                       | 月曜ローテーション枠（50%）         |
| `question`     | 問いかけ・議論系                                                     | **木曜固定** + 月曜ローテーション枠 |
| `url_reaction` | Yahoo!ニュース記事への率直な反応（URLはリプライへ）                  | 月曜固定枠（50%）                   |
| `trend`        | Google Trends トレンド連動（話題を問わず何にでも反応）               | 日曜固定                            |

## 実装のこだわり

### 1. カテゴリローテーション設計

単純なランダム選択では同じカテゴリが連続するケースが発生する。SSM Parameter Store に直近4件の投稿カテゴリを記録し、**現在候補から直近履歴を除外**することで均等なローテーションを実現（`MAX_CATEGORY_HISTORY=4`・v2.0で7→4に変更）。フォロワーに同じトーンの投稿が続かないようコンテンツの多様性を担保。

### 2. 曜日別固定スロットの設計思想

投稿頻度を毎日→週2回（月・木）に減らすにあたり、固定枠を「最もエンゲージメントが見込めるモード」に寄せつつ、**月曜は `url_reaction` と通常ローテーションを50%ずつ出し分けてコンテンツの予測可能性を下げる**設計に変更（固定一辺倒だと逆に「Bot感」が強まるため）。

- **木曜 `question`**: 調査の結果、最もインプレッションが伸びやすい曜日と判明。返信エンゲージメント最大化を狙う問いかけ投稿で固定
- **月曜 `url_reaction` / ローテーション 50%**: 週明けの情報収集ニーズに合わせて Zenn/Qiita 記事感想を投入しつつ、半分はローテーションプールから選び多様性を担保
- **日曜 `trend`**: 週末の話題と会社員の日常を絡めてバズりやすいコンテンツを投入

### 3. Bedrock システムプロンプトの導入

カテゴリ別の「一行目フック必須」「体言止め禁止」「絵文字の使用箇所制限」を**システムプロンプト**として設定。temperature=0.95 の高い多様性設定と組み合わせ、毎回異なる表現ながらも口調が崩れない投稿を生成。

### 4. `url_reaction` の記事概要拡張

当初 150 文字の記事概要では Bedrock が感想の根拠を生成しにくい問題があった。記事本文冒頭を 300 文字に拡張し、具体的な感想付きで投稿できるよう改善。

### 5. ハッシュタグの動的ローテーション

`#会社員あるある` / `#仕事術` / `#働き方` など10個のハッシュタグプールから投稿ごとに選択し、特定タグへの依存を避ける。アルゴリズムの変動に対してリスク分散。

### 6. 実行失敗のSNS通知（2026-07-05追加）

Scheduler・Lambda双方のリトライを0にしているため、失敗した回の投稿は静かに消えログを見ない限り気づけなかった。001と同じ`EventInvokeConfig.DestinationConfig.OnFailure → SNS → email`パターンを移植し、`RecipientEmail`パラメータ設定時のみ有効化（未設定なら通知設定自体をスキップ）。

### 7. recipe/jissoku・questionのお題/テーマ重複回避（2026-07-05追加）

カテゴリ自体は直近4件除外があるが、recipe/jissokuが共有する12業務お題・questionの10テーマ軸には重複回避がなく、確率1/12や1/10で近い内容が連続しうる問題があった。002のトピック除外方式と同じくSSM履歴（recipe_tasksは直近5件、question_themesは直近4件、いずれも総数より必ず小さい値）で直近使用分を除外してから選択する。

### 8. trendカテゴリのNGワードフィルタ（2026-07-05追加）

Google Trends急上昇には訃報・事件・災害・政治が頻繁に入るため、「訃報トレンド×軽いつぶやき」が生成されるとアカウントの信頼を損なうリスクがあった。Tier1〜3の全候補から、訃報・逮捕・災害・政治関連のNGワードを含むキーワードを事前除外する。

### 9. AIコンセプトの全面撤廃とバズ狙いへの転換（2026-07-05）

投稿頻度がほとんど変わらず反応が薄かったため、ユーザーの意向で「AI活用系Bot」という前提を撤廃し、話題をAIに限らない「なんとか生きてる普通の会社員」のあるある系バズ狙いコンテンツへ全面転換した。

- **フックを強化**: 「1行目が命」の書き出しパターンに挑発型（「〜はもう終わってる」等）を追加し、断定・強い意見で終わる投稿を許容するよう`ABSOLUTE_RULES`/`STYLE_GUIDE`を改訂（ただし個人・企業攻撃や誤情報の断定は禁止）
- **話題を仕事・お金・人間関係・トレンド全般に拡大**: 全カテゴリ（recipe/jissoku/hikaku/shippai/fukugyo/question/trend/url_reaction）のプロンプト・few-shot例・お題・ハッシュタグ・キーワードリストを非AI一般テーマに書き換え
- **url_reactionのRSSフィードを一般ニュースに変更**: Zenn/Qiita（AI関連タグ）からYahoo!ニュース（経済・国内・エンタメ）へ切り替え
- **trendのAI紐付けを撤廃**: `pick_ai_relatable_trend`→`pick_relatable_trend`にリネームし、Tier1/2キーワードを仕事・お金・生活全般に変更。Tier3（任意の日本語キーワード）フォールバックは維持のため実質どんな話題も拾える
- リスク許容度は「積極的」（賛否が分かれてもいい）とユーザーが明示。ただし誹謗中傷・差別・誤情報の断定は引き続き禁止

## 技術スタック

| レイヤー         | 技術                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| 実行基盤         | AWS Lambda（Python 3.14）                                                                               |
| スケジューリング | Amazon EventBridge Scheduler（JST対応・2スロット）                                                      |
| 生成AI           | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / temperature=0.95） |
| 状態管理         | SSM Parameter Store（8パラメータで履歴管理）                                                            |
| 外部データ       | Yahoo!ニュース RSS / Google Trends RSS                                                                  |
| 投稿先           | X API v2                                                                                                |
| IaC              | CloudFormation                                                                                          |

## ディレクトリ構成

```text
003_x-poster_zer0-0326/
├── src/
│   ├── lambda_function.py              # メインロジック
│   ├── cfn-x-poster-zer0-0326.yaml
│   ├── deploy.sh                       # デプロイスクリプト
│   └── tests/
│       └── test_lambda_function.py     # ユニットテスト（23件）
├── scripts/
│   └── test_invoke.sh                  # テストスクリプト（dry_runペイロード対応）
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

# dry_run テスト（実投稿・SSM履歴更新なし。ペイロードで指定するため本番環境変数は変更しない）
bash scripts/test_invoke.sh
# mode指定（random / trend）
bash scripts/test_invoke.sh trend

# ユニットテスト（23件）
cd src && python -m pytest tests/ -v
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
| `/ai_bot/history/recipe_tasks`        | String       | Lambda自動更新（2026-07-05追加） |
| `/ai_bot/history/question_themes`     | String       | Lambda自動更新（2026-07-05追加） |

## トラブルシューティング

| 症状                   | 原因                           | 対処                                                        |
| ---------------------- | ------------------------------ | ----------------------------------------------------------- |
| 投稿されない           | 環境変数 `DRY_RUN=true` のまま | Lambda 環境変数 `DRY_RUN` を `false` に更新                 |
| 同カテゴリが連続投稿   | SSM履歴破損                    | `/ai_bot/history/used_categories` を削除してリセット        |
| X API 403 Forbidden    | APIクレジット不足              | developer.x.com でクレジット残高確認・チャージ              |
| X API 401 Unauthorized | アクセストークン期限切れ       | `bash src/setup_ssm.sh` で4キーを再登録                     |
| Bedrock エラー         | モデルアクセス未承認           | AWS Console → Bedrock → モデルアクセスで Haiku 4.5 を有効化 |
| url_reaction 記事が0件 | Yahoo!ニュースRSSフィード取得失敗 | CloudWatch Logs で HTTP ステータス確認                  |
| 実行失敗に気づかない  | 通知メール未設定               | CFn `RecipientEmail` パラメータを設定してスタック更新（2026-07-05追加） |

## コスト内訳

| サービス                               | 月額                 |
| -------------------------------------- | -------------------- |
| Lambda 実行（~35回/月）                | ~$0.001              |
| Bedrock Claude Haiku（~400 tokens/回） | ~$0.04               |
| X API（$0.01/件 × 34件/月）            | ~$0.34               |
| EventBridge・SSM                       | ~$0                  |
| **合計**                               | **~$0.38（約57円）** |

## 変更履歴

| 日付       | バージョン | 内容                                                                                                                                                                                                                                                                                                    |
| ---------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-15 | v1         | 初版リリース。EventBridge Scheduler + Lambda + Bedrock Haiku による毎日22:00 X自動投稿                                                                                                                                                                                                                  |
| 2026-04-20 | v1.1       | 6カテゴリローテーション（shigoto/fukugyo/jitsuwa/question/suji/url_reaction）実装。SSMで直近7件履歴管理                                                                                                                                                                                                 |
| 2026-04-25 | v1.2       | 曜日別固定スロット追加。水曜=question固定、火・金=url_reaction固定                                                                                                                                                                                                                                      |
| 2026-05-01 | v1.3       | Google Trends RSS連動の `trend` カテゴリ（日曜10:00）追加。Tier1/2/3優先度でキーワード選択                                                                                                                                                                                                              |
| 2026-05-10 | v1.4       | url_reaction の記事概要を150→300文字に拡張。Bedrockが具体的な感想を生成しやすくなるよう改善                                                                                                                                                                                                             |
| 2026-05-29 | v1.5       | スタック名・Lambda関数名を `x-poster-zer0-0326` にリネーム。DRY_RUNテスト済み                                                                                                                                                                                                                           |
| 2026-06-07 | v1.6       | 投稿頻度を毎日→毎週月・木に変更。曜日別ロジックを再設計（木=question固定、月=url_reaction/ローテーション50%出し分け）。エンゲージメント向上・Bot感の軽減が目的                                                                                                                                          |
| 2026-06-08 | v1.7       | 夜投稿の時刻を 22:00 → 20:00 JST に変更。001（@Zer0_Infra）と投稿時刻を統一し管理をシンプル化                                                                                                                                                                                                           |
| 2026-06-11 | v1.8       | 人間味改善：投稿ごとに文章フォーマット4種（改行ポエム調/通常文体/短文ひとこと/通常文+一言）を抽選してプロンプトに注入し、毎回同じポエム調になるのを解消。「…」・フィラーの使用回数制限、自虐オチ偏重の緩和、140字カットを文末境界で切るよう改善。url_reactionに「記事にないことを断定しない」ルール追加 |
| 2026-06-11 | v1.9       | リーチ最適化：url_reaction の記事URLを本文からリプライぶら下げに変更（リンク入り投稿のリーチ抑制対策）。約35%はハッシュタグなしで投稿（Bot感軽減）                                                                                                                                                      |
| 2026-06-22 | v2.2       | バグ修正＋ブラッシュアップ：url_reactionハッシュタグ二重付与防止（モデル挿入タグを除去してから pick_hashtag）、url_reaction を NO_HASHTAG_RATE 除外、FORCE_CATEGORY フォールバック時の category 未セットを修正、CFn に `ReservedConcurrentExecutions: 1` 追加                                           |
| 2026-06-11 | v2.0       | 投稿コンセプトを再設計：共感ポエム路線から「持ち帰れる具体を1つ入れる」実用路線へ。新カテゴリ recipe / jissoku / hikaku / shippai を新設し shigoto / jitsuwa / suji / nichijo を廃止。url_reaction・fukugyo のプロンプト強化、カテゴリ履歴を直近4件に変更、FORCE_CATEGORY 環境変数を追加                |
| 2026-06-15 | v2.1       | コードレビュー反映：trend / url_reaction の固定スロットを used_categories に書き込まないよう修正（ローテーション枠が圧迫されるバグを解消）。`save_url_history` の未使用引数 `used_urls` を削除。マジックナンバー（タグなし率・月曜url_reaction率・本文上限）を定数化                                    |
| 2026-06-27 | v2.3       | コードレビュー反映（IAM最小権限化）：Bedrock IAM Resource の全リージョンワイルドカード `arn:aws:bedrock:*::foundation-model/...` を削除し、明示の `ap-northeast-1` と `ap-northeast-3` の2リージョンに統一（001 と同じ最小権限構成に揃える）                                                            |
| 2026-07-03 | v2.4       | **第2巡Fableレビュー HIGH修正**: 001と共通の加重文字数バグを修正（weighted length安全弁を追加）。複数タグ1行のケースでタグ除去漏れが再発する不具合を行単位判定に変更。EventBridge Schedulerのデフォルトリトライ（185回）を無効化（二重投稿防止）・6フィード直列取得のtimeoutを10→5秒に短縮              |
| 2026-07-05 | v2.5       | **Fableブラッシュアップ**: 001と同じOnFailure SNS通知を追加（RecipientEmail設定時のみ）・Bedrockクライアントにリトライ設定追加＋Timeout 60→90秒・trendカテゴリにNGワードフィルタ追加（炎上防止）・dry_runをイベントペイロード化しtest_invoke.shの本番環境変数書き換え方式を廃止（事故リスク解消）・recipe/jissokuのお題とquestionのテーマ軸にSSM履歴除外を追加（マンネリ化対策）・weightedトリムの重複ロジックを共通ヘルパーに統合し投稿URLをログ/戻り値に追加。ユニットテスト23件新規追加。CFn更新・Lambdaデプロイ・本番dry_run検証済み |
| 2026-07-05 | v2.6       | **AIコンセプト全面撤廃・バズ狙いへ転換**: ユーザー要望により「AI活用系Bot」の前提を撤廃し、話題をAIに限らない会社員あるある系コンテンツへ変更。全カテゴリのプロンプト・few-shot例・お題・ハッシュタグ・キーワードを非AI一般テーマに書き換え、フック強化（挑発型追加・断定終わりの許容）とバズ狙いの強い意見を明示的に許可（誹謗中傷・誤情報は禁止）。url_reactionのRSSフィードをZenn/Qiita（AI関連タグ）→Yahoo!ニュース（経済/国内/エンタメ）に変更。`pick_ai_relatable_trend`を`pick_relatable_trend`にリネームしAI紐付け要件を撤廃（Tier3で任意の話題を拾う）。テスト24件（AI関連アサーションを新テーマに合わせて更新）全パス。Lambdaデプロイ・本番dry_run検証済み |
