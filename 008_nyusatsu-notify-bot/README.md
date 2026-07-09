# 008 入札情報通知Bot（清掃業界向け・横浜市パイロット）

> 横浜市が公開する入札（調達）公告を自動収集し、清掃・ビルメンテナンス業を営む中小企業・個人事業主向けに、清掃関連キーワードに合致する案件だけをメールで自動通知するサブスクリプションサービス。

**現在のステータス: v0.10。パイロット実装・AWS上でテスト運用中（横浜市単体・課金導入前）。実配信接続・SESバウンス/苦情の自動配信停止まで実装済み**  

## 概要

| 項目       | 内容                                                                |
| ---------- | ------------------------------------------------------------------- |
| 対象自治体 | 横浜市（「ヨコハマ・入札のとびら」発注情報）                        |
| 対象業種   | 清掃・ビルメンテナンス業                                            |
| 収集頻度   | 毎日 6:00 JST（EventBridge Scheduler）                              |
| 通知方法   | Amazon SES によるメール送信                                         |
| 収集元URL  | `https://keiyaku.city.yokohama.lg.jp/epco/servlet/p?job=KokokuList` |

## アーキテクチャ

![アーキテクチャ図](images/008_architecture.png)

```text
EventBridge（毎日6:00 JST）
  └─▶ Lambda（zer0-nyusatsu-collector）
        ├─ SSM Parameter Store から通知先メール・SES送信元・キーワードを取得
        ├─ 横浜市入札サイトから公告一覧(KokokuList)を取得し、公告番号(kokoku_no)を抽出
        ├─ DynamoDB(zer0-nyusatsu-processed-kokoku) と照合し未処理の号のみ処理
        ├─ 各号の案件一覧(KokokuAnkenList)を取得し「委託」セクションのみ解析
        ├─ 案件名がキーワード(清掃/美化/害虫防除/ねずみ防除)に合致すれば
        │    運営者+DynamoDB(zer0-nyusatsu-lp-waitlist)のactive購読者へ個別SES送信
        └─ 処理済みの号をDynamoDBに記録（重複通知防止）
              失敗時はSQS(DLQ)へ退避
```

SES送信にはConfiguration Set（`zer0-nyusatsu-config-set`）を付与し、バウンス・苦情をSNS経由で検知。Permanentバウンス・苦情アドレスはLambda（`zer0-nyusatsu-bounce-handler`）が自動で`unsubscribed`にする。

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

| 項目     | 内容                                                                                                                    |
| -------- | ----------------------------------------------------------------------------------------------------------------------- |
| 提供形態 | メールによる定期通知                                                                                                    |
| 料金     | 月額3,000〜5,000円程度のセルフサーブ帯を想定（未確定・現在は無料テスト運用）                                            |
| 決済     | Stripe Payment Links を利用予定（[docs_payment_setup.md](./docs_payment_setup.md)参照）。自前の決済システムは開発しない |
| 収集元   | 横浜市発注情報（パイロット）。将来的にエリア拡大を検討                                                                  |

## AWSリソース（デプロイ済み）

