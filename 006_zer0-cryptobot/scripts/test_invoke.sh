#!/bin/bash
# CryptoBot Executor テスト実行スクリプト
#
# 使い方:
#   ./test_invoke.sh              # Step1: 空シグナルテスト（Phase A のみ）
#   ./test_invoke.sh signal       # Step2: SOL ロング シグナル注入テスト（約定しない値で）
#   ./test_invoke.sh short_signal # SOL ショート シグナル注入テスト（約定しない値で）
#   ./test_invoke.sh state        # SSM state の確認
#   ./test_invoke.sh clear        # SSM state のクリア
#
# フルフローテスト（全フェーズ順番に実行）:
#   ./test_invoke.sh fulltest        # Phase B: SOLロング 500円で即時約定注文
#   ./test_invoke.sh short_fulltest  # Phase B: SOLショート 500円で即時約定注文
#   ./test_invoke.sh phase_a         # Phase A: 既存ポジション管理を手動トリガー
#                                    # （fulltest後: TP1/SL発注確認 → trailing確認 → close確認）
#
# 特殊テスト:
#   ./test_invoke.sh cancel_test       # 24時間未約定キャンセルテスト
#                                      # 事前に signal か short_signal で buy_pending を作成すること
#   ./test_invoke.sh phase_a_force_sl  # SL強制約定テスト（active → SL経路クローズ）
#   ./test_invoke.sh phase_a_force_tp1 # TP1強制約定テスト（active → trailing移行）
#   ./test_invoke.sh trail_inject      # トレーリングSL更新テスト（価格注入）
#                                      # 事前に trailing ポジションが必要
#
# ※ phase_a_force_sl / phase_a_force_tp1 / cancel_orders / market_close は
#    Lambda に ENABLE_FORCE_TEST=1 が必要:
#      ENABLE_FORCE_TEST=1 bash scripts/deploy.sh
#    テスト終了後は必ず通常デプロイに戻す:
#      bash scripts/deploy.sh

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
    echo "⚠️  警告: SSM stateをクリアしても bitbank 上の注文・ポジションは残ります。"
    echo "    クリア前に bitbank アプリで未決済注文・建玉がないか必ず確認してください。"
    echo ""
    aws ssm put-parameter \
        --name "${SSM_STATE}" \
        --value '{"positions":{}}' \
        --type String \
        --overwrite \
        --region "${REGION}"
    echo "クリア完了: {\"positions\":{}}"
    ;;

  fulltest)
    echo "=== フルフローテスト Step1: SOL ロング 500円 即時約定 ==="
    SOL_PRICE=$(curl -sf "https://public.bitbank.cc/sol_jpy/ticker" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['last'])")
    ATR=$(python3 -c "print(round(float('${SOL_PRICE}') * 0.02, 0))")
    echo "SOL現在価格: ${SOL_PRICE}円  ATR: ${ATR}円"
    echo "投資額: 500円（テスト固定）/ 即時約定モード（現在価格+0.5%で発注）"
    echo ""

    PAYLOAD=$(python3 -c "
import json
payload = {
    'test_invest_jpy': 500,
    'test_entry_above': True,
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
    echo ""
    echo ">>> 次のステップ:"
    echo "    1. SSM state確認: ./test_invoke.sh state"
    echo "    2. 約定後: ./test_invoke.sh phase_a  → TP1+SL発注確認"
    echo "    3. TP1かSL約定後: ./test_invoke.sh phase_a  → close確認"
    ;;

  phase_a)
    echo "=== Phase A 手動トリガー（既存ポジション管理）==="
    echo "現在のSSM state:"
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
    echo ""
    echo "最新ログ確認（最大2分前まで）:"
    aws logs tail "${LOG_GROUP}" \
        --region "${REGION}" \
        --since 2m
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

  short_fulltest)
    echo "=== フルフローテスト (SHORT) Step1: SOL ショート 500円 即時約定 ==="
    SOL_PRICE=$(curl -sf "https://public.bitbank.cc/sol_jpy/ticker" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['last'])")
    ATR=$(python3 -c "print(round(float('${SOL_PRICE}') * 0.02, 0))")
    echo "SOL現在価格: ${SOL_PRICE}円  ATR: ${ATR}円"
    echo "投資額: 500円（テスト固定）/ 即時約定モード（現在価格-0.5%で発注）"
    echo ""

    PAYLOAD=$(python3 -c "
import json
payload = {
    'test_invest_jpy': 500,
    'test_entry_above': True,
    'signals': [{
        'pair': 'sol_jpy',
        'side': 'short',
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
    echo ""
    echo ">>> 次のステップ:"
    echo "    1. SSM state確認: ./test_invoke.sh state"
    echo "    2. 約定後: ./test_invoke.sh phase_a → TP1+SL発注確認"
    echo "       TP1: エントリー価格 - ATR×2（下方・ショート利確）"
    echo "       SL : エントリー価格 + ATR×1.5（上方・ショート損切り、stop_limit）"
    ;;

  short_signal)
    echo "=== SOL ショート シグナル注入テスト（約定なし・cancel_test 用）==="
    SOL_PRICE=$(curl -sf "https://public.bitbank.cc/sol_jpy/ticker" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['last'])")
    ATR=$(python3 -c "print(round(float('${SOL_PRICE}') * 0.02, 0))")
    echo "SOL現在価格: ${SOL_PRICE}円  ATR: ${ATR}円"
    echo "指値: 現在価格 × 1.01（1%上 = 絶対に約定しない）"

    PAYLOAD=$(python3 -c "
import json
payload = {
    'signals': [{
        'pair': 'sol_jpy',
        'side': 'short',
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
    echo ""
    echo ">>> 次のステップ: ./test_invoke.sh cancel_test"
    ;;

  cancel_test)
    echo "=== 24時間未約定キャンセルテスト ==="
    echo ""

    RAW_STATE=$(aws ssm get-parameter \
        --name "${SSM_STATE}" \
        --region "${REGION}" \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo '{"positions":{}}')

    echo "現在のstate:"
    echo "${RAW_STATE}" | python3 -m json.tool

    PENDING_COUNT=$(echo "${RAW_STATE}" | python3 -c "
import sys, json
state = json.load(sys.stdin)
count = sum(1 for p in state['positions'].values() if p.get('status') == 'buy_pending')
print(count)
")

    if [ "${PENDING_COUNT}" -eq 0 ]; then
        echo ""
        echo "ERROR: buy_pending のポジションがありません。"
        echo "先に ./test_invoke.sh signal か ./test_invoke.sh short_signal を実行してください。"
        exit 1
    fi

    echo ""
    echo "buy_pending ポジション ${PENDING_COUNT} 件の buy_timestamp を 86401 秒前に設定します..."
    MODIFIED_STATE=$(echo "${RAW_STATE}" | python3 -c "
import sys, json, time
state = json.load(sys.stdin)
for pair, pos in state['positions'].items():
    if pos.get('status') == 'buy_pending':
        old_ts = pos.get('buy_timestamp', 0)
        pos['buy_timestamp'] = time.time() - 86401
        print(f'  修正: {pair}  buy_timestamp {old_ts:.0f} -> {pos[\"buy_timestamp\"]:.0f}', file=sys.stderr)
print(json.dumps(state))
")
    echo ""

    aws ssm put-parameter \
        --name "${SSM_STATE}" \
        --value "${MODIFIED_STATE}" \
        --type String \
        --overwrite \
        --region "${REGION}"
    echo "SSM 更新完了（タイムスタンプ改ざん済み）"
    echo ""

    echo "Phase A 実行（24時間経過を検知してキャンセルするはず）..."
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
    echo ""
    echo "最新ログ:"
    aws logs tail "${LOG_GROUP}" --region "${REGION}" --since 2m
    echo ""
    echo ">>> キャンセル後のstate確認: ./test_invoke.sh state"
    ;;

  phase_a_force_sl)
    echo "=== [TEST] SL 強制約定テスト（active → SL経路クローズ）==="
    echo "注意: SL約定を強制シミュレート。TP1注文キャンセル + 残30%成行クローズが走ります。"
    echo ""
    echo "現在のSSM state:"
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
        --payload '{"test_force_sl_fill": true, "signals":[]}' \
        --cli-binary-format raw-in-base64-out \
        "${OUTPUT_FILE}"

    echo ""
    echo "Lambda レスポンス:"
    cat "${OUTPUT_FILE}" | python3 -m json.tool
    echo ""
    echo "最新ログ:"
    aws logs tail "${LOG_GROUP}" --region "${REGION}" --since 2m
    ;;

  phase_a_force_tp1)
    echo "=== [TEST] TP1 強制約定テスト（active → trailing移行）==="
    echo "注意: TP1約定を強制シミュレート。SL注文キャンセル + trail_sl発注 + trailing状態に移行します。"
    echo ""
    echo "現在のSSM state:"
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
        --payload '{"test_force_tp1_fill": true, "signals":[]}' \
        --cli-binary-format raw-in-base64-out \
        "${OUTPUT_FILE}"

    echo ""
    echo "Lambda レスポンス:"
    cat "${OUTPUT_FILE}" | python3 -m json.tool
    echo ""
    echo "最新ログ:"
    aws logs tail "${LOG_GROUP}" --region "${REGION}" --since 2m
    ;;

  trail_inject)
    echo "=== トレーリングSL更新テスト（有利方向へ価格注入）==="
    echo ""

    RAW_STATE=$(aws ssm get-parameter \
        --name "${SSM_STATE}" \
        --region "${REGION}" \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo '{"positions":{}}')

    echo "現在のstate:"
    echo "${RAW_STATE}" | python3 -m json.tool

    TRAIL_COUNT=$(echo "${RAW_STATE}" | python3 -c "
import sys, json
state = json.load(sys.stdin)
count = sum(1 for p in state['positions'].values() if p.get('status') == 'trailing')
print(count)
")

    if [ "${TRAIL_COUNT}" -eq 0 ]; then
        echo ""
        echo "ERROR: trailing のポジションがありません。"
        echo "fulltest → phase_a でエントリー → TP1約定後に trailing 状態になります。"
        exit 1
    fi

    echo ""
    echo "trailing ポジション ${TRAIL_COUNT} 件に有利価格を注入します..."
    MODIFIED_STATE=$(echo "${RAW_STATE}" | python3 -c "
import sys, json, urllib.request
state = json.load(sys.stdin)
for pair, pos in state['positions'].items():
    if pos.get('status') != 'trailing':
        continue
    url = f'https://public.bitbank.cc/{pair}/ticker'
    with urllib.request.urlopen(url, timeout=5) as r:
        current = float(json.loads(r.read())['data']['last'])
    direction = pos.get('direction', 'long')
    atr = pos.get('atr_jpy', current * 0.02)
    if direction == 'long':
        # highest_price を現在価格より 3% 低く設定 → current > highest が真になる
        pos['highest_price'] = round(current * 0.97, 0)
        # trail_sl_price を entry より 10% 低く設定 → new_trail_val > trail_sl が真になる
        old_sl = pos.get('trail_sl_price', pos.get('entry_price', current))
        pos['trail_sl_price'] = round(pos.get('entry_price', current) * 0.90, 0)
        print(f'  {pair}(long): highest_price → {pos[\"highest_price\"]:.0f}  trail_sl {old_sl:.0f} → {pos[\"trail_sl_price\"]:.0f}  current={current:.0f}', file=sys.stderr)
    else:
        # lowest_price を現在価格より 3% 高く設定 → current < lowest が真になる
        pos['lowest_price'] = round(current * 1.03, 0)
        # trail_sl_price を entry より 10% 高く設定 → new_trail_val < trail_sl が真になる
        old_sl = pos.get('trail_sl_price', pos.get('entry_price', current))
        pos['trail_sl_price'] = round(pos.get('entry_price', current) * 1.10, 0)
        print(f'  {pair}(short): lowest_price → {pos[\"lowest_price\"]:.0f}  trail_sl {old_sl:.0f} → {pos[\"trail_sl_price\"]:.0f}  current={current:.0f}', file=sys.stderr)
print(json.dumps(state))
")
    echo ""

    aws ssm put-parameter \
        --name "${SSM_STATE}" \
        --value "${MODIFIED_STATE}" \
        --type String \
        --overwrite \
        --region "${REGION}"
    echo "SSM 更新完了（価格注入済み）"
    echo ""

    echo "Phase A 実行（trail SL 更新を検知するはず）..."
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
    echo ""
    echo "最新ログ:"
    aws logs tail "${LOG_GROUP}" --region "${REGION}" --since 2m
    echo ""
    echo ">>> state確認: ./test_invoke.sh state"
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
