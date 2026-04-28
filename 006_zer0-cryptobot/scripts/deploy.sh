#!/bin/bash
set -euo pipefail

# ============================================================
# Zer0-CryptoBot デプロイスクリプト
# ============================================================

REGION="ap-northeast-1"
STACK_NAME="zer0-cryptobot"
SAM_BUCKET="zer0-sam-deploy"

# テスト用強制フラグ（デフォルト0=無効）
# テスト時: ENABLE_FORCE_TEST=1 bash scripts/deploy.sh
ENABLE_FORCE_TEST="${ENABLE_FORCE_TEST:-0}"

# 必須環境変数チェック
if [ -z "${SENDER_EMAIL:-}" ] || [ -z "${RECIPIENT_EMAIL:-}" ]; then
  echo "Error: 環境変数を設定してください"
  echo ""
  echo "使い方:"
  echo "  export SENDER_EMAIL='your-verified@example.com'"
  echo "  export RECIPIENT_EMAIL='notify@example.com'"
  echo "  ./deploy.sh"
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
echo "SAMバケット   : ${SAM_BUCKET}"
echo "スケジュール  : 4時間毎（UTC 0/4/8/12/16/20時）"
echo "=============================="
echo ""

# SAM デプロイ用 S3 バケット確認
echo "[1/4] SAMデプロイ用S3バケットを確認中..."
if ! aws s3 ls "s3://${SAM_BUCKET}" 2>/dev/null; then
  echo "  バケットを作成します: ${SAM_BUCKET}"
  aws s3 mb "s3://${SAM_BUCKET}" --region "${REGION}"
fi
echo "  OK: ${SAM_BUCKET}"

# SAM ビルド（template.yaml はルートにあるので scripts/ の親へ移動）
echo ""
echo "[2/4] SAMビルド中..."
cd "$(dirname "$0")/.."
sam build --region "${REGION}"

# SAM デプロイ
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
    EnableForceTest="${ENABLE_FORCE_TEST}" \
  --no-fail-on-empty-changeset

# デプロイ結果確認
echo ""
echo "[4/4] デプロイ結果を確認中..."
aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs" \
  --output table

# S3 クリーンアップ（全スタックが参照しないアーティファクトを削除）
echo ""
echo "[5/5] S3クリーンアップ中..."
STACKS_USING_BUCKET=("zenn-article-generator" "zenn-mid-article-generator" "zer0-cryptobot")
KEEP_KEYS=()
for s in "${STACKS_USING_BUCKET[@]}"; do
  keys=$(aws cloudformation get-template --stack-name "$s" \
    --query "TemplateBody" --output json 2>/dev/null \
    | grep -oE '"[a-f0-9]{32}"' | tr -d '"' || true)
  for k in $keys; do
    KEEP_KEYS+=("$k")
  done
done

DELETED=0
while IFS= read -r key; do
  keep=false
  for k in "${KEEP_KEYS[@]}"; do
    [[ "$key" == "$k" ]] && keep=true && break
  done
  if [ "$keep" = false ]; then
    aws s3 rm "s3://${SAM_BUCKET}/${key}" --region "${REGION}" > /dev/null 2>&1 || true
    echo "  削除: ${key}"
    DELETED=$((DELETED + 1))
  fi
done < <(aws s3 ls "s3://${SAM_BUCKET}/" --region "${REGION}" 2>/dev/null | awk '{print $NF}')
echo "  ${DELETED}件削除完了"

echo ""
echo "=============================="
echo "デプロイ完了！"
echo "=============================="

# GitHub 公開リポジトリへ同期
bash /root/Zer0/sync_to_public.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【動作確認コマンド】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Analyzer 手動実行:"
echo "  aws lambda invoke --function-name Zer0-CryptoBot-Analyzer \\"
echo "    --payload '{}' /tmp/analyzer.json --region ${REGION}"
echo "  cat /tmp/analyzer.json"
echo ""
echo "  ログ確認:"
echo "  aws logs tail /aws/lambda/Zer0-CryptoBot-Analyzer --since 10m --region ${REGION}"
echo "  aws logs tail /aws/lambda/Zer0-CryptoBot-Executor --since 10m --region ${REGION}"
echo ""
echo "  SSM state 確認:"
echo "  aws ssm get-parameter --name '/Zer0/CryptoBot/state' --region ${REGION}"
echo ""
echo "  SSM セットアップ（未実施の場合）:"
echo "  bash ./setup_ssm.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "スケジュール: 毎日 0/4/8/12/16/20 時（UTC）= JST +9h"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
