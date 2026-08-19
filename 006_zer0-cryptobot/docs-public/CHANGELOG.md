# 006_Zer0_CryptoBot 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-04-24

### 初版リリース（v1）

- Binance分析→bitbank発注→SSMステート管理の基本フロー

### 信用取引対応（v2）

- 現物→信用に変更。ロング+ショート双方向対応

## 2026-04-27

### SL構造変更（v2.1）

- TP1(30%)+SL(70%)=100% に統一。SL約定時に TP1 を自動キャンセル（bitbank 超過発注拒否リスク解消）

## 2026-04-28

### bitbank API修正（v2.2）

- position_side必須・stop_limit SL・残30%自動クローズに対応

### 安定性改善10件（v2.3）

- 証拠金維持率閾値・SSMリトライ・テストスクリプト拡充等

### 実行頻度・失敗通知（v2.4）

- Executor 30分毎化・FailureNotifier Lambdaを追加

## 2026-05-19

### Supertrend検出バグ修正（v2.5）

- 未確定足除外でSupertrend転換を正確に検出するバグ修正

## 2026-05-28

### エントリー方式変更（v2.6）

- エントリーを成行注文に変更

## 2026-06-10

### 取引履歴記録機能を追加（v2.7）

- 全決済パスで確定損益をS3に追記し、WeeklySummaryが週次/累計損益・勝率・PFを集計
- 戦略改善4案（ADX・日足HTF・遅延エントリー・XRP追加）をバックテストで比較し全て不採用
- deploy.shのSIGPIPEバグ修正（`| true`→`|| true`）

## 2026-06-11

### TP/SL倍率変更（v2.8）

- 勝率向上のためTP/SL倍率を変更（TP1 2.0→1.75 / 初期SL 1.5→2.0 / トレール 1.5→1.0）
- 全期間バックテストで勝率62%→73%・PF1.93・5年資本成長+234%に改善

## 2026-06-15

### コードレビュー反映 H-1/H-3/M-6（v2.9）

- CloudWatch Logs保持を関数別に適正化（Executor 3日/他7日）
- 「SQS DLQ」誇大記載を実態（EventInvokeConfigのOnFailure通知）に修正
- Executorに`ReservedConcurrentExecutions: 1`を設定し二重発注を防止。H-2/H-4/M-1/M-5は対応済み

### コードレビューMEDIUM 3件修正（v3.0）

- M-2: 約定情報取得を`order_fill()`ヘルパーに集約し、欠落・型不正時は次回再評価へスキップ
- M-3: `sol_jpy`の`price_prec`を0→1に修正（実APIに一致）
- M-4: 取引履歴の1決済=1オブジェクト設計を明記し、WeeklySummaryの履歴読込をprefix集計へ修正

### TP/SL再最適化・dstフィルター（v3.1）

- 現実コスト込みバックテストで旧v2.8がPF0.96と負け越しと判明
- TP/SL倍率を再最適化（TP1 1.75→1.25/初期SL 2.0→2.5/トレール 1.0→0.75、全期間PF1.15）
- Analyzerにdst（ダブルSupertrend）フィルターを追加し勝率72.9%・最大DD5.2%に改善

### bitbank公式API仕様照合でバグ1件修正（v3.2）

- TP1注文喪失検知のstatus文字列がAPIに存在しない値で永久に発火しないデッドコードだったため、実際に返る`CANCELED_UNFILLED`/`CANCELED_PARTIALLY_FILLED`/`REJECTED`に修正
- 注文・キャンセル・証拠金APIの他項目は仕様と一致を確認済み

### 全Lambda徹底監査でバグ2件修正（v3.3）

- 緊急決済が`buy_pending`の約定済み建玉を決済せず残すリスク → 実約定数量を取得し成行決済
- トレーリング移行時に旧SLキャンセル未確認のまま新SLを発注すると二重決済注文になる恐れ → 消滅確認できない場合は次回再試行
- `deploy.sh`に`SKIP_SYNC`フラグ追加。他の監査項目は問題なし

