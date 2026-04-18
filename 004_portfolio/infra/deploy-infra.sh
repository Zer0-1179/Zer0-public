#!/bin/bash
# deploy-infra.sh - インフラ構築（初回のみ実行）
# S3バケット + Lambda + CloudFrontディストリビューションを作成する
#
# 使い方:
#   cd infra && bash deploy-infra.sh
#
# 実行後:
#   CloudFrontUrl を src/.env の SITE_URL に設定してください

set -e

STACK_NAME="Zer0-portfolio"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== ポートフォリオサイト インフラ構築 ==="
echo "スタック名: $STACK_NAME"
echo "リージョン: $REGION"
echo ""

# ── CloudFormationスタックのデプロイ ──────────────────────────
echo "[1/2] CloudFormationスタックをデプロイ中..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo "  ✓ スタックデプロイ完了"

# ── 作成されたリソース情報の表示 ────────────────────────────────
echo ""
echo "[2/2] 作成されたリソース情報:"
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
