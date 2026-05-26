# 007 Zer0 Touring App — Claude 作業ルール

## CFn更新時の必須パラメータ

`zer0-touring` スタックを更新する際は **必ず** `CertificateArn` を指定すること。省略するとCloudFrontのカスタムドメイン・SSL証明書設定が消えてサイトが落ちる（デフォルト値が空文字のため）。

```bash
# 必ず && で繋いで1コマンドで実行すること（変数スコープ問題防止）
CERT_ARN=$(aws cloudformation describe-stacks --stack-name zer0-touring-cert \
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text) && \
aws cloudformation update-stack \
  --stack-name zer0-touring \
  --template-body file:///root/Zer0/007_Zer0_TouringApp/infra/cfn-touring.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=CertificateArn,ParameterValue="$CERT_ARN" \
  --region ap-northeast-1
```

> **注意**: `$CERT_ARN` の取得と `update-stack` を別々のコマンド実行にすると変数が引き継がれず CertificateArn が空になる。必ず `&&` で繋いで1回の実行にすること。また `--template-body` には絶対パスを使うこと。
