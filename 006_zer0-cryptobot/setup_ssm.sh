#!/bin/bash
set -euo pipefail

# ============================================================
# Zer0-CryptoBot SSM パラメータ登録スクリプト
# bitbank API キーを SSM Parameter Store に SecureString で保存する
# ============================================================

REGION="ap-northeast-1"

# Zer0-CryptoBot-APIKEY.txt からキーを読み込む（存在する場合）
APIKEY_FILE="$(dirname "$0")/Zer0-CryptoBot-APIKEY.txt"

if [ -f "$APIKEY_FILE" ]; then
  echo "Zer0-CryptoBot-APIKEY.txt からキーを読み込みます..."
  # ファイルフォーマット: 2行目がAPIキー、5行目がシークレット
  API_KEY=$(sed -n '2p' "$APIKEY_FILE" | tr -d '[:space:]')
  API_SECRET=$(sed -n '5p' "$APIKEY_FILE" | tr -d '[:space:]')
  echo "  APIキー: ${API_KEY:0:8}..."
  echo "  シークレット: ${API_SECRET:0:8}..."
else
  # ファイルがない場合は手動入力
  echo "bitbank APIキーを入力してください:"
  read -rp "  API Key: " API_KEY
  read -rsp "  API Secret: " API_SECRET
  echo ""
fi

echo ""
echo "[1/3] API Key を SSM に登録中..."
aws ssm put-parameter \
  --name "/Zer0/CryptoBot/bitbank/api_key" \
  --value "${API_KEY}" \
  --type SecureString \
  --overwrite \
  --region "${REGION}" > /dev/null
echo "  OK: /Zer0/CryptoBot/bitbank/api_key"

echo ""
echo "[2/3] API Secret を SSM に登録中..."
aws ssm put-parameter \
  --name "/Zer0/CryptoBot/bitbank/api_secret" \
  --value "${API_SECRET}" \
  --type SecureString \
  --overwrite \
  --region "${REGION}" > /dev/null
echo "  OK: /Zer0/CryptoBot/bitbank/api_secret"

echo ""
echo "[3/3] 初期 state を SSM に登録中..."
aws ssm put-parameter \
  --name "/Zer0/CryptoBot/state" \
  --value '{"positions":{}}' \
  --type String \
  --overwrite \
  --region "${REGION}" > /dev/null
echo "  OK: /Zer0/CryptoBot/state"

echo ""
echo "=============================="
echo "SSM 登録完了"
echo "=============================="
echo ""
echo "登録されたパラメータ:"
aws ssm get-parameters \
  --names \
    "/Zer0/CryptoBot/bitbank/api_key" \
    "/Zer0/CryptoBot/bitbank/api_secret" \
    "/Zer0/CryptoBot/state" \
  --region "${REGION}" \
  --query "Parameters[*].{Name:Name,Type:Type}" \
  --output table

echo ""
echo "注意: APIKEY.txt は SSM 登録後に削除することを推奨します"
echo "  rm ${APIKEY_FILE}"
