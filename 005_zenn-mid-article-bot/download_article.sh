#!/bin/bash
# S3から最新のZenn中級記事をoutput/にダウンロードし、S3オブジェクトを削除する

set -e

BUCKET="zer0-dev-s3"
S3_PREFIX="zenn-mid-articles"
OUTPUT_DIR="$(cd "$(dirname "$0")" && pwd)/output"
REGION="ap-northeast-1"

echo "=== Zenn中級記事ダウンロード ==="

# S3に存在するフォルダ一覧を取得
FOLDERS=$(aws s3api list-objects-v2 \
  --bucket "$BUCKET" \
  --prefix "${S3_PREFIX}/" \
  --delimiter "/" \
  --region "$REGION" \
  --query "CommonPrefixes[].Prefix" \
  --output text 2>/dev/null)

if [ -z "$FOLDERS" ] || [ "$FOLDERS" = "None" ]; then
  echo "S3に未ダウンロードの記事はありません。"
  exit 0
fi

echo "ダウンロード対象フォルダ:"
echo "$FOLDERS"
echo ""

for FOLDER in $FOLDERS; do
  # フォルダ名（例: zenn-mid-articles/20260501_210000_serverless_ec/）からベース名を取得
  BASENAME=$(echo "$FOLDER" | sed "s|${S3_PREFIX}/||" | tr -d '/')

  # 連番を付与（output/ 内の既存 NNN_* ディレクトリ数 + 1）
  EXISTING_COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -type d -name '[0-9][0-9][0-9]_*' 2>/dev/null | wc -l)
  NUM=$(printf "%03d" $((EXISTING_COUNT + 1)))
  ARTICLE_DIR="${OUTPUT_DIR}/${NUM}_${BASENAME}"
  LOCAL_IMAGES_DIR="${ARTICLE_DIR}/images"

  mkdir -p "$ARTICLE_DIR" "$LOCAL_IMAGES_DIR"

  echo "ダウンロード中: ${NUM}_${BASENAME}"

  # mdファイルをダウンロード
  aws s3 sync \
    "s3://${BUCKET}/${FOLDER}" \
    "$ARTICLE_DIR/" \
    --exclude "images/*" \
    --region "$REGION" \
    --quiet

  # images/ 以下をダウンロード
  aws s3 sync \
    "s3://${BUCKET}/${FOLDER}images/" \
    "$LOCAL_IMAGES_DIR/" \
    --region "$REGION" \
    --quiet

  echo "  保存先: ${ARTICLE_DIR}/${BASENAME}.md"

  # S3オブジェクトを削除
  echo "  S3から削除中..."
  aws s3 rm "s3://${BUCKET}/${FOLDER}" \
    --recursive \
    --region "$REGION" \
    --quiet

  echo "  完了: s3://${BUCKET}/${FOLDER} を削除しました"
  echo ""
done

echo "=== ダウンロード完了 ==="
echo "保存先: $OUTPUT_DIR"
ls -d "$OUTPUT_DIR"/[0-9][0-9][0-9]_* 2>/dev/null || true
