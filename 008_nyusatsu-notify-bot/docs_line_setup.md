# LINE通知 導入ガイド（v0.28）

## 方針

メール通知と並列の選択肢として、LINE公式アカウント経由のプッシュ通知を提供する（[[project_008_status]]参照。ユーザーが「メールと並列の選択肢」「LP登録後に友だち追加URLを発行」を選択）。LP登録時に「LINEで受け取る」を選ぶと、LIFF（LINE Front-end Framework）ページで友だち追加とアカウント連携を1画面で完結させる。

## ユーザー自身が行う必要がある作業（Claudeでは代行不可）

LINE公式アカウントの開設・チャネル作成は本人名義のLINEアカウントでの操作が必要なため、以下はユーザー側の作業。

1. [LINE Official Account Manager](https://www.linebiz.com/jp/entry/) で公式アカウントを新規開設（無料。個人事業主・屋号でも作成可能）
2. 開設後、[LINE Developers コンソール](https://developers.line.biz/console/) にログインし、作成したアカウントに紐づく **プロバイダー** を確認（無ければ新規作成）
3. 同じプロバイダー配下に **Messaging API チャネル**（開設した公式アカウントと同じもの）があることを確認
4. Messaging APIチャネルの「Messaging API設定」タブから以下を取得:
   - **チャネルアクセストークン（長期）**: 「発行」ボタンで発行
   - **チャネルシークレット**: 「チャネル基本設定」タブに表示されている値
5. 同じプロバイダー配下に **LINEログインチャネル** を新規作成（Messaging APIチャネルとは別に必要）
6. LINEログインチャネルの「LIFF」タブから **LIFFアプリを新規追加**:
   - **サイズ**: Full（全画面表示、推奨）
   - **エンドポイントURL**: `https://nyusatsu.zer0-infra.com/line-link.html`
   - **Scope**: `profile` にチェック（ユーザーIDの取得に必要。`openid`は不要）
   - **ボットリンク機能**: **On (Aggressive)** を選択（LIFFログインと同時に友だち追加を促す設定。これが「1画面で完結」の要）
   - 対象の**Messaging APIチャネル**（手順3〜4のもの）と同じプロバイダーであれば、ボットリンク機能で自動的に紐付けられる
7. 発行された **LIFF ID**（`1234567890-abcdefgh` のような形式）を控える

## 認証情報の反映（Claude側で実行）

3つの値（チャネルアクセストークン・チャネルシークレット・LIFF ID）を受け取ったら、以下のコマンドでSSMパラメータへ反映する（プレースホルダー`REPLACE_AFTER_LINE_SETUP`から実際の値へ上書き）:

```bash
aws ssm put-parameter --name /zer0/008-nyusatsu/line-channel-access-token --type String --overwrite --value "実際のチャネルアクセストークン" --region ap-northeast-1
aws ssm put-parameter --name /zer0/008-nyusatsu/line-channel-secret --type String --overwrite --value "実際のチャネルシークレット" --region ap-northeast-1
aws ssm put-parameter --name /zer0/008-nyusatsu/line-liff-id --type String --overwrite --value "実際のLIFF ID" --region ap-northeast-1
```

LIFF IDはLPのHTMLに埋め込む値のため、反映後に `cd lp && bash deploy.sh` を再実行して `line-link.html` に注入し直す必要がある。

## Messaging API Webhookの設定（ユーザー側の追加作業）

1. Messaging APIチャネルの「Messaging API設定」タブで **Webhook URL** を設定する
   - URL: `aws cloudformation describe-stacks --stack-name zer0-nyusatsu-lp-backend --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text --region ap-northeast-1` で取得できる値の末尾を `/register` から `/line/webhook` に置き換えたもの
   - 「Webhookの利用」をONにする
   - 「検証」ボタンで疎通確認（チャネルシークレットのSSM反映が先に済んでいる必要がある）
2. 「応答メッセージ」機能はOFFにする（Bot側は友だち追加/ブロック検知のみを行い、対話には応答しないため）
3. 「あいさつメッセージ」は任意（ONのままでも動作に支障なし、内容を編集したい場合はダッシュボードで設定）

## 実装済みの仕組み（Claude側で実装完了）

- **登録**: LP登録フォームで「LINEで受け取る」を選ぶと、メール確認をスキップし、代わりに `token`・`email` を含んだLIFF URL（`https://liff.line.me/{LIFF_ID}?token=...&email=...`）を返す
- **連携**: `line-link.html`（LIFFページ）が `liff.init()` → 未ログインなら `liff.login()` → `liff.getProfile()` でLINEユーザーIDを取得し、`POST /line/link` へ送信。バックエンドがトークンを検証しDynamoDBの該当レコードを `status=active, channel=line, line_user_id=...` に更新する（メールの二重オプトインに相当する処理）
- **通知**: collector Lambdaが日次の該当案件通知・週次稼働レポートの両方で、`channel=line` の購読者にはLINE Messaging APIの `push` エンドポイントでプレーンテキストメッセージを送る（メールのHTMLカードとは別に簡潔な箇条書き形式）
- **解約検知**: LINE公式アカウントをブロック（unfollow）されると、Webhookでそれを検知し自動的に `status=unsubscribed, reason=line_block` にする

## 費用

無料プランで月200通まで無料。008の想定利用者数（数十社規模、1利用者あたり週数通）なら十分無料枠内に収まる見込み。超過した場合は従量課金プラン（月5,000円で15,000通等）への切替が必要。

## 未検証・要実機確認の項目

以下はLIFF ID等の実認証情報がないと検証できないため、ユーザーの開設作業完了後に一緒に確認する:

- LIFFページの実際の見た目・友だち追加フローの体験（PC/スマホ双方）
- CSP（`connect-src`に`https://api.line.me` `https://liff.line.me`、`script-src`に`https://static.line-scdn.net`を許可済みだが、LIFF SDKが実際に必要とする通信先の過不足）
- LINE Messaging APIのpush送信の実疎通（テスト送信で確認）
- Webhookの署名検証が実際のLINEからのリクエストで通ること
