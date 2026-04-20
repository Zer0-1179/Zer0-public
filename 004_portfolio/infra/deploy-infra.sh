#!/bin/bash
# deploy-infra.sh - インフラ構築（初回のみ実行）
#
# 使い方:
#   cd infra && bash deploy-infra.sh
#
# 実行後:
#   CloudFrontUrl を src/.env の SITE_URL に設定してください

set -e

STACK_NAME="Zer0-portfolio"
CERT_STACK_NAME="Zer0-portfolio-cert"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
CERT_REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== ポートフォリオサイト インフラ構築 ==="
echo "スタック名: $STACK_NAME"
echo "リージョン: $REGION"
echo ""

# ── [1/3] 証明書スタック (us-east-1) ──────────────────────────
echo "[1/3] ACM証明書スタックをデプロイ中 ($CERT_REGION)..."

# 既存証明書のインポートが必要な場合はスキップ、なければ新規作成
CERT_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$CERT_STACK_NAME" \
  --region "$CERT_REGION" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [ "$CERT_STATUS" = "DOES_NOT_EXIST" ]; then
  echo "  証明書スタックを新規作成します..."
  aws cloudformation deploy \
    --template-file "${SCRIPT_DIR}/certificate.yaml" \
    --stack-name "$CERT_STACK_NAME" \
    --region "$CERT_REGION" \
    --no-fail-on-empty-changeset
else
  echo "  証明書スタック既存 (Status: $CERT_STATUS), 更新をスキップ"
fi

CERT_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$CERT_STACK_NAME" \
  --region "$CERT_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text)

echo "  ✓ 証明書ARN: $CERT_ARN"

# ── [2/3] メインスタック (ap-northeast-1) ─────────────────────
echo ""
echo "[2/3] メインスタックをデプロイ中 ($REGION)..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides CertificateArn="$CERT_ARN"

echo "  ✓ スタックデプロイ完了"

# ── [3/3] 作成されたリソース情報の表示 ────────────────────────
echo ""
echo "[3/3] 作成されたリソース情報:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table

echo ""
echo "=== インフラ構築完了 ==="
echo ""
echo "次のステップ:"
echo "  1. 上記 CloudFrontUrl を ../src/.env の SITE_URL に設定"
echo "  2. note.comのRSSフィードURLを ../src/.env の NOTE_RSS_URL に設定"
echo "     例: NOTE_RSS_URL=https://note.com/YOUR_NOTE_ID/rss"
echo "  3. cd .. && bash deploy.sh"
echo ""
echo "カスタムドメイン（www.zer0-infra.com）を有効にするには："
echo "  お名前.comで以下のCNAMEレコードを追加:"
DIST_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text | sed 's|https://||')
echo "    ホスト名: www"
echo "    VALUE:    $DIST_DOMAIN"
