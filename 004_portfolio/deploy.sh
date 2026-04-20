#!/bin/bash
# deploy.sh - ポートフォリオサイト ビルド → Lambda更新 → S3同期 → CloudFrontキャッシュ無効化
#
# 使い方:
#   通常デプロイ:     bash deploy.sh
#   DRY RUN確認:      bash deploy.sh --dry-run
#
# 前提条件:
#   - インフラ構築済み: cd infra && bash deploy-infra.sh
#   - src/.env に NOTE_RSS_URL を設定済み（任意）

set -e

STACK_NAME="Zer0-portfolio"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
MODE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/src"

echo "=== ポートフォリオサイト デプロイ ==="

# ── [0/5] CloudFormation OutputsからAWSリソース情報を取得 ────────
echo "[0/6] AWSリソース情報を取得中..."

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --output text 2>/dev/null || echo "")

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
  --output text 2>/dev/null || echo "")

LAMBDA_FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text 2>/dev/null || echo "")

SITE_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [ -z "$BUCKET_NAME" ] || [ -z "$DISTRIBUTION_ID" ] || [ -z "$LAMBDA_FUNCTION_NAME" ]; then
  echo "エラー: CloudFormationスタック '$STACK_NAME' が見つかりません。"
  echo "先に実行してください: cd infra && bash deploy-infra.sh"
  exit 1
fi

echo "  ✓ バケット     : $BUCKET_NAME"
echo "  ✓ Distribution : $DISTRIBUTION_ID"
echo "  ✓ Lambda       : $LAMBDA_FUNCTION_NAME"
echo "  ✓ サイトURL    : $SITE_URL"

# ── DRY RUN ─────────────────────────────────────────────────────
if [ "$MODE" = "--dry-run" ]; then
  echo ""
  echo "[DRY RUN] 設定確認完了。実際にデプロイするには: bash deploy.sh"
  exit 0
fi

# ── [1/5] Astroビルド ─────────────────────────────────────────────
echo ""
echo "[1/6] Astroビルド中..."
cd "$SRC_DIR"
export SITE_URL
npm run build
echo "  ✓ ビルド完了"

# ── [2/5] Lambda zip 作成 & S3アップロード ───────────────────────
echo ""
echo "[2/6] Lambda パッケージ作成中..."
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# lambda.mjs + dist/server/ + package.json をコピー
cp "${SRC_DIR}/lambda.mjs" "$TMPDIR/"
mkdir -p "$TMPDIR/dist"
cp -r "${SRC_DIR}/dist/server" "$TMPDIR/dist/"
cp "${SRC_DIR}/package.json" "$TMPDIR/"

# 本番依存のみインストール
cd "$TMPDIR"
npm install --production --ignore-scripts --silent

# zip 作成
ZIP_PATH="${SCRIPT_DIR}/lambda-deployment.zip"
zip -r "$ZIP_PATH" . > /dev/null
ZIP_SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
echo "  ✓ zip 作成完了 (${ZIP_SIZE})"

# S3 にアップロード
aws s3 cp "$ZIP_PATH" "s3://${BUCKET_NAME}/lambda/deployment.zip" \
  --region "$REGION" \
  --no-progress
echo "  ✓ S3 アップロード完了"

# ── [3/5] Lambda コード更新 & 環境変数更新 ──────────────────────
echo ""
echo "[3/6] Lambda 更新中..."
aws lambda update-function-code \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --s3-bucket "$BUCKET_NAME" \
  --s3-key "lambda/deployment.zip" \
  --region "$REGION" \
  --output text > /dev/null

aws lambda wait function-updated \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$REGION"

aws lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --environment "Variables={SITE_URL=${SITE_URL}}" \
  --region "$REGION" \
  --output text > /dev/null

aws lambda wait function-updated \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$REGION"

echo "  ✓ Lambda 更新完了"

# ── [4/5] S3 静的アセット同期 ───────────────────────────────────
echo ""
echo "[4/6] 静的アセット同期中..."
cd "$SCRIPT_DIR"
# _astro/ はコンテンツハッシュ付きなので長期キャッシュ
aws s3 sync "${SRC_DIR}/dist/client/_astro/" "s3://${BUCKET_NAME}/_astro/" \
  --cache-control "public,max-age=31536000,immutable" \
  --region "$REGION" \
  --no-progress
# images/ など _astro/ 以外の静的ファイルは短期キャッシュ
aws s3 sync "${SRC_DIR}/dist/client/" "s3://${BUCKET_NAME}/" \
  --exclude "_astro/*" \
  --cache-control "public,max-age=86400" \
  --region "$REGION" \
  --no-progress
echo "  ✓ S3 同期完了"

# ── [5/5] CloudFrontキャッシュ無効化 ────────────────────────────
echo ""
echo "[5/6] CloudFrontキャッシュを無効化中..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query "Invalidation.Id" \
  --output text)
echo "  ✓ 無効化ID: ${INVALIDATION_ID}"

echo ""
echo "=== デプロイ完了 ==="
echo "サイトURL: ${SITE_URL}"
echo "※ キャッシュ反映まで約1〜2分かかります"

# ── [6/6] 疎通確認 ──────────────────────────────────────────────
echo ""
echo "[6/6] 疎通確認..."

PAGES=(
  "/ja/" "/ja/about/" "/ja/projects/" "/ja/articles/" "/ja/contact/"
  "/en/" "/en/about/" "/en/projects/" "/en/articles/" "/en/contact/"
)
ALL_OK=true
for PAGE in "${PAGES[@]}"; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SITE_URL}${PAGE}")
  if [ "$STATUS" != "200" ]; then
    echo "  ❌ $PAGE → $STATUS"
    ALL_OK=false
  else
    echo "  ✅ $PAGE → 200"
  fi
done

# 404ページ確認（存在しないパスが正しく404を返すこと）
STATUS_404=$(curl -s -o /dev/null -w "%{http_code}" "${SITE_URL}/ja/not-found-check/")
if [ "$STATUS_404" != "404" ]; then
  echo "  ❌ /ja/not-found-check/ → $STATUS_404 (expected 404)"
  ALL_OK=false
else
  echo "  ✅ /ja/not-found-check/ → 404"
fi

echo ""
echo "  セキュリティヘッダー確認..."
REQUIRED_HEADERS=("x-content-type-options" "x-frame-options" "strict-transport-security")
for H in "${REQUIRED_HEADERS[@]}"; do
  VAL=$(curl -sI "${SITE_URL}/ja/" | grep -i "^${H}:")
  if [ -z "$VAL" ]; then
    echo "  ❌ $H 未設定"
    ALL_OK=false
  else
    echo "  ✅ $H: $VAL"
  fi
done

echo ""
$ALL_OK && echo "=== 全チェック OK ===" || { echo "⚠️ 一部チェックに問題あり"; exit 1; }

# GitHubへ自動同期
echo ""
bash /root/Zer0/sync_to_public.sh
