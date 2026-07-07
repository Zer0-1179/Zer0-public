#!/bin/bash
# deploy-infra.sh - LPインフラ構築（初回のみ実行）
#
# 使い方:
#   cd infra && bash deploy-infra.sh

set -e

STACK_NAME="zer0-nyusatsu-lp-hosting"
CERT_STACK_NAME="zer0-nyusatsu-lp-cert"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
CERT_REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Nyusatsu LP インフラ構築 ==="

# ── [1/3] 証明書スタック (us-east-1) ──────────────────────────
echo "[1/3] ACM証明書スタックをデプロイ中 ($CERT_REGION)..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/certificate.yaml" \
  --stack-name "$CERT_STACK_NAME" \
  --region "$CERT_REGION" \
  --no-fail-on-empty-changeset

CERT_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$CERT_STACK_NAME" \
  --region "$CERT_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text)

echo "  証明書ARN: $CERT_ARN"

# ── [2/3] メインスタック (ap-northeast-1) ─────────────────────
echo "[2/3] メインスタックをデプロイ中 ($REGION)..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cfn-lp-hosting.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --no-fail-on-empty-changeset \
  --parameter-overrides CertificateArn="$CERT_ARN"

# ── [3/3] 出力情報の表示 ───────────────────────────────────────
echo "[3/3] 作成されたリソース情報:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table

DIST_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text | sed 's|https://||')

echo ""
echo "カスタムドメイン（nyusatsu.zer0-infra.com）を有効にするには："
echo "  お名前.comで以下のCNAMEレコードを追加:"
echo "    ホスト名: nyusatsu"
echo "    VALUE:    $DIST_DOMAIN"
echo ""
echo "証明書のDNS検証レコードは以下で確認できます:"
echo "  aws acm describe-certificate --certificate-arn $CERT_ARN --region us-east-1 \\"
echo "    --query 'Certificate.DomainValidationOptions[0].ResourceRecord'"
