#!/bin/bash
# Stripe Test Clock E2E用の専用DynamoDBレコードを、識別子の値を出さずに管理する。
# Test Clock由来の購読はcheckout.session.completedを通らないため、支払い失敗を
# 検証する前にcustomer/subscriptionを突合済みの専用レコードとして作成する必要がある。

set +x
set -euo pipefail

readonly REGION="ap-northeast-1"
readonly TABLE_NAME="zer0-nyusatsu-lp-waitlist"
readonly TEST_MARKER="stripe-e2e-test"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

usage() {
  echo "Usage: $0 {create|abort|cleanup}" >&2
}

if [[ "$#" -ne 1 || ( "$1" != "create" && "$1" != "cleanup" && "$1" != "abort" ) ]]; then
  usage
  exit 2
fi

ACTION="$1"

# テストデータ以外の既存購読者を扱えないよう、予約済みexample.comと固定接頭辞だけを許可する。
read -r -p "Test email (stripe-e2e-...@example.com): " TEST_EMAIL
if [[ ! "$TEST_EMAIL" =~ ^stripe-e2e-[a-z0-9-]+@example\.com$ ]]; then
  echo "[error] Test email must use the reserved stripe-e2e-...@example.com form." >&2
  exit 2
fi

# Stripe識別子はコマンド引数、標準出力、作業記録へ流さない。
read -r -s -p "Stripe customer ID: " STRIPE_CUSTOMER_ID
printf '\n'
read -r -s -p "Stripe subscription ID: " STRIPE_SUBSCRIPTION_ID
printf '\n'
if [[ ! "$STRIPE_CUSTOMER_ID" =~ ^cus_[A-Za-z0-9]+$ ]] || [[ ! "$STRIPE_SUBSCRIPTION_ID" =~ ^sub_[A-Za-z0-9]+$ ]]; then
  echo "[error] The supplied Stripe identifiers do not have the expected format." >&2
  exit 2
fi

# 接続先の取り違えと主キー変更を早期に拒否する。アカウントIDやテーブル内容は出力しない。
if [[ -z "$(aws sts get-caller-identity --query Account --output text --no-cli-pager)" ]]; then
  echo "[error] Unable to confirm the AWS caller." >&2
  exit 1
fi
if [[ "$(aws dynamodb describe-table --table-name "$TABLE_NAME" --region "$REGION" \
  --query "Table.KeySchema[?AttributeName=='email'].KeyType | [0]" --output text --no-cli-pager)" != "HASH" ]]; then
  echo "[error] The expected waitlist table or email primary key was not confirmed." >&2
  exit 1
