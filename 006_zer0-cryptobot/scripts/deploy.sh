#!/bin/bash
set -euo pipefail

# ============================================================
# Zer0-CryptoBot デプロイスクリプト
# SAM不使用・CloudFormation + Lambda直接コードデプロイ
# ============================================================

REGION="ap-northeast-1"
STACK_NAME="zer0-cryptobot"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# テスト用強制フラグ（デフォルト0=無効）
# テスト時: ENABLE_FORCE_TEST=1 bash scripts/deploy.sh
ENABLE_FORCE_TEST="${ENABLE_FORCE_TEST:-0}"

if [ -z "${SENDER_EMAIL:-}" ] || [ -z "${RECIPIENT_EMAIL:-}" ]; then
  echo "Error: 環境変数を設定してください"
  echo ""
  echo "使い方:"
  echo "  export SENDER_EMAIL='your-verified@example.com'"
  echo "  export RECIPIENT_EMAIL='notify@example.com'"
  echo "  bash scripts/deploy.sh"
  echo ""
  echo "テスト時:"
  echo "  ENABLE_FORCE_TEST=1 bash scripts/deploy.sh"
  exit 1
fi

echo "=============================="
echo "デプロイ設定"
echo "=============================="
echo "リージョン    : ${REGION}"
echo "スタック名    : ${STACK_NAME}"
echo "送信元メール  : ${SENDER_EMAIL}"
echo "通知先メール  : ${RECIPIENT_EMAIL}"
echo "ForceTest     : ${ENABLE_FORCE_TEST}"
echo "スケジュール  : 4時間毎（UTC 0/4/8/12/16/20時）"
echo "=============================="
echo ""

# [1/3] CloudFormationスタックをデプロイ（S3不使用）
echo "[1/3] CloudFormationスタックをデプロイ中..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation-cryptobot.yaml" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    SenderEmail="${SENDER_EMAIL}" \
    RecipientEmail="${RECIPIENT_EMAIL}" \
    EnableForceTest="${ENABLE_FORCE_TEST}" \
  --no-fail-on-empty-changeset
echo "  ✓ スタックデプロイ完了"

# [2/3] Lambdaコードを直接デプロイ（S3不使用）
echo ""
echo "[2/3] Lambdaコードをデプロイ中（S3不使用）..."

# Analyzer
cd "${SCRIPT_DIR}/lambda/analyzer"
pip install -r requirements.txt -t . -q 2>/dev/null || true
zip -r /tmp/analyzer.zip lambda_function.py -q
zip -r /tmp/analyzer.zip *.py 2>/dev/null | true
# 依存パッケージがあれば同梱（requirements.txtの内容）
if grep -v "^#\|^$" requirements.txt 2>/dev/null | grep -q .; then
  zip -r /tmp/analyzer.zip . -x "*.pyc" -x "__pycache__/*" -q
fi
aws lambda update-function-code \
  --function-name Zer0-CryptoBot-Analyzer \
  --zip-file fileb:///tmp/analyzer.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified]" --output text
echo "  ✓ Analyzer コードデプロイ完了"

# Executor
cd "${SCRIPT_DIR}/lambda/executor"
if grep -v "^#\|^$" requirements.txt 2>/dev/null | grep -q .; then
  pip install -r requirements.txt -t . -q 2>/dev/null || true
  zip -r /tmp/executor.zip . -x "*.pyc" -x "__pycache__/*" -q
else
  zip -r /tmp/executor.zip lambda_function.py -q
fi
aws lambda update-function-code \
  --function-name Zer0-CryptoBot-Executor \
  --zip-file fileb:///tmp/executor.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified]" --output text
echo "  ✓ Executor コードデプロイ完了"

# FailureNotifier
cd "${SCRIPT_DIR}/lambda/failure_notifier"
zip -r /tmp/failure_notifier.zip lambda_function.py -q
aws lambda update-function-code \
  --function-name Zer0-CryptoBot-FailureNotifier \
  --zip-file fileb:///tmp/failure_notifier.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified]" --output text
echo "  ✓ FailureNotifier コードデプロイ完了"

cd "${SCRIPT_DIR}/lambda/weekly_summary"
zip -r /tmp/weekly_summary.zip lambda_function.py -q
aws lambda update-function-code \
  --function-name Zer0-CryptoBot-WeeklySummary \
  --zip-file fileb:///tmp/weekly_summary.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified]" --output text
echo "  ✓ WeeklySummary コードデプロイ完了"

rm -f /tmp/analyzer.zip /tmp/executor.zip /tmp/failure_notifier.zip /tmp/weekly_summary.zip

# [3/3] デプロイ結果確認
echo ""
echo "[3/3] デプロイ結果を確認中..."
aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs" \
  --output table

# GitHubへ自動同期
bash /root/Zer0/sync_to_public.sh

echo ""
echo "=============================="
echo "デプロイ完了！"
echo "=============================="
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【動作確認コマンド】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Analyzer 手動実行:"
echo "  aws lambda invoke --function-name Zer0-CryptoBot-Analyzer \\"
echo "    --payload '{}' /tmp/analyzer_res.json --region ${REGION} && cat /tmp/analyzer_res.json"
echo ""
echo "  ログ確認:"
echo "  aws logs tail /aws/lambda/Zer0-CryptoBot-Analyzer --since 10m --region ${REGION}"
echo "  aws logs tail /aws/lambda/Zer0-CryptoBot-Executor --since 10m --region ${REGION}"
echo ""
echo "  SSM state 確認:"
echo "  aws ssm get-parameter --name '/Zer0/CryptoBot/state' --region ${REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "スケジュール: 毎日 0/4/8/12/16/20 時（UTC）= JST +9h"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
