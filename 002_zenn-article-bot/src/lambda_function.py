import json
import os
import random
import boto3
import datetime
from botocore.config import Config
try:
    from diagram_generator import generate_diagrams
except ImportError:
    def generate_diagrams(topic_id, base_path):
        return []

# AWS clients
bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=880, connect_timeout=10),
)
ses = boto3.client("ses", region_name="ap-northeast-1")
s3  = boto3.client("s3",  region_name="ap-northeast-1")
ssm = boto3.client("ssm", region_name="ap-northeast-1")
cfn = boto3.client("cloudformation", region_name="ap-northeast-1")

# Lambda環境かどうかで出力先を切り替え
_IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Environment variables
SES_SENDER_EMAIL    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT_EMAIL = os.environ["SES_RECIPIENT_EMAIL"]
BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    "/tmp/zenn_articles" if _IS_LAMBDA
    else os.path.expanduser("~/Zer0/002_Zenn_Auto_Article_Bot/output"),
)
S3_BUCKET  = os.environ.get("S3_BUCKET", "zer0-dev-s3")
S3_PREFIX  = "zenn-articles"
OUTPUT_KEEP_MAX = 5  # ローカル output/ に残す記事フォルダの最大数

# SSM: 直近トピック履歴
SSM_PARAM_PATH      = "/zenn-article-bot/recent-topics"
RECENT_TOPICS_LIMIT = 5

AWS_TOPICS = [
    {
        "id": "ec2",
        "name": "Amazon EC2",
        "subtitle": "仮想サーバーを使いこなす完全ガイド",
        "keywords": "インスタンスタイプ, AMI, セキュリティグループ, キーペア, Elastic IP",
    },
    {
        "id": "s3",
        "name": "Amazon S3",
        "subtitle": "オブジェクトストレージ徹底活用ガイド",
        "keywords": "バケット, オブジェクト, ストレージクラス, バージョニング, 静的Webサイトホスティング",
    },
    {
        "id": "iam",
        "name": "AWS IAM",
        "subtitle": "セキュアなアクセス管理を実現する完全ガイド",
        "keywords": "ユーザー, グループ, ロール, ポリシー, MFA, 最小権限の原則",
    },
    {
        "id": "vpc",
        "name": "Amazon VPC",
        "subtitle": "仮想ネットワーク設計の完全ガイド",
        "keywords": "サブネット, ルートテーブル, インターネットゲートウェイ, NATゲートウェイ, セキュリティグループ",
    },
    {
        "id": "rds",
        "name": "Amazon RDS",
        "subtitle": "マネージドデータベースサービス完全ガイド",
        "keywords": "MySQL, PostgreSQL, Multi-AZ, リードレプリカ, 自動バックアップ, パラメータグループ",
    },
    {
        "id": "lambda",
        "name": "AWS Lambda",
        "subtitle": "サーバーレスアーキテクチャ入門ガイド",
        "keywords": "関数, トリガー, イベント, コールドスタート, レイヤー, 同時実行数",
    },
    {
        "id": "cloudwatch",
        "name": "Amazon CloudWatch",
        "subtitle": "監視・ログ管理の完全ガイド",
        "keywords": "メトリクス, アラーム, ログ, ダッシュボード, イベント, Insights",
    },
    {
        "id": "ecs",
        "name": "Amazon ECS",
        "subtitle": "コンテナオーケストレーション完全ガイド",
        "keywords": "タスク定義, クラスター, サービス, Fargate, ECR, ロードバランサー",
    },
    {
        "id": "dynamodb",
        "name": "Amazon DynamoDB",
        "subtitle": "NoSQLデータベース完全活用ガイド",
        "keywords": "テーブル, パーティションキー, ソートキー, GSI, LSI, オンデマンドキャパシティ",
    },
    {
        "id": "cloudfront",
        "name": "Amazon CloudFront",
        "subtitle": "CDNで高速・安全なコンテンツ配信ガイド",
        "keywords": "ディストリビューション, オリジン, エッジロケーション, キャッシュ, WAF連携",
    },
    {
        "id": "api_gateway",
        "name": "Amazon API Gateway",
        "subtitle": "REST/WebSocket APIを構築する完全ガイド",
        "keywords": "REST API, HTTP API, Lambda統合, 認証, スロットリング, ステージ",
    },
    {
        "id": "sqs",
        "name": "Amazon SQS",
        "subtitle": "メッセージキューで疎結合アーキテクチャを実現するガイド",
        "keywords": "標準キュー, FIFOキュー, デッドレターキュー, 可視性タイムアウト, ロングポーリング",
    },
    # ─── AI / ML 系 ───────────────────────────────────────────────────────────
    {
        "id": "bedrock",
        "name": "Amazon Bedrock",
        "subtitle": "生成AIをアプリに組み込む完全ガイド",
        "keywords": "基盤モデル, Claude, Titan, RAG, Knowledge Base, プロンプトエンジニアリング, Agents",
    },
    {
        "id": "sagemaker",
        "name": "Amazon SageMaker AI",
        "subtitle": "機械学習モデルの構築・学習・デプロイ完全ガイド",
        "keywords": "Studio, Training Job, Endpoint, Pipeline, Feature Store, Ground Truth, AutoML",
    },
    {
        "id": "rekognition",
        "name": "Amazon Rekognition",
        "subtitle": "画像・動画解析AIサービス活用ガイド",
        "keywords": "物体検出, 顔認識, テキスト検出, コンテンツモデレーション, カスタムラベル, 顔比較",
    },
    {
        "id": "textract",
        "name": "Amazon Textract",
        "subtitle": "文書・帳票の自動データ抽出完全ガイド",
        "keywords": "OCR, フォーム解析, テーブル抽出, 非同期処理, S3連携, ドキュメント解析",
    },
    # ─── その他主要サービス ────────────────────────────────────────────────────
    {
        "id": "step_functions",
        "name": "AWS Step Functions",
        "subtitle": "サーバーレスワークフロー自動化完全ガイド",
        "keywords": "ステートマシン, タスク, 並列処理, エラーハンドリング, Retry, Catch, Express Workflow",
    },
    {
        "id": "sns",
        "name": "Amazon SNS",
        "subtitle": "Pub/Subメッセージングで通知基盤を構築するガイド",
        "keywords": "トピック, サブスクリプション, プッシュ通知, メール, SQS連携, フィルタリングポリシー",
    },
    {
        "id": "elasticache",
        "name": "Amazon ElastiCache",
        "subtitle": "インメモリキャッシュでアプリを高速化するガイド",
        "keywords": "Redis, Memcached, クラスター, レプリケーション, セッション管理, キャッシュ戦略, TTL",
    },
    {
        "id": "route53",
        "name": "Amazon Route 53",
        "subtitle": "DNS・トラフィック管理で可用性を高める完全ガイド",
        "keywords": "ホストゾーン, Aレコード, エイリアス, フェイルオーバー, ヘルスチェック, レイテンシールーティング",
    },
    {
        "id": "kinesis",
        "name": "Amazon Kinesis",
        "subtitle": "リアルタイムデータストリーミング完全ガイド",
        "keywords": "Data Streams, Firehose, シャード, コンシューマー, S3連携, リアルタイム分析, Data Analytics",
    },
    {
        "id": "cloudtrail",
        "name": "AWS CloudTrail",
        "subtitle": "AWSアカウントの操作ログ管理・セキュリティ監査ガイド",
        "keywords": "証跡, イベント履歴, S3保存, EventBridge連携, セキュリティ監査, コンプライアンス, 不審な操作検知",
    },
]

