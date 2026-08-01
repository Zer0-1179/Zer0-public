#!/bin/bash
# ZennArticleGenerator テスト実行スクリプト
# dry_run: true でS3アップロード・メール送信・SSM書き込みを一切スキップする
# （本番モデルは元々Haikuのためコスト面の追加配慮は不要）

set -euo pipefail

FUNCTION_NAME="ZennArticleGenerator"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
OUTPUT_FILE="/tmp/zenn_test_result.json"

echo "=============================="
echo "テスト実行（dry_run=true）"
echo "=============================="

aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --invocation-type RequestResponse \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 0 \
  --payload '{"dry_run": true}' \
  "${OUTPUT_FILE}"

echo ""
echo "Lambda レスポンス:"
cat "${OUTPUT_FILE}" | python3 -m json.tool
echo ""
echo "直近ログ:"
aws logs tail "${LOG_GROUP}" \
  --region "${REGION}" \
  --since 3m
