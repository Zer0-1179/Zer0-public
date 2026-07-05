#!/bin/bash
# CloudWatch Logsに構造化ログ（metric: pageview / template_download / template_zip_download）として
# 記録されているアクセス実績を集計する。追加AWSリソース（CloudFront標準ログ・RUM等）は使わず、
# 既存のLambda実行ログをCloudWatch Logs Insightsでクエリするだけなので追加コストはゼロ。
#
# 使い方: bash scripts/query-analytics.sh [集計対象日数（デフォルト7）]

set -euo pipefail

LOG_GROUP="/aws/lambda/Zer0-portfolio-ssr"
REGION="ap-northeast-1"
DAYS="${1:-7}"
END_TIME=$(date +%s)
START_TIME=$((END_TIME - DAYS * 86400))

run_query() {
  local query="$1"
  local query_id
  query_id=$(aws logs start-query \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --query-string "$query" \
    --query "queryId" --output text)

  # クエリ完了まで待機（CloudWatch Logs Insightsは非同期実行）
  while true; do
    status=$(aws logs get-query-results --query-id "$query_id" --region "$REGION" --query "status" --output text)
    [ "$status" = "Complete" ] && break
    sleep 1
  done
  aws logs get-query-results --query-id "$query_id" --region "$REGION" --output json
}

echo "=== ページビュー数（言語別・直近${DAYS}日） ==="
run_query '
fields @message
| filter @message like /"metric":"pageview"/
| parse @message /"lang":"(?<lang>[^"]+)"/
| stats count() as views by lang
' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for row in data.get('results', []):
    d = {f['field']: f['value'] for f in row}
    print(f\"  {d.get('lang','?'):4s}: {d.get('views','0')}件\")
"

echo ""
echo "=== ページビュー数（パス別 上位20・直近${DAYS}日） ==="
run_query '
fields @message
| filter @message like /"metric":"pageview"/
| parse @message /"path":"(?<path>[^"]+)"/
| stats count() as views by path
| sort views desc
| limit 20
' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for row in data.get('results', []):
    d = {f['field']: f['value'] for f in row}
    print(f\"  {d.get('views','0'):>5s}件  {d.get('path','?')}\")
"

echo ""
echo "=== テンプレート単体DL数（ファイル別・直近${DAYS}日） ==="
run_query '
fields @message
| filter @message like /"metric":"template_download"/
| parse @message /"filename":"(?<filename>[^"]+)"/
| stats count() as downloads by filename
| sort downloads desc
' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for row in data.get('results', []):
    d = {f['field']: f['value'] for f in row}
    print(f\"  {d.get('downloads','0'):>5s}件  {d.get('filename','?')}\")
"

echo ""
echo "=== ZIP一括DL数（対象別・直近${DAYS}日） ==="
run_query '
fields @message
| filter @message like /"metric":"template_zip_download"/
| parse @message /"zipname":"(?<zipname>[^"]+)"/
| stats count() as downloads by zipname
| sort downloads desc
' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for row in data.get('results', []):
    d = {f['field']: f['value'] for f in row}
    print(f\"  {d.get('downloads','0'):>5s}件  {d.get('zipname','?')}\")
"