| リソース                | 名称                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------- |
| CloudFormationスタック  | `zer0-nyusatsu-notify-bot`                                                                        |
| Lambda関数              | `zer0-nyusatsu-collector`（Python 3.13）                                                          |
| DynamoDBテーブル        | `zer0-nyusatsu-processed-kokoku`                                                                  |
| SQS(DLQ)                | `zer0-nyusatsu-notify-bot-dlq`                                                                    |
| SSM Parameter           | `/zer0/008-nyusatsu/notify-email`, `/zer0/008-nyusatsu/ses-sender`, `/zer0/008-nyusatsu/keywords`, `/zer0/008-nyusatsu/hmac-secret`, `/zer0/008-nyusatsu/unsubscribe-base-url` |
| EventBridge Rule        | `zer0-nyusatsu-daily-schedule`（`cron(0 21 * * ? *)` = 毎日6:00 JST）                             |
| SNS Topic               | `zer0-nyusatsu-alarm-topic`（DLQ滞留アラームの通知先、NotifyEmail宛）                             |
| CloudWatch Alarm        | `zer0-nyusatsu-dlq-messages-alarm-01`                                                             |
| SES Configuration Set   | `zer0-nyusatsu-config-set`（バウンス・苦情検知用）                                                |
| SNS Topic               | `zer0-nyusatsu-ses-events-topic`（バウンス・苦情通知、NotifyEmail宛+Lambda購読）                  |
| Lambda関数              | `zer0-nyusatsu-bounce-handler`（Python 3.13、バウンス・苦情受信で自動配信停止）                   |
| CloudFormationスタック  | `zer0-nyusatsu-ses-domain`                                                                        |
| SES ドメインID          | `info.zer0-infra.com`（Easy DKIM、検証済み。送信元 `notify@info.zer0-infra.com`）                 |
| CloudFormationスタック  | `zer0-nyusatsu-lp-backend`（事前登録API）                                                         |
| DynamoDBテーブル        | `zer0-nyusatsu-lp-waitlist`                                                                       |
| Lambda関数              | `zer0-nyusatsu-lp-waitlist`（Python 3.13）                                                        |
| API Gateway             | `zer0-nyusatsu-lp-api`（HTTP API、`POST /register` / `GET /confirm` / `GET+POST /unsubscribe`）   |
| CloudFormationスタック  | `zer0-nyusatsu-mail-relay`（問合せメール受信転送）                                                |
| S3バケット              | `zer0-nyusatsu-mail-s3`（受信メール一時保管）                                                     |
| Lambda関数              | `zer0-nyusatsu-mail-forwarder`, `zer0-nyusatsu-activate-ruleset`（Python 3.13）                   |
| SES 受信ルールセット    | `zer0-nyusatsu-rules`（`nyusatsu@zer0-infra.com`宛を受信）                                        |
| CloudFormationスタック  | `zer0-nyusatsu-lp-cert`（us-east-1）, `zer0-nyusatsu-lp-hosting`（LP配信）                        |
| S3バケット / CloudFront | `zer0-nyusatsu-lp-s3` / `nyusatsu.zer0-infra.com`                                                 |

## ランディングページ（LP）・事前登録

集客用LP `https://nyusatsu.zer0-infra.com` を公開（S3 + CloudFront + ACM）。Apple風のスクロール連動アニメーションで、課題提起・仕組み・対象エリア/業種・料金・FAQを掲載し、メールアドレス入力の事前登録フォームを設置。フッターには問合せ用アドレス`nyusatsu@zer0-infra.com`とプライバシーポリシー（`privacy.html`）を記載し、問合せメールはSES受信ルール→S3→Lambda（`zer0-nyusatsu-mail-forwarder`）で個人メールへ自動転送する。

**登録〜配信停止フロー（v0.9、二重オプトイン）**: フォーム送信は`zer0-nyusatsu-lp-api`（HTTP API）経由でLambda（`zer0-nyusatsu-lp-waitlist`）が`zer0-nyusatsu-lp-waitlist`（DynamoDB、`status: pending/active/unsubscribed`）に保存し、登録者本人へ確認メール（広告要素なしのトランザクショナルメール）を送信する。メール内の確認リンク（HMAC-SHA256署名付きトークン、`GET /confirm`）をクリックすると`active`になり運営者へ通知される。通知メール・週次サマリーメールには`List-Unsubscribe`/`List-Unsubscribe-Post`ヘッダー（RFC 8058 One-Click対応）と本文中のワンクリック解除リンク（`GET+POST /unsubscribe`）を付与。フォームには非表示のhoneypotフィールドでbot登録を弾く。

## 動作確認済み事項（2026-07-07）

