#!/bin/bash
# deploy.sh - LPの静的アセットをS3へ同期しCloudFrontキャッシュを無効化する
#
# 使い方:
#   cd lp && bash deploy.sh

set -euo pipefail

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

if [[ "${BUCKET_NAME}" != "zer0-nyusatsu-lp-s3" ]]; then
  echo "[error] unexpected LP bucket: ${BUCKET_NAME}" >&2
  exit 1
fi
if [[ -z "${DIST_ID}" || "${DIST_ID}" == "None" ]]; then
  echo "[error] CloudFront distribution output is unavailable" >&2
  exit 1
fi

# API GatewayのIDはバックエンドスタック再作成のたびに変わるため、
# src/index.html には埋め込まず、デプロイ時にlp-backendスタックのOutputから
# 都度取得してビルド用一時ディレクトリに注入する（ソース側はプレースホルダのまま保つ）。
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "$BACKEND_STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text)

# LIFF ID(v0.28)も同様にSSMから都度注入する(ユーザーがLINE Developersコンソールで
# チャネル作成後にCLIで値を設定するまでは"REPLACE_AFTER_LINE_SETUP"のまま)。
LINE_LIFF_ID=$(aws ssm get-parameter \
  --name /nyusatsu/line-liff-id \
  --region "$REGION" \
  --query "Parameter.Value" \
  --output text)

if [[ -z "${API_ENDPOINT}" || "${API_ENDPOINT}" == "None" ]]; then
  echo "[error] backend API endpoint output is unavailable" >&2
  exit 1
fi
if [[ -z "${LINE_LIFF_ID}" || "${LINE_LIFF_ID}" == "None" ]]; then
  echo "[error] LINE LIFF ID parameter is unavailable" >&2
  exit 1
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp -r "${SCRIPT_DIR}/src/." "$BUILD_DIR/"
python3 - "${BUILD_DIR}/index.html" "${BUILD_DIR}/line-link.html" "${API_ENDPOINT}" "${LINE_LIFF_ID}" <<'PYEOF'
from pathlib import Path
import sys

index_path = Path(sys.argv[1])
line_link_path = Path(sys.argv[2])
api_endpoint = sys.argv[3]
line_liff_id = sys.argv[4]

for path in (index_path, line_link_path):
    path.write_text(path.read_text(encoding="utf-8").replace("__API_ENDPOINT__", api_endpoint), encoding="utf-8")
line_link_path.write_text(
    line_link_path.read_text(encoding="utf-8").replace("__LINE_LIFF_ID__", line_liff_id),
    encoding="utf-8",
)
PYEOF

if rg -q '__API_ENDPOINT__|__LINE_LIFF_ID__' "${BUILD_DIR}"; then
  echo "[error] LP build still contains an unresolved deployment placeholder" >&2
  exit 1
fi

NON_HTML_SYNC_PLAN="$(aws s3 sync "${BUILD_DIR}/" "s3://${BUCKET_NAME}/" --delete --dryrun --region "$REGION" --exclude "*.html")"
HTML_SYNC_PLAN="$(aws s3 sync "${BUILD_DIR}/" "s3://${BUCKET_NAME}/" --delete --dryrun --region "$REGION" --exclude "*" --include "*.html")"
if [[ -z "${NON_HTML_SYNC_PLAN}" && -z "${HTML_SYNC_PLAN}" ]]; then
  echo "更新対象のLPアセットはありません。CloudFront invalidationは実行しません。"
  exit 0
fi

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

# index.html・line-link.html内の(プレースホルダ埋め込み後の)inline <script>ブロック
# 全てからCSP用のsha256ハッシュを算出し、CloudFrontのscript-srcに反映する。
# 'unsafe-inline'は使わず、コンテンツ変更のたびにこのデプロイで自動的に
# ハッシュを再計算するため、手動更新忘れによるCSPブロックを防ぐ(Fable指摘、2026-07-13)。
echo "[2/3] CSPスクリプトハッシュを更新中..."
SCRIPT_HASHES=$(python3 - "${BUILD_DIR}/index.html" "${BUILD_DIR}/line-link.html" <<'PYEOF'
import re, hashlib, base64, sys
hashes = []
for path in sys.argv[1:]:
    html = open(path, encoding="utf-8").read()
    # 属性なしの<script>(=同一オリジンのインラインスクリプト)のみ対象。
    # <script src="...">のような外部読み込みタグはハッシュ不要(ホスト許可で対応)。
    for s in re.findall(r'<script>(.*?)</script>', html, re.DOTALL):
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
