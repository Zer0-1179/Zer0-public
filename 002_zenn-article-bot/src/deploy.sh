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

# [1/2] CloudFormationスタックデプロイ
echo ""
echo "[1/2] CloudFormationスタックをデプロイ中..."
aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/cfn-article-generator.yaml" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    SenderEmail="${SENDER_EMAIL}" \
    RecipientEmail="${RECIPIENT_EMAIL}" \
    BedrockArticleModelId="${BEDROCK_MODEL_ID:-jp.anthropic.claude-haiku-4-5-20251001-v1:0}" \
  --no-fail-on-empty-changeset
echo "  ✓ スタックデプロイ完了"

# [2/2] Lambdaコードを直接デプロイ（S3不使用）
echo ""
echo "[2/2] Lambdaコードをデプロイ中..."
cd "${SCRIPT_DIR}"
# 画像はGPTに生成・配置を依頼する運用のため、diagram_generator.py・aws_icons/・fonts/は
# 本番Lambdaにはもう不要（同梱すると無駄にデプロイパッケージが膨らむ）。
# ファイル自体は将来のため削除せずリポジトリに残している。
zip -r /tmp/zenn_function.zip \
  lambda_function.py \
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
echo "  テスト実行（dry_run・S3/メール/SSMをスキップ）:"
echo "  bash ~/Zer0/002_Zenn_Auto_Article_Bot/scripts/test_invoke.sh"
echo ""
echo "  本番実行:"
echo "  aws lambda invoke --function-name ZennArticleGenerator --region ${REGION} --invocation-type Event --payload '{}' /tmp/res.json"
echo ""
echo "【ログ確認】"
echo "  aws logs tail /aws/lambda/ZennArticleGenerator --region ${REGION} --since 10m"
echo ""
echo "自動実行スケジュール: 第1・第3木曜 21:00 JST（UTC 12:00）"
