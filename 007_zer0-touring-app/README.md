# 007 Zer0 Touring App

バイク乗りが「今すぐ走りたい」とき、現在地と天気をもとにAIが日帰りツーリングコースを3つ提案するPWAアプリ。

## アーキテクチャ

![アーキテクチャ図](../images/007_architecture.png)

| レイヤー | 技術 |
|---|---|
| フロントエンド | Astro (static) + PWA (Web Manifest + Service Worker) |
| 現在地取得 | ブラウザ Geolocation API |
| 天気取得 | Open-Meteo API（無料・APIキー不要） |
| AIコース提案 | AWS Bedrock Claude Haiku |
| API | Lambda + API Gateway (HTTP API) |
| ホスティング | CloudFront + S3 |
| ドメイン | touring.zer0-infra.com（設定手順は下記） |

月額コスト: ~$0.40/月（100回利用想定）

## ディレクトリ構成

```
007_Zer0_TouringApp/
├── frontend/           # Astro PWA ソース
├── backend/            # Lambda 関数
├── infra/              # CloudFormation テンプレート + デプロイスクリプト
├── generate_diagram.py # アーキテクチャ図生成
└── システム仕様書.md
```

## デプロイ手順

### 初回（カスタムドメインなし）

```bash
bash infra/deploy-infra.sh
```

### カスタムドメイン（touring.zer0-infra.com）設定

```bash
# 1. us-east-1 で ACM 証明書を発行
bash infra/deploy-infra.sh --cert
# → DNS 検証 CNAME を DNS レジストラに追加
# → 証明書が ISSUED になるまで待機

# 2. 証明書 ARN を確認
aws cloudformation describe-stacks --stack-name zer0-touring-cert \
  --region us-east-1 --query "Stacks[0].Outputs"

# 3. メインスタックに証明書 ARN を渡して再デプロイ
aws cloudformation deploy \
  --stack-name zer0-touring \
  --template-file infra/cloudformation-touring.yaml \
  --region ap-northeast-1 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "ParameterKey=CertificateArn,ParameterValue=<ARN>"

# 4. DNS レジストラで CNAME を追加
# touring.zer0-infra.com → <CloudFrontDomain>.cloudfront.net
```

### Lambda コードのみ更新

```bash
bash backend/deploy.sh
```

### フロントエンドのみ更新

```bash
cd frontend && npm run build
aws s3 sync dist/ s3://zer0-touring-s3 --delete
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

## ローカル開発

```bash
cd frontend
npm install
PUBLIC_API_URL=https://<api-gateway-id>.execute-api.ap-northeast-1.amazonaws.com npm run dev
```

`PUBLIC_API_URL` を設定しない場合、`/api/suggest` を同一オリジンで呼ぶ（本番のみ動作）。
