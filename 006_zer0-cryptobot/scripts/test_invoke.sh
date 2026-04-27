#!/bin/bash
# CryptoBot Executor テスト実行スクリプト
#
# 使い方:
#   ./test_invoke.sh            # Step1: 空シグナルテスト（Phase A のみ）
#   ./test_invoke.sh signal     # Step2: SOL ロング シグナル注入テスト
#   ./test_invoke.sh state      # SSM state の確認
#   ./test_invoke.sh clear      # SSM state のクリア

set -euo pipefail

EXECUTOR="Zer0-CryptoBot-Executor"
REGION="ap-northeast-1"
LOG_GROUP="/aws/lambda/${EXECUTOR}"
SSM_STATE="/Zer0/CryptoBot/state"
OUTPUT_FILE="/tmp/cryptobot_test_result.json"

MODE="${1:-empty}"

# ──────────────────────────────────────────────
show_logs() {
    echo ""
    echo ">>> CloudWatch ログ（Ctrl+C で停止）"
    aws logs tail "${LOG_GROUP}" \
        --region "${REGION}" \
        --since 2m \
        --follow
}

# ──────────────────────────────────────────────
case "${MODE}" in

  state)
    echo "=== SSM state 確認 ==="
    VALUE=$(aws ssm get-parameter \
        --name "${SSM_STATE}" \
        --region "${REGION}" \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo '{"positions":{}}')
    echo "${VALUE}" | python3 -m json.tool
    ;;

  clear)
    echo "=== SSM state クリア ==="
    aws ssm put-parameter \
        --name "${SSM_STATE}" \
        --value '{"positions":{}}' \
        --type String \
        --overwrite \
        --region "${REGION}"
    echo "クリア完了: {\"positions\":{}}"
    ;;

  signal)
    echo "=== Step2: SOL ロング シグナル注入テスト ==="
    # 現在価格を取得して ATR を設定（ATR = 価格 × 2% 程度）
    SOL_PRICE=$(curl -sf "https://public.bitbank.cc/sol_jpy/ticker" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['last'])")
    ATR=$(python3 -c "print(round(float('${SOL_PRICE}') * 0.02, 0))")

    echo "SOL現在価格: ${SOL_PRICE}円  ATR: ${ATR}円"

    PAYLOAD=$(python3 -c "
import json
payload = {
    'signals': [{
        'pair': 'sol_jpy',
        'side': 'long',
        'binance_price': float('${SOL_PRICE}'),
        'atr': float('${ATR}')
    }]
}
print(json.dumps(payload))
")
    echo "Payload: ${PAYLOAD}"
    echo ""

    aws lambda invoke \
        --function-name "${EXECUTOR}" \
        --region "${REGION}" \
        --invocation-type RequestResponse \
        --payload "${PAYLOAD}" \
        --cli-binary-format raw-in-base64-out \
        "${OUTPUT_FILE}"

    echo ""
    echo "Lambda レスポンス:"
    cat "${OUTPUT_FILE}" | python3 -m json.tool
    show_logs
    ;;

  *)
    echo "=== Step1: 空シグナルテスト（Phase A / 証拠金チェックのみ）==="
    echo "SSM state:"
    aws ssm get-parameter \
        --name "${SSM_STATE}" \
        --region "${REGION}" \
        --query "Parameter.Value" \
        --output text 2>/dev/null | python3 -m json.tool || echo '{"positions":{}}'
    echo ""

    aws lambda invoke \
        --function-name "${EXECUTOR}" \
        --region "${REGION}" \
        --invocation-type RequestResponse \
        --payload '{"signals":[]}' \
        --cli-binary-format raw-in-base64-out \
        "${OUTPUT_FILE}"

    echo ""
    echo "Lambda レスポンス:"
    cat "${OUTPUT_FILE}" | python3 -m json.tool
    show_logs
    ;;

esac
