# 008 入札情報通知Bot（清掃業界向け・横浜市パイロット）

> 横浜市が公開する入札（調達）公告を自動収集し、清掃・ビルメンテナンス業を営む中小企業・個人事業主向けに、清掃関連キーワードに合致する案件だけをメールで自動通知するサブスクリプションサービス。

**現在のステータス: パイロット実装・AWS上でテスト運用中（横浜市単体・課金導入前）**

## 概要

| 項目 | 内容 |
| ---- | ---- |
| 対象自治体 | 横浜市（「ヨコハマ・入札のとびら」発注情報） |
| 対象業種 | 清掃・ビルメンテナンス業 |
| 収集頻度 | 毎日 6:00 JST（EventBridge Scheduler） |
| 通知方法 | Amazon SES によるメール送信 |
| 収集元URL | `https://keiyaku.city.yokohama.lg.jp/epco/servlet/p?job=KokokuList` |

## アーキテクチャ

![アーキテクチャ図](images/008_architecture.png)

```text
EventBridge（毎日6:00 JST）
  └─▶ Lambda（zer0-nyusatsu-collector）
        ├─ SSM Parameter Store から通知先メール・SES送信元・キーワードを取得
        ├─ 横浜市入札サイトから公告一覧(KokokuList)を取得し、公告番号(kokoku_no)を抽出
        ├─ DynamoDB(zer0-nyusatsu-processed-kokoku) と照合し未処理の号のみ処理
        ├─ 各号の案件一覧(KokokuAnkenList)を取得し「委託」セクションのみ解析
        ├─ 案件名がキーワード(清掃/美化/害虫防除/ねずみ防除)に合致すればSESでメール通知
        └─ 処理済みの号をDynamoDBに記録（重複通知防止）
              失敗時はSQS(DLQ)へ退避
```

## 背景・課題

- 官公庁の入札案件は発注機関ごとにサイトがバラバラで、中小・個人事業主が自力で探すのは負担が大きい
- 告知から締切まで約10日程度と短く、見逃すと機会損失になる
- 既存の最大手サービス（NJSS）は初期費用30万円＋年間約77万円と高額で、中小企業・個人事業主には手が届かない
- 一方、月8,000〜8,800円帯には既に廉価版競合が複数存在するため、**月3,000〜5,000円のセルフサーブ帯**を狙う

## 提供する価値

清掃・ビルメンテナンス業の中小企業・個人事業主に対し、清掃関連キーワードに合う入札案件だけを自動で毎日メール通知する。役所サイトを自分で巡回する手間と見逃しリスクをなくし、NJSSを払えない層でも案件を取りこぼさず受注機会を増やせるようにする。

## なぜ横浜市を最初のターゲットにしたか

Fableでの調査比較の結果、以下の理由で横浜市を選定した。

- 案件一覧・詳細ともに**GET URLのみでセッション不要**に取得でき、技術的に最も実装しやすい（愛知県・神奈川県は規約上の制約やCSRFトークンが必要）
- 横浜市の公式著作権ポリシーで「数値データ・簡単な表は著作権保護対象外で自由利用可」と明記されており、案件名・番号等の事実データ通知は法的に問題が少ない
- 自動収集に関する明示的な禁止規定なし（robots.txt制限もなし）
- 一方、愛知県（あいち電子調達共同システム）は約60団体を1本のシステムでカバーできる強みがあるが、利用規約に「目的外利用禁止」条項がありグレーゾーン。商用利用の可否は運営協議会へ事前照会が必要なため、パイロットでは見送った

## 法的な留意事項

- 収集対象は横浜市の**ログイン不要の公開ページ**のみ（規約でスクレイピング禁止と明記されたサイトは対象外方針）
- 通知するのは案件名・契約番号・入札方式・担当部局等の**事実データ**のみで、原文・画像の転載は行わない
- アクセス間隔は3秒以上空け、日次1回のみ実行し対象サーバーに負荷をかけない設計

## ビジネスモデル

| 項目 | 内容 |
| ---- | ---- |
| 提供形態 | メールによる定期通知 |
| 料金 | 月額3,000〜5,000円程度のセルフサーブ帯を想定（未確定・現在は無料テスト運用） |
| 決済 | Stripe Payment Links を利用予定（[docs_payment_setup.md](./docs_payment_setup.md)参照）。自前の決済システムは開発しない |
| 収集元 | 横浜市発注情報（パイロット）。将来的にエリア拡大を検討 |

## AWSリソース（デプロイ済み）

