#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

FUNCTION_NAME="zer0-touring-suggest"
ZIP="/tmp/touring-backend.zip"

echo "[1/2] Lambda zip 作成..."
zip -j "$ZIP" lambda_function.py
echo "      → $ZIP"

echo "[2/2] Lambda コード更新..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP" \
  --query "FunctionArn" --output text
aws lambda wait function-updated --function-name "$FUNCTION_NAME"

echo "✅ Lambda デプロイ完了: $FUNCTION_NAME"
