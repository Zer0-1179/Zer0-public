#!/bin/bash
# deploy.sh - X AI Bot deploy script (no S3)
# Step 1: aws cloudformation deploy  -> infrastructure + Lambda definition (placeholder code)
# Step 2: aws lambda update-function-code --zip-file -> upload actual code directly (no S3)
# Prerequisites:
#   1. aws configure completed
#   2. SSM parameters set (run setup_ssm.sh first)

set -e

REGION="ap-northeast-1"
STACK_NAME="x-ai-bot"
FUNCTION_NAME="XAiBot"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-jp.anthropic.claude-haiku-4-5-20251001-v1:0}"
SSM_PREFIX="${SSM_PREFIX:-/ai_bot}"
ZIP_PATH="/tmp/xaibot_function.zip"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=========================================="
echo "  X AI Bot Deploy (no S3)"
echo "  Account: ${ACCOUNT_ID}"
echo "  Region:  ${REGION}"
echo "  Stack:   ${STACK_NAME}"
echo "=========================================="

cd "$(dirname "$0")"

# Step 1: Deploy infrastructure via CloudFormation (no S3 required)
echo "[1/3] Deploying infrastructure (CloudFormation)..."
aws cloudformation deploy \
    --template-file template.yaml \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        "BedrockModelId=${BEDROCK_MODEL_ID}" \
        "SsmPrefix=${SSM_PREFIX}"

# Step 2: Package Lambda code into a local zip
echo "[2/3] Packaging Lambda code..."
rm -f "${ZIP_PATH}"
python3 -c "
import zipfile, os
with zipfile.ZipFile('${ZIP_PATH}', 'w', zipfile.ZIP_DEFLATED) as z:
    z.write('lambda_function.py')
print('  Package: ${ZIP_PATH} (' + str(round(os.path.getsize('${ZIP_PATH}') / 1024, 1)) + ' KB)')
"

# Step 3: Upload code directly to Lambda (no S3)
echo "[3/3] Updating Lambda function code (direct upload)..."
aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ZIP_PATH}" \
    --region "${REGION}" \
    --query "[FunctionName, CodeSize, LastModified]" \
    --output table

# Show stack outputs
echo ""
echo "Stack outputs:"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs" \
    --output table

echo ""
echo "=========================================="
echo "  Deploy complete! (S3 not used)"
echo ""
echo "  Test commands:"
echo "  # AI Tips (7:00 post)"
echo "  aws lambda invoke --function-name XAiBot --region ${REGION} \\"
echo "    --payload '{\"post_type\": \"tips\"}' --cli-binary-format raw-in-base64-out response.json"
echo ""
echo "  # Gadget intro (12:00 post)"
echo "  aws lambda invoke --function-name XAiBot --region ${REGION} \\"
echo "    --payload '{\"post_type\": \"gadget\"}' --cli-binary-format raw-in-base64-out response.json"
echo ""
echo "  # AI news (21:00 post)"
echo "  aws lambda invoke --function-name XAiBot --region ${REGION} \\"
echo "    --payload '{\"post_type\": \"news\"}' --cli-binary-format raw-in-base64-out response.json"
echo ""
echo "  Logs:"
echo "  aws logs tail /aws/lambda/XAiBot --since 5m --region ${REGION}"
echo "=========================================="
