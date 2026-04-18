#!/bin/bash
set -euo pipefail

# ============================================================
# matplotlib Lambda Layer ビルドスクリプト
# matplotlib + numpy + pillow を Lambda Layer としてパッケージ化
# Amazon Linux 2023 (x86_64) 互換
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAYER_DIR="${SCRIPT_DIR}/layer"
PYTHON_DIR="${LAYER_DIR}/python"
ZIP_PATH="${SCRIPT_DIR}/matplotlib_layer.zip"
REGION="ap-northeast-1"
LAYER_NAME="matplotlib-aws-icons-mid"

echo "=============================="
echo "Lambda Layer ビルド開始"
echo "=============================="

# クリーンアップ
rm -rf "${LAYER_DIR}" "${ZIP_PATH}"
mkdir -p "${PYTHON_DIR}"

# ── [1/3] matplotlib + 依存パッケージをインストール ──────────────────────────
echo "[1/3] matplotlib をインストール中..."
/tmp/py314env/bin/pip install matplotlib \
    --target "${PYTHON_DIR}" \
    --platform manylinux_2_28_x86_64 \
    --platform manylinux2014_x86_64 \
    --python-version 3.14 \
    --only-binary=:all: \
    --upgrade \
    --quiet

echo "  インストール直後サイズ: $(du -sh "${PYTHON_DIR}" | cut -f1)"

# ── [1.5/3] 不要ファイルを削除してサイズ削減 ─────────────────────────────────
echo "[1.5/3] 不要ファイルを削除中..."
find "${PYTHON_DIR}" -type d -name "tests"       -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "test"        -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "sample_data" -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -name "*.pyc" -delete 2>/dev/null || true
find "${PYTHON_DIR}" -name "*.pyo" -delete 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "*.egg-info"  -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -name "*.ttf" ! -path "*/matplotlib/*" -delete 2>/dev/null || true

echo "  削除後サイズ: $(du -sh "${PYTHON_DIR}" | cut -f1)"

# ── [2/3] zip 化 ──────────────────────────────────────────────────────────────
echo "[2/3] zip 化中..."
cd "${LAYER_DIR}"
zip -r "${ZIP_PATH}" python -q
echo "  サイズ: $(du -sh "${ZIP_PATH}" | cut -f1)"

# ── [3/3] Lambda Layer としてアップロード ─────────────────────────────────────
echo "[3/3] Lambda Layer をアップロード中..."
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name "${LAYER_NAME}" \
    --description "matplotlib + numpy + pillow for AWS mid-level architecture diagrams" \
    --zip-file "fileb://${ZIP_PATH}" \
    --compatible-runtimes python3.14 \
    --compatible-architectures x86_64 \
    --region "${REGION}" \
    --query "LayerVersionArn" \
    --output text)

echo ""
echo "=============================="
echo "Layer ビルド完了！"
echo "=============================="
echo "Layer ARN: ${LAYER_ARN}"
echo ""
echo "次のステップ:"
echo "  bash src/deploy.sh でデプロイしてください"
