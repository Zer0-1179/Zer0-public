# CloudFormation テンプレート集

再利用可能な CloudFormation テンプレートです。  
SAM は使用しません。Lambda のコードデプロイは `aws lambda update-function-code` で直接行います。

---

## テンプレート一覧

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-kms-key.yaml` | カスタマー管理KMSキー | なし |
| `cfn-s3-bucket.yaml` | S3バケット | なし（KMSは任意） |
| `cfn-cloudwatch-logs.yaml` | CloudWatch ロググループ | なし（KMSは任意） |
| `cfn-sqs-queue.yaml` | SQSキュー + DLQ | なし（KMSは任意） |
| `cfn-iam-role-lambda.yaml` | Lambda用 IAMロール | なし |
| `cfn-scheduled-lambda.yaml` | Lambda + EventBridge スケジュール | なし（単独完結） |
| `cfn-vpc.yaml` | VPC + サブネット + ルートテーブル | なし |
| `cfn-igw.yaml` | Internet Gateway | **cfn-vpc.yaml** |
| `cfn-nat-gateway.yaml` | NAT Gateway + EIP | **cfn-vpc.yaml + cfn-igw.yaml** |

---

## VPCスタックのデプロイ順

VPC関連の3テンプレートは依存関係があるため、以下の順番で作成します。

```
1. cfn-vpc.yaml          VPC・サブネット・ルートテーブルを作成
2. cfn-igw.yaml          パブリックサブネットにインターネット接続を追加
3. cfn-nat-gateway.yaml  プライベートサブネットにインターネット接続を追加（任意・約¥5,000/月）
```

`cfn-igw.yaml` と `cfn-nat-gateway.yaml` は `Fn::ImportValue` で VPC スタックの出力を参照するため、**VPC スタック名（`VpcStackName` パラメータ）を正確に指定する必要があります**。

---

## 各テンプレート詳細

---

### cfn-vpc.yaml

VPC・パブリック/プライベートサブネット（各2AZ）・ルートテーブルを作成します。

**デフォルト CIDR 設計**

| 種別 | AZ-a | AZ-c |
|---|---|---|
| VPC | `10.0.0.0/16` | — |
| パブリック | `10.0.1.0/24` | `10.0.2.0/24` |
| プライベート | `10.0.11.0/24` | `10.0.12.0/24` |

**パラメータ**

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `ProjectName` | `my-project` | リソース名プレフィックス（小文字英数字・ハイフンのみ） |
| `Env` | `dev` | 環境（`dev` / `prd`） |
| `VpcCidr` | `10.0.0.0/16` | VPC の CIDR ブロック |
| `PublicSubnetCidrs` | `10.0.1.0/24,10.0.2.0/24` | パブリックサブネット（カンマ区切り） |
| `PrivateSubnetCidrs` | `10.0.11.0/24,10.0.12.0/24` | プライベートサブネット（カンマ区切り） |

**出力（Export）**

- `VpcId` / `VpcCidr`
- `PublicRouteTableId` / `PrivateRouteTableId`
- `PublicSubnet01Id` / `PublicSubnet02Id`
- `PrivateSubnet01Id` / `PrivateSubnet02Id`

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-vpc \
  --template-file cfn-vpc.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

---

### cfn-igw.yaml

Internet Gateway を作成し VPC にアタッチ。パブリックルートテーブルに `0.0.0.0/0 → IGW` のルートを追加します。

**制約**

- `cfn-vpc.yaml` を先にデプロイしていること
- VPC スタックに `PublicRouteTableId` の Export があること
- 1 VPC に IGW は 1 つまで（AWS の制限）

**パラメータ**

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `ProjectName` | `my-project` | リソース名プレフィックス |
| `Env` | `dev` | 環境（`dev` / `prd`） |
| `VpcStackName` | `my-project-dev-vpc` | VPC スタック名（ImportValue の参照先） |

**出力（Export）**

- `InternetGatewayId`

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-igw \
  --template-file cfn-igw.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev \
    VpcStackName=my-project-dev-vpc
```

---

### cfn-nat-gateway.yaml

PublicSubnet01 に NAT Gateway を作成し、プライベートルートテーブルに `0.0.0.0/0 → NAT GW` のルートを追加します。

**制約**

- `cfn-vpc.yaml` と `cfn-igw.yaml` を先にデプロイしていること（NAT GW はパブリックサブネットに置く必要がある）
- VPC スタックに `PublicSubnet01Id` と `PrivateRouteTableId` の Export があること
- **料金**: NAT Gateway は約 $0.045/時間 ＋ 転送量課金。1ヶ月常時稼働で約 **¥5,000/月**
- 高可用性が必要な場合は AZ ごとに 1 台（2台で約 ¥10,000/月）
- 使わないときはスタックを削除してコストを抑えること