## 2026-06-19

### Phase B即時TP1/SL発注＋Opusレビュー修正（v3.4）

- 成行発注後に約定を最大20秒ポーリングしTP1/SLを即時発注（旧設計は最大30分のノーガード期間）
- CRITICAL: 注文ID記録による二重発注防止の冪等化
- ほかポーリング30→20秒短縮・CANCELED即時脱出・PARTIALLY_FILLED受け入れ・共通ヘルパー抽出

## 2026-06-27

### コードレビューLOWバグ修正（v3.5）

- L-6: 全4 IAMロールから未使用の`ses:SendRawEmail`を削除し`ses:SendEmail`のみに最小権限化（デプロイ済み）
- L-5: Phase Bスキップ分岐に設計意図コメント追加。L-1〜L-4は調査の結果すでに対応済みと確認、コード修正なし

## 2026-07-03

### 第2巡Fableレビュー HIGH3件修正（v3.6）

- 緊急決済失敗時にstateを消去せず建玉を残す問題を修正。トレーリングSL再発注失敗時の自己修復を追加。部分約定エントリーの孤児化を防止
- MEDIUM: TP1数量丸め誤差修正・SL損益記録の実約定量化・EventInvokeConfigリトライ0化で二重発注防止

### CloudWatchアラーム2個追加（v3.7）

- Executor Errors（1件以上でメール通知）とExecutor死活監視（1時間呼び出しゼロで通知、TreatMissingData: breaching）をSNSメール通知付きで追加
- 可観測性ゼロだった状態を解消（無料枠10個中7個使用）

### state⇄実建玉リコンサイル追加（v3.8）

- `GET /user/margin/positions`で実建玉を取得し、SSM stateとの不一致（孤児state・孤児建玉・方向不一致）をExecutor実行毎に検知しメール通知（自動修復なし）
- buy_pendingは対象外。本番実行で一致確認OK

### 週次サマリーに資金増額判断進捗を追加（v3.9）

- 累計クローズN/20・N/30、実勝率/実PF/最大DDの基準達成（○/△/×）を自動表示
- 無敗時に「クローズなし」と誤表示するバグを修正
- 陳腐化した参考値をv3.1基準（勝率72.9%/PF1.16/DD5.2%）に更新。本番メール送信確認済み

### セーフモード・キルスイッチ追加（v4.0）

- SSMパラメータ`/Zer0/CryptoBot/mode`（normal/pause_entry/halt）でExecutorの挙動を切替
- pause_entryは新規建てのみ停止、haltは全処理停止。未作成・不正値・読込失敗はnormal扱い（fail-safe）
- 本番でhalt→normalの実動作確認済み

### トレーリングSL更新メールを抑制（v4.1）

- 強トレンド時は30分毎に送信され得た`notify_trail_updated`をログのみに変更（メール送信廃止）
- 約定・クローズ・警告・緊急の重要通知がトレール更新メールに埋もれるのを防止。更新の事実はCloudWatch Logsに引き続き記録される

### ドキュメント鮮度修正（v4.2）

- v3.6で`MaximumRetryAttempts`を2→0にした後も残っていた「最大2回リトライ」「3回連続起動失敗時」等の記述をFailureNotifier docstring・README・システム仕様書・アーキテクチャ図から一掃
- 件名も「🚨Executor 起動失敗（リトライ上限）」→「🚨Executor 起動失敗」に修正

### Binance APIフォールバックホスト追加（v4.3）

- `fetch_binance`を同一ホスト3回再試行からapi.binance.com→api1〜4→data-api.binance.visionのホストローテーションに変更
- 単一ホスト障害・レート制限時のシグナル欠落を防止。本番疎通確認済み

### pytestテスト整備（v4.4）

