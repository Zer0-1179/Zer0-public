#!/bin/bash
# XAiBot テスト実行スクリプト
# DRY_RUN=true に切り替えて実行し、X投稿をスキップ

set -euo pipefail

FUNCTION_NAME="XAiBot"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
MODE="${1:-random}"  # 引数でmode指定可（random/trend）

echo "=============================="
echo "テスト実行（DRY_RUN=true / mode=${MODE}）"
echo "=============================="

# DRY_RUN=true に切り替え
echo "[1/3] DRY_RUN=true に設定中..."
aws lambda update-function-configuration \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --environment "Variables={BEDROCK_MODEL_ID=jp.anthropic.claude-haiku-4-5-20251001-v1:0,SSM_PREFIX=/ai_bot,DRY_RUN=true}" \
  --query 'Environment.Variables.DRY_RUN' \
  --output text > /dev/null

# 設定反映を待機
sleep 3

echo "[2/3] Lambda 実行中..."
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --invocation-type Event \
  --payload "{\"mode\": \"${MODE}\"}" \
  /tmp/xai_test_result.json > /dev/null

# DRY_RUN=false に戻す（バックグラウンドで）
aws lambda update-function-configuration \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --environment "Variables={BEDROCK_MODEL_ID=jp.anthropic.claude-haiku-4-5-20251001-v1:0,SSM_PREFIX=/ai_bot,DRY_RUN=false}" \
  --output none &

echo "[3/3] ログを確認中（Ctrl+C で停止）..."
echo ""

aws logs tail "${LOG_GROUP}" \
  --region "${REGION}" \
  --since 1m \
  --follow
