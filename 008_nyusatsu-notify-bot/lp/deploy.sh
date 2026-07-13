#!/bin/bash
# deploy.sh - LPの静的アセットをS3へ同期しCloudFrontキャッシュを無効化する
#
# 使い方:
#   cd lp && bash deploy.sh

set -e

STACK_NAME="zer0-nyusatsu-lp-hosting"
BACKEND_STACK_NAME="zer0-nyusatsu-lp-backend"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --output text)

DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
  --output text)

# API GatewayのIDはバックエンドスタック再作成のたびに変わるため、
# src/index.html には埋め込まず、デプロイ時にlp-backendスタックのOutputから
# 都度取得してビルド用一時ディレクトリに注入する（ソース側はプレースホルダのまま保つ）。
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "$BACKEND_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text)

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp -r "${SCRIPT_DIR}/src/." "$BUILD_DIR/"
sed -i "s|__API_ENDPOINT__|${API_ENDPOINT}|g" "${BUILD_DIR}/index.html"

echo "[1/3] S3へ同期中 (s3://$BUCKET_NAME)..."
# HTML以外(画像・アイコン等)は適度な期間キャッシュし、HTMLはno-cacheにする。
# CloudFront invalidationはエッジキャッシュのみクリアしブラウザの手元キャッシュには
# 効かないため、Cache-Controlを明示しないと更新が反映されにくい(Fable指摘、2026-07-13)。
aws s3 sync "${BUILD_DIR}/" "s3://${BUCKET_NAME}/" --delete --region "$REGION" \
  --exclude "*.html" \
  --cache-control "public, max-age=300, must-revalidate"
aws s3 sync "${BUILD_DIR}/" "s3://${BUCKET_NAME}/" --delete --region "$REGION" \
  --exclude "*" --include "*.html" \
  --cache-control "no-cache, must-revalidate"

# index.html内の(API_ENDPOINT埋め込み後の)4つのinline <script>ブロックから
# CSP用のsha256ハッシュを算出し、CloudFrontのscript-srcに反映する。
# 'unsafe-inline'は使わず、コンテンツ変更のたびにこのデプロイで自動的に
# ハッシュを再計算するため、手動更新忘れによるCSPブロックを防ぐ(Fable指摘、2026-07-13)。
echo "[2/3] CSPスクリプトハッシュを更新中..."
SCRIPT_HASHES=$(python3 - "${BUILD_DIR}/index.html" <<'PYEOF'
import re, hashlib, base64, sys
html = open(sys.argv[1], encoding="utf-8").read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
hashes = []
for s in scripts:
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    hashes.append("'sha256-" + base64.b64encode(digest).decode() + "'")
print(" ".join(hashes))
PYEOF
)

CERT_ARN=$(aws cloudformation describe-stacks \
  --stack-name "zer0-nyusatsu-lp-cert" \
  --region us-east-1 \
  --query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" \
  --output text)
API_ORIGIN=$(echo "$API_ENDPOINT" | sed 's|/register$||')

aws cloudformation deploy \
  --template-file "${SCRIPT_DIR}/infra/cfn-lp-hosting.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --no-fail-on-empty-changeset \
  --parameter-overrides CertificateArn="$CERT_ARN" ApiOrigin="$API_ORIGIN" ScriptHashes="$SCRIPT_HASHES"

echo "[3/3] CloudFrontキャッシュを無効化中 (Distribution: $DIST_ID)..."
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null

echo "デプロイ完了。"
