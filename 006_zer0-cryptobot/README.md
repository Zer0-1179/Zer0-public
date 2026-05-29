# 006 Zer0 CryptoBot

> BTC 200EMA で市場方向を判定し bitbank 信用取引で BTC/ETH/SOL をロング・ショート両方向に4時間毎自動売買するサーバーレスBot。5年バックテスト（LUNA崩壊・FTX破綻含む）で勝率61.9%、PF1.62を確認済み。全テスト完了・本番稼働中。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20EventBridge%20%7C%20SSM-orange)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://python.org)
[![Exchange](https://img.shields.io/badge/取引所-bitbank-black)](https://bitbank.cc)
[![Cost](https://img.shields.io/badge/月額-~%240-green)](https://aws.amazon.com/pricing)

## 概要

| 項目           | 内容                                                                  |
| -------------- | --------------------------------------------------------------------- |
| 取引所         | bitbank（信用取引 / レバレッジ最大2倍）                               |
| 対象コイン     | BTC / ETH / SOL                                                       |
| 取引方向       | ロング + ショート 両方向                                              |
| シグナルデータ | Binance API（4時間足 OHLCV / リアルタイム出来高）                     |
| 実行頻度       | Analyzer: 4時間毎 / Executor: 30分毎                                  |
| リスク管理     | トレーリング SL / TP1 部分利確（30%） / 証拠金維持率監視              |
| 月額コスト     | AWS ~$0（無料枠内）/ 取引手数料：BTC 0% / ETH・SOL -0.04%（リベート） |

## アーキテクチャ

![アーキテクチャ図](images/006_architecture.png)

```text
EventBridge Scheduler（Analyzer: 4時間毎 / Executor: 30分毎）
  ├─▶ Analyzer Lambda
  │     ├─ Binance API（4時間足 OHLCV・出来高取得）
  │     ├─ BTC 200EMA で市場方向（ロング/ショート）判定
  │     ├─ Supertrend 転換 + Volume スパイク = エントリーシグナル
  │     └─ SSM に シグナル・State 書き込み
  │
  ├─▶ Executor Lambda
  │     ├─ SSM からシグナル・State 読み込み
  │     ├─ bitbank API（新規注文 / TP1 / トレーリング SL 更新）
  │     ├─ 証拠金維持率監視（危険水準で自動成行決済）
  │     └─ SSM State 更新
  │
  ├─▶ FailureNotifier Lambda（DLQ トリガー）
  │     └─ SES（エラーメール通知）
  │
  └─▶ WeeklySummary Lambda（毎週日曜 09:00 JST）
        └─ SES（週次損益レポート）
```

## エントリー条件

### 市場方向判定（BTC 4時間足）

- **ロングモード**: BTC 終値 > BTC 200EMA
- **ショートモード**: BTC 終値 < BTC 200EMA

### エントリーシグナル（BTC/ETH/SOL 各独立）

| 条件            | 詳細                                                 |
| --------------- | ---------------------------------------------------- |
| 200EMA クロス   | 終値が 200EMA を上抜け（ロング）/ 下抜け（ショート） |
| Supertrend 転換 | 上昇転換（ロング）/ 下降転換（ショート）             |
| Volume スパイク | 直近20本の平均出来高より大きい                       |

全条件同時成立時のみエントリー → 月平均約5〜6回の厳選エントリー

## リスク管理

| 仕組み               | 設定値                                        |
| -------------------- | --------------------------------------------- |
| TP1（部分利確）      | エントリー価格 ± ATR×2 で 30% 決済            |
| トレーリング SL      | TP1 約定後、最高値/最安値から ATR×1.5 を追従  |
| 最大保有ポジション   | 各コイン 1つ（BTC+ETH+SOL で最大3ポジション） |
| 緊急決済             | 証拠金維持率が危険水準を下回ると自動成行決済  |
| 24h 未約定キャンセル | エラー時の保険（成行は通常即時約定）          |

## バックテスト結果

| 期間              | 取引数 | 勝率  | PF   | 最大DD | 資本成長 |
| ----------------- | ------ | ----- | ---- | ------ | -------- |
| 2年（2024〜2026） | 133    | 60.9% | 1.56 | 9.5%   | +36.5%   |
| 3年（2023〜2026） | 204    | 63.2% | 1.63 | 9.5%   | +66.4%   |
| 4年（2022〜2026） | 291    | 61.5% | 1.51 | 9.5%   | +85.7%   |
| 5年（2021〜2026） | 360    | 61.9% | 1.62 | 9.5%   | +190.3%  |

> LUNA崩壊（2022年5月）・FTX破綻（2022年11月）を含む最悪シナリオでも全期間で合格基準（勝率≥50%・PF≥1.5・DD≤30%）をクリア。

## 実装のこだわり

### 1. Analyzer / Executor の Lambda 分離設計

シグナル検出と注文実行を分離し、SSM Parameter Store で状態を受け渡す設計。Executor が高頻度（30分毎）でトレーリング SL を更新できるのに対し、Analyzer は4時間毎のバッチ処理で済む。処理の責務分離によりデバッグ・テストが容易になり、Executor のみ停止してシグナル確認だけ継続するような運用も可能。

### 2. Binance シグナル × bitbank 発注の設計

bitbank の板が薄いため価格シグナルに bitbank 価格を使うとノイズが大きい。**Binance の4時間足**（高流動性・信頼性の高い価格データ）でシグナル判定し、bitbank で**成行注文**を発注するアーキテクチャを採用。シグナルが出た瞬間に確実にエントリーすることを優先し、トレンドフォロー戦略としての整合性を高めている。

### 3. SSM による無人運用の実現

ポジション State（保有コイン・エントリー価格・SL水準）を SSM Parameter Store に保存することで、Lambda がステートレスに動作。再デプロイ・コールドスタート後も State が維持され、24時間無人運用を実現。

### 4. 証拠金維持率の多段階リスク制御

Executor が実行するたびに証拠金維持率を確認：

- **警告レベル**: SES でメール通知
- **危険レベル**: 全ポジションを自動成行決済
追証・ロスカットに到達する前に自動的にリスクをゼロにする仕組み。

## 技術スタック

| レイヤー         | 技術                                                  |
| ---------------- | ----------------------------------------------------- |
| 実行基盤         | AWS Lambda（Python 3.14）× 4関数                      |
| スケジューリング | Amazon EventBridge Scheduler（2スケジュール）         |
| 状態管理         | AWS SSM Parameter Store（ポジション State・シグナル） |
| 通知             | Amazon SES（エラー通知・週次レポート）                |
| 信頼性           | SQS DLQ + CloudWatch Alarm                            |
| データソース     | Binance API（REST）/ python-binance                   |
| 取引所 API       | bitbank API（python-bitbankcc）                       |
| IaC              | CloudFormation（22リソース全管理）                    |

## ディレクトリ構成

```text
006_Zer0_CryptoBot/
├── lambda/
│   ├── analyzer/        # シグナル検出
│   │   └── lambda_function.py
│   ├── executor/        # 注文実行・SL管理
│   │   └── lambda_function.py
│   ├── failure_notifier/ # DLQ エラー通知
│   └── weekly_summary/  # 週次レポート
├── backtest/
│   └── backtest.py      # 5年バックテスト
├── scripts/
│   ├── setup_ssm.sh     # SSM パラメータ初期化
│   ├── deploy.sh        # デプロイスクリプト
│   └── test_invoke.sh   # テストシナリオ（10種）
├── cfn-cryptobot.yaml
└── images/
    └── 006_architecture.png
```

## デプロイ

```bash
# 1. SSM パラメータ初期化（API キー設定）
bash scripts/setup_ssm.sh

# 2. CloudFormation + Lambda デプロイ
bash scripts/deploy.sh
```

## テスト / 動作確認

```bash
# シナリオ別テスト（10種）
bash scripts/test_invoke.sh [空シグナル|fulltest|SL強制|TP1強制|ロング|ショート|...]

# バックテスト実行
python3 backtest/backtest.py --years 5
python3 backtest/backtest.py --years 5 --multi  # BTC/ETH/SOL 複数同時
```

## 緊急停止

```bash
# EventBridge を無効化してBot停止（ポジションは保持）
aws scheduler update-schedule --name zer0-cryptobot-analyzer \
  --state DISABLED --region ap-northeast-1
aws scheduler update-schedule --name zer0-cryptobot-executor \
  --state DISABLED --region ap-northeast-1
```

## 注意事項

- 初期必要資金: bitbank 信用取引口座に最低10,000円
- APIキー権限: 取引権限・残高照会権限のみ（**出金権限は絶対に付与しない**）
- 本Botの運用は自己責任。過去のバックテスト結果は将来の利益を保証しない
- 2028年以降の確定申告では申告分離課税が適用予定（税率20%）
