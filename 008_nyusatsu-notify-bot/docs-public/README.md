# 008 入札情報ウォッチ（旧称: 入札情報通知Bot、清掃業界向け・横浜市パイロット）

> 横浜市が公開する入札（調達）公告を自動収集し、清掃・ビルメンテナンス業を営む中小企業・個人事業主向けに、清掃関連キーワードに合致する案件だけをメールで自動通知するサブスクリプションサービス。プロジェクト内部の識別子（AWSリソース名・ディレクトリ名等）は`nyusatsu`のまま変更していない。

**現在のステータス: v0.24。パイロット実装・AWS上でテスト運用中（横浜市単体）。LP・法務ページの配色をメールと同じ青系に統一しUI/UX細部を調整、独自ブランドのfavicon・OGP画像も新規作成。次はStripe Payment Links発行**  

## 概要

| 項目       | 内容                                                                |
| ---------- | ------------------------------------------------------------------- |
| 対象自治体 | 横浜市（「ヨコハマ・入札のとびら」発注情報）                        |
| 対象業種   | 清掃・ビルメンテナンス業                                            |
| 収集頻度   | 毎日 6:00 JST（EventBridge Scheduler）                              |
| 通知方法   | Amazon SES によるメール送信                                         |
| 収集元URL  | `https://keiyaku.city.yokohama.lg.jp/epco/servlet/p?job=KokokuList` |

## アーキテクチャ

![アーキテクチャ図](../images/008_architecture.png)

```text
EventBridge（毎日6:00 JST）
  └─▶ Lambda（zer0-nyusatsu-collector）
        ├─ SSM Parameter Store から通知先メール・SES送信元・キーワードを取得
        ├─ 横浜市入札サイトから公告一覧(KokokuList)を取得し、公告番号(kokoku_no)を抽出
        ├─ DynamoDB(zer0-nyusatsu-processed-kokoku) と照合し未処理の号のみ処理
        ├─ 各号の案件一覧(KokokuAnkenList)を取得し「委託」セクションのみ解析
        ├─ 案件名または工種等区分がキーワード(清掃・美化・害虫防除ほか計10語)に合致すれば詳細ページから
        │    種目・参加資格・履行場所・履行期間・開札予定日時を取得(追加リクエストなし)
        ├─ マッチ案件をDynamoDB(zer0-nyusatsu-match-history)に記録(60日TTL)
        ├─ 運営者+DynamoDB(zer0-nyusatsu-lp-waitlist)のactive購読者へ個別SES送信
        └─ 処理済みの号をDynamoDBに記録（重複通知防止）
              失敗時はSQS(DLQ)へ退避
```

SES送信にはConfiguration Set（`zer0-nyusatsu-config-set`）を付与し、バウンス・苦情をSNS経由で検知。Permanentバウンス・苦情アドレスはLambda（`zer0-nyusatsu-bounce-handler`）が自動で`unsubscribed`にする。登録確認時（`GET /confirm`）には、`zer0-nyusatsu-match-history`から直近1ヶ月のマッチ実績をバックフィルしたウェルカムメールを送信する。

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
| 料金     | 月額3,000円（予定）。セルフサーブ帯での検討を経て確定（未確定要素あり・現在は無料テスト運用）                            |
| 決済     | Stripe Payment Links を利用予定（[docs_payment_setup.md](../docs_payment_setup.md)参照）。自前の決済システムは開発しない |
| 収集元   | 横浜市発注情報（パイロット）。将来的にエリア拡大を検討                                                                  |

## AWSリソース（デプロイ済み）

