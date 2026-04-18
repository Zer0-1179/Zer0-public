#!/bin/bash
set -euo pipefail

# ============================================================
# Zenn中級記事自動生成システム デプロイスクリプト
# ============================================================

REGION="ap-northeast-1"
STACK_NAME="zenn-mid-article-generator"
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
echo "実行スケジュール: 毎月1日・15日 21:00 JST"
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
    BedrockModelId="${BEDROCK_MODEL_ID:-jp.anthropic.claude-sonnet-4-6}" \
  --no-fail-on-empty-changeset

# デプロイ結果の確認
echo ""
echo "[4/5] デプロイ結果を確認中..."
aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs" \
  --output table

# S3クリーンアップ: 全スタックが参照しているキー以外を削除
echo ""
echo "[5/5] S3クリーンアップ中..."
STACKS_USING_BUCKET=("zenn-article-generator" "zenn-mid-article-generator")
KEEP_KEYS=()
for s in "${STACKS_USING_BUCKET[@]}"; do
  keys=$(aws cloudformation get-template --stack-name "$s" \
    --query "TemplateBody" --output json 2>/dev/null \
    | grep -o '"[a-f0-9]\{32\}"' | tr -d '"' || true)
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
    aws s3 rm "s3://${SAM_BUCKET}/${key}" --region "${REGION}" > /dev/null
    echo "  削除: ${key}"
    DELETED=$((DELETED + 1))
  fi
done < <(aws s3 ls "s3://${SAM_BUCKET}/" --region "${REGION}" | awk '{print $NF}')
echo "  ✓ ${DELETED}件削除完了"

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
echo "【AWS公式アイコン更新】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  diagrams パッケージを更新したときは以下を再実行してデプロイ:"
echo "  cd ~/Zer0/005_Zenn_Mid_Article_Bot/src"
echo "  python3 install_aws_icons.py   # aws_icons/ を公式PNGで上書き"
echo "  ./deploy.sh                    # 再デプロイ"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【ローカル動作確認】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  実行コマンド:"
echo "  cd ~/Zer0/005_Zenn_Mid_Article_Bot/src"
echo "  SES_SENDER_EMAIL=${SENDER_EMAIL} SES_RECIPIENT_EMAIL=${RECIPIENT_EMAIL} python3 lambda_function.py"
echo ""
echo "  成功時の出力例（所要時間: 約60〜90秒）:"
echo "  [20260501_210000] Zenn中級記事自動生成を開始します"
echo "  Step 1: 直近トピックをSSMから取得中..."
echo "  Step 2: Bedrockでトピックを選択中..."
echo "  選択されたトピック: サーバーレスECバックエンド完全構成 (serverless_ec)"
echo "  記事タイプ: architecture"
echo "  Step 3: 記事を生成中（4,000〜6,000文字）..."
echo "  記事生成完了: 5,123文字"
echo "  Step 4: ローカルに保存中（記事MD + 構成図PNG）..."
echo "  PNG生成完了: 2枚（AWS公式アーキテクチャアイコン使用）"
echo "  Step 7: メール通知を送信中..."
echo "  [20260501_210000] 処理が正常に完了しました"
echo ""
echo "  確認事項:"
echo "  - ~/Zer0/005_Zenn_Mid_Article_Bot/output/ に .md と _diagram_1.png, _diagram_2.png が生成されていること"
echo "  - アーキテクチャ図にAWS公式アイコンが使用されていること"
echo "  - ${RECIPIENT_EMAIL} にHTMLメールが届いていること"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【Lambda動作確認】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  実行コマンド（非同期）:"
echo "  aws lambda invoke --function-name ZennMidArticleGenerator --region ${REGION} --invocation-type Event /tmp/res.json"
echo ""
echo "  ログ確認:"
echo "  aws logs tail /aws/lambda/ZennMidArticleGenerator --region ${REGION} --since 10m --follow"
echo ""
echo "  成功時のログ（最終行）:"
echo "  [YYYYMMDD_HHMMSS] 処理が正常に完了しました"
echo ""
echo "  ダウンロード:"
echo "  bash ~/Zer0/005_Zenn_Mid_Article_Bot/download_article.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "自動実行スケジュール: 毎月1日・15日 21:00 JST（UTC 12:00）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
