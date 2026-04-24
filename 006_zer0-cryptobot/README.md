# 006_Zer0_CryptoBot — 仮想通貨自動売買Bot

SOL / AVAX / ADA を対象に、Binance のシグナルと bitbank の注文執行を組み合わせた**現物自動売買 Bot**。
EventBridge で **4時間毎**に自動起動し、テクニカル指標で買いタイミングを自動判定・発注・管理する。

## 全体構成図

![006 全体構成図](./images/006_architecture.png)

## このBotの仕組み（簡単に）

```
4時間毎に自動起動
    ↓
① 相場の状態をチェック（Analyzer）
    ├─ BTCが下落トレンド → 今回は何もしない（全スキップ）
    └─ BTCが上昇トレンド → 各コインを分析
            ↓ シグナル（買いタイミング）があれば
② 注文を出す・管理する（Executor）
    ├─ 新規: bitbankに指値買い注文を出す
    ├─ 買い約定後: 利確・損切り注文を自動発注
    ├─ 利確第1段階（TP1）後: 損切りをブレイクイーブンに移動
    └─ トレーリングSL: 価格上昇に合わせて損切りラインを自動引き上げ
            ↓
③ 売買結果をメールで通知（SES）
```

## フォルダ構成

```
006_Zer0_CryptoBot/
├── lambda/
│   ├── analyzer/
│   │   ├── lambda_function.py   # シグナル判定 Lambda
│   │   └── requirements.txt
│   └── executor/
│       ├── lambda_function.py   # 注文執行・ポジション管理 Lambda
│       └── requirements.txt
├── backtest/
│   ├── backtest.py              # ローカルバックテスト（過去2年分で検証）
│   ├── result.png               # バックテスト損益推移グラフ
│   └── requirements.txt
├── images/
│   └── 006_architecture.png    # 全体構成図
├── scripts/
│   ├── deploy.sh               # AWSへのデプロイスクリプト
│   └── setup_ssm.sh            # APIキーをAWSに登録するスクリプト
├── README.md
├── システム仕様書.md            # 詳細仕様（用語解説付き）
└── template.yaml               # AWS SAM テンプレート（インフラ定義）
```

## 取引仕様

| 項目 | 内容 |
| ---- | ---- |
| 取引所 | bitbank（国内・現物取引） |
| 対象コイン | SOL（ソラナ）/ AVAX（アバランチ）/ ADA（カルダノ） |
| データソース | Binance（海外取引所）の4時間足価格データ |
| 最大同時保有 | 3コインまで |
| 1ポジション投資額 | 残高 ÷ 空きスロット数 × 90%（自動計算） |
| 最小発注額 | 1,000円 |

## エントリー条件（4つすべて満たしたときだけ買う）

| # | 条件 | 意味 |
|---|------|------|
| 1 | BTC が 200EMA 以上 | ビットコイン全体が上昇トレンド |
| 2 | 対象コインが 200EMA 以上 | そのコイン自体も上昇トレンド |
| 3 | Supertrend が**緑転換** | 「下落→上昇」に切り替わった瞬間だけ |
| 4 | 出来高が直近20本平均より多い | 取引が活発で信頼性が高い |

> **Supertrend 緑転換**: 前の4時間が「赤（下落）」で今の4時間が「緑（上昇）」に変わった1本だけが対象。継続中は発動しない。

## 利確・損切りの仕組み

| 注文 | 価格 | 数量 | 説明 |
| ---- | ---- | ---- | ---- |
| TP1（第1利確） | 買値 + ATR×2 | 30% | 最初の利確。ここで損切りをブレイクイーブンに移動 |
| トレーリングSL | 最高値 − ATR×1.5 | 70% | 価格上昇に合わせて自動で引き上げ。最終的な利確 |
| 初期SL（損切り） | 買値 − ATR×1.5 | 100% | TP1前に価格が下落したときの損切り |

> **ATR（Average True Range）**: 価格の「振れ幅」を表す指標。値が大きいほど値動きが荒い。これを基準に利確・損切り幅を自動設定するため、相場の状況に合わせた柔軟な設定になる。

> **トレーリングSL**: 例えば SOL が1,500円で買い → TP1の1,800円で30%売却 → その後2,000円に上昇したとき損切りラインも1,700円に引き上げ → 最終的に1,700円を下回ったら残り70%を自動売却。上昇した利益を守りながら追いかける。

