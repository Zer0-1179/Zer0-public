#!/bin/bash
set -euo pipefail

# ============================================================
# Zenn中級記事自動生成システム デプロイスクリプト
# SAM不使用・S3不使用・Lambdaコード直接更新
# ============================================================

REGION="ap-northeast-1"
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
echo "関数名         : ZennMidArticleGenerator"
echo "実行スケジュール: 毎月1日・15日 21:00 JST"
echo "=============================="
echo ""

# [1/2] Lambdaコードを直接デプロイ（S3不使用）
echo "[1/2] Lambdaコードをデプロイ中..."
cd "${SCRIPT_DIR}"
zip -r /tmp/zenn_mid_function.zip \
  lambda_function.py \
  diagram_generator.py \
  -q
echo "  zipサイズ: $(du -sh /tmp/zenn_mid_function.zip | cut -f1)"

aws lambda update-function-code \
  --function-name ZennMidArticleGenerator \
  --zip-file fileb:///tmp/zenn_mid_function.zip \
  --region "${REGION}" \
  --query "[FunctionName, LastModified, CodeSize]" \
  --output text

rm -f /tmp/zenn_mid_function.zip
echo "  ✓ Lambdaコードデプロイ完了"

# [2/2] デプロイ結果確認
echo ""
echo "[2/2] Lambda関数の状態を確認中..."
aws lambda get-function-configuration \
  --function-name ZennMidArticleGenerator \
  --region "${REGION}" \
  --query "{State:State,Runtime:Runtime,Timeout:Timeout,MemorySize:MemorySize,LastModified:LastModified}" \
  --output table

# GitHubへ自動同期
bash /root/Zer0/sync_to_public.sh

echo ""
echo "=============================="
echo "デプロイ完了！"
echo "=============================="
echo ""
echo "【Lambda動作確認】"
echo "  テスト実行（Haiku使用・コスト削減）:"
echo "  bash ~/Zer0/005_Zenn_Mid_Article_Bot/scripts/test_invoke.sh"
echo ""
echo "  本番実行（Sonnet使用）:"
echo "  aws lambda invoke --function-name ZennMidArticleGenerator --region ${REGION} --invocation-type Event --payload '{}' /tmp/res.json"
echo ""
echo "  ログ確認:"
echo "  aws logs tail /aws/lambda/ZennMidArticleGenerator --region ${REGION} --since 10m --follow"
echo ""
echo "  ダウンロード:"
echo "  bash ~/Zer0/005_Zenn_Mid_Article_Bot/scripts/download_article.sh"
echo ""
echo "自動実行スケジュール: 毎月1日・15日 21:00 JST（UTC 12:00）"
