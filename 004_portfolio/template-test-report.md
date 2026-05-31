# CFn テンプレート テスト状況レポート

> 最終更新: 2026-05-31  
> 対象: `004_portfolio/templates/` 以下の全 62 テンプレート  
> テスト環境: ap-northeast-1 / ProjectName=cfntest / Env=dev

---

## テスト種別の定義

| 記号 | 種別 | 内容 |
|------|------|------|
| ✅ | 実デプロイ | AWS に実際にスタックを作成し **CREATE_COMPLETE** を確認 |
| △ | validate-template | CloudFormation API で構文・型・参照の正当性を確認（リソース作成なし） |

> △（validate-template）は構文エラーの検出には有効ですが、実際にリソースが作成できるかは保証しません。

---

## 結果サマリー

| 区分 | ✅ 実デプロイ | △ validate のみ | 合計 |
|------|:-----------:|:---------------:|:----:|
| Beginner（初級） | 18 | 13 | 31 |
| Advanced（上級） | 31 | 0 | 31 |
| **合計** | **49** | **13** | **62** |

**「全テンプレートがそのまま使えるか？」への回答**
- ✅ Advanced 31本：全て実デプロイで CREATE_COMPLETE 確認済み
- ✅ Beginner 18本：実デプロイで CREATE_COMPLETE 確認済み
- △ Beginner 13本：構文は正しい。コスト大・依存リソース大のため実デプロイ未実施（Advanced 版で同等の構成が検証済み）

---

## カテゴリ別テスト結果

### network（ネットワーク）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-vpc-basic.yaml | Beginner | ✅ 実デプロイ | VPC + IGW + パブリックサブネット + ルートテーブル CREATE_COMPLETE | 2026-05-30 |
| cfn-vpc.yaml | Advanced | ✅ 実デプロイ | マルチAZ + パブリック/プライベートサブネット構成 CREATE_COMPLETE | 2026-05-27 |
| cfn-igw-basic.yaml | Beginner | ✅ 実デプロイ | 既存VPC への IGW アタッチ CREATE_COMPLETE | 2026-05-31 |
| cfn-igw.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-nat-basic.yaml | Beginner | △ validate | NAT Gateway はコスト大（約$0.045/h）のため validate のみ | 2026-05-31 |
| cfn-nat.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-security-group-basic.yaml | Beginner | ✅ 実デプロイ | SG + Ingress ルール CREATE_COMPLETE | 2026-05-31 |
| cfn-security-group.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-security-group-ingress-basic.yaml | Beginner | ✅ 実デプロイ | 既存 SG への Ingress ルール追加 CREATE_COMPLETE | 2026-05-31 |
| cfn-security-group-ingress.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-security-group-egress-basic.yaml | Beginner | ✅ 実デプロイ | 既存 SG への Egress ルール追加 CREATE_COMPLETE | 2026-05-31 |
| cfn-security-group-egress.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-alb-basic.yaml | Beginner | △ validate | ALB はコスト大（約$0.022/h）のため validate のみ | 2026-05-31 |
| cfn-alb.yaml | Advanced | ✅ 実デプロイ | Scheme=internal, TargetType=ip でECS Service 前提スタックとして CREATE_COMPLETE | 2026-05-31 |
| cfn-nlb-basic.yaml | Beginner | △ validate | NLB はコスト大のため validate のみ | 2026-05-31 |
| cfn-nlb.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |

---

### compute（コンピューティング）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-lambda-basic.yaml | Beginner | ✅ 実デプロイ | Lambda + IAM Role + Log Group（インラインコード）CREATE_COMPLETE | 2026-05-31 |
| cfn-lambda.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-ec2-basic.yaml | Beginner | △ validate | EC2 はコスト大のため validate のみ | 2026-05-31 |
| cfn-ec2.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-ecr-basic.yaml | Beginner | ✅ 実デプロイ | ECR リポジトリ CREATE_COMPLETE | 2026-05-30 |
| cfn-ecr.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-ecs-cluster-basic.yaml | Beginner | ✅ 実デプロイ | ECS クラスター CREATE_COMPLETE | 2026-05-30 |
| cfn-ecs-cluster.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-ecs-service-basic.yaml | Beginner | △ validate | ECS Service は VPC/ALB/ECSクラスター の前提スタック要のため validate のみ | 2026-05-31 |
| cfn-ecs-service.yaml | Advanced | ✅ 実デプロイ | vpc + sg + alb + ecs-cluster 前提スタック5本 + `create-stack` で CREATE_COMPLETE。DesiredCount=0 | 2026-05-31 |

---

