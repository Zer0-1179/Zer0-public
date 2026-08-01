#!/bin/bash
# ZennMidArticleGenerator テスト実行スクリプト
# dry_run: true でS3アップロード・メール送信・SSM書き込みを一切スキップする
# （test_mode: true はHaiku(安価)への切替のみで、S3・メール送信は実行されるため
#  動作確認の既定はdry_runを使うこと。2026-08-01にdry_run未実装のまま呼び出し、
#  実メール送信8通・実課金が発生した事故を踏まえて既定をdry_runに変更した）

set -euo pipefail

FUNCTION_NAME="ZennMidArticleGenerator"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
OUTPUT_FILE="/tmp/mid_test_result.json"

echo "=============================="
echo "テスト実行（dry_run=true, test_mode=true でHaiku使用）"
echo "=============================="

aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --invocation-type RequestResponse \
  --cli-binary-format raw-in-base64-out \
  --payload '{"dry_run": true, "test_mode": true}' \
  "${OUTPUT_FILE}"

echo ""
echo "Lambda レスポンス:"
cat "${OUTPUT_FILE}" | python3 -m json.tool
echo ""
echo "直近ログ:"
aws logs tail "${LOG_GROUP}" \
  --region "${REGION}" \
  --since 3m
