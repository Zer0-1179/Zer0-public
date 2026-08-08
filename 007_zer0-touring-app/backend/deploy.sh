#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# lambda_function.py は zer0-touring-suggest（提案API）と zer0-touring-stats
# （利用統計集計バッチ、EventBridge Scheduler起動）の両方のハンドラーを含む
# ため、同じzipを両関数にデプロイする。
FUNCTION_NAMES=("zer0-touring-suggest" "zer0-touring-stats")
ZIP="/tmp/touring-backend.zip"

echo "[1/2] Lambda zip 作成..."
rm -f "$ZIP"
zip -j "$ZIP" lambda_function.py
echo "      → $ZIP"

echo "[2/2] Lambda コード更新..."
for FUNCTION_NAME in "${FUNCTION_NAMES[@]}"; do
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP" \
    --query "FunctionArn" --output text
  aws lambda wait function-updated --function-name "$FUNCTION_NAME"
  echo "✅ Lambda デプロイ完了: $FUNCTION_NAME"
done