# ─── AWS公式ドキュメント URL マップ ───────────────────────────────────────────
DOCS_URL_MAP: dict[str, str] = {
    "ec2":            "https://docs.aws.amazon.com/ja_jp/AWSEC2/latest/UserGuide/concepts.html",
    "s3":             "https://docs.aws.amazon.com/ja_jp/AmazonS3/latest/userguide/Welcome.html",
    "iam":            "https://docs.aws.amazon.com/ja_jp/IAM/latest/UserGuide/introduction.html",
    "vpc":            "https://docs.aws.amazon.com/ja_jp/vpc/latest/userguide/what-is-amazon-vpc.html",
    "rds":            "https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/UserGuide/Welcome.html",
    "lambda":         "https://docs.aws.amazon.com/ja_jp/lambda/latest/dg/welcome.html",
    "cloudwatch":     "https://docs.aws.amazon.com/ja_jp/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html",
    "ecs":            "https://docs.aws.amazon.com/ja_jp/AmazonECS/latest/developerguide/Welcome.html",
    "dynamodb":       "https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/Introduction.html",
    "cloudfront":     "https://docs.aws.amazon.com/ja_jp/AmazonCloudFront/latest/DeveloperGuide/Introduction.html",
    "api_gateway":    "https://docs.aws.amazon.com/ja_jp/apigateway/latest/developerguide/welcome.html",
    "sqs":            "https://docs.aws.amazon.com/ja_jp/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html",
    "bedrock":        "https://docs.aws.amazon.com/ja_jp/bedrock/latest/userguide/what-is-bedrock.html",
    "sagemaker":      "https://docs.aws.amazon.com/ja_jp/sagemaker/latest/dg/whatis.html",
    "rekognition":    "https://docs.aws.amazon.com/ja_jp/rekognition/latest/dg/what-is.html",
    "textract":       "https://docs.aws.amazon.com/ja_jp/textract/latest/dg/what-is.html",
    "step_functions": "https://docs.aws.amazon.com/ja_jp/step-functions/latest/dg/welcome.html",
    "sns":            "https://docs.aws.amazon.com/ja_jp/sns/latest/dg/welcome.html",
    "elasticache":    "https://docs.aws.amazon.com/ja_jp/AmazonElastiCache/latest/dg/WhatIs.html",
    "route53":        "https://docs.aws.amazon.com/ja_jp/Route53/latest/DeveloperGuide/Welcome.html",
    "kinesis":        "https://docs.aws.amazon.com/ja_jp/streams/latest/dev/introduction.html",
    "cloudtrail":     "https://docs.aws.amazon.com/ja_jp/awscloudtrail/latest/userguide/cloudtrail-user-guide.html",
}