- ブートストラップ実行（既存81号を通知なしで処理済み登録）が正常完了
- 2回目以降の実行で新規号0件時に即時終了することを確認
- 未処理号を1件人為的に作り、実データで「委託」セクション抽出→キーワードマッチ→SES送信→DynamoDB記録の一連の流れがエラーなく完走することを確認
- SESは本番アクセス取得済み（2026-07-08）。送信上限50,000通/日・14通/秒で任意の宛先へ送信可能
- LP事前登録API: 登録・重複登録判定・不正メール形式の拒否をcurlで確認済み
- 問合せメール転送: S3への直接投入でLambda転送処理（DynamoDB不要、SES送信のみ）が正常完了することを確認済み。MXレコードはお名前.comに追加済みでDNS反映待ち

## 動作確認済み事項（2026-07-09）

ユーザーから「登録者に確認メールは届くのか、配信停止はワンクリックか」と問われ監査した結果判明した重大なギャップ（LP登録と実通知が未接続・確認メールなし・配信停止が手動返信のみ）を修正し、実メールで全フローを検証した（v0.9）。続けて配信停止URLの長さ指摘を受けリンク埋め込み化（v0.9.1）、実配信の接続とバウンス・苦情対応を実装（v0.10）。

- 登録→確認メール受信→確認リンククリック→`active`化→運営者通知、の一連を実メール（Gmail）で確認済み
- honeypotフィールドを埋めた送信が実際にDynamoDBへ登録されないことを確認済み
- 配信停止: `GET /unsubscribe`は確認ページを返すのみで状態変化なし、`POST /unsubscribe`で実際に`unsubscribed`になることを確認済み。不正トークンは400で拒否
- HTML版メールで「配信停止はこちら」「登録を確定する」がクリック可能なリンクとして表示されることをGmailで確認済み
- **実配信接続（B-1）**: テスト購読者を`active`化した状態で`send_notification`を実行し、運営者宛+購読者宛の両方に個別メールが届くことを確認済み
- **バウンス・苦情対応（B-3）**: SESシミュレーターアドレス（`bounce@simulator.amazonses.com`・`complaint@simulator.amazonses.com`）宛に実送信し、Permanentバウンス・苦情それぞれがSNS経由でLambda（`zer0-nyusatsu-bounce-handler`）に届き、該当アドレスが自動で`unsubscribed`になることを確認済み
- 監査の過程で、問合せメール転送Lambda（`zer0-nyusatsu-mail-forwarder`）が実コード未反映（プレースホルダーのまま）で受信メールが消失する状態になっていたことを発見。実コードを反映し、滞留していたメールも手動再処理して復旧

## 今後の進め方

課金開始前にFableで市場調査をやり直した結果（2026-07-08）、法務対応（特商法表記・利用規約・プライバシーポリシー）と流量計測が課金開始の前提条件と判明した。2026-07-09にA群（登録確認・ワンクリック配信停止等）・B-1（実配信接続）・B-3（バウンス/苦情対応）が完了。

1. 課金開始前必須の法務対応（特商法表記・利用規約・プライバシーポリシー、バーチャルオフィス等の検討）
2. 流量計測を1〜2ヶ月継続し、価格・対象エリアを最終判断
3. Stripe決済導入（[docs_payment_setup.md](./docs_payment_setup.md)）
4. LPでの集客開始・横浜市での検証が安定したら対象エリア拡大を検討
5. 購読者管理のマルチテナント化は保留（エリア/業種のフィルタ軸が実際に増える段階になるまで不要というFable判断）

## 変更履歴

直近3件のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

| 日付       | バージョン | 内容                                                                                                                                                           |
| ---------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-09 | v0.9       | 登録↔実通知未接続・確認メール皆無・配信停止非ワンクリックと判明。二重オプトイン・確認メール・ワンクリック配信停止・honeypot・プライバシーポリシー等を実装      |
| 2026-07-09 | v0.9.1     | 配信停止URLが長い指摘を受け、通知・確認メールをHTML化。「配信停止はこちら」「登録を確定する」にリンクを埋め込み、生URLはテキスト版フォールバックのみに           |
| 2026-07-09 | v0.10      | 実配信を接続(B-1)。SESバウンス・苦情の受け皿(B-3、Configuration Set+SNS+自動配信停止Lambda)を追加。シミュレーターで実際の検知→自動配信停止まで確認             |
