#!/bin/bash
# setup_ssm.sh - X API認証情報をSSMパラメータストアに投入
# 使用方法: bash setup_ssm.sh
# 実行前にX DeveloperポータルでAPIキーを取得しておくこと

set -e

REGION="ap-northeast-1"
SSM_PREFIX="/ai_bot"

echo "=========================================="
echo "  X AI Bot - SSMパラメータ設定"
echo "  プレフィックス: ${SSM_PREFIX}"
echo "  ※ 入力値はターミナルに表示されません"
echo "=========================================="

read -s -p "API Key (twitter_api_key): " API_KEY; echo
read -s -p "API Key Secret (twitter_api_secret): " API_SECRET; echo
read -s -p "Access Token (twitter_access_token): " ACCESS_TOKEN; echo
read -s -p "Access Token Secret (twitter_access_token_secret): " ACCESS_TOKEN_SECRET; echo

echo ""
echo "SSMへ書き込み中..."

aws ssm put-parameter \
    --region "${REGION}" \
    --name "${SSM_PREFIX}/twitter_api_key" \
    --value "${API_KEY}" \
    --type SecureString \
    --overwrite

aws ssm put-parameter \
    --region "${REGION}" \
    --name "${SSM_PREFIX}/twitter_api_secret" \
    --value "${API_SECRET}" \
    --type SecureString \
    --overwrite

aws ssm put-parameter \
    --region "${REGION}" \
    --name "${SSM_PREFIX}/twitter_access_token" \
    --value "${ACCESS_TOKEN}" \
    --type SecureString \
    --overwrite

aws ssm put-parameter \
    --region "${REGION}" \
    --name "${SSM_PREFIX}/twitter_access_token_secret" \
    --value "${ACCESS_TOKEN_SECRET}" \
    --type SecureString \
    --overwrite

echo ""
echo "SSMパラメータ一覧（値は隠蔽）:"
aws ssm describe-parameters \
    --region "${REGION}" \
    --filters "Key=Path,Values=${SSM_PREFIX}" \
    --query "Parameters[*].[Name,Type,LastModifiedDate]" \
    --output table

echo ""
echo "設定完了! 次のステップ: bash deploy.sh"
