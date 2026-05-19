#!/bin/bash
set -euo pipefail

# ============================================================
# Zenn技術記事自動生成システム デプロイスクリプト
# SAM不使用・S3不使用・CloudFormation + Lambda直接更新
# ============================================================

REGION="ap-northeast-1"
STACK_NAME="zenn-article-generator"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "${SENDER_EMAIL:-}" ] || [ -z "${RECIPIENT_EMAIL:-}" ]; then
  echo "Error: 環境変数を設定してください"
  echo ""
  echo "使い方:"
  echo "  export SENDER_EMAIL='your-verified@example.com'"
  echo "  export RECIPIENT_EMAIL='notify@example.com'"
  echo "  ./deploy.sh"
  echo ""
  echo "Layerを更新する場合: DEPLOY_LAYER=1 ./deploy.sh"
  exit 1
fi

echo "=============================="
echo "デプロイ設定"
echo "=============================="
echo "リージョン     : ${REGION}"
echo "スタック名     : ${STACK_NAME}"
echo "送信元メール   : ${SENDER_EMAIL}"
echo "通知先メール   : ${RECIPIENT_EMAIL}"
echo "=============================="
echo ""

# [1/3] Layerデプロイ（DEPLOY_LAYER=1 のときのみ）
LAYER_ARN=""
if [ "${DEPLOY_LAYER:-0}" = "1" ]; then
  echo "[1/3] Lambda Layerをデプロイ中（直接publish・S3不要）..."
  LAYER_ZIP="${SCRIPT_DIR}/../matplotlib_layer.zip"
  if [ ! -f "${LAYER_ZIP}" ]; then
    echo "Error: ${LAYER_ZIP} が見つかりません。build_layer.sh を実行してください。"
    exit 1
  fi
  LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name matplotlib-aws-icons \
    --description "matplotlib + numpy + Pillow + AWS official icons for article diagram generation" \
    --zip-file "fileb://${LAYER_ZIP}" \
    --compatible-runtimes python3.14 \
    --compatible-architectures x86_64 \
    --region "${REGION}" \
    --query "LayerVersionArn" --output text)
  echo "  ✓ Layer publish 完了: ${LAYER_ARN}"
else
  # 現在スタックが使用中の Layer ARN を取得
  LAYER_ARN=$(aws lambda get-function-configuration \
    --function-name ZennArticleGenerator \
    --region "${REGION}" \
    --query "Layers[0].Arn" --output text 2>/dev/null || \
    echo "arn:aws:lambda:${REGION}:$(aws sts get-caller-identity --query Account --output text):layer:matplotlib-aws-icons:36")
  echo "[1/3] Layer: ${LAYER_ARN}（既存を使用）"
fi

# [2/3] CloudFormationスタックデプロイ
echo ""
echo "[2/3] CloudFormationスタックをデプロイ中..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cloudformation-article-generator.yaml" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    SenderEmail="${SENDER_EMAIL}" \
    RecipientEmail="${RECIPIENT_EMAIL}" \
    BedrockModelId="${BEDROCK_MODEL_ID:-jp.anthropic.claude-haiku-4-5-20251001-v1:0}" \
    DiagramsLayerArn="${LAYER_ARN}" \
  --no-fail-on-empty-changeset
echo "  ✓ スタックデプロイ完了"

# [3/3] Lambdaコードを直接デプロイ（S3不使用）
echo ""
echo "[3/3] Lambdaコードをデプロイ中..."
cd "${SCRIPT_DIR}"
zip -r /tmp/zenn_function.zip \
  lambda_function.py \
  diagram_generator.py \
  aws_icons/ \
  fonts/ \
  -q
echo "  zipサイズ: $(du -sh /tmp/zenn_function.zip | cut -f1)"

aws lambda update-function-code \
  --function-name ZennArticleGenerator \
  --zip-file fileb:///tmp/zenn_function.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified, CodeSize]" \
  --output text

rm -f /tmp/zenn_function.zip
echo "  ✓ Lambdaコードデプロイ完了"

# 結果確認
echo ""
echo "デプロイ結果を確認中..."
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
echo "【Lambda動作確認】"
echo "  aws lambda invoke --function-name ZennArticleGenerator --region ${REGION} response.json && cat response.json"
echo ""
echo "【ログ確認】"
echo "  aws logs tail /aws/lambda/ZennArticleGenerator --region ${REGION} --since 10m"
echo ""
echo "【Layerを更新する場合】"
echo "  bash scripts/build_layer.sh  # matplotlib_layer.zip をビルド"
echo "  DEPLOY_LAYER=1 ./deploy.sh   # Layer publish + スタック更新"
echo ""
echo "自動実行スケジュール: 毎週木曜日 21:00 JST（UTC 12:00）"