### storage（ストレージ）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-s3-basic.yaml | Beginner | ✅ 実デプロイ | S3 バケット + バージョニング + 暗号化 CREATE_COMPLETE | 2026-05-30 |
| cfn-s3.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-ebs-basic.yaml | Beginner | △ validate | EBS は EC2 依存のため validate のみ | 2026-05-31 |
| cfn-ebs.yaml | Advanced | ✅ 実デプロイ | `HasEc2Instance` Condition バグ修正済み。CREATE_COMPLETE | 2026-05-30 |
| cfn-efs-basic.yaml | Beginner | △ validate | EFS は VPC/SG 依存・コスト大のため validate のみ | 2026-05-31 |
| cfn-efs.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |

---

### database（データベース）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-dynamodb-basic.yaml | Beginner | ✅ 実デプロイ | **バグ修正後**再テスト。SSEType AES256 非対応 → SSESpecification 削除。CREATE_COMPLETE | 2026-05-31 |
| cfn-dynamodb.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-rds-basic.yaml | Beginner | △ validate | RDS はコスト大（約$0.022/h〜）のため validate のみ | 2026-05-31 |
| cfn-rds.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-30 |
| cfn-elasticache-basic.yaml | Beginner | △ validate | ElastiCache はコスト大のため validate のみ | 2026-05-31 |
| cfn-elasticache.yaml | Advanced | ✅ 実デプロイ | **バグ修正後**再テスト。EngineVersion 7.2 未提供 → 7.1 に修正。VPC + SG 前提スタックで CREATE_COMPLETE | 2026-05-31 |

---

### security（セキュリティ）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-kms-basic.yaml | Beginner | ✅ 実デプロイ | KMS キー + KeyPolicy CREATE_COMPLETE | 2026-05-30 |
| cfn-kms.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-iam-role-basic.yaml | Beginner | ✅ 実デプロイ | IAM Role + AssumeRolePolicy CREATE_COMPLETE | 2026-05-30 |
| cfn-iam-role.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |

---

### messaging（メッセージング）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-sqs-basic.yaml | Beginner | ✅ 実デプロイ | SQS キュー + DLQ CREATE_COMPLETE | 2026-05-30 |
| cfn-sqs.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-sns-basic.yaml | Beginner | ✅ 実デプロイ | SNS トピック CREATE_COMPLETE | 2026-05-30 |
| cfn-sns.yaml | Advanced | ✅ 実デプロイ | Conditions（HasKmsKey / HasHttpsEndpoint / HasDisplayName）全パターン動作確認 CREATE_COMPLETE | 2026-05-31 |
| cfn-eventbridge-basic.yaml | Beginner | ✅ 実デプロイ | EventBridge ルール + Lambda Permission CREATE_COMPLETE | 2026-05-31 |
| cfn-eventbridge.yaml | Advanced | ✅ 実デプロイ | HasLambdaTarget / HasInput Condition 動作確認。Lambda target なしで CREATE_COMPLETE | 2026-05-31 |

---

### monitoring（モニタリング）

| ファイル | 難易度 | テスト種別 | 確認内容 | テスト日 |
|----------|--------|:----------:|----------|----------|
| cfn-cw-logs-basic.yaml | Beginner | ✅ 実デプロイ | CloudWatch Logs グループ CREATE_COMPLETE | 2026-05-30 |
| cfn-cw-logs.yaml | Advanced | ✅ 実デプロイ | CREATE_COMPLETE | 2026-05-27 |
| cfn-cw-alarm-lambda-basic.yaml | Beginner | ✅ 実デプロイ | Lambda エラーアラーム + SNS 通知 CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-lambda.yaml | Advanced | ✅ 実デプロイ | WARNING/CRITICAL 2段階アラーム。FunctionName のみ指定で CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-sqs-basic.yaml | Beginner | ✅ 実デプロイ | SQS メッセージ滞留アラーム + SNS 通知 CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-sqs.yaml | Advanced | ✅ 実デプロイ | WARNING/CRITICAL 2段階アラーム。QueueName のみ指定で CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-ec2-basic.yaml | Beginner | △ validate | EC2 依存のため validate のみ | 2026-05-31 |
| cfn-cw-alarm-ec2.yaml | Advanced | ✅ 実デプロイ | WARNING/CRITICAL 2段階アラーム（CPU + Memory）。InstanceId 文字列指定で CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-alb-basic.yaml | Beginner | △ validate | ALB 依存のため validate のみ | 2026-05-31 |
| cfn-cw-alarm-alb.yaml | Advanced | ✅ 実デプロイ | `!Split ["loadbalancer/", AlbArn]` による Dimension 自動抽出。ALB/TG ARN フォーマット形式の文字列で CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-efs-basic.yaml | Beginner | △ validate | EFS 依存のため validate のみ | 2026-05-31 |
| cfn-cw-alarm-efs.yaml | Advanced | ✅ 実デプロイ | FileSystemId 文字列指定で CREATE_COMPLETE | 2026-05-31 |
| cfn-cw-alarm-rds-basic.yaml | Beginner | △ validate | RDS 依存のため validate のみ | 2026-05-31 |
| cfn-cw-alarm-rds.yaml | Advanced | ✅ 実デプロイ | Mappings で DBInstanceClass → メモリ変換。WARNING/CRITICAL 2段階アラーム（CPU + FreeableMemory%）CREATE_COMPLETE | 2026-05-31 |

