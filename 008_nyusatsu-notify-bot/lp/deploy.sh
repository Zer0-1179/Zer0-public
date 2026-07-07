#!/bin/bash
# deploy.sh - LPの静的アセットをS3へ同期しCloudFrontキャッシュを無効化する
#
# 使い方:
#   cd lp && bash deploy.sh

set -e

STACK_NAME="zer0-nyusatsu-lp-hosting"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --output text)

DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
  --output text)

echo "[1/2] S3へ同期中 (s3://$BUCKET_NAME)..."
aws s3 sync "${SCRIPT_DIR}/src/" "s3://${BUCKET_NAME}/" --delete --region "$REGION"

echo "[2/2] CloudFrontキャッシュを無効化中 (Distribution: $DIST_ID)..."
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null

echo "デプロイ完了。"