**パラメータ**

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `ProjectName` | `my-project` | リソース名プレフィックス |
| `Env` | `dev` | 環境（`dev` / `prd`） |
| `VpcStackName` | `my-project-dev-vpc` | VPC スタック名（ImportValue の参照先） |

**出力（Export）**

- `NatGatewayId`
- `EipAddress`（NAT GW の固定グローバル IP）

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-nat-gateway \
  --template-file cfn-nat-gateway.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev \
    VpcStackName=my-project-dev-vpc
```

**削除**

```bash
aws cloudformation delete-stack --stack-name my-project-dev-nat-gateway
```

---

### cfn-kms-key.yaml

カスタマー管理 KMS キーを作成します。S3・SQS・CloudWatch Logs・SSM 等の暗号化に使用できます。

**制約**

- キーを削除するとき `PendingWindowInDays`（デフォルト 7 日）の待機期間がある
- キーを削除すると暗号化されたデータは永久に復号不可になる

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-kms \
  --template-file cfn-kms-key.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

**出力取得（他スタックで使用する場合）**

```bash
KMS_ARN=$(aws cloudformation describe-stacks \
  --stack-name my-project-dev-kms \
  --query "Stacks[0].Outputs[?OutputKey=='KmsKeyArn'].OutputValue" \
  --output text)
```

---

### cfn-s3-bucket.yaml

バージョニング・暗号化・ライフサイクル設定済みの S3 バケットを作成します。

**環境による差異**

| 設定 | dev | prd |
|---|---|---|
| バージョニング | 無効 | 有効 |
| オブジェクト有効期限 | 90日 | 365日 |
| DeletionPolicy | Delete | **Retain** |

**制約**

- `prd` 環境ではスタック削除後もバケットが残る（手動削除が必要）
- バケット名はグローバル一意。デフォルト: `{ProjectName}-{Env}[-{BucketSuffix}]`

**デプロイ（KMSなし）**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-s3 \
  --template-file cfn-s3-bucket.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

**デプロイ（KMSあり）**

```bash
aws cloudformation deploy \
  --stack-name my-project-prd-s3 \
  --template-file cfn-s3-bucket.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=prd \
    KmsKeyId=$KMS_ARN
```

---

### cfn-cloudwatch-logs.yaml

CloudWatch ロググループを作成します。Lambda 関数名に合わせたロググループ名の指定が可能です。

**環境による差異**

| 設定 | dev | prd |
|---|---|---|
| 保持期間 | 30日 | 90日 |

**制約**

- KMS 暗号化を使う場合、KMS キーポリシーに `logs.<region>.amazonaws.com` への `kms:Encrypt/Decrypt` 権限が必要

**デプロイ（Lambdaログ用）**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-logs \
  --template-file cfn-cloudwatch-logs.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev \
    LogGroupName=/aws/lambda/my-function
```

---

### cfn-sqs-queue.yaml

SQS キュー + デッドレターキュー（DLQ）を作成します。

**制約**

- `VisibilityTimeout` は Lambda のタイムアウト × 6 以上を推奨
- DLQ の保持期間は本キューの保持期間より長く設定すること（デフォルト: 本キュー4日、DLQ14日）

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-sqs \
  --template-file cfn-sqs-queue.yaml \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

---

### cfn-iam-role-lambda.yaml

Lambda 実行ロールを作成します。CloudWatch Logs への書き込み権限が標準で含まれます。

**制約**

- `--capabilities CAPABILITY_NAMED_IAM` が必要

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-lambda-role \
  --template-file cfn-iam-role-lambda.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

**追加ポリシーあり**

```bash
aws cloudformation deploy \
  --stack-name my-project-dev-lambda-role \
  --template-file cfn-iam-role-lambda.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev \
    AdditionalPolicy1=arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess
```

---

### cfn-scheduled-lambda.yaml

Lambda 関数 + EventBridge スケジュール + IAM ロール + SSM アクセス + Bedrock アクセスを一括作成します。

**制約**

- `--capabilities CAPABILITY_NAMED_IAM` が必要
- スケジュールは UTC 指定。JST は UTC+9（例: 09:00 JST = `cron(0 0 * * ? *)`）
- Lambda コードはデプロイ後に `aws lambda update-function-code` で別途アップロードする

**デプロイ**

```bash
aws cloudformation deploy \
  --stack-name my-bot \
  --template-file cfn-scheduled-lambda.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=my-bot \
    SsmPrefix=/my-bot
```

**Lambda コードのアップロード**

```bash
zip lambda.zip lambda_function.py
aws lambda update-function-code \
  --function-name my-bot \
  --zip-file fileb://lambda.zip
```
