# 004 Portfolio — Claude 作業ルール

## CFn更新時の必須パラメータ

`Zer0-portfolio` スタックを直接 `update-stack` で更新する際は **必ず** `CertificateArn` を指定すること。省略するとCloudFrontのカスタムドメイン・SSL証明書設定が消えてサイトが落ちる（デフォルト値が空文字のため）。

```bash
# 必ず && で繋いで1コマンドで実行すること（変数スコープ問題防止）
CERT_ARN=$(aws cloudformation describe-stacks --stack-name Zer0-portfolio-cert \
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text) && \
aws cloudformation update-stack \
  --stack-name Zer0-portfolio \
  --template-body file:///root/Zer0/004_portfolio/infra/cfn-portfolio.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=CertificateArn,ParameterValue="$CERT_ARN" \
  --region ap-northeast-1
```

> **注意**: `$CERT_ARN` の取得と `update-stack` を別々のコマンド実行にすると変数が引き継がれず CertificateArn が空になる。必ず `&&` で繋いで1回の実行にすること。また `--template-body` には絶対パスを使うこと。

**推奨**: インフラ変更は `cd infra && bash deploy-infra.sh` を使う（証明書ARNを自動取得して渡してくれる）。

## デプロイコマンド

```bash
# コード・フロントのみ更新（通常はこれ）
cd /root/Zer0/004_portfolio && bash scripts/deploy.sh

# インフラ変更を含む場合
cd /root/Zer0/004_portfolio/infra && bash deploy-infra.sh
```

## カスタムドメイン

- URL: https://www.zer0-infra.com
- CloudFront Distribution: `Zer0-portfolio` スタックで管理
- ACM証明書スタック: `Zer0-portfolio-cert`（us-east-1）

## 管理者モード（非公開ページ）

`https://www.zer0-infra.com/ja/?admin=<トークン>` に一度アクセスするとCookie（365日）が保存され、
ナビに「CryptoBot実績」（006の非公開トレード実績ページ）が表示される。`?admin=off` で解除。

```bash
# トークン取得
aws ssm get-parameter --name /Zer0/Portfolio/cryptobot-stats-auth \
  --with-decryption --region ap-northeast-1 --query Parameter.Value --output text
```

認証ロジックは `src/src/middleware.ts` に集約（`Astro.locals.isAdmin`）。