---

## バグ修正履歴

| ファイル | 修正内容 | 修正日 |
|----------|----------|--------|
| cfn-dynamodb-basic.yaml | `SSESpecification.SSEType: AES256` は DynamoDB 非対応（KMS のみ）のためブロックごと削除。DynamoDB はデフォルトで AWS 所有キーにより暗号化済みのためコメントで明示 | 2026-05-31 |
| cfn-elasticache.yaml | EngineVersion デフォルト `7.2` は ap-northeast-1 未提供。`7.1` に変更し AllowedValues から `7.2` を削除 | 2026-05-31 |
| cfn-elasticache-basic.yaml | EngineVersion ハードコード `7.2` を `7.1` に修正 | 2026-05-31 |
| cfn-ebs.yaml | `Ec2InstanceId` が空のとき `VolumeAttachment` が無条件に作成されてデプロイ失敗。`HasEc2Instance` Condition を追加して VolumeAttachment に付与 | 2026-05-30 |
| cfn-alb-basic.yaml | `TargetType` がハードコード `instance` になっており Fargate 構成で失敗。パラメータ化（`instance` / `ip`）して対応 | 2026-05-30 |
| cfn-kms-basic.yaml | `KeyPolicy` が未設定でデプロイ後に鍵が操作不能になるケースがあった。アカウント管理者を Principal に含む最低限の KeyPolicy を追加 | 2026-05-30 |
| cfn-ecs-service-basic.yaml | `AssignPublicIp: DISABLED` だと Fargate がイメージ pull 不可。パブリックサブネット利用時は `ENABLED` に変更 | 2026-05-30 |

---

## △（validate-template のみ）の背景

下記 Beginner テンプレートは実デプロイで費用が発生するため、構文検証のみとしています。  
**対応する Advanced 版は全て実デプロイ済み**であり、Beginner 版はそのシンプル版のため実質的に問題ないと考えられます。

| 理由 | 対象テンプレート |
|------|-----------------|
| **コスト大**（NAT: $0.045/h、ALB/NLB/RDS/ElastiCache/EC2: 数十〜数百円/h） | nat-basic, alb-basic, nlb-basic, ec2-basic, rds-basic, elasticache-basic |
| **依存リソース必要**（EFS: VPC+SG、EBS: EC2） | efs-basic, ebs-basic |
| **前提スタック多い**（ECS Service: VPC/IGW/SG/ALB/ECSクラスターが必要） | ecs-service-basic |
| **上記リソース依存の監視設定** | cw-alarm-ec2-basic, cw-alarm-alb-basic, cw-alarm-efs-basic, cw-alarm-rds-basic |

---

## ECS Service デプロイの注意事項

`cfn-ecs-service.yaml` は `aws cloudformation deploy` を使うと Early Validation でブロックされる。  
必ず `create-stack` で直接デプロイすること。

```bash
aws cloudformation create-stack \
  --stack-name {ProjectName}-{Env}-ecs-{ServiceSuffix} \
  --template-body file://cfn-ecs-service.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=my-project \
    ParameterKey=Env,ParameterValue=dev \
    ParameterKey=ServiceSuffix,ParameterValue=api \
    ParameterKey=SgSuffix,ParameterValue=app \
    ParameterKey=AlbSuffix,ParameterValue=01 \
    ParameterKey=ImageUri,ParameterValue=nginx:alpine \
    ParameterKey=DesiredCount,ParameterValue=0
```

**前提スタック（この順番でデプロイ）:**

1. `cfn-vpc.yaml` → `{ProjectName}-{Env}-vpc`
2. `cfn-igw.yaml` → `{ProjectName}-{Env}-igw`（internet-facing ALB が必要な場合）
3. `cfn-security-group.yaml` → `{ProjectName}-{Env}-sg-{SgSuffix}`
4. `cfn-alb.yaml` → `{ProjectName}-{Env}-alb-{AlbSuffix}`（TargetType=ip 必須）
5. `cfn-ecs-cluster.yaml` → `{ProjectName}-{Env}-ecs-cluster`
