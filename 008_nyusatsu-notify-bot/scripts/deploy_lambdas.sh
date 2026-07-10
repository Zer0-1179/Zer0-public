#!/bin/bash
# deploy_lambdas.sh - 4つのバックエンドLambda(collector/lp_waitlist/bounce_handler/
# mail_forwarder)の実コードを一括でaws lambda update-function-codeで反映する。
#
# 背景: これらのLambdaはCFnテンプレート上ZipFileのプレースホルダーとしてデプロイされ、
# 実コードは別途update-function-codeで反映する運用(プロジェクト共通ルール、SAM不使用)。
# v0.9で「mail_forwarderへのこの反映コマンドの実行を忘れる」障害が実際に発生した
# (プレースホルダーのままRuntime.ImportModuleErrorで機能停止)。このスクリプトは
# 4つ全てを1コマンドでまとめて反映することで、一部だけ反映し忘れるリスクを減らす。
#
# 使い方:
#   cd 008_Nyusatsu_Notify_Bot && bash scripts/deploy_lambdas.sh
#   (infra/cfn-nyusatsu-notify-bot.yaml / infra/cfn-lp-backend.yaml / infra/cfn-mail-relay.yaml の
#    aws cloudformation deploy 実行後、必ずこのスクリプトも続けて実行すること)

set -e

REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

deploy_one() {
  local dir_name="$1"
  local function_name="$2"
  local zip_path="${TMP_DIR}/${dir_name}.zip"

  echo "[deploy] ${function_name} <- lambda/${dir_name}/lambda_function.py"
  (cd "${SCRIPT_DIR}/lambda/${dir_name}" && zip -q "${zip_path}" lambda_function.py)
  aws lambda update-function-code \
    --function-name "${function_name}" \
    --zip-file "fileb://${zip_path}" \
    --region "${REGION}" \
    --output text \
    --query "LastUpdateStatus" > /dev/null
}

deploy_one collector zer0-nyusatsu-collector
deploy_one lp_waitlist zer0-nyusatsu-lp-waitlist
deploy_one bounce_handler zer0-nyusatsu-bounce-handler
deploy_one mail_forwarder zer0-nyusatsu-mail-forwarder

echo "[deploy] 4Lambdaすべての反映が完了しました。"
