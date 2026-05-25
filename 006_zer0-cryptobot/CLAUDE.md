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

## スタック名

- メインスタック: `zer0-cryptobot`（ap-northeast-1）