## バックテスト結果（過去2年分・4時間足）

> **バックテスト**: 実際に取引する前に、過去のデータでシミュレーションして戦略の有効性を確認すること。

| 指標 | 説明 | 値 | 合格基準 |
| ---- | ---- | -- | -------- |
| 勝率 | 利益が出たトレードの割合 | **59.6%** | ≥50% ✓ |
| PF（プロフィットファクター） | 総利益÷総損失。高いほど優秀 | **1.74** | ≥1.5 ✓ |
| 最大DD（ドローダウン） | 資産ピークからの最大減少率 | **3.4%** | ≤30% ✓ |
| 資本成長（2年） | 10,000円スタートで | **+16.9%（11,686円）** | — |
| 月平均トレード数 | 年47回÷24ヶ月 | **約2.0回/月** | — |

## AWSリソース一覧

| リソース | 名称 | 設定 |
| -------- | ---- | ---- |
| Lambda | Zer0-CryptoBot-Analyzer | Python 3.14, 256MB, 120秒 |
| Lambda | Zer0-CryptoBot-Executor | Python 3.14, 256MB, 300秒 |
| EventBridge | Zer0-CryptoBot-Schedule | 4時間毎（UTC 0/4/8/12/16/20時） |
| SSM | /Zer0/CryptoBot/bitbank/api_key | SecureString（暗号化保存） |
| SSM | /Zer0/CryptoBot/bitbank/api_secret | SecureString（暗号化保存） |
| SSM | /Zer0/CryptoBot/state | String（ポジション状態JSON） |
| SES | — | 売買通知メール送信 |
| CloudWatch | /aws/lambda/Zer0-CryptoBot-* | ログ保存期間 7日 |

## 月額コスト

| 費目 | 金額 |
| ---- | ---- |
| AWS（Lambda・EventBridge・SSM・SES・CloudWatch） | **$0**（無料枠内） |
| bitbank 取引手数料 | 約**10〜15円/月**（0.12% × 月1.5トレード想定） |

## デプロイ手順

```bash
# 1. APIキーをAWSに登録（初回のみ）
bash scripts/setup_ssm.sh

# 2. AWSにデプロイ
export SENDER_EMAIL="送信元メールアドレス"
export RECIPIENT_EMAIL="通知先メールアドレス"
bash scripts/deploy.sh
```

## 動作確認コマンド

```bash
# 発注なしでExecutorの動作確認（テスト用）
aws lambda invoke \
  --function-name Zer0-CryptoBot-Executor \
  --payload '{"signals":[]}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/executor.json \
  --region ap-northeast-1 && cat /tmp/executor.json

# Analyzerのログを確認（直近10分）
aws logs tail /aws/lambda/Zer0-CryptoBot-Analyzer --since 10m --region ap-northeast-1

# 現在のポジション状態を確認
aws ssm get-parameter --name "/Zer0/CryptoBot/state" --region ap-northeast-1
```

## 注意事項

- **初期資金**: 10,000円以上を bitbank に入金推奨。残高1,000円未満で新規発注停止
- **APIキー権限**: 「現物取引」「残高照会」のみ許可。**出金権限は絶対に付与しない**
- **確定申告**: 仮想通貨の売却益は雑所得として課税対象
- **バックテストの限界**: 過去データによる検証。将来の収益を保証するものではない

## 緊急停止

```bash
# EventBridgeスケジュールを無効化（botを止める）
aws scheduler update-schedule \
  --name Zer0-CryptoBot-Schedule \
  --state DISABLED \
  --schedule-expression "cron(0 */4 * * ? *)" \
  --flexible-time-window '{"Mode": "OFF"}' \
  --target "{\"Arn\": \"$(aws lambda get-function --function-name Zer0-CryptoBot-Analyzer --region ap-northeast-1 --query Configuration.FunctionArn --output text)\", \"RoleArn\": \"$(aws iam get-role --role-name Zer0-CryptoBot-SchedulerRole-ap-northeast-1 --query Role.Arn --output text)\"}" \
  --region ap-northeast-1
```

## バックテスト実行

```bash
pip install -r backtest/requirements.txt
python3 backtest/backtest.py
# → コンソールに勝率/PF/DD/資本成長を表示
# → backtest/result.png に損益推移グラフを保存
```

## 詳細仕様

用語解説・技術詳細・運用ガイドは [システム仕様書.md](./システム仕様書.md) を参照。
