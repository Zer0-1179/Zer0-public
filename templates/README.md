# CloudFormation テンプレート集

実際の運用プロジェクトで使用している CloudFormation テンプレートを汎用化して公開しています。  
SAM は使用しません。Lambda のコードデプロイは `aws lambda update-function-code` で直接行います。

---

## テンプレート一覧

### ネットワーク

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-vpc.yaml` | VPC・サブネット・ルートテーブル | なし |
| `cfn-igw.yaml` | Internet Gateway | cfn-vpc |
| `cfn-nat.yaml` | NAT Gateway + EIP | cfn-vpc, cfn-igw |
| `cfn-security-group.yaml` | セキュリティグループ（空） | cfn-vpc |
| `cfn-security-group-ingress.yaml` | Ingressルール | cfn-security-group |
| `cfn-security-group-egress.yaml` | Egressルール（制限時のみ） | cfn-security-group |
| `cfn-alb.yaml` | ALB + ターゲットグループ | cfn-vpc, cfn-security-group |
| `cfn-nlb.yaml` | NLB + ターゲットグループ | cfn-vpc, cfn-security-group |

### コンピューティング

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-ec2.yaml` | EC2インスタンス + IAMロール + インスタンスプロファイル | cfn-vpc, cfn-security-group |
| `cfn-lambda.yaml` | Lambda関数 + 実行ロール + ロググループ | なし |
| `cfn-ecr.yaml` | ECRリポジトリ | なし |
| `cfn-ecs-cluster.yaml` | ECSクラスター（Fargate / Fargate Spot） | なし |
| `cfn-ecs-service.yaml` | ECSサービス + タスク定義 + 実行ロール | cfn-vpc, cfn-security-group, cfn-alb, cfn-ecs-cluster, cfn-ecr |

### ストレージ

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-s3.yaml` | S3バケット（バージョニング・暗号化・ライフサイクル） | なし |
| `cfn-ebs.yaml` | EBSボリューム + EC2アタッチメント | cfn-ec2 |
| `cfn-efs.yaml` | EFSファイルシステム + マウントターゲット（2AZ） | cfn-vpc, cfn-security-group |

### データベース

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-rds.yaml` | RDS DBインスタンス（MySQL / PostgreSQL） + サブネットグループ | cfn-vpc, cfn-security-group |
| `cfn-dynamodb.yaml` | DynamoDBテーブル（PITR・TTL・KMSオプション） | なし |

### セキュリティ

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-kms.yaml` | カスタマー管理KMSキー + エイリアス | なし |
| `cfn-iam-role.yaml` | Lambda用IAM実行ロール | なし |

### モニタリング・メッセージング

| ファイル名 | 作成リソース | 依存 |
|---|---|---|
| `cfn-cw-logs.yaml` | CloudWatch ロググループ | なし |
| `cfn-sqs.yaml` | SQSキュー + デッドレターキュー（DLQ） | なし |

---

## 命名規則

```
テンプレートファイル名:
  cfn-{Service}.yaml            # 例: cfn-s3.yaml
  cfn-{Service}-{Type}.yaml     # 例: cfn-ecs-cluster.yaml

スタック名:
  {ProjectName}-{Env}-{Service}
  {ProjectName}-{Env}-{Service}-{Suffix}   # Suffix は識別子が必要な場合

リソース名:
  {ProjectName}-{Env}-{Service}-{Suffix}   # Suffix は省略可
```

| サービス | リソース名例（ProjectName=pj, Env=dev） |
|---|---|
| VPC | `pj-dev-vpc` |
| NAT Gateway | `pj-dev-ngw` |
| Security Group | `pj-dev-sg-web` |
| ALB | `pj-dev-alb-01` |
| EC2 | `pj-dev-ec2` |
| Lambda | `pj-dev-lambda-api` |
| ECS Cluster | `pj-dev-ecs-cluster` |
| ECS Service | `pj-dev-ecs-api` |
| ECR | `pj-dev-ecr-app` |
| S3 | `pj-dev-s3-assets` |
| RDS | `pj-dev-rds` |
| DynamoDB | `pj-dev-dynamodb-users` |
| SQS | `pj-dev-sqs-orders` |
| KMS (alias) | `alias/pj-dev-kms` |
| IAM Role | `pj-dev-lambda-role` |

---

## Env による自動切替

`Env` パラメータ（`dev` / `stg` / `prd`）で環境ごとの設定を自動切替。  
`stg` は `dev` と同じ設定値。`prd` のみ以下が変わります。

| 設定 | dev / stg | prd |
|---|---|---|
| DeletionPolicy | Delete | **Retain** |
| バックアップ保持期間（RDS） | 1日 | 7日 |
| S3バージョニング | 無効 | 有効 |
| S3オブジェクト有効期限 | 90日 | 365日 |
| CWLogsリテンション | 7日 | 365日 |
| SQSメッセージ保持 | 1時間 | 14日 |
| DynamoDB削除保護 | 無効 | **有効** |
| KMS削除待機期間 | 7日 | 30日 |

---

## スタック間参照

クロススタック参照は `Outputs` + `Fn::ImportValue` で対応。  
`ProjectName` と `Env` を揃えれば自動的に参照先が解決されます。

```
VPC スタック名:  {ProjectName}-{Env}-vpc
SG スタック名:   {ProjectName}-{Env}-sg-{SgSuffix}
ALB スタック名:  {ProjectName}-{Env}-alb-{AlbSuffix}
```

---

## デプロイ基本コマンド

```bash
aws cloudformation deploy \
  --stack-name <ProjectName>-<Env>-<Service> \
  --template-file cfn-<service>.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=my-project \
    Env=dev
```

各テンプレートのコメント冒頭に詳細なデプロイ例があります。