| リソース                | 名称                                                                                                                                                                                                                                                              |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CloudFormationスタック  | `zer0-nyusatsu-notify-bot`                                                                                                                                                                                                                                        |
| Lambda関数              | `zer0-nyusatsu-collector`（Python 3.13）                                                                                                                                                                                                                          |
| DynamoDBテーブル        | `zer0-nyusatsu-processed-kokoku`                                                                                                                                                                                                                                  |
| DynamoDBテーブル        | `zer0-nyusatsu-match-history`（マッチ案件履歴、60日TTL、バックフィルウェルカムメール用）                                                                                                                                                                          |
| SQS(DLQ)                | `zer0-nyusatsu-notify-bot-dlq`                                                                                                                                                                                                                                    |
| SSM Parameter           | `/zer0/008-nyusatsu/notify-email`, `/zer0/008-nyusatsu/ses-sender`, `/zer0/008-nyusatsu/keywords`, `/zer0/008-nyusatsu/hmac-secret`, `/zer0/008-nyusatsu/unsubscribe-base-url`, `/zer0/008-nyusatsu/payment-required`, `/zer0/008-nyusatsu/stripe-webhook-secret` |
| EventBridge Rule        | `zer0-nyusatsu-daily-schedule`（`cron(0 21 * * ? *)` = 毎日6:00 JST）                                                                                                                                                                                             |
| SNS Topic               | `zer0-nyusatsu-alarm-topic`（DLQ滞留アラームの通知先、NotifyEmail宛）                                                                                                                                                                                             |
| CloudWatch Alarm        | `zer0-nyusatsu-dlq-messages-alarm-01`                                                                                                                                                                                                                             |
| SES Configuration Set   | `zer0-nyusatsu-config-set`（バウンス・苦情検知用）                                                                                                                                                                                                                |
| SNS Topic               | `zer0-nyusatsu-ses-events-topic`（バウンス・苦情通知、NotifyEmail宛+Lambda購読）                                                                                                                                                                                  |
| Lambda関数              | `zer0-nyusatsu-bounce-handler`（Python 3.13、バウンス・苦情受信で自動配信停止）                                                                                                                                                                                   |
| CloudFormationスタック  | `zer0-nyusatsu-ses-domain`                                                                                                                                                                                                                                        |
| SES ドメインID          | `info.zer0-infra.com`（Easy DKIM、検証済み。送信元 `notify@info.zer0-infra.com`）                                                                                                                                                                                 |
| CloudFormationスタック  | `zer0-nyusatsu-lp-backend`（事前登録API）                                                                                                                                                                                                                         |
| DynamoDBテーブル        | `zer0-nyusatsu-lp-waitlist`                                                                                                                                                                                                                                       |
| Lambda関数              | `zer0-nyusatsu-lp-waitlist`（Python 3.13）                                                                                                                                                                                                                        |
| API Gateway             | `zer0-nyusatsu-lp-api`（HTTP API、`POST /register` / `GET /confirm` / `GET+POST /unsubscribe` / `POST /stripe/webhook`）                                                                                                                                          |
| Lambda関数              | `zer0-nyusatsu-stripe-webhook`（Python 3.13、Stripe決済イベントで購読者を突合・更新）                                                                                                                                                                             |
| CloudFormationスタック  | `zer0-nyusatsu-mail-relay`（問合せメール受信転送）                                                                                                                                                                                                                |
| S3バケット              | `zer0-nyusatsu-mail-s3`（受信メール一時保管）                                                                                                                                                                                                                     |
| Lambda関数              | `zer0-nyusatsu-mail-forwarder`, `zer0-nyusatsu-activate-ruleset`（Python 3.13）                                                                                                                                                                                   |
| SES 受信ルールセット    | `zer0-nyusatsu-rules`（`nyusatsu@zer0-infra.com`宛を受信）                                                                                                                                                                                                        |
| CloudFormationスタック  | `zer0-nyusatsu-lp-cert`（us-east-1）, `zer0-nyusatsu-lp-hosting`（LP配信）                                                                                                                                                                                        |
| S3バケット / CloudFront | `zer0-nyusatsu-lp-s3` / `nyusatsu.zer0-infra.com`                                                                                                                                                                                                                 |

## ランディングページ（LP）・事前登録

集客用LP `https://nyusatsu.zer0-infra.com` を公開（S3 + CloudFront + ACM）。Apple風のスクロール連動アニメーションで、課題提起・仕組み・対象エリア/業種・料金・FAQを掲載し、メールアドレス入力の事前登録フォームを設置。フッターには問合せ用アドレス`nyusatsu@zer0-infra.com`とプライバシーポリシー（`privacy.html`）・利用規約（`terms.html`）・特定商取引法に基づく表記（`tokushoho.html`）を記載し、問合せメールはSES受信ルール→S3→Lambda（`zer0-nyusatsu-mail-forwarder`）で個人メールへ自動転送する。LP・法務ページの配色は通知メール・確認/配信停止ページと同じ白背景+青系アクセント（`#2b6cb0`）で統一している（v0.21）。独自ブランドのfavicon（虫眼鏡アイコン）・OGP画像（SNS等でURL共有時のプレビュー画像）も全ページに設定済み（v0.24）。