| リソース | 名称 |
| -------- | ---- |
| CloudFormationスタック | `zer0-nyusatsu-notify-bot` |
| Lambda関数 | `zer0-nyusatsu-collector`（Python 3.13） |
| DynamoDBテーブル | `zer0-nyusatsu-processed-kokoku` |
| SQS(DLQ) | `zer0-nyusatsu-notify-bot-dlq` |
| SSM Parameter | `/zer0/008-nyusatsu/notify-email`, `/zer0/008-nyusatsu/ses-sender`, `/zer0/008-nyusatsu/keywords` |
| EventBridge Rule | `zer0-nyusatsu-daily-schedule`（`cron(0 21 * * ? *)` = 毎日6:00 JST） |
| CloudFormationスタック | `zer0-nyusatsu-ses-domain` |
| SES ドメインID | `info.zer0-infra.com`（Easy DKIM、検証済み。送信元 `notify@info.zer0-infra.com`） |
| CloudFormationスタック | `zer0-nyusatsu-lp-backend`（事前登録API） |
| DynamoDBテーブル | `zer0-nyusatsu-lp-waitlist` |
| Lambda関数 | `zer0-nyusatsu-lp-waitlist`（Python 3.13） |
| API Gateway | `zer0-nyusatsu-lp-api`（HTTP API、`POST /register`） |
| CloudFormationスタック | `zer0-nyusatsu-mail-relay`（問合せメール受信転送） |
| S3バケット | `zer0-nyusatsu-mail-s3`（受信メール一時保管） |
| Lambda関数 | `zer0-nyusatsu-mail-forwarder`, `zer0-nyusatsu-activate-ruleset`（Python 3.13） |
| SES 受信ルールセット | `zer0-nyusatsu-rules`（`nyusatsu@zer0-infra.com`宛を受信） |
| CloudFormationスタック | `zer0-nyusatsu-lp-cert`（us-east-1）, `zer0-nyusatsu-lp-hosting`（LP配信） |
| S3バケット / CloudFront | `zer0-nyusatsu-lp-s3` / `nyusatsu.zer0-infra.com` |

## ランディングページ（LP）・事前登録

集客用LP `https://nyusatsu.zer0-infra.com` を公開（S3 + CloudFront + ACM）。Apple風のスクロール連動アニメーションで、課題提起・仕組み・対象エリア/業種・料金・FAQを掲載し、メールアドレス入力の事前登録フォームを設置。フォーム送信は`zer0-nyusatsu-lp-api`（HTTP API）経由でLambdaが`zer0-nyusatsu-lp-waitlist`（DynamoDB）に保存し、SESで運営者に通知する。フッターには問合せ用アドレス`nyusatsu@zer0-infra.com`を記載し、SES受信ルール→S3→Lambda（`zer0-nyusatsu-mail-forwarder`）で個人メールへ自動転送する。

## 動作確認済み事項（2026-07-07）

- ブートストラップ実行（既存81号を通知なしで処理済み登録）が正常完了
- 2回目以降の実行で新規号0件時に即時終了することを確認
- 未処理号を1件人為的に作り、実データで「委託」セクション抽出→キーワードマッチ→SES送信→DynamoDB記録の一連の流れがエラーなく完走することを確認
- SESはサンドボックスモード（送信元・宛先とも検証済みメールのみ送信可）。本番顧客への送信には本番アクセス申請が必要
- LP事前登録API: 登録・重複登録判定・不正メール形式の拒否をcurlで確認済み
- 問合せメール転送: S3への直接投入でLambda転送処理（DynamoDB不要、SES送信のみ）が正常完了することを確認済み。MXレコードはお名前.comに追加済みでDNS反映待ち

## 今後の進め方

1. MXレコードのDNS反映確認後、実メールでの問合せ転送のエンドツーエンドテスト
2. 実際に清掃関連案件がヒットした際の通知メール文面の実地確認
3. SES本番アクセス申請（サンドボックス解除）
4. Stripe決済導入（[docs_payment_setup.md](./docs_payment_setup.md)）
5. LPでの集客開始・横浜市での検証が安定したら対象エリア拡大を検討

## 変更履歴

直近3件のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

| 日付 | バージョン | 内容 |
| ---- | ---------- | ---- |
| 2026-07-07 | v0.3 | SES送信ドメイン`info.zer0-infra.com`をEasy DKIMで検証・CFn管理化（`zer0-nyusatsu-ses-domain`スタック） |
| 2026-07-07 | v0.4 | LP事前登録(DynamoDB+API Gateway+Lambda)・問合せメール転送(SES受信+S3+Lambda)・LP静的サイト(`nyusatsu.zer0-infra.com`、S3+CloudFront)を追加。SES送信元を`info.zer0-infra.com`へ切替。MXレコード反映・実メール転送まで確認済み |
| 2026-07-07 | v0.5 | Fableレビュー反映。構成図のレイアウト規約違反を修正、メール転送LambdaにDLQ追加、CSPのAPI IDハードコード解消、その他中低優先度の指摘を修正 |