fi
if [[ "$(aws cloudformation describe-stacks --stack-name zer0-nyusatsu-lp-backend --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='WaitlistTableName'].OutputValue | [0]" --output text --no-cli-pager)" != "$TABLE_NAME" ]]; then
  echo "[error] The owning stack does not confirm the expected waitlist table." >&2
  exit 1
fi

KEY_FILE="$WORK_DIR/key.json"
VERIFY_VALUES_FILE="$WORK_DIR/verify-values.json"
CLEANUP_VALUES_FILE="$WORK_DIR/cleanup-values.json"
ABORT_VALUES_FILE="$WORK_DIR/abort-values.json"
ITEM_FILE="$WORK_DIR/item.json"
NOW_EPOCH="$(date +%s)"
printf '{"email":{"S":"%s"}}' "$TEST_EMAIL" > "$KEY_FILE"
printf '{":marker":{"S":"%s"},":customer":{"S":"%s"},":subscription":{"S":"%s"},":now":{"N":"%s"},":pending":{"S":"pending"},":paid":{"S":"paid"},":source":{"S":"stripe-e2e-test"}}' \
  "$TEST_MARKER" "$STRIPE_CUSTOMER_ID" "$STRIPE_SUBSCRIPTION_ID" "$NOW_EPOCH" > "$VERIFY_VALUES_FILE"
printf '{":marker":{"S":"%s"},":customer":{"S":"%s"},":subscription":{"S":"%s"},":pending":{"S":"pending"},":canceled":{"S":"canceled"},":source":{"S":"stripe-e2e-test"}}' \
  "$TEST_MARKER" "$STRIPE_CUSTOMER_ID" "$STRIPE_SUBSCRIPTION_ID" > "$CLEANUP_VALUES_FILE"
printf '{":marker":{"S":"%s"},":customer":{"S":"%s"},":subscription":{"S":"%s"},":pending":{"S":"pending"},":paid":{"S":"paid"},":source":{"S":"stripe-e2e-test"}}' \
  "$TEST_MARKER" "$STRIPE_CUSTOMER_ID" "$STRIPE_SUBSCRIPTION_ID" > "$ABORT_VALUES_FILE"

abort_unprocessed_record() {
  # Test Clockを進める前だけに使う回収経路。Webhookイベントを1件でも処理した行は残す。
  aws dynamodb delete-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --key "file://$KEY_FILE" \
    --condition-expression "e2e_test_marker = :marker AND stripe_customer_id = :customer AND stripe_subscription_id = :subscription AND #status = :pending AND payment_status = :paid AND #source = :source AND attribute_not_exists(stripe_last_event_id)" \
    --expression-attribute-names '{"#status":"status","#source":"source"}' \
    --expression-attribute-values "file://$ABORT_VALUES_FILE" \
    --return-values NONE \
    --return-consumed-capacity NONE \
    --no-cli-pager > /dev/null
}

if [[ "$ACTION" == "abort" ]]; then
  abort_unprocessed_record
  echo "[ok] Unprocessed dedicated Stripe E2E test record was deleted without printing identifiers."
  exit 0
fi

if [[ "$ACTION" == "create" ]]; then
  # pendingのままにして、試験中にcollectorがテスト行を通知対象として扱わないようにする。
  printf '{"email":{"S":"%s"},"status":{"S":"pending"},"payment_status":{"S":"paid"},"source":{"S":"stripe-e2e-test"},"e2e_test_marker":{"S":"%s"},"stripe_customer_id":{"S":"%s"},"stripe_subscription_id":{"S":"%s"},"registered_at":{"N":"%s"}}' \
    "$TEST_EMAIL" "$TEST_MARKER" "$STRIPE_CUSTOMER_ID" "$STRIPE_SUBSCRIPTION_ID" "$NOW_EPOCH" > "$ITEM_FILE"

  aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --item "file://$ITEM_FILE" \
    --condition-expression "attribute_not_exists(email)" \
    --return-consumed-capacity NONE \
    --no-cli-pager > /dev/null

  # 作成直後に、同じcustomer/subscriptionの行だけを条件付き更新する。
  # 失敗時はレコードを残して停止し、誤った購読に対する試験を防ぐ。
  if ! aws dynamodb update-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --key "file://$KEY_FILE" \
    --update-expression "SET e2e_last_verified_at = :now" \
    --condition-expression "e2e_test_marker = :marker AND stripe_customer_id = :customer AND stripe_subscription_id = :subscription AND #status = :pending AND #payment_status = :paid AND #source = :source AND attribute_not_exists(stripe_last_event_id)" \
    --expression-attribute-names '{"#status":"status","#payment_status":"payment_status","#source":"source"}' \
    --expression-attribute-values "file://$VERIFY_VALUES_FILE" \
    --return-values NONE \
    --return-consumed-capacity NONE \
    --no-cli-pager > /dev/null; then
    echo "[error] Pair verification failed; attempting safe pre-event rollback." >&2
    if abort_unprocessed_record; then
      echo "[ok] The unverified test record was rolled back." >&2
    else
      echo "[error] The record was preserved because the safe rollback condition did not match." >&2
    fi
    exit 1
  fi

  echo "[ok] Dedicated Stripe E2E test record was created and pair-verified without printing identifiers."
  exit 0
fi

# canceledまで確認できた非配信の専用テスト行だけを削除する。条件不一致時は何も削除しない。
aws dynamodb delete-item \
  --table-name "$TABLE_NAME" \
  --region "$REGION" \
  --key "file://$KEY_FILE" \
  --condition-expression "e2e_test_marker = :marker AND stripe_customer_id = :customer AND stripe_subscription_id = :subscription AND #status = :pending AND payment_status = :canceled AND #source = :source" \
  --expression-attribute-names '{"#status":"status","#source":"source"}' \
  --expression-attribute-values "file://$CLEANUP_VALUES_FILE" \
  --return-values NONE \
  --return-consumed-capacity NONE \
  --no-cli-pager > /dev/null
echo "[ok] Dedicated canceled Stripe E2E test record was deleted without printing identifiers."
