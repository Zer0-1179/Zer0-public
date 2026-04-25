# 006_Zer0_CryptoBot — 仮想通貨自動売買Bot

Binance のシグナルを使い bitbank の**信用取引**で BTC / ETH / SOL を**ロング・ショート両方向**に自動売買する Bot。
EventBridge で **4時間毎**に自動起動し、テクニカル指標でエントリータイミングを自動判定・発注・管理する。

## 全体構成図

![006 全体構成図](./images/006_architecture.png)

## このBotの仕組み（簡単に）

```
4時間毎に自動起動
    ↓
① 相場の状態をチェック（Analyzer）
    ├─ BTCが200EMA以上 → 上昇相場 → ロングシグナルを探す
    └─ BTCが200EMA以下 → 下落相場 → ショートシグナルを探す
            ↓ 常にExecutorを呼び出し（シグナルの有無に関わらず）
② 注文を出す・管理する（Executor）
    ├─ [安全確認] 証拠金維持率チェック
    │     ├─ 150%以下 → ⚠️警告メール送信（継続）
    │     └─ 120%以下 / 追証中 → 🚨全ポジション成行決済して停止
    ├─ 新規: bitbank信用取引に指値注文（ロング最大2 / ショート最大2）
    ├─ 約定後: 利確・損切り注文を自動発注（発注後に3回リトライで存在確認）
    ├─ 利確第1段階（TP1）後: 損切りをブレイクイーブンに移動
    └─ トレーリングSL: 価格変動に合わせて損切りラインを自動更新
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

| 項目                  | 内容                                           |
| --------------------- | ---------------------------------------------- |
| 取引所                | bitbank（国内・信用取引）                      |
| 対象コイン            | BTC / ETH / SOL（信用取引対応ペアのみ）        |
| 取引方向              | ロング（買い建て）/ ショート（売り建て）両方向 |
| データソース          | Binance（海外取引所）の4時間足価格データ       |
| 最大同時保有          | 3ポジションまで                                |
| 1ポジション投資証拠金 | 証拠金残高 ÷ 空きスロット数 × 90%（自動計算）  |
| 最小発注額            | 1,000円                                        |

## エントリー条件

**市場方向の判定（共通）**  

| BTC 価格 vs 200EMA | 市場方向                              |
| ------------------ | ------------------------------------- |
| BTC ≥ 200EMA       | ロング市場 → ロングシグナルを探す     |
| BTC < 200EMA       | ショート市場 → ショートシグナルを探す |

**各コインのエントリー条件**  

| #   | ロング                           | ショート                         |
| --- | -------------------------------- | -------------------------------- |
| 1   | 対象コインが 200EMA 以上         | 対象コインが 200EMA 以下         |
| 2   | Supertrend が**緑転換**（赤→緑） | Supertrend が**赤転換**（緑→赤） |
| 3   | 出来高が直近20本平均より多い     | 出来高が直近20本平均より多い     |

## 利確・損切りの仕組み

|                      | ロング                       | ショート                     |
| -------------------- | ---------------------------- | ---------------------------- |
| TP1                  | 買値 **+** ATR×2（30%利確）  | 売値 **−** ATR×2（30%利確）  |
| 初期SL               | 買値 **−** ATR×1.5           | 売値 **+** ATR×1.5           |
| トレーリングSL初期値 | 約定価格（ブレイクイーブン） | 約定価格（ブレイクイーブン） |
| トレーリング更新     | 最高値 − ATR×1.5 で引き上げ  | 最安値 + ATR×1.5 で引き下げ  |

## バックテスト結果（過去2年分・4時間足）

| 指標                         | 値                                         | 合格基準 |
| ---------------------------- | ------------------------------------------ | -------- |
| 勝率                         | **60.9%**                                  | ≥50% ✓   |
| PF（プロフィットファクター） | **1.56**                                   | ≥1.5 ✓   |
| 最大DD（ドローダウン）       | **9.5%**                                   | ≤30% ✓   |
| 資本成長（2年）              | **+36.5%（10,000円→13,653円）**            | —        |
| 月平均トレード数             | **約5.5回**（ロング:66件 / ショート:67件） | —        |

## AWSリソース一覧

| リソース    | 名称                               | 設定                            |
| ----------- | ---------------------------------- | ------------------------------- |
| Lambda      | Zer0-CryptoBot-Analyzer            | Python 3.14, 256MB, 120秒       |
| Lambda      | Zer0-CryptoBot-Executor            | Python 3.14, 256MB, 300秒       |
| EventBridge | Zer0-CryptoBot-Schedule            | 4時間毎（UTC 0/4/8/12/16/20時） |
| SSM         | /Zer0/CryptoBot/bitbank/api_key    | SecureString（暗号化保存）      |
| SSM         | /Zer0/CryptoBot/bitbank/api_secret | SecureString（暗号化保存）      |
| SSM         | /Zer0/CryptoBot/state              | String（ポジション状態JSON）    |
| SES         | —                                  | 売買通知メール送信              |
| CloudWatch  | /aws/lambda/Zer0-CryptoBot-*       | ログ保存期間 7日                |

## 月額コスト

| 費目                                             | 金額                                                    |
| ------------------------------------------------ | ------------------------------------------------------- |
| AWS（Lambda・EventBridge・SSM・SES・CloudWatch） | **$0**（無料枠内）                                      |
| bitbank 取引手数料                               | BTC: **0%** / ETH・SOL: **−0.04%（リベート収入）** 往復 |
| bitbank 日次利息                                 | 0.04%/日（保有日数分） → 月間コスト**数円〜数十円程度** |

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

- **初期資金**: 10,000円でテスト運用開始（3ポジション分の証拠金）
- **APIキー権限**: 「取引」「残高照会」のみ許可。**出金権限は付与しない**
- **追証**: 委託保証金率が **50%以下**になると翌営業日15時に追証発生（24時間以内に解消要）
- **ロスカット**: 委託保証金率が **25%以下**で bitbank が全建玉を強制決済
- **Bot自動監視**: 4時間毎に維持率チェック。150%以下で警告・120%以下で全ポジション自動成行決済
- **日次利息**: BTC/ETH 0.04%/日・SOL 0%（キャンペーン〜2025/6/30）が保有期間分発生
- **確定申告**: 現行は雑所得（最大55%）。**2028年1月以降は申告分離課税20.315%に改正予定**

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
