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
| `cfn-cw-logs.yaml` | CloudWatch ロググループ（最大5グループ一括作成） | なし |
| `cfn-sqs.yaml` | SQSキュー + デッドレターキュー（DLQ） | なし |
| `cfn-cw-alarm-ec2.yaml` | EC2 CPU・メモリ アラーム（WARNING/CRITICAL 各2段階、計4アラーム） | なし |
| `cfn-cw-alarm-rds.yaml` | RDS CPU・FreeableMemory アラーム（計4アラーム） | なし |
| `cfn-cw-alarm-efs.yaml` | EFS バーストクレジット・I/O使用率 アラーム（計4アラーム） | なし |
| `cfn-cw-alarm-lambda.yaml` | Lambda エラー・スロットル・Duration アラーム（計6アラーム） | なし |
| `cfn-cw-alarm-sqs.yaml` | SQS キュー滞留・メッセージ経過時間 アラーム（計4アラーム） | なし |
| `cfn-cw-alarm-alb.yaml` | ALB 5xxエラー・異常ホスト・レイテンシ アラーム（計6アラーム） | なし |

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

## コーディング規則

### セクションコメント（必須）

使用する全セクションの直前に以下の形式でコメントを記載する。

```yaml
# -----------------------------------------------
# Metadata
# Organizes the parameter input UI in the CloudFormation console.
# -----------------------------------------------
Metadata:
```

| セクション | コメントに含める内容 |
|---|---|
| Metadata | ParameterGroups による視覚的グループ化・ParameterLabels による表示名変更 |
| Parameters | デプロイ時に渡す値・AllowedValues・Default の説明 |
| Mappings | 静的参照テーブル・`!FindInMap [Table, Key, Item]` の使い方 |
| Conditions | パラメータから導出した Boolean フラグ・`!If [Condition, IfTrue, IfFalse]` の使い方 |
| Resources | DeletionPolicy・主要プロパティの補足説明 |
| Outputs | スタック作成後の参照値・Export/ImportValue でのクロススタック参照 |

### AllowedValues の書き方（ブロック記法に統一）

```yaml
# 正しい（ブロック記法）
AllowedValues:
  - stg
  - dev
  - prd

# NG（フロー記法）
AllowedValues: [stg, dev, prd]
```

Metadata の `ParameterGroups` > `Parameters` リストも同様にブロック記法を使う。

### 論理名の数字サフィックス（ゼロパディング必須）

リソース名・Condition 名・Output 名など数字を含む論理名はゼロパディングする。

```yaml
# 正しい
LogGroup01:
HasLogGroup02:

# NG
LogGroup1:
HasGroup2:
```

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

## CloudWatch アラーム 閾値設定ガイド

各アラームテンプレートには WARNING / CRITICAL の2段階の閾値パラメータがあります。  
通知先は `WarningActionArn`（Slack 等）と `CriticalActionArn`（PagerDuty 等）で分離できます。

### 閾値の設定方針

| メトリクス | 単位 | 設定の考え方 |
|---|---|---|
| CPU 使用率 | % | Warning=70 / Critical=90 が一般的な出発点。バースト型ワークロードは評価期間を長めに |
| EC2 メモリ（mem_used_percent） | % | Warning=70 / Critical=90。CWAgent が % で返すのでそのまま指定可 |
| RDS FreeableMemory | **bytes** | ★下記「RDS メモリ閾値の考え方」参照 |
| EFS BurstCreditBalance | **bytes** | ★下記「EFS バーストクレジット閾値の考え方」参照 |
| Lambda Errors / Throttles | 件数/分 | 件数は呼び出し量依存。少量呼び出しなら Warning=1/Critical=10、大量なら引き上げる |
| Lambda Duration | ms | タイムアウトの 65% を Warning、85% を Critical に設定するのが一般的 |
| SQS キュー滞留 | 件数 | コンシューマーの処理能力に合わせて設定。メッセージ経過時間（Age）の方が SLA 指標として正確 |
| SQS メッセージ経過時間 | 秒 | 許容する最大処理遅延時間を Warning・Critical に設定 |
| ALB 5xxエラー | 件数/分 | トラフィック量依存。本番は Warning=5/Critical=20 から始めてチューニング |
| ALB 異常ホスト数 | 台数 | Warning=0（1台でも異常）/ Critical=1（複数台異常）が一般的 |
| ALB レイテンシ | 秒 | SLA に合わせて設定。Warning=1s / Critical=3s が汎用的な出発点 |

---

### RDS メモリ閾値の考え方

`FreeableMemory` は **バイト単位** で指定します。  
閾値はインスタンスの総メモリに対する割合で考えるのがベストプラクティスです。

**推奨目安：Warning = 総メモリの 30%、Critical = 総メモリの 15%**

| インスタンスクラス | 総メモリ | Warning 閾値（30%） | Critical 閾値（15%） |
|---|---|---|---|
| db.t3.micro | 1 GB | 322122547 | 161061274 |
| db.t3.small | 2 GB | 644245094 | 322122547 |
| db.t3.medium | 4 GB | 1288490189 | 644245094 |
| db.t3.large | 8 GB | 2576980378 | 1288490189 |
| db.r6g.large | 16 GB | 5153960755 | 2576980378 |
| db.r6g.xlarge | 32 GB | 10307921510 | 5153960755 |
| db.r6g.2xlarge | 64 GB | 20615843021 | 10307921510 |

**計算式：** `総メモリ(GB) × 1073741824 × 閾値割合`  
例: db.t3.medium の Warning 閾値 = `4 × 1073741824 × 0.30 = 1288490189`

> **注意：** インスタンスタイプを変更する際は閾値も合わせて更新してください。  
> テンプレートのデフォルト値（Warning=1GB / Critical=512MB）は db.t3.medium 前後を想定しています。  
> `Env=prd` でデプロイ後にスケールアップした場合、閾値が小さすぎてアラームが鳴らなくなります。

---

### EFS バーストクレジット閾値の考え方

`BurstCreditBalance` は **バイト単位** で指定します。  
EFS のバーストスループットは `100 MB/s × ストレージ量(TB)` で、クレジットも同じ比率で決まります。

**推奨目安：Warning = 残り 6 時間分、Critical = 残り 3 時間分のバーストクレジット**

| EFS ストレージ量 | 最大バースト | Warning 閾値（6時間分） | Critical 閾値（3時間分） |
|---|---|---|---|
| 1 TB | 100 MB/s | 2160000000000 | 1080000000000 |
| 5 TB | 500 MB/s | 10800000000000 | 5400000000000 |
| 10 TB | 1000 MB/s | 21600000000000 | 10800000000000 |

**計算式：** `バーストスループット(MB/s) × 3600秒 × 残り時間(h) × 1000000`  
例: 1TB の Warning = `100 × 3600 × 6 × 1000000 = 2160000000000`

> **注意：** EFS のストレージ量は時間経過で変わります。ストレージが大幅に増減したら閾値を見直してください。  
> テンプレートのデフォルト値（Warning=2TB / Critical=1TB）はおよそ 1TB ストレージ × 6時間/3時間を想定しています。

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
