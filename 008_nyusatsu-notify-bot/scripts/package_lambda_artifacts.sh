#!/bin/bash
# package_lambda_artifacts.sh - CFnが参照するLambda ZIPをVersioning有効S3へ配置する。
#
# このスクリプトはZIPをアップロードするだけで、CloudFormationの変更セット実行や
# Lambdaの直接更新はしない。出力したバージョンIDを、独立レビュー済みの各
# CloudFormation変更セットのパラメータに渡す。

set -euo pipefail

SINGLE_TARGET=""
if [[ "$#" -eq 1 && "$1" == "--stripe-webhook-only" ]]; then
  SINGLE_TARGET="stripe_webhook"
elif [[ "$#" -eq 1 && "$1" == "--collector-only" ]]; then
  SINGLE_TARGET="collector"
elif [[ "$#" -eq 1 && "$1" == "--bounce-handler-only" ]]; then
  SINGLE_TARGET="bounce_handler"
elif [[ "$#" -ne 0 ]]; then
  echo "Usage: $0 [--stripe-webhook-only|--collector-only|--bounce-handler-only]" >&2
  exit 2
fi

REGION="ap-northeast-1"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
ARTIFACT_STACK_NAME="zer0-nyusatsu-lambda-artifacts"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ARTIFACT_BUCKET="$(aws cloudformation describe-stacks \
  --stack-name "${ARTIFACT_STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" \
  --output text)"
EXPECTED_BUCKET="zer0-nyusatsu-lambda-artifacts-${ACCOUNT_ID}-${REGION}"

if [[ "${ARTIFACT_BUCKET}" != "${EXPECTED_BUCKET}" ]]; then
  echo "[error] artifact bucket output does not match the expected account and region" >&2
  exit 1
fi
if [[ "$(aws s3api get-bucket-versioning --bucket "${ARTIFACT_BUCKET}" --expected-bucket-owner "${ACCOUNT_ID}" --query 'Status' --output text)" != "Enabled" ]]; then
  echo "[error] artifact bucket versioning is not enabled" >&2
  exit 1
fi
aws s3api get-bucket-encryption --bucket "${ARTIFACT_BUCKET}" --expected-bucket-owner "${ACCOUNT_ID}" > /dev/null
if ! aws s3api get-public-access-block \
  --bucket "${ARTIFACT_BUCKET}" \
  --expected-bucket-owner "${ACCOUNT_ID}" \
  --output json | jq -e \
    '[.PublicAccessBlockConfiguration.BlockPublicAcls, .PublicAccessBlockConfiguration.BlockPublicPolicy, .PublicAccessBlockConfiguration.IgnorePublicAcls, .PublicAccessBlockConfiguration.RestrictPublicBuckets] == [true, true, true, true]' \
    > /dev/null; then
  echo "[error] artifact bucket public access block is incomplete" >&2
  exit 1
fi

upload_one() {
  local source_dir="$1"
  local object_name="$2"
  local zip_path="${WORK_DIR}/${object_name}.zip"
  local version_id

  (
    cd "${PROJECT_DIR}/lambda/${source_dir}"
    zip -q "${zip_path}" lambda_function.py
  )
  version_id="$(aws s3api put-object \
    --bucket "${ARTIFACT_BUCKET}" \
    --expected-bucket-owner "${ACCOUNT_ID}" \
    --key "lambda/${object_name}.zip" \
    --body "${zip_path}" \
    --region "${REGION}" \
    --server-side-encryption AES256 \
    --query 'VersionId' \
    --output text)"
  if [[ -z "${version_id}" || "${version_id}" == "None" ]]; then
    echo "[error] Versioning is not enabled for s3://${ARTIFACT_BUCKET}" >&2
    return 1
  fi
  printf '%s' "${version_id}"
}

if [[ -n "${SINGLE_TARGET}" ]]; then
  # 単一関数の修正では、無関係なartifact versionを増やさない。
  if [[ "${SINGLE_TARGET}" == "stripe_webhook" ]]; then
    DEPLOYMENT_TARGET="zer0-nyusatsu-stripe-webhook"
    DISPLAY_NAME="Stripe webhook"
  elif [[ "${SINGLE_TARGET}" == "collector" ]]; then
    DEPLOYMENT_TARGET="zer0-nyusatsu-collector"
    DISPLAY_NAME="collector"
  else
    DEPLOYMENT_TARGET="zer0-nyusatsu-bounce-handler"
    DISPLAY_NAME="bounce handler"
  fi

  echo "[1/1] Packaging and uploading the ${DISPLAY_NAME} artifact..."
  SINGLE_VERSION="$(upload_one "${SINGLE_TARGET}" "${SINGLE_TARGET}")"
  cat <<EOF
[2/2] Upload complete. Use only this version in an independently reviewed Change Set:
  cfn-lambda-code-deployment.yaml:
    DeploymentTarget=${DEPLOYMENT_TARGET}
    ArtifactVersion=${SINGLE_VERSION}
EOF
  exit 0
fi

echo "[1/5] Packaging and uploading Lambda artifacts..."
BOUNCE_HANDLER_VERSION="$(upload_one bounce_handler bounce_handler)"
COLLECTOR_VERSION="$(upload_one collector collector)"
WAITLIST_VERSION="$(upload_one lp_waitlist lp_waitlist)"
STRIPE_WEBHOOK_VERSION="$(upload_one stripe_webhook stripe_webhook)"
MAIL_FORWARDER_VERSION="$(upload_one mail_forwarder mail_forwarder)"

cat <<EOF
[2/5] Upload complete. Retrieve LambdaArtifactBucket from the artifact stack without printing it,
then use only these versions in independently reviewed Change Sets:
  zer0-nyusatsu-notify-bot:
    BounceHandlerCodeVersion=${BOUNCE_HANDLER_VERSION}
    CollectorCodeVersion=${COLLECTOR_VERSION}
  zer0-nyusatsu-lp-backend:
    WaitlistCodeVersion=${WAITLIST_VERSION}
    StripeWebhookCodeVersion=${STRIPE_WEBHOOK_VERSION}
  zer0-nyusatsu-mail-relay:
    MailForwarderCodeVersion=${MAIL_FORWARDER_VERSION}
EOF