**登録〜配信停止フロー（v0.9、二重オプトイン）**: フォーム送信は`zer0-nyusatsu-lp-api`（HTTP API）経由でLambda（`zer0-nyusatsu-lp-waitlist`）が`zer0-nyusatsu-lp-waitlist`（DynamoDB、`status: pending/active/unsubscribed`）に保存し、登録者本人へ確認メール（広告要素なしのトランザクショナルメール）を送信する。メール内の確認リンク（HMAC-SHA256署名付きトークン、`GET /confirm`）をクリックすると`active`になり運営者へ通知される。通知メール・週次サマリーメールには`List-Unsubscribe`/`List-Unsubscribe-Post`ヘッダー（RFC 8058 One-Click対応）と本文中のワンクリック解除リンク（`GET+POST /unsubscribe`）を付与。フォームには非表示のhoneypotフィールドでbot登録を弾く。確認完了時には、`zer0-nyusatsu-match-history`から直近1ヶ月のマッチ実績を参照したバックフィルウェルカムメールを送る（v0.11。実績がない場合も稼働状況を伝える文面）。

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

## 動作確認済み事項（2026-07-09、v0.11）

ユーザーから「顧客へのサービス提供は完璧か、お金を払っても使いたいレベルか」と問われ、Fableに率直な品質レビューを依頼。実測データ（横浜市の入札公告は原則毎週火曜発行、直近6週で計19件・うち3週はゼロ件）を踏まえ「今すぐ実装すべき」4項目を実装・実データで検証した。

- **参加資格情報の追加**: 実際の詳細ページ（`kokoku_no=18104`、貯水槽清掃案件）で種目・所在地区分/順位・企業規模・履行場所・履行期間・開札予定日時が正しく抽出できることを確認済み（既存の締切取得と同じ1回のPOSTで完結、追加リクエストなし）
- **バックフィルウェルカムメール**: テスト登録・確認後、直近1ヶ月の実マッチ案件7件（貯水槽清掃・点検業務委託×7）が種目・参加資格・履行場所・履行期間付きで実際に届くことをGmailで確認済み
- **週次サマリーの購読者配信**: 委託案件チェック総数（例:152件）を含む文面で、オーナー宛・購読者宛の両方に届くことを確認済み
- **副次的に発見・修正したバグ**: 問合せメール転送（`zer0-nyusatsu-mail-forwarder`）の転送件名が、元メールのRFC 2047エンコード済みSubjectヘッダーをデコードせずに連結していたため`=?utf-8?B?...?=`という文字列がそのまま表示される不具合を発見。モダンな`email.policy.default`でのパース+`EmailMessage`での再構築に修正し、件名が正しく表示されること・添付`.eml`が`message/rfc822`として認識されることを確認済み

## 今後の進め方

課金開始前にFableで市場調査をやり直した結果（2026-07-08）、法務対応（特商法表記・利用規約・プライバシーポリシー）と流量計測が課金開始の前提条件と判明した。2026-07-09にA群（登録確認・ワンクリック配信停止等）・B-1（実配信接続）・B-3（バウンス/苦情対応）・プロダクト品質レビュー対応（v0.11、参加資格情報・バックフィルウェルカムメール等）・キーワード拡充（v0.12）が完了。Fableの採点は実装前6/10→実装後8〜9/10相当（法務・決済除く）。

1. 課金開始前必須の法務対応（特商法表記・利用規約・プライバシーポリシー、バーチャルオフィス等の検討）— コーディングでは解決できない、ユーザー自身の判断・行動が必要
2. Stripe決済連携（[docs_payment_setup.md](../docs_payment_setup.md)）— アカウント開設はKYC必須のためユーザー自身の作業
3. 流量計測を1〜2ヶ月継続し、価格・対象エリアを最終判断（v0.12でキーワードを10語に拡充したため、拡充後の実マッチ件数も含めて計測）
4. 複数自治体への拡大: 横浜市は公告が週1回のため通知頻度に構造的な上限がある。近隣市を追加すればムラを緩和できるが工数大、流量計測の結果次第
5. LPでの集客開始・横浜市での検証が安定したら対象エリア拡大を検討
6. 購読者管理のマルチテナント化は保留（エリア/業種のフィルタ軸が実際に増える段階になるまで不要というFable判断）

## 変更履歴

直近3件のみ表示。全履歴は [CHANGELOG.md](./CHANGELOG.md) を参照。

| 日付       | 内容                                                                                                          |
| ---------- | -------------------------------------------------------------------------------------------------------------- |
| 2026-07-14 | LINE残テスト6項目を実機確認。Webhook利用OFFの設定漏れでブロック検知が届かなかった問題と、締切不明案件のLINE通知文言が重複する表示バグを発見・修正 |
| 2026-07-14 | Fable追加レビューで発覚したLINEチャネル乗っ取り脆弱性を修正。第三者がメールアドレスを知るだけで既存購読者の通知先を無断でLINEへ切替可能だった問題を解消 |
| 2026-07-14 | Fable追加レビューの中優先度4件を修正。法務ページのLINE/IP/Stripe未反映・Stripe支払い回復未処理・SSMコメント齟齬・送信失敗宛先への重複通知を解消 |
