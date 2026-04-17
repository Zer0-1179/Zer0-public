#!/bin/bash
set -euo pipefail

# ============================================================
# Zenn技術記事自動生成システム デプロイスクリプト
# ============================================================

REGION="ap-northeast-1"
STACK_NAME="zenn-article-generator"
SAM_BUCKET="zer0-sam-deploy"

# 必須パラメータの確認
if [ -z "${SENDER_EMAIL:-}" ] || [ -z "${RECIPIENT_EMAIL:-}" ]; then
  echo "Error: 環境変数を設定してください"
  echo ""
  echo "使い方:"
  echo "  export SENDER_EMAIL='your-verified@example.com'"
  echo "  export RECIPIENT_EMAIL='notify@example.com'"
  echo "  ./deploy.sh"
  echo ""
  echo "注意: SENDER_EMAIL はSESで検証済みのメールアドレスである必要があります"
  exit 1
fi

echo "=============================="
echo "デプロイ設定"
echo "=============================="
echo "リージョン     : ${REGION}"
echo "スタック名     : ${STACK_NAME}"
echo "送信元メール   : ${SENDER_EMAIL}"
echo "通知先メール   : ${RECIPIENT_EMAIL}"
echo "SAMバケット    : ${SAM_BUCKET}"
echo "=============================="
echo ""

# SAMデプロイ用S3バケットを作成（存在しない場合）
echo "[1/4] SAMデプロイ用S3バケットを確認中..."
if ! aws s3 ls "s3://${SAM_BUCKET}" 2>/dev/null; then
  echo "  バケットを作成します: ${SAM_BUCKET}"
  aws s3 mb "s3://${SAM_BUCKET}" --region "${REGION}"
fi
echo "  OK: ${SAM_BUCKET}"

# Layer ビルド
echo ""
echo "[0/4] Lambda Layer をビルド中..."
bash "$(dirname "$0")/../build_layer.sh"

# SAMビルド
echo ""
echo "[2/4] SAMビルド中..."
sam build --region "${REGION}"

# SAMデプロイ
echo ""
echo "[3/4] デプロイ中..."
sam deploy \
  --stack-name "${STACK_NAME}" \
  --s3-bucket "${SAM_BUCKET}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    SenderEmail="${SENDER_EMAIL}" \
    RecipientEmail="${RECIPIENT_EMAIL}" \
    BedrockModelId="${BEDROCK_MODEL_ID:-jp.anthropic.claude-haiku-4-5-20251001-v1:0}" \
  --no-fail-on-empty-changeset

# デプロイ結果の確認
echo ""
echo "[4/4] デプロイ結果を確認中..."
aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs" \
  --output table

echo ""
echo "=============================="
echo "デプロイ完了！"
echo "=============================="
echo ""
echo "次のステップ:"
echo ""
echo "1. SESで送信元メールアドレスを検証してください（まだの場合）"
echo "   aws ses verify-email-identity --email-address ${SENDER_EMAIL} --region ${REGION}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【ローカル動作確認】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  実行コマンド:"
echo "  cd ~/Zer0/002_Zenn_Auto_Article_Bot/src"
echo "  SES_SENDER_EMAIL=${SENDER_EMAIL} SES_RECIPIENT_EMAIL=${RECIPIENT_EMAIL} python3 lambda_function.py"
echo ""
echo "  成功時の出力例（所要時間: 約30〜60秒）:"
echo "  [20240101_090000] Zenn技術記事自動生成を開始します"
echo "  Step 1: Bedrockでトピックを選択中..."
echo "  選択されたトピック: Amazon VPC          ← 毎回ランダムに変わる"
echo "  Step 2: 記事を生成中（3,000〜5,000文字）..."
echo "  記事生成完了: 3,842文字                 ← 3000〜5000の範囲ならOK"
echo "  Step 3: ローカルに保存中（記事MD + 構成図PNG）..."
echo "  MD保存完了:  ~/Zer0/002_Zenn_Auto_Article_Bot/output/20240101_090000_vpc.md"
echo "  PNG生成完了: 2枚 output/006_20240101_090000_vpc/images/20240101_090000_vpc_diagram_1.png ..."
echo "  Step 4: メール通知を送信中..."
echo "  メール送信完了"
echo "  [20260412_210000] 処理が正常に完了しました"
echo ""
echo "  確認事項:"
echo "  - ~/Zer0/002_Zenn_Auto_Article_Bot/output/ に .md と _diagram_1.png, _diagram_2.png が生成されていること"
echo "  - ${RECIPIENT_EMAIL} にHTMLメールが届いていること"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【Lambda動作確認】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  実行コマンド:"
echo "  aws lambda invoke --function-name ZennArticleGenerator --region ${REGION} response.json && cat response.json"
echo ""
echo "  成功時のresponse.json（statusCode: 200 であることを確認）:"
echo '  {'
echo '    "statusCode": 200,'
echo '    "body": "{\"message\": \"記事生成が完了しました\", \"topic\": \"Amazon EC2\", \"character_count\": 3842, ...}"'
echo '  }'
echo ""
echo "  失敗時の確認方法:"
echo "  aws logs tail /aws/lambda/ZennArticleGenerator --region ${REGION} --since 10m"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "自動実行スケジュール: 毎週木曜日 21:00 JST（UTC 12:00）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
