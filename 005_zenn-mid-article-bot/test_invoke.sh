#!/bin/bash
# ZennMidArticleGenerator テスト実行スクリプト
# test_mode: true を渡すことでHaiku(安価)に自動切替

set -euo pipefail

FUNCTION_NAME="ZennMidArticleGenerator"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
OUTPUT_FILE="/tmp/mid_test_result.json"

echo "=============================="
echo "テスト実行（Haiku使用）"
echo "=============================="

# test_mode: true を渡して非同期実行
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --invocation-type Event \
  --payload '{"test_mode": true}' \
  "${OUTPUT_FILE}" > /dev/null

echo "実行開始しました。ログを確認中..."
echo ""

# ログをフォロー（Ctrl+Cで停止）
aws logs tail "${LOG_GROUP}" \
  --region "${REGION}" \
  --since 1m \
  --follow
