#!/bin/bash
# deploy-infra.sh - インフラ構築（初回のみ実行）
# WAF(us-east-1) → メインスタック(ap-northeast-1) の順でデプロイ
#
# 使い方:
#   cd infra && bash deploy-infra.sh
#
# 実行後:
#   CloudFrontUrl を src/.env の SITE_URL に設定してください

set -e

STACK_NAME="Zer0-portfolio"
WAF_STACK_NAME="Zer0-portfolio-waf"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
WAF_REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== ポートフォリオサイト インフラ構築 ==="
echo "スタック名: $STACK_NAME"
echo "リージョン: $REGION"
echo ""

# ── [1/3] WAF WebACL (us-east-1) ──────────────────────────────
echo "[1/3] WAF WebACLをデプロイ中 (us-east-1)..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/waf.yaml" \
  --stack-name "$WAF_STACK_NAME" \
  --region "$WAF_REGION" \
  --no-fail-on-empty-changeset

echo "  ✓ WAFスタックデプロイ完了"

WAF_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$WAF_STACK_NAME" \
  --region "$WAF_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='WebACLArn'].OutputValue" \
  --output text)

if [ -z "$WAF_ARN" ]; then
  echo "エラー: WAF WebACL ARNの取得に失敗しました"
  exit 1
fi
echo "  ✓ WebACL ARN: $WAF_ARN"

# ── [2/3] メインスタック (ap-northeast-1) ─────────────────────
echo ""
echo "[2/3] メインスタックをデプロイ中 ($REGION)..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides WebAclArn="${WAF_ARN}" \
  --no-fail-on-empty-changeset

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