# ─── Zennフロントマター用メタ情報 ─────────────────────────────────────────────
_ZENN_META: dict[str, dict] = {
    "ec2":           {"emoji": "🖥️",  "topics": ["aws", "ec2", "インフラ", "クラウド"]},
    "s3":            {"emoji": "🪣",  "topics": ["aws", "s3", "ストレージ", "クラウド"]},
    "iam":           {"emoji": "🔐",  "topics": ["aws", "iam", "セキュリティ", "クラウド"]},
    "vpc":           {"emoji": "🌐",  "topics": ["aws", "vpc", "ネットワーク", "クラウド"]},
    "rds":           {"emoji": "🗄️",  "topics": ["aws", "rds", "データベース", "クラウド"]},
    "lambda":        {"emoji": "⚡",  "topics": ["aws", "lambda", "サーバーレス", "クラウド"]},
    "cloudwatch":    {"emoji": "📊",  "topics": ["aws", "cloudwatch", "監視", "クラウド"]},
    "ecs":           {"emoji": "📦",  "topics": ["aws", "ecs", "コンテナ", "docker"]},
    "dynamodb":      {"emoji": "💾",  "topics": ["aws", "dynamodb", "nosql", "データベース"]},
    "cloudfront":    {"emoji": "🚀",  "topics": ["aws", "cloudfront", "cdn", "クラウド"]},
    "api_gateway":   {"emoji": "🔌",  "topics": ["aws", "apigateway", "api", "サーバーレス"]},
    "sqs":           {"emoji": "📬",  "topics": ["aws", "sqs", "メッセージキュー", "クラウド"]},
    "bedrock":       {"emoji": "🤖",  "topics": ["aws", "bedrock", "生成ai", "llm"]},
    "sagemaker":     {"emoji": "🧠",  "topics": ["aws", "sagemakerAI", "機械学習", "ai"]},
    "rekognition":   {"emoji": "👁️",  "topics": ["aws", "rekognition", "画像認識", "ai"]},
    "textract":      {"emoji": "📄",  "topics": ["aws", "textract", "ocr", "ai"]},
    "step_functions":{"emoji": "🔄",  "topics": ["aws", "stepfunctions", "ワークフロー", "サーバーレス"]},
    "sns":           {"emoji": "📢",  "topics": ["aws", "sns", "通知", "クラウド"]},
    "elasticache":   {"emoji": "⚡",  "topics": ["aws", "elasticache", "redis", "キャッシュ"]},
    "route53":       {"emoji": "🌍",  "topics": ["aws", "route53", "dns", "ネットワーク"]},
    "kinesis":       {"emoji": "🌊",  "topics": ["aws", "kinesis", "ストリーミング", "データ"]},
    "cloudtrail":    {"emoji": "🔍",  "topics": ["aws", "cloudtrail", "セキュリティ", "監査"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
「読んでよかった」と思わせる記事を書いてください。テンプレートを埋める作業ではなく、読者の課題を解決する記事です。

## テーマ
{topic_name}：{topic_subtitle}

## キーワード（記事中に自然に含めること）
{keywords}

{docs_section}
## 読者像
プログラミング経験はあるが、AWSをほぼ使ったことがない初級エンジニア。
「概念を知りたい」より「実際に動かして仕事で使いたい」が動機。

---

## 品質の原則

**書くこと**
- 冒頭で「誰の・どんな問題を・どう解決するか」を1段落以内に伝える
- 具体的な数字・コマンド・レスポンス例で語る（「高速です」ではなく「〜ms以下」）
- 1文1意。「〜し、〜であり、〜するため」は分割する
- 「〜できます」（「〜することができます」は使わない）
- 各ステップに「なぜそうするか」の理由を添える

**書かないこと・避けること**
- 「本記事では〜について解説します」（宣言型の導入）
- 「非常に重要です」「ぜひ試してみてください」（根拠のない煽り文句）
- 読者が知っていることの説明（「AWSはクラウドです」等の自明な前提）
- 前セクションをそのままなぞるだけのまとめ
- 根拠のない最上級表現（「最も優れた」「業界標準」）
- 文章で書けるのに箇条書きに逃げる（流れを作れる部分は文章で書く）
- 手順を示さずに「〜は簡単です」と言う

---

## Zenn Markdown記法（効果的な場面でのみ使う）

**テーブル**: 比較・一覧が読者の判断を助ける場面で使う
**:::message**: 読者が見落としやすい重要ポイントのみ（乱発しない）
**:::message alert**: コスト・セキュリティの具体的な注意（「注意してください」だけでなく何に注意するかを書く）
**:::details**: 読まなくてもメインが理解できる応用・補足
**コードブロック**: 言語またはファイル名を必ず指定

使用例:
:::message
重要なポイント（読者が見落としやすいこと）
:::

:::message alert
コスト・セキュリティの注意（具体的に書く）
:::

:::details 応用：本番環境向けの設定
補足内容
:::

```bash:動作確認
aws s3 ls
```

```json:レスポンス例
{{"status": "ok"}}
```

---

## 記事の見出し構成

「はじめに」と「まとめ」は必ず含める。
中間セクションはサービスの特性・読者の理解フローに合わせて自由に構成する（毎回同じ構成にしなくてよい）。

### ## はじめに
- **冒頭の1文で {topic_name} が「誰の・どんな問題を・どう解決するか」を伝える**
  - 課題から入る例: 「〜に困ったことはありませんか？{topic_name}を使うと〜」
  - 本質から入る例: 「{topic_name}は〜するためのサービスです。これがあると〜が不要になります」
  - 「この記事では〜を解説します」という宣言は使わない
- この記事を読むと「何ができるようになるか」を1〜2文で示す
- 書き終えたら以下のマーカーを**単独行**で挿入（前後に空行必須）:

{{DIAGRAM_1}}

  直前に図を見る動機づけになる1〜2文を書く（毎回違う切り口で。例文のコピー不可）:
  - 「{topic_name}の全体像を先に掴んでおくと、以降の説明がすっと入ってきます。」
  - 「実際の現場でどう使われているか、構成図から先に見ておきましょう。」

### 中間セクション（以下から選んで自由に構成する）

| 要素 | 内容 |
|------|------|
| サービス概要 | 役割・特徴・ユースケース 2〜3例。`:::message` で一言まとめ |
| 料金体系 | Free Tier・主要課金項目。`:::message alert` で見落としやすいコスト |
| ハンズオン | AWSコンソール操作手順（下記参照） |
| アーキテクチャ / 連携パターン | 実務でよく使う構成例・他サービスとの組み合わせ |
| ベストプラクティス / 落とし穴 | 実務で詰まるポイント・よくある設定ミス |
| 他サービスとの使い分け | 「〇〇との違い」「どちらを選ぶか」の判断基準 |

**ハンズオンを含める場合**、セクション冒頭（手順前）に以下を挿入（前後に空行必須）:

{{DIAGRAM_2}}

  直前に図を見る動機づけになる1〜2文を書く（毎回違う切り口で）

ハンズオンに必ず含めること:
- **前提条件**（必要なもの。箇条書き）
- **操作手順**（番号付き。各ステップに「なぜそうするか」とつまずきやすいポイント）
- **動作確認**（コマンドまたはブラウザ操作 ＋ **成功時のレスポンス例をコードブロックで必ず示す**）
- **後片付け**（料金が発生しないようリソースを削除する手順）

### ## まとめ
- **「次に何をすべきか」を中心に書く**（学んだことの箇条書き再掲は避ける）
- {topic_name}を使うべき場面・使わなくてよい場面の整理
- 次のステップとして効果的な関連サービスの提案

---

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |

---

## 注意事項
- **記事の先頭にYAML frontmatter（--- で囲まれたブロック）を書かない**（frontmatterはシステムが自動付与する）
- 見出しは ## や ### を使ったMarkdown形式で書く（# は使わない）
- コードやコマンドはバッククォート3つで囲み、言語名またはファイル名を指定する
- 重要な用語は**太字**で強調する
- AWSコンソールの操作は具体的なメニュー名やボタン名を明記する
- 料金は2026年時点の情報を参考にし「最新情報はAWS公式サイトで確認してください」と注記する
- curlコマンドやブラウザ確認では**成功時のレスポンス例を必ずコードブロックで示す**（「結果が表示されます」のような曖昧な表現は使わない）
- `:::message` や `:::details` は前後に必ず空行を入れること
- コードブロック内のサンプル日付は**本日の日付（{today}）** を基準にする（`2024`や`2023`等の過去の年は使わない。連番が必要な場合は翌日・数時間後など`{today}`前後の日付を使う）
- **文字数**: 2,000〜3,500文字程度（水増しより内容の充実を優先する）

---

## コード品質の必須ルール

### IAM ポリシー
- IAM ポリシーは最小権限で書く。`Resource: '*'` を使う場合はその理由を文中で説明する
- `Describe*` / `List*` 系アクションはリソース条件を非サポートのため `Resource: '*'` のみで記述し、変更系アクション（`Put*` / `Delete*` / `Stop*` 等）と同一ステートメントに混在させない

### Lambda Runtime
- Lambda の Runtime は現時点の最新安定版を使う: `python3.13`（Python）/ `nodejs22.x`（Node.js）
- 旧バージョン（`python3.12` / `nodejs20.x` 等）は使わない

### CloudFormation・AWS CLI の正確性
- 記事内のコードは省略・疑似コードなしで、**実際に動く完全な記述**にする
- CLIコマンドは `--region ap-northeast-1` を明示する
- SNS メール購読はデプロイ後に**確認メールのクリックが必要**な旨を記事内で必ず明記する

### AWS サービスの制約
- サービスの「できないこと・注意点」を「できること」と同等の重みで記載する
- 料金は断定的に書かず幅を持たせる（「〜円程度」「〜$以下」形式）
"""


# ─── AWS公式ドキュメント取得 ──────────────────────────────────────────────────

def fetch_aws_docs(topic_id: str, max_chars: int = 6000) -> str:
    """AWS公式ドキュメントを取得してプレーンテキストを返す。失敗時は空文字列。"""
    import re
    import urllib.request

    url = DOCS_URL_MAP.get(topic_id, "")
    if not url:
        print(f"[Docs] {topic_id}: URL未定義のためスキップ")
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)

        main = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
        content = main.group(1) if main else html

        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        print(f"[Docs] {topic_id}: {len(text)}文字取得 ({url})")
        return text[:max_chars]
    except Exception as e:
        print(f"[Docs] {topic_id}: 取得エラー（スキップ）: {e}")
        return ""


# ─── SSM: トピック重複除外 ────────────────────────────────────────────────────

def get_recent_topics() -> list[str]:
    """SSM から直近のトピックIDリストを取得する（最大 RECENT_TOPICS_LIMIT 件）"""
    try:
        response = ssm.get_parameter(Name=SSM_PARAM_PATH)
        ids = json.loads(response["Parameter"]["Value"])
        return ids if isinstance(ids, list) else []
    except ssm.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"SSM読み込みエラー（除外なしで続行）: {e}")
        return []


def save_topic_to_ssm(topic_id: str):
    """選択したトピックを SSM に保存する（最新 RECENT_TOPICS_LIMIT 件を保持）"""
    recent = get_recent_topics()
    recent.append(topic_id)
    recent = recent[-RECENT_TOPICS_LIMIT:]
    try:
        ssm.put_parameter(
            Name=SSM_PARAM_PATH,
            Value=json.dumps(recent),
            Type="String",
            Overwrite=True,
        )
        print(f"SSM保存完了: {recent}")
    except Exception as e:
        print(f"SSM書き込みエラー（無視して続行）: {e}")


# ─── トピック選択 ─────────────────────────────────────────────────────────────

def select_topic_with_bedrock(excluded_ids: list[str]) -> dict:
    """Bedrock を使って重複を避けながらトピックを選択する"""
    available = [t for t in AWS_TOPICS if t["id"] not in excluded_ids]
    if not available:
        # 全トピックが除外済みの場合（通常は発生しない）はリセット
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS

    topic_list = "\n".join([f"- {t['id']}: {t['name']}" for t in available])

    prompt = f"""以下のAWSサービス一覧から、今週の記事テーマを1つランダムに選んでください。
選択する際は、純粋にランダムに選んでください。

{topic_list}

選んだサービスのIDのみを返してください（例: ec2）。説明は不要です。"""

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result   = json.loads(response["body"].read())
    topic_id = result["content"][0]["text"].strip().lower()
    usage = result.get("usage", {})
    print(f"[Bedrock/topic] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")

    # Bedrock の返答が除外リストにない available トピックと一致するか確認
    for topic in available:
        if topic["id"] == topic_id:
            return topic

    # 一致しない場合は available からランダム選択
    return random.choice(available)


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict, today: str) -> tuple[str, bool]:
    """Bedrock を使って記事を生成する。(article_text, is_truncated) を返す"""
    docs_content = fetch_aws_docs(topic["id"])
    docs_section = (
        "## AWS公式ドキュメント（根拠情報）\n"
        "以下はAWS公式ドキュメントから取得した情報です。技術的事実はこの内容を根拠として正確に記述し、矛盾しないようにしてください。\n"
        "ドキュメントに記載のない事実は、確実に知っている場合のみ記述し、不確かな場合は記述しないか「〜の場合があります」等の不確定表現を使ってください。\n\n"
        f"{docs_content}\n\n---\n"
        if docs_content else ""
    )
    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        keywords=topic["keywords"],
        today=today,
        docs_section=docs_section,
    )

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    usage = result.get("usage", {})
    stop_reason = result.get("stop_reason", "unknown")
    is_truncated = stop_reason == "max_tokens"
    print(f"[Bedrock/article] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}, stop={stop_reason}")
    if is_truncated:
        print("[WARNING] 記事がmax_tokensで打ち切られました。記事が不完全な可能性があります。")

    # Bedrock が記事冒頭に YAML frontmatter を付けることがあるため除去する
    if text.lstrip().startswith("---"):
        # 2つ目の "---" までをスキップ
        lines = text.lstrip().splitlines(keepends=True)
        end = 1
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                end = i + 1
                break
        text = "".join(lines[end:]).lstrip()

    return text, is_truncated


# ─── MD 生成（画像プレースホルダー付き） ─────────────────────────────────────

_DIAGRAM_CAPTIONS = [
    "{topic_name} – よく使われる全体構成図",
    "{topic_name} – ハンズオンで構築する構成図",
]


def _make_image_placeholder(png_path: str, topic_name: str, index: int) -> str:
    filename = os.path.basename(png_path)
    caption_tmpl = _DIAGRAM_CAPTIONS[index - 1] if index - 1 < len(_DIAGRAM_CAPTIONS) \
        else "{topic_name} 構成図" + str(index)
    caption = caption_tmpl.format(topic_name=topic_name)
    return (
        f"\n"
        f":::message\n"
        f"📷 **【Zenn投稿時】** `{filename}` をZennエディタでアップロードし、下の画像パスをZenn CDN URLに置き換えてください。\n"
        f":::\n\n"
        f"![{caption}](./images/{filename})\n"
        f"*{caption}*\n"
    )


def _embed_image_placeholders(article: str, png_paths: list[str], topic_name: str) -> str:
    """{DIAGRAM_N} マーカーを画像プレースホルダーに置換する。
    マーカーが見つからない場合はフォールバック挿入（はじめに直後 / ハンズオン直後）。
    """
    if not png_paths:
        return article

    _FALLBACK_HEADINGS = ["はじめに", "ハンズオン"]

    result = article
    for img_idx, png_path in enumerate(png_paths):
        n = img_idx + 1
        marker = "{" + f"DIAGRAM_{n}" + "}"
        placeholder = _make_image_placeholder(png_path, topic_name, n)

        if marker in result:
            result = result.replace(marker, placeholder, 1)
        else:
            # フォールバック: 対応する見出し名の直後に挿入
            lines = result.split("\n")
            target = _FALLBACK_HEADINGS[img_idx] if img_idx < len(_FALLBACK_HEADINGS) else None
            h2_positions = [i for i, line in enumerate(lines) if line.startswith("## ")]
            if target:
                matched = [i for i, line in enumerate(lines)
                           if line.startswith("## ") and target in line]
                insert_idx = matched[0] if matched else \
                    h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            else:
                insert_idx = h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            lines.insert(insert_idx + 1, placeholder)
            result = "\n".join(lines)

    return result


SSM_COUNTER_PATH = "/zenn-article-bot/article-counter"

def _next_article_number(output_dir: str) -> str:
    """SSMカウンターから次の記事番号を取得してインクリメントする（例: '016'）"""
    try:
        resp = ssm.get_parameter(Name=SSM_COUNTER_PATH)
        current = int(resp["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        current = 0
    next_num = current + 1
    ssm.put_parameter(Name=SSM_COUNTER_PATH, Value=str(next_num), Type="String", Overwrite=True)
    return f"{next_num:03d}"


def _cleanup_old_articles(output_dir: str, keep: int = OUTPUT_KEEP_MAX) -> None:
    """output/ 内の記事フォルダが keep 個を超えたら古いものを削除する"""
    import glob
    import shutil
    folders = sorted(glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9]_*")))
    for folder in folders[:-keep] if len(folders) > keep else []:
        shutil.rmtree(folder)
        print(f"古い記事フォルダを削除: {os.path.basename(folder)}")


def save_to_local(topic: dict, article: str, timestamp: str) -> tuple[str, list[str]]:
    """記事を MD ファイルに保存し、構成図 PNG も生成する。(mdパス, pngパスリスト) を返す"""
    output_dir = os.path.expanduser(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    base_name   = f"{timestamp}_{topic['id']}"
    num         = _next_article_number(output_dir)
    article_dir = os.path.join(output_dir, f"{num}_{base_name}")
    images_dir  = os.path.join(article_dir, "images")
    os.makedirs(article_dir, exist_ok=True)
    os.makedirs(images_dir,  exist_ok=True)

    md_path  = os.path.join(article_dir, f"{base_name}.md")
    png_base = os.path.join(images_dir,  f"{base_name}_diagram")

    # 構成図を生成（最大2枚）
    png_paths = generate_diagrams(topic["id"], png_base)

    # 図1・図2ともに {DIAGRAM_N} マーカーで記事中に挿入（マーカー不在時はフォールバック）
    article_with_images = _embed_image_placeholders(article, png_paths, topic["name"])

    # Zennフロントマター用メタ情報
    meta = _ZENN_META.get(topic["id"], {"emoji": "☁️", "topics": ["aws", "クラウド"]})
    topics_json = json.dumps(meta["topics"], ensure_ascii=False)

    full_content = f"""---
title: "{topic['name']}：{topic['subtitle']}"
emoji: "{meta['emoji']}"
type: "tech"
topics: {topics_json}
published: false
---

{article_with_images}

<!-- 生成情報: topic={topic['id']} / generated_at={timestamp} / chars={len(article)} / images={len(png_paths)}枚 -->
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    _cleanup_old_articles(output_dir)
    return md_path, png_paths


# ─── S3 アップロード ──────────────────────────────────────────────────────────

def upload_to_s3(md_path: str, png_paths: list[str], s3_folder: str) -> str:
    """MD ファイルと PNG 画像を S3 にアップロードし、S3 フォルダパスを返す"""
    s3_base = f"{S3_PREFIX}/{s3_folder}"

    md_key = f"{s3_base}/{os.path.basename(md_path)}"
    s3.upload_file(md_path, S3_BUCKET, md_key, ExtraArgs={"ContentType": "text/markdown"})
    print(f"S3アップロード: s3://{S3_BUCKET}/{md_key}")

    for png_path in png_paths:
        png_key = f"{s3_base}/images/{os.path.basename(png_path)}"
        s3.upload_file(png_path, S3_BUCKET, png_key, ExtraArgs={"ContentType": "image/png"})
        print(f"S3アップロード: s3://{S3_BUCKET}/{png_key}")

    return f"s3://{S3_BUCKET}/{s3_base}/"


# ─── CFn テンプレート検証 ────────────────────────────────────────────────────

def validate_cfn_in_article(article_text: str) -> list[str]:
    """記事内の完全なCFnテンプレートをcloudformation:ValidateTemplateでチェックする"""
    import re
    import yaml as _yaml

    issues = []
    pattern = r'```(?:yaml|YAML)(?::[^\n]*)?\n(.*?)```'
    blocks = re.findall(pattern, article_text, re.DOTALL)

    complete = []
    for i, block in enumerate(blocks, 1):
        if 'Resources:' not in block:
            continue
        try:
            parsed = _yaml.safe_load(block)
            if isinstance(parsed, dict) and 'Resources' in parsed:
                complete.append((i, block))
        except _yaml.YAMLError as e:
            issues.append(f"ブロック{i}: YAML構文エラー — {str(e)[:200]}")

    if not complete and not issues:
        return []

    for i, block in complete:
        try:
            cfn.validate_template(TemplateBody=block)
        except Exception as e:
            msg = getattr(e, 'response', {}).get('Error', {}).get('Message', str(e))
            issues.append(f"ブロック{i}: {str(msg)[:300]}")

    print(f"[CFn検証] 完全テンプレート{len(complete)}件検証 / 問題{len(issues)}件")
    return issues


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, s3_url: str = "", is_truncated: bool = False,
    cfn_issues: list | None = None,
):
    """SES でメール通知を送信する"""
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    subject = (
        f"【⚠️ 記事が途中で切れています】{topic['name']} - {timestamp}"
        if is_truncated else
        f"【Zenn記事生成完了】{topic['name']}の記事が生成されました - {timestamp}"
    )

    png_list_html = "".join(
        f'<li><code>{os.path.basename(p)}</code></li>' for p in png_paths
    ) if png_paths else "<li>（生成なし）</li>"

    s3_row = (
        f'<tr><td style="padding:5px;font-weight:bold;">S3保存先</td>'
        f'<td><code>{s3_url}</code></td></tr>'
        if s3_url else ""
    )
    download_row = (
        '<li>S3からローカルにダウンロード: '
        '<code>bash ~/Zer0/002_Zenn_Auto_Article_Bot/download_article.sh</code></li>'
        if s3_url else ""
    )

    cfn_issues = cfn_issues or []
    truncation_warning_text = """
⚠️ 警告: 記事が途中で切れています
記事の生成がmax_tokensに達したため、末尾が不完全な可能性があります。
Zennに投稿する前に内容を必ず確認してください。
""" if is_truncated else ""

    cfn_warning_text = (
        "⚠️ CFnテンプレート検証で問題が見つかりました:\n"
        + "\n".join(f"  - {i}" for i in cfn_issues) + "\n"
    ) if cfn_issues else ""

    body_text = f"""Zenn技術記事の自動生成が完了しました。
{truncation_warning_text}{cfn_warning_text}
■ 記事情報
- テーマ: {topic['name']}（{topic['subtitle']}）
- 文字数: {char_count:,}文字
- 生成日時: {timestamp}
- 構成図PNG: {diagram_info}
- S3保存先: {s3_url}

■ 記事プレビュー（先頭300文字）
{preview}...

■ 次のアクション
1. bash ~/Zer0/002_Zenn_Auto_Article_Bot/download_article.sh
2. Zennエディタで新規記事を作成（または zenn-cli で管理）
3. MDファイルの内容を貼り付け
4. :::message ブロック内の指示に従ってPNGをアップロード・差し替え
5. published: false → true に変更して公開

このメールは自動送信されています。
"""

    truncation_warning_html = """
  <div style="background:#fff3cd;border:2px solid #f0ad4e;padding:15px;border-radius:8px;margin:20px 0;">
    <h3 style="color:#856404;margin-top:0;">⚠️ 記事が途中で切れています</h3>
    <p style="color:#856404;margin:0;">
      記事の生成が <code>max_tokens</code> に達したため、末尾が不完全な可能性があります。<br>
      Zennに投稿する前に内容を必ず確認してください。
    </p>
  </div>
""" if is_truncated else ""

    cfn_issues_html = (
        '<div style="background:#fde8e8;border:2px solid #e53e3e;padding:15px;border-radius:8px;margin:20px 0;">'
        '<h3 style="color:#c53030;margin-top:0;">⚠️ CFnテンプレート検証で問題が見つかりました</h3>'
        '<ul style="color:#c53030;margin:0;">'
        + "".join(f'<li><code>{i}</code></li>' for i in cfn_issues)
        + '</ul></div>'
    ) if cfn_issues else (
        '<div style="background:#e8f5e9;border:1px solid #66bb6a;padding:10px 15px;border-radius:8px;margin:20px 0;">'
        '<p style="color:#2e7d32;margin:0;">✅ CFnテンプレート検証 — 問題なし</p>'
        '</div>'
    )

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#3EA8FF;">Zenn技術記事の自動生成が完了しました</h2>
  {truncation_warning_html}
  {cfn_issues_html}

  <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事情報</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:5px;font-weight:bold;">テーマ</td>
          <td>{topic['name']}（{topic['subtitle']}）</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">文字数</td>
          <td>{char_count:,}文字</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">生成日時</td>
          <td>{timestamp}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">構成図PNG</td>
          <td><ul style="margin:0;padding-left:16px;">{png_list_html}</ul></td></tr>
      {s3_row}
    </table>
  </div>

  <div style="background:#fff8e1;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事プレビュー</h3>
    <p style="color:#555;">{preview}...</p>
  </div>

  <div style="background:#e8f5e9;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>次のアクション</h3>
    <ol>
      {download_row}
      <li>Zennエディタで新規記事を作成</li>
      <li>MDファイルの内容を貼り付け</li>
      <li><code>:::message</code> ブロックの指示に従ってPNGをアップロード・差し替え</li>
      <li><code>published: false</code> → <code>true</code> に変更して公開</li>
    </ol>
  </div>

  <p style="color:#999;font-size:12px;">このメールは自動送信されています。</p>
</body>
</html>
"""

    ses.send_email(
        Source=SES_SENDER_EMAIL,
        Destination={"ToAddresses": [SES_RECIPIENT_EMAIL]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"},
            },
        },
    )


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def run():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    today     = now.strftime("%Y-%m-%d")   # コードサンプル日付用 (例: 2026-04-12)

    print(f"[{timestamp}] Zenn技術記事自動生成を開始します")

    # Step 1: 直近トピック取得 → Bedrock でトピック選択 → SSM に保存
    print("Step 1: Bedrockでトピックを選択中...")
    recent_topics = get_recent_topics()
    print(f"  除外トピック（直近{len(recent_topics)}件）: {recent_topics}")
    topic = select_topic_with_bedrock(excluded_ids=recent_topics)
    print(f"  選択されたトピック: {topic['name']}")
    save_topic_to_ssm(topic["id"])

    # Step 2: 記事生成
    print("Step 2: 記事を生成中（2,000〜3,500文字）...")
    article, is_truncated = generate_article(topic, today)
    char_count = len(article)
    print(f"  記事生成完了: {char_count:,}文字")

    # Step 3: ローカル保存（MD + PNG）
    print("Step 3: ファイル保存中（記事MD + 構成図PNG）...")
    md_path, png_paths = save_to_local(topic, article, timestamp)
    print(f"  MD保存完了: {md_path}")
    print(f"  PNG生成完了: {len(png_paths)}枚 {png_paths}" if png_paths else "  PNG生成: スキップ")

    # Step 4: S3 アップロード
    print("Step 4: S3にアップロード中...")
    s3_folder = f"{timestamp}_{topic['id']}"
    s3_url    = upload_to_s3(md_path, png_paths, s3_folder)
    print(f"  S3アップロード完了: {s3_url}")

    # Step 5: CFnテンプレート検証
    print("Step 5: CFnテンプレートを検証中...")
    try:
        cfn_issues = validate_cfn_in_article(article)
        if cfn_issues:
            print(f"  ⚠️ CFn問題検出: {len(cfn_issues)}件")
        else:
            print("  ✓ CFn検証問題なし")
    except Exception as e:
        print(f"  CFn検証スキップ（無視して続行）: {e}")
        cfn_issues = []

    # Step 6: SES メール通知
    print("Step 6: メール通知を送信中...")
    send_email_notification(topic, article, md_path, png_paths, timestamp, s3_url, is_truncated, cfn_issues)
    print("  メール送信完了")

    print(f"[{timestamp}] 処理が正常に完了しました")
    return topic, char_count, md_path, png_paths, s3_url


def lambda_handler(event, context):
    topic, char_count, md_path, png_paths, s3_url = run()
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "記事生成が完了しました",
                "topic":   topic["name"],
                "character_count": char_count,
                "images_generated": len(png_paths),
                "s3_url": s3_url,
            },
            ensure_ascii=False,
        ),
    }


if __name__ == "__main__":
    run()
