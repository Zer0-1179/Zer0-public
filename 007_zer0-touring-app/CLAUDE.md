# 007 Zer0 Touring App — Claude 作業ルール

## CFn更新時の必須パラメータ

`zer0-touring` スタックを更新する際は **必ず** `CertificateArn` を指定すること。省略するとCloudFrontのカスタムドメイン・SSL証明書設定が消えてサイトが落ちる（デフォルト値が空文字のため）。

```bash
# 証明書ARNはこのコマンドで取得してから渡すこと
CERT_ARN=$(aws cloudformation describe-stacks --stack-name zer0-touring-cert \
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text)

aws cloudformation update-stack \
  --stack-name zer0-touring \
  --template-body file://infra/cloudformation-touring.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=CertificateArn,ParameterValue="$CERT_ARN" \
  --region ap-northeast-1
```
