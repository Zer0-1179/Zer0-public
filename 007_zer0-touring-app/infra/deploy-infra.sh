#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

STACK="zer0-touring"
CERT_STACK="zer0-touring-cert"
REGION="ap-northeast-1"

# ────────────────────────────────────────────
# Step 0: オプション解析
# ────────────────────────────────────────────
DEPLOY_CERT=false
DEPLOY_FRONTEND=true
for arg in "$@"; do
  case $arg in
    --cert)       DEPLOY_CERT=true ;;
    --no-frontend) DEPLOY_FRONTEND=false ;;
  esac
done

# ────────────────────────────────────────────
# Step 1: ACM 証明書（us-east-1 / 初回のみ）
# ────────────────────────────────────────────
if $DEPLOY_CERT; then
  echo "=== [1/4] ACM 証明書デプロイ (us-east-1) ==="
  aws cloudformation deploy \
    --stack-name "$CERT_STACK" \
    --template-file cfn-certificate.yaml \
    --region us-east-1 \
    --capabilities CAPABILITY_IAM

  CERT_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$CERT_STACK" \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
    --output text)

  echo ""
  echo "⚠️  DNS 検証 CNAME を DNS レジストラに追加してください"
  echo "    ACM コンソール → 証明書 → DNS 検証レコードを確認"
  echo "    証明書 ARN: $CERT_ARN"
  echo ""
  echo "検証完了後、再度このスクリプトを引数なしで実行してください。"
  echo "Cert ARN をメモしておいてください: $CERT_ARN"
  exit 0
fi

# ────────────────────────────────────────────
# Step 2: メインスタックデプロイ（ap-northeast-1）
# ────────────────────────────────────────────
# 証明書 ARN の取得（スタックが存在する場合のみ）
CERT_ARN=""
if aws cloudformation describe-stacks --stack-name "$CERT_STACK" --region us-east-1 &>/dev/null; then
  CERT_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$CERT_STACK" \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
    --output text 2>/dev/null || echo "")
fi

echo "=== [2/4] メインスタックデプロイ ($REGION) ==="
PARAMS="ParameterKey=CertificateArn,ParameterValue=${CERT_ARN}"
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file cfn-touring.yaml \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "$PARAMS"

# スタック出力取得
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)
CF_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" --output text)
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" --output text)

echo "    S3 Bucket : $BUCKET"
echo "    CF Domain : $CF_DOMAIN"
echo "    API URL   : $API_URL"

# ────────────────────────────────────────────
# Step 3: Lambda コードデプロイ
# ────────────────────────────────────────────
echo "=== [3/4] Lambda コードデプロイ ==="
bash "$(dirname "$0")/../backend/deploy.sh"

# ────────────────────────────────────────────
# Step 4: フロントエンドビルド & S3 同期
# ────────────────────────────────────────────
if $DEPLOY_FRONTEND; then
  echo "=== [4/4] フロントエンドビルド & S3 同期 ==="
  FRONTEND_DIR="$(dirname "$0")/../frontend"
  cd "$FRONTEND_DIR"

  npm install --silent
  npm run build

  # dist/ → S3 同期（ハッシュ付き _astro/ は長期キャッシュ、それ以外は1日）
  aws s3 sync dist/ "s3://${BUCKET}" --delete \
    --exclude "_astro/*"
  aws s3 sync dist/_astro/ "s3://${BUCKET}/_astro/" \
    --cache-control "public,max-age=31536000,immutable"
  aws s3 cp dist/index.html "s3://${BUCKET}/index.html" \
    --cache-control "public,max-age=0,must-revalidate"

  echo "=== CloudFront キャッシュ無効化 ==="
  aws cloudfront create-invalidation \
    --distribution-id "$DIST_ID" \
    --paths "/*" \
    --query "Invalidation.Id" --output text
fi

# ────────────────────────────────────────────
# 完了メッセージ
# ────────────────────────────────────────────
echo ""
echo "✅ デプロイ完了"
echo "   CloudFront URL : https://${CF_DOMAIN}"
echo "   API Gateway URL: ${API_URL}"
if [ -n "$CERT_ARN" ]; then
  echo "   カスタムドメイン: https://touring.zer0-infra.com"
else
  echo ""
  echo "⚠️  カスタムドメイン設定手順（初回のみ）:"
  echo "   1. bash infra/deploy-infra.sh --cert  を実行"
  echo "   2. DNS レジストラで ACM の CNAME 検証レコードを追加"
  echo "   3. 証明書が ISSUED になったら再度 bash infra/deploy-infra.sh を実行"
  echo "   4. DNS レジストラで touring.zer0-infra.com → ${CF_DOMAIN} の CNAME を追加"
fi
