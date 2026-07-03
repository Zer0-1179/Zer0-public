# 006 CryptoBot — Claude 作業ルール

## デプロイ前の必須確認

`SENDER_EMAIL` と `RECIPIENT_EMAIL` の環境変数が必須。未設定だとデプロイスクリプトが即終了する。

```bash
export SENDER_EMAIL='<SESで認証済みのメールアドレス>'
export RECIPIENT_EMAIL='<通知先メールアドレス>'
cd /root/Zer0/006_Zer0_CryptoBot && bash scripts/deploy.sh
```

## 初回セットアップ（新環境のみ）

デプロイ前に必ずSSMパラメータ（bitbank APIキー等）を初期化すること。

```bash
bash scripts/setup_ssm.sh
```

## 本番稼働中Bot — 操作時の注意

- **24時間自動売買が稼働中**。Lambda・EventBridgeを停止・削除する前にポジションを確認すること
- SSM Parameter Store にポジション State（保有コイン・エントリー価格・SL水準）が保存されている。SSMパラメータを誤って削除するとBotがポジション管理を失う
- テスト実行: `ENABLE_FORCE_TEST=1 bash scripts/deploy.sh`（テストフラグが有効になり即実行される）

## 緊急停止・一時停止（v4.0〜）

EventBridgeスケジュールを無効化する前に、まずSSMパラメータ`/Zer0/CryptoBot/mode`での切替を検討すること。既存ポジションのSL管理を止めずに新規建てだけ止められる。

```bash
# 新規建てのみ停止（既存ポジションのTP1/SL/トレーリング管理は継続）
aws ssm put-parameter --name /Zer0/CryptoBot/mode --value pause_entry --type String --overwrite --region ap-northeast-1

# 全処理停止（既存ポジション管理も止まる。ポジションがある状態での長時間停止は非推奨）
aws ssm put-parameter --name /Zer0/CryptoBot/mode --value halt --type String --overwrite --region ap-northeast-1

# 復帰
aws ssm put-parameter --name /Zer0/CryptoBot/mode --value normal --type String --overwrite --region ap-northeast-1
```

パラメータ未作成・不正値・読込失敗は全て`normal`扱い（fail-safe）。

## スタック名

- メインスタック: `zer0-cryptobot`（ap-northeast-1）