- `tests/`にpytest 27件を新設（純関数・リコンサイル・セーフモード・Binanceフォールバック・analyze_coin）
- backtest.py（pandas）とanalyzer（純Python）のATR/Supertrend一致を検証するパリティテストを追加し、二重実装のドリフトを検知可能に

## 2026-07-04

### stats.json用語整理（v4.5）

- update_public_stats→update_stats_json改名。バケットは完全非公開のため「public-read」という古い記述をコメント・ログから削除
- 閲覧経路は004 SSR Lambdaのs3:GetObjectのみに統一（004側でBasic認証ページ実装・本番検証済み）

## 2026-07-13

### リコンサイル誤検知バグ修正（v4.6）

- reconcile_positionsをPhase A/B（決済検知・state更新）より前に実行していたため、取引所側で先に約定したトレーリングSL決済等の正常なクローズも「stateにあるが実建玉なし（孤児state）」と誤検知しメール送信していた
- Phase A/Bの後に実行するよう順序変更し解消。テスト側の未改名（update_public_stats→update_stats_json）5件も修正

## 2026-07-21

### state⇄実建玉不一致アラートの原因調査・復旧

- bitbankアプリで手動決済したbtc_jpy/eth_jpyのlongポジションが、Bot側のTP1/SL/トレーリング経路を通らずに成行決済されたため、SSM stateだけがポジション保有中のまま残り30分毎にreconcile不一致メールが送信され続けていた
- コード側の不具合ではなく手動決済によるstateとの乖離と確認。SSM stateの孤児ポジションを削除し、bitbank側に残っていたbtc_jpyの未約定トレーリングSL注文（stop_limit、INACTIVE）をキャンセルして解消
- 通知メールの文字化け報告も合わせて調査。Gmail上の件名・本文・HTML部は実データで確認した限り正しくUTF-8エンコードされており再現せず。スマートフォンの非Gmailメールアプリ側の表示崩れの可能性が高く、Bot側の送信コード（send_email、Charset=UTF-8）に問題は見つからなかった
- 手動決済はrecord_trade()を通らないため、004ポートフォリオのトレード実績ページ（stats.json）に今回の利益（btc_jpy +138.5円／eth_jpy +120.5円）が反映されていなかった。bitbank実約定価格を元に取引履歴レコードを追記しstats.jsonを再生成、累計損益+584.8円で反映済み

### 現在ポジションの状況表示を追加（004連携）

- 「TP1部分利確後、次はいつ利確するのか分からず不安」というフィードバックを受け、Executorに`update_positions_json()`を追加。Phase A完了毎（30分毎）にSSM state内の保有中ポジション（TP1待ち/トレーリング中）のスナップショットを非公開S3（`zer0-cryptobot-stats-s3/positions.json`）へ書き出す
- トレーリング中は確保済み利益ライン（trail_sl_price）・これまでの高値/安値・現在の含み損益・「固定の利確ラインはなく高値からATR×0.75反落で自動決済される」という説明を表示。004側のIAM（Zer0-portfolioスタック）・006側のIAM（zer0-cryptobotスタック）双方にpositions.json用の権限を追加
- 週足勝率が実際は8勝2敗（80%）であることも判明（テーブル上の-2.6円/-1.3円は、TP1後のトレーリングSLが建値ぴったりでなくSL_SLIPPAGE(0.3%)分だけ不利な価格で約定するために生じる、意図された小幅損失）
- SOL/JPY 500円の実弾テスト（TP1強制約定→トレーリング中カード表示→実クローズ）でactive/trailing両方の表示を検証。テスト用トレード2件・往復コスト数円はstats.jsonから除去済み
- 「最終更新」表示がSSR実行環境(UTC)でレンダリングされ9時間ずれていた既存バグ（`toLocaleString('ja-JP')`にtimeZone未指定）も発見し、`timeZone: 'Asia/Tokyo'`を明示して合わせて修正

### TP1約定メールに「次の決済ライン」を明記

