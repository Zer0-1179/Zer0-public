#!/bin/bash
# x-poster-zer0-0326 テスト実行スクリプト
# ペイロードで dry_run: true を渡して実行し、X投稿・SSM履歴更新をスキップ
# （以前は本番環境変数DRY_RUNを書き換えて戻す方式だったが、戻し処理が失敗すると
#  本番投稿が全停止する事故リスクがあったため、ペイロード指定に一本化した）

set -euo pipefail

FUNCTION_NAME="x-poster-zer0-0326"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
MODE="${1:-random}"  # 引数でmode指定可（random/trend）

echo "=============================="
echo "テスト実行（dry_run=true / mode=${MODE}）"
echo "=============================="

echo "[1/2] Lambda 実行中（同期呼び出し）..."
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${REGION}" \
  --invocation-type RequestResponse \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"mode\": \"${MODE}\", \"dry_run\": true}" \
  /tmp/xai_test_result.json > /dev/null

echo "[2/2] 実行結果:"
cat /tmp/xai_test_result.json
echo ""
echo ""
echo "直近ログ:"
aws logs tail "${LOG_GROUP}" \
  --region "${REGION}" \
  --since 3m
