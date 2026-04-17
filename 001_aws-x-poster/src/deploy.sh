#!/bin/bash
# deploy.sh - ビルド → SSMにシークレット登録 → Lambda デプロイ
#
# 使い方:
#   初回セットアップ:  ./deploy.sh
#   コードのみ更新:    ./deploy.sh --code-only
#   DRY RUNテスト:     ./deploy.sh --test

set -e

FUNCTION_NAME="aws-x-poster"
STACK_NAME="aws-x-poster-stack"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
MODE="${1:-}"

echo "=== AWS X Auto Poster デプロイ ==="

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DRY RUN テスト
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if [ "$MODE" = "--test" ]; then
    echo "[Test] DRY_RUN=true で Lambda を実行..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --environment "Variables={SSM_PREFIX=/xposter,DRY_RUN=true}" \
        --region "$REGION" > /dev/null
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION" \
        --log-type Tail \
        --query "LogResult" \
        --output text \
        /tmp/xposter_test_out.json | base64 -d

    echo ""
    echo "[戻り値]"
    cat /tmp/xposter_test_out.json

    echo ""
    echo "[Test] DRY_RUN=false に戻します..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --environment "Variables={SSM_PREFIX=/xposter,DRY_RUN=false}" \
        --region "$REGION" > /dev/null
    exit 0
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# コードのみ更新（--code-only）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if [ "$MODE" = "--code-only" ]; then
    echo "[1/2] Lambda ZIPを作成..."
    rm -rf .lambda_build && mkdir .lambda_build
    pip install requests requests-oauthlib -t .lambda_build/ -q
    cp lambda_function.py .lambda_build/
    cd .lambda_build && zip -r ../lambda.zip . -q && cd ..
    echo "  ✓ lambda.zip 作成完了 ($(du -sh lambda.zip | cut -f1))"

    echo "[2/2] Lambda 関数コードを更新..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://lambda.zip \
        --region "$REGION" \
        --query "[FunctionName,CodeSize,LastModified]" \
        --output table

    rm -rf .lambda_build lambda.zip
    echo ""
    echo "=== コード更新完了 ==="
    echo "DRY RUNテスト: ./deploy.sh --test"
    exit 0
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 初回フルデプロイ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── 1. SSM Parameter Store にシークレットを登録 ──────
echo "[1/4] SSM にシークレットを登録..."

read -p "X API Key:         " X_API_KEY
read -p "X API Secret:      " X_API_SECRET
read -p "X Access Token:    " X_ACCESS_TOKEN
read -p "X Access Secret:   " X_ACCESS_SECRET

for NAME_VAL in \
    "x-api-key:$X_API_KEY" \
    "x-api-secret:$X_API_SECRET" \
    "x-access-token:$X_ACCESS_TOKEN" \
    "x-access-secret:$X_ACCESS_SECRET"
do
    PARAM_NAME="${NAME_VAL%%:*}"
    PARAM_VAL="${NAME_VAL#*:}"
    aws ssm put-parameter \
        --name "/xposter/${PARAM_NAME}" \
        --value "${PARAM_VAL}" \
        --type SecureString \
        --overwrite \
        --region "$REGION"
    echo "  ✓ /xposter/${PARAM_NAME}"
done

# ── 2. 依存パッケージをLambda用にパッケージング ────────
echo "[2/4] Lambda ZIPを作成..."
rm -rf .lambda_build && mkdir .lambda_build
pip install requests requests-oauthlib -t .lambda_build/ -q
cp lambda_function.py .lambda_build/
cd .lambda_build && zip -r ../lambda.zip . -q && cd ..
echo "  ✓ lambda.zip 作成完了 ($(du -sh lambda.zip | cut -f1))"

# ── 3. CloudFormation スタックをデプロイ ──────────────
echo "[3/4] CloudFormation スタックをデプロイ..."
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name "$STACK_NAME" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION"
echo "  ✓ スタック デプロイ完了"

# ── 4. Lambda コードを更新 ────────────────────────────
echo "[4/4] Lambda 関数コードを更新..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://lambda.zip \
    --region "$REGION" \
    --query "[FunctionName,CodeSize,LastModified]" \
    --output table

rm -rf .lambda_build lambda.zip

echo ""
echo "=== デプロイ完了 ==="
echo "DRY RUNテスト: ./deploy.sh --test"