- 「TP1確定後、次はいくらで利確するのか」への回答としてnotify_trail_started()のメール本文を拡充。固定の「TP2」は存在せず、残り70%はトレーリングSL（現時点はentry_priceでブレイクイーブン）で管理される旨と、ATR×0.75反転で決済される仕組みを明記
- 004実績ページ（現在のポジション）へのリンクも追加し、最新の決済ラインをいつでも確認できるように誘導

## 2026-08-10

### 構成図をdraw.ioでの手動編集に移行、AWS公式Cloud/Region枠を導入

- matplotlib(`scripts/generate_diagram.py`)での矢印微調整では意図した見た目にならなかったため、構成図をユーザー自身がdraw.io(diagrams.net)で手直しする運用に変更。`images/006_architecture.drawio`を新規作成し、以後はこのファイルが構成図の一次情報源
- クラスター枠を独自の色付き角丸四角形から、draw.io標準搭載の公式AWS4シェイプ(`shape=mxgraph.aws4.group`)に変更。最外周に「AWS Cloud」(実線)、その内側に「ap-northeast-1」の「Region」枠(点線)を配置
- 斜め方向の接続のうち他ノードのアイコン・ラベルと交差しうるものを直角配線(`edgeStyle=orthogonalEdgeStyle`)に整理し、線の交差・重なりを解消
- 変更はドキュメント用画像のみでAWSリソース・コードの変更を伴わないため、AWSデプロイ・pytestは対象外

### 週次サマリーメールに「稼働状況」セクションを追加、資金増額進捗をテーブル化

- 「シグナルが出ない週はBotが止まっているように見える」という指摘を受け、`weekly_summary`のメール冒頭に稼働状況の一文を追加。シグナル0件の週は「Supertrend転換待ちで異常ではない、Analyzer/Executorは定期実行を継続しており問題があれば別途アラームメールで通知される」旨を明記し、決済があった週は「◯件の決済があり正常稼働中」と表示する
- HTML版では緑のアクセント枠付きカードとして目立つ位置(ヘッダー直下)に配置
- 資金増額判断の進捗（累計クローズ数・実勝率・実PF・最大DD）のHTML表示を、`<br>`区切りの1段落から他セクションと統一したテーブル形式に変更し、○/△/×の達成マークも値のすぐ後ろに配置して読みやすくした
- `compute_scale_up_metrics()`に指標計算を集約し、テキスト版・HTML版どちらもそこから整形する構成に整理
- pytest 8件を新規追加（稼働状況メッセージの分岐・達成マークの閾値・テキストとHTMLの表示一致を検証）し、全45件通過を確認。ローカルでHTML本文をレンダリングし見た目も確認済み。`bash scripts/deploy.sh`で本番デプロイ、Lambda更新（`LastUpdateStatus: Successful`）を確認

## 2026-08-13

### 8プロジェクト横断のREADME/システム仕様書 記載漏れ監査・修正

- 緊急停止セクションがEventBridgeスケジュール無効化の旧手順のみで、v4.0で追加した「SSMパラメータ`/Zer0/CryptoBot/mode`でのセーフモード切替（新規建てのみ停止/全処理停止）」が未反映だったため、優先手順として追記（README/システム仕様書両方）
- システム仕様書のSSMパラメータ一覧表に`mode`パラメータが未掲載だったため追加
- 技術スタック表に第2S3バケット`zer0-cryptobot-stats-s3`（`positions.json`、004ポートフォリオの「現在のポジション」表示用）が未記載だったため追加

## 2026-08-19

### 通知/SES送信先メールアドレスの変更

- SenderEmail/RecipientEmailを`sinnjibaby@gmail.com`から`sj.hatanaka@gmail.com`に変更
- SESで新アドレスを検証、CloudWatchアラーム用SNSトピック`Zer0-CryptoBot-Alarms`の購読を新アドレスへ切替
- CFnスタック`zer0-cryptobot`を`update-stack`でパラメータ更新・デプロイ
