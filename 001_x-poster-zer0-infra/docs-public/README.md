# 001 X Poster Bot (@Zer0_Infra)

> AWS公式の日本語RSSからインフラ系サービスのアップデートを抽出し、Bedrock Claude で @Zer0_Infra の口調に変換して、インフラ運用者の目線でXへ毎週月・木20時に自動投稿するサーバーレスBot。3段階の重複フィルタと事実検証で品質を担保。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20EventBridge-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Cost](https://img.shields.io/badge/月額-~%240.45-green)](https://aws.amazon.com/pricing)

## 概要

| 項目       | 内容                                                                    |
| ---------- | ----------------------------------------------------------------------- |
| 投稿頻度   | 毎週月・木 20:00 JST（夜）の週2回                                       |
| 情報ソース | AWS公式ニュース / AWSブログ日本語版（インフラ系サービスの記事のみ）     |
| 取得期間   | 過去14日以内の記事のみ                                                  |
| 重複排除   | URL完全一致 → キーワード → AWSサービス名の3段階                         |
| AI変換     | Amazon Bedrock Claude Haiku（①口調変換 → ②記事本文との事実検証の2段階） |
| IaC        | CloudFormation（全リソース管理）                                        |
| 月額コスト | ~$0.45（約70円）                                                        |

## アーキテクチャ

![アーキテクチャ図](../images/001_architecture_plugin_flowdot.svg)

```text
EventBridge ルール（月・木 20:00 JST）
  └─▶ Lambda（Python 3.14）
        ├─ RSS 取得（AWS公式ニュース・AWSブログ日本語版）
        ├─ インフラ系記事の抽出 + 14日フィルタ + 3段階重複排除
        ├─ 根拠本文の取得（公式ニュースはRSS本文、ブログは<article>内）
        ├─ Bedrock Claude Haiku ①投稿文生成 → ②事実検証（2段階呼び出し）
        ├─ SSM Parameter Store（投稿履歴。4KB上限を超えないよう切り詰めて保存）
        └─ X API v2（本文投稿 → 記事URLをリプライにぶら下げ / スレッド連投）
```

## 技術スタック

| レイヤー         | 技術                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------ |
| 実行基盤         | AWS Lambda（Python 3.14 / 256MB / 120秒）                                            |
| スケジューリング | Amazon EventBridge ルール（UTC cron、JST 換算）                                      |
| AI変換           | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0`） |
| 状態管理         | AWS Systems Manager Parameter Store                                                  |
| 投稿先           | X（旧Twitter）API v2                                                                 |
| IaC              | AWS CloudFormation                                                                   |

## 実装のこだわり

### 1. インフラ系記事の抽出

AWS公式ニュースは1日に10件以上出て、生成AIや業界特化サービスの告知が大半を占める。以前は各フィードの上位5件だけを見ていたため、インフラの話題がほとんど拾われなかった。

- **全件取得してから絞り込み**: 公式ニュースは最大100件を取得し、EC2・VPC・CloudWatch・CloudFormation・ECS・Lambda等の`INFRA_KEYWORDS`をタイトルに含む記事だけを候補にする
- **部分一致の誤検出防止**: 英数字の境界つきで判定し、「WebSocket」の中の「EBS」のような一致を拾わない
- **関係の薄い告知の除外**: GovCloud・他リージョンへの提供拡大や、移行ツール等の運用と関係の薄いサービスを除外する。東京・大阪が対象に含まれる告知は残す

### 2. 3段階の重複排除ロジック

単純な URL 一致だと「別 URL の同内容記事」を投稿してしまうケースがあった。

- **第1段階**: 投稿済み URL 完全一致チェック（SSM 保存）
- **第2段階**: タイトルキーワード類似度チェック
- **第3段階**: AWS サービス名抽出 + 直近投稿との重複チェック

### 3. IAM 最小権限設計

`AmazonBedrockFullAccess` から特定モデル ARN のみ許可するカスタムポリシーに変更。SSM も `/xposter/*` パスのみ読み取り許可に絞り込み、最小権限の原則を実装。

### 4. 投稿前の事実検証（2段階 Bedrock 呼び出し）

RSS の概要150文字だけを根拠に生成すると、対応リージョン・料金・制限値などをモデルが推測で補ってしまうリスクがある。対策として、

- **グラウンディング**: 記事本文（最大2,500文字）をプロンプトに渡し、「記事に書いてあることだけを事実として使う」ルールを徹底。AWSのページは先頭がナビゲーションで占められるため、公式ニュースはRSSに入っている告知本文、ブログはページの`<article>`内だけを使う
- **体験談の禁止**: 投稿者がまだ試していない機能について「使ってみた」「ハマった」と書かないよう、生成・検証の両方で体験談の記述を禁止
- **事実検証パス**: 生成された投稿を記事本文と突き合わせる2回目の Bedrock 呼び出しで検証。根拠のない事実主張は削除または感想・疑問形に書き換えてから投稿（出力はプリフィル + JSON 形式で本文のみを確実に抽出）

### 5. リーチ最適化（万垢運用の定石を反映）

- **URLはリプライにぶら下げ**: Xのアルゴリズムは外部リンク入り投稿のリーチを抑制するため、本文にはURLを入れず投稿直後にリプライとして付ける
- **ハッシュタグは最大1個・約35%はタグなし**: Xではタグの流入効果が薄く、毎回複数タグはBot感・スパム感のシグナルになるため
- **スレッド形式の解説投稿（thread_tips）**: 「〜のアップデート、運用目線で整理してみる🧵」のようなフック＋1ツイート1ポイントの連投
- **問いかけで締める比率を最多に**: Xが公開しているおすすめアルゴリズム（[xai-org/x-algorithm](https://github.com/xai-org/x-algorithm)）では、予測リプライ率の重み（5.0）が予測いいね率の重み（0.66）の約7倍。インフラ運用者が自分の環境を答えたくなる具体的な問いかけを40%の確率で入れる

### 6. 投稿履歴の容量管理

投稿履歴はSSM Parameter Store（Standard tier、上限4KB）に1件のJSONで保存している。2026年9月に上限に達して保存が毎回失敗し、投稿タイプが1種類に固定される不具合が起きた（保存失敗は投稿成功後のため握りつぶされ、気づきにくかった）。保存前に3,800バイト以内へ古い要素から切り詰める`fit_history()`を入れ、URL履歴等の件数も実際に必要な分まで減らした。

### 7. 人間味のランダム化

毎回同じ長さ・同じ締め方になる AI っぽさを消すため、投稿ごとに「目安文字数」と「締め方（問いかけ40%/共感25%/感想25%/余韻10%）」をコード側で抽選してプロンプトに注入。同義ハッシュタグ（`#ElasticLoadBalancing`→`#ELB`、`#SystemsManager`→`#SSM`）は略称側に正規化して重複排除。

## ディレクトリ構成

```text
001_x-poster_zer0-infra/
├── src/
│   ├── lambda_function.py          # メインロジック
│   ├── cfn-x-poster-zer0-infra.yaml
│   ├── deploy.sh                   # デプロイスクリプト
│   └── requirements.txt
├── tests/                          # pytest（純関数のユニットテスト）
└── images/
    ├── 001_architecture_plugin.drawio        # 構成図（draw.ioで手動編集する一次情報源）
    └── 001_architecture_plugin_flowdot.svg   # 上記からエクスポートした画像（本ドキュメントで表示）
```

## デプロイ

```bash
# 初回（CloudFormation + Lambda コード）
bash src/deploy.sh --full

# コードのみ更新
bash src/deploy.sh

# DRY_RUN テスト（実投稿なし）
bash src/deploy.sh --test
```

## 運用コマンド

```bash
# 最新ログ確認
aws logs tail /aws/lambda/x-poster-zer0-infra --follow --region ap-northeast-1

# EventBridge 一時停止・再開
aws events disable-rule --name x-poster-zer0-infra-evening --region ap-northeast-1
aws events enable-rule  --name x-poster-zer0-infra-evening --region ap-northeast-1

# 投稿履歴リセット（重複投稿が起きた場合）
aws ssm delete-parameter --name "/xposter/posted-history" --region ap-northeast-1
```

## ロールバック

```bash
# デプロイ済みバージョン一覧確認
aws lambda list-versions-by-function --function-name x-poster-zer0-infra \
  --region ap-northeast-1 --query "Versions[-5:].[Version,LastModified]" --output table

# 前バージョンに戻す（GitHub から該当コミットを checkout → 再デプロイ）
bash src/deploy.sh
```

## コスト内訳

| サービス                                   | 月額                 |
| ------------------------------------------ | -------------------- |
| Lambda 実行（約9回/月 × ~6秒）             | ~$0                  |
| Bedrock Claude Haiku（生成+検証 2回/投稿） | ~$0.02               |
| X API（$0.02/件 × 約21件/月）              | ~$0.43               |
| EventBridge・SSM                           | ~$0                  |
| **合計**                                   | **~$0.45（約70円）** |

X APIの件数は、通常投稿が本文＋URLリプライの2件、スレッドが約3.5件で、4タイプを順に回す前提の概算。

## トラブルシューティング

| 症状           | 原因                          | 対処                                   |
| -------------- | ----------------------------- | -------------------------------------- |
| 投稿が0件      | RSS/Atom フィード取得失敗     | CloudWatch Logs で HTTP ステータス確認 |
| 重複投稿       | SSM パラメータ破損            | `/xposter/posted-history` を手動クリア |
| Bedrock エラー | IAM 権限不足                  | カスタムポリシーのモデル ARN を確認    |
| X API 403      | レート制限                    | 15分後に再実行                         |
| 投稿タイプが毎回同じ | SSM履歴の保存失敗（上限4KB超過） | ログの`[History] 保存失敗`を確認。`fit_history()`の上限・件数を見直す |
| インフラ系記事0件 | 日本語版フィードの掲載遅れ・キーワード不一致 | ログの`[RSS] インフラ系N件`を確認。`INFRA_KEYWORDS`を見直す |

## 変更履歴

直近1日分のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

### 2026-10-25

#### 投稿履歴の保存失敗による投稿タイプ固定の修正

- SSMパラメータ`/xposter/posted-history`（Standard tier、上限4,096文字）が4,093文字に達し、9月以降は投稿後の履歴保存が毎回`ValidationException`で失敗していた
- 保存失敗は「投稿成功済み」としてログ出力のみで握りつぶされていたため、アラーム・失敗通知は発火しなかった
- 履歴が2026-09-07時点で凍結したため、投稿タイプが毎回`news_intro`に固定され、投稿済みURLも記録されず重複投稿のリスクがあった
- 保存前に`fit_history()`で3,800バイト以内へ切り詰めるよう修正した（使用済みURL→効果測定ログ→キーワードの順に、下限を残して古い要素から削る）
- 使用済みURLを28件→10件、キーワード履歴を40件→12件、効果測定ログ`post_log`を30件→20件に縮小した
- 全タイプ使用済み時に履歴の先頭を返していたため、同じタイプが3回連続し得た巡回の偏りも、最後の使用が最も古いタイプを選ぶ方式に修正した

#### 投稿内容をインフラ運用者向けに変更

- 情報ソースをAWS公式の日本語RSS（What's New・AWSブログ日本語版）の2つに絞り、クラスメソッド・Zenn・Qiita・英語版AWSブログを削除した
- 公式ニュースは上位5件ではなく最大100件を取得し、`INFRA_KEYWORDS`（EC2・VPC・CloudWatch等）をタイトルに含む記事だけを候補にした
- GovCloud・他リージョンへの提供拡大告知と、AWS Transform・AWS HealthOmics等の運用と関係の薄いサービスの記事を候補から除外した
- キーワード判定を英数字の境界つきにし、「WebSocket」中の「EBS」や「OpenSearch Dashboards」中の「RDS」のような部分一致を防いだ
- 投稿タイプを`infra_update`・`ops_benefit`・`ops_caution`・`thread_tips`の4種に刷新し、`news_intro`・`aws_failure`・`news_comparison`・`classmethod_reaction`を廃止した
- 旧`aws_failure`はLLMに「自分がハマった体験談」を書かせており捏造の恐れがあったため、生成・事実検証の両方で体験談の記述を禁止した
- インフラ系記事が0件の場合は、AI系の記事を投稿せず記事に依拠しない`aws_tips`投稿にフォールバックするようにした

#### 事実検証の根拠本文の修正

- AWSのページはHTML先頭2,500文字がナビゲーションで占められ、告知本文が生成・事実検証の根拠に入っていなかった
- 公式ニュースはRSSのdescription（告知本文全文）を、ブログはページの`<article>`内を根拠に使うよう変更し、HTMLエンティティも復元するようにした

#### インプレッション向上の調整

- Xの公開アルゴリズム（`xai-org/x-algorithm`の`home-mixer/params/param.rs`）で予測リプライ率の重み5.0が予測いいね率0.66の約7倍であることを根拠に、締め方の問いかけ比率を25%→40%に上げた
- 問いかけの例をインフラ運用者が自分の環境を答えたくなる具体的なものに変え、体験を前提にした例（「同じ経験ある人いる？」等）を外した
- 書き出しで対象サービスと変更点が分かるようにするルールを追加した

#### 構成図・ポートフォリオの更新

- 構成図のRSSソース表記（5ソース・Classmethod/Zenn/Qiita）をAWS公式の日本語2ソースに更新した（draw.io CLIで再エクスポート）
- 004ポートフォリオの構成図（SVG・PNG）と`projects.ts`の001説明文を更新し、本番デプロイした

#### テスト・レビュー

- pytestを24件→54件に拡充した（巡回の偏り・履歴サイズ・地域除外・部分一致・本文抽出・HTMLエンティティ等）
- Fable 5のコードレビューで指摘された高2件・中3件・低3件を反映した

#### 資料・構成の整合性修正

- CFnテンプレートのDescription（「毎夜20時」「ニュース紹介系」等の旧記述）を現行仕様に直し、ResourcesとOutputsにセクションコメントを追加してスタックを更新した
- `deploy.sh --full`が環境変数`RECIPIENT_EMAIL`未設定時に空文字で上書きし、SNS失敗通知の設定ごと削除する恐れがあったため、未設定なら前回値を引き継ぐよう修正した
- 構成図のエッジラベルを実装に合わせて修正した（Converse API→InvokeModel、投稿済みURL→投稿履歴、RSS/Atom→RSS）
- 使われていない旧構成図スクリプト`scripts/generate_diagram.py`、旧構成図を残していた`images/old/`、Pythonのキャッシュフォルダを削除した
- 公開CHANGELOGに記載されていた通知先の個人メールアドレスを伏せた（003・006・007の公開資料と003の`deploy.sh`の既定値も同様に削除）

#### 対象サービスの追加

- ECSのメトリクス無料化・Lambdaの再帰ループ検出など運用に直結する更新も拾うため、ECS・EKS・Fargate・Lambda・EventBridgeを`INFRA_KEYWORDS`に追加した
- 2026-10-25時点のフィードで、インフラ系の候補記事が24件から31件に増えた

#### Fable再レビューの反映

- 地域告知の除外条件が「クロスリージョン」「マルチリージョン」の一般提供まで除外していたため、これらを除外対象から外した
- 履歴の保存に失敗した場合、投稿後に例外を返してLambdaを失敗扱いにし、SNSのメール通知が届くようにした（リトライ0のため二重投稿にはならない）
- SSMの履歴に`null`が入っていても落ちないよう、履歴の読み出しを統一した
- `deploy.sh`の空配列の展開を、古いbash（macOS標準の3.2）でも動く書き方に変えた（003も同様）
- 公開中の`images/構成図更新手順.md`に含まれていたWindowsのユーザー名をプレースホルダに置き換え、`sync_to_public.sh`の機密スキャンに個人メールアドレスとWindowsユーザー名のパターンを追加した
- コスト表を週2回の運用に合わせて月約$0.45（約70円）に直し、IAM権限・ハッシュタグ正規化の例など資料の細かいずれを修正した
- 構成図の注記でCloudWatch Logsを「全リージョン共通の横断サービス」としていた誤りを直した（CloudWatch Logsはリージョンごとのサービス）

#### Fable再レビュー残件の反映

- 失敗通知のSNS送信権限を、条件付きの`AWS::IAM::Policy`＋`DependsOn`から、ロール内の`!If`付きインラインポリシー`xposter-sns`に移した（003も同様に`x-poster-zer0-0326-sns`）
- 移行前の書き方では、RecipientEmailが空のまま新規作成すると「Unresolved resource dependencies」で失敗する問題があった
- 旧ポリシーと同名にすると、更新時の旧リソース削除で新しい権限まで消えるため別名にし、変更セットで確認してから両スタックを更新した
- スレッド生成でモデル出力が読めない場合、その回を欠投にせず`infra_update`の通常投稿に切り替えるようにした
- 003・004・006・007の仕様書の目次`docs/システム仕様書.md`を、同名フォルダ内の`README.md`に移した（同名のファイルとフォルダを並べないルールへの準拠）
- pytestを56件に拡充した
