#!/bin/bash
# S3から最新のZenn記事をoutput/にダウンロードし、S3オブジェクトを削除する

set -e

BUCKET="zer0-dev-s3"
S3_PREFIX="zenn-articles"
OUTPUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/output"
REGION="ap-northeast-1"

echo "=== Zenn記事ダウンロード ==="

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
  # フォルダ名（例: zenn-articles/20260331_210000_sqs/）からベース名を取得
  BASENAME=$(echo "$FOLDER" | sed "s|${S3_PREFIX}/||" | tr -d '/')

  # 連番を付与（output/ 内の既存 NNN_* ディレクトリの最大値 + 1）
  # 注意: 過去に「ディレクトリ数 + 1」で採番していたため、一時的にディレクトリが
  # 欠けていた期間（例: 早期のテストフォルダを削除した直後）に既存の最大番号より
  # 小さい番号が再割り当てされ、番号の重複が発生した実例がある（2026-09-20修正）。
  # 個数ではなく実際に存在する番号の最大値を基準にすることで再発を防ぐ。
  MAX_NUM=$(find "$OUTPUT_DIR" -maxdepth 1 -type d -name '[0-9][0-9][0-9]_*' -printf '%f\n' 2>/dev/null \
    | sed -E 's/^([0-9]{3})_.*/\1/' | sort -n | tail -1)
  MAX_NUM=${MAX_NUM:-0}
  NUM=$(printf "%03d" $((10#$MAX_NUM + 1)))
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
