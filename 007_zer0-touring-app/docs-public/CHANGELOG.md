# 007_Zer0_TouringApp 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-08-02

### ローカルNode.jsバージョンを固定

- `.nvmrc`を追加し、動作確認済みのNode.js v24.18.0をローカル開発バージョンとして固定

## 2026-05-10

### 初版リリース（v1）

- Astro static PWA + Lambda Bedrock Haiku + CloudFront でツーリングコース提案

## 2026-05-12

### 実道路距離の上書き（v1.1）

- Nominatim ジオコーディング + OSRM ルーティングによる実道路距離・所要時間の上書き機能を追加

## 2026-05-14

### ルーティング二重構成（v1.2）

- Google Maps Directions API 優先（月9,900件まで）+ OSRM フォールバックの二重構成を実装

## 2026-05-15

### レートリミット（v1.3）

- DynamoDB IP別・日別レートリミット（1日3回）を追加。TTL翌々日自動削除。管理者バイパス（X-Admin-Token）対応

## 2026-05-18

### SNSシェア機能（v1.4）

- DynamoDB URL短縮 + Lambda OGP HTMLレスポンスによるSNSシェア機能（`/api/share` → `/s/{id}`）を追加

## 2026-05-20

### スタイルタグ（v1.5）

- スタイルタグ（峠道・海沿い・温泉・グルメ・絶景・自然・歴史・ガッツリ走る・のんびり）9種類 + 3×3グリッドUIを追加

## 2026-05-22

### 天気ウィジェット（v1.6）

- 現在地・目的地の天気比較ウィジェット（バイク走行アニメーション）+ 7日間週間天気予報ストリップを追加

## 2026-05-25

### iOS Safari対応（v1.7）

- バックグラウンドリロード対応（`?course=` URL復元）+ popstate ネイティブ戻るジェスチャー対応

## 2026-06-15

### セキュリティ改善（v1.8）

- JST化・CSP 'unsafe-inline'除去・secrets.choice化・DeletionPolicy追加
- GMaps使用量をDynamoDBアトミック管理へ移行

## 2026-06-27

### セキュリティ修正（v1.9）

- ADMIN_TOKEN を `secrets.compare_digest` で定数時間比較に変更
- 共有リンク数値フィールドを `Number()` 正規化して HTML 注入防止。`?admin=off` 解除ロジックバグ修正

### S3ライフサイクル設定（v2.0）

- `zer0-touring-s3` に未完了マルチパート 7 日後中断ルールを CFn で追加

## 2026-07-03

### 第2巡Fableレビュー HIGH2件修正（v2.1）

- X-Forwarded-Forを末尾信頼に変更しレートリミット回避を防止
- `/api/share`の自動POSTをフロント側で解消し、バックエンドにレートリミット・サイズ上限を追加
- MEDIUM: レート消費順序修正・Bedrock timeout短縮・/s/*・/api/*にセキュリティヘッダー適用

### execute-api直接アクセスの完全遮断（v2.2）

- CloudFront→API Gateway間に`X-Origin-Verify`共有シークレット（SSM SecureString管理）を追加し、Lambda側で検証・不一致は403
- CloudFrontを経由しないbot/スクリプトのレートリミット回避を遮断

### 緊急障害対応: コース生成504を修正（v2.3）

- Open-Meteo API劣化による外部API遅延の累積でLambda Timeout(30秒)を超過していたため、残り時間チェックを追加し時間不足時は外部APIをスキップしAI推定値で必ず応答
- フロントの天気系fetch 3箇所にも5秒タイムアウトを追加しUIハングを解消

### 安全バッファ拡大（v2.4）

- `MIN_TIME_BUFFER_MS`を4秒→6秒に拡大し、応答をより確実に返せるよう調整
- 判明した制約: API Gateway HTTP APIのLambda統合タイムアウトは30秒固定でAWS仕様上引き上げ不可のため、Lambda関数自体のTimeoutを30秒より延長しても効果がない
- エラー回避には残り時間バッファの拡大で対応する方針とした

### CloudWatchアラーム整備（v2.5）

- Lambda Errors・Duration p95(25秒超)・API Gateway 5xxの3アラームをSNSメール通知付きでCFnに追加
- 障害発生時にユーザー報告より先に気づけるようにした（`AlarmEmail`パラメータ、`deploy-infra.sh`は`ALARM_EMAIL`環境変数で指定）

### ジオコーディングDynamoDBキャッシュ（v2.6）

- `nominatim_geocode`の結果を`zer0-touring-ratelimit`テーブルに`geocode#{originバケット}#{地名}`キーでキャッシュ（TTL 90日）し、Nominatimの1req/秒直列呼び出しを削減
- 本番で書き込み確認済み

### コース履歴保存機能（v2.7）

- 生成結果を新規`zer0-touring-history`テーブル（端末ID+時刻の複合キー、TTL180日）に自動保存
- 端末IDはlocalStorageに保存し`X-Device-Id`ヘッダーで送信
- `GET/POST /api/history`ルートと履歴一覧画面を追加。本番検証済み

### 狙い目日選択機能（v2.8）

- 週間予報の各日をタップすると、その日の予報（最高気温・天気）でコースを再生成できるようにした（GPSは再取得せず既存の位置情報を再利用）
- プロンプト自体は変更せず、temperature/weather_conditionを対象日の値に差し替えるだけで実現
- ビルド成功・HTML構造の本番反映は確認済みだが、タップ操作自体のブラウザ実機確認は未実施

### ルートマップ機能（v2.9）

- 詳細画面にLeaflet+OpenStreetMapで現在地・目的地・スポットのマーカーとOSRM実道路ルートを表示
- leafletをnpm依存に追加しViteでバンドル
- CSPに`router.project-osrm.org`・`*.tile.openstreetmap.org`を追加。本番でCSP・配信・OSRM疎通確認済み

### 二段階レスポンス化（v3.0）

- `/api/suggest`から外部API取得（Nominatim/OSRM/Google Maps/Open-Meteo）を分離し、Bedrock生成結果をAI推定値のまま即返却（28秒→9.8秒、本番実測）
- 精密データは新設`POST /api/enrich`で詳細画面表示時に取得し自動再描画。DAILY_LIMITは生成のみ対象

### テスト整備（v3.1）

- バックエンドに`backend/tests/`（pytest、boto3モック、17件）を追加しedge-secret検証・XFF末尾信頼・キャッシュ・履歴・二段階分離を回帰テスト化
- フロントは`fmtHours`等を`src/scripts/course-utils.ts`に切り出しVitestで12件のユニットテストを追加

## 2026-07-13

### OGP画像の刷新（v3.2）

- OGP画像を正方形アイコン(icon-512.png)流用から専用の1200x630画像に変更。SNS共有時に不自然に切れる問題を解消
- 008プロジェクトのブランドアセット作業の際、ユーザー指示による自己調査で発見・修正

### ブランドfavicon一式追加（v3.3）

- 独自ブランドfavicon一式(favicon-16/32.png・apple-touch-icon.png・favicon.ico)を既存のicon-512.pngから生成し追加
- 以前は`<link rel="icon">`が未設定でブラウザタブのアイコン表示が保証されていなかった点も是正

## 2026-07-16

### CloudWatchアラーム1個を008へ譲渡

- AWSアカウント全体でCloudWatchアラームが無料枠10個中10個で上限に達しており、008(入札情報ウォッチ)の中核Lambda(lp_waitlist、登録/LINE連携/Stripe Webhook等を処理)にエラー検知アラームが一つも無いことが判明した
- `Zer0-touring-lambda-errors`を削除して枠を確保した。`Zer0-touring-apigw-5xx`は残置。007のLambdaはAPI Gateway同期呼び出し専用のため、未処理例外・タイムアウト・スロットリングはいずれも5xxとして検知でき、失敗検知のカバレッジはほぼ維持される（Fableに独立検証を依頼し同結論を確認済み）
- CFn更新（`zer0-touring`スタック、`CertificateArn`必須の既知ルールに従い実施）後、本番サイト(`touring.zer0-infra.com`)がHTTP 200で正常応答することを確認

## 2026-08-08

### 利用実績集計バッチ・ポートフォリオサイトへの公開グラフ追加

- 利用回数（何回呼び出されているか）をユーザーから問われ調査した結果、CloudFrontアクセス数はbot/クローラーの静的ファイル取得が混ざり実利用の指標として不正確と判明。実際にAPI(Bedrock呼び出し)が呼ばれた回数(Lambda Invocationsメトリクス)を実利用の指標として採用することにした
- 新規Lambda`zer0-touring-stats`(`stats_handler`)を実装。当初`AWS/Lambda Invocations`（関数単位の呼び出し数）を使う設計だったが、`zer0-touring-suggest`は`/api/status`等の他ルートも同居しているため無関係な呼び出しまで合算されると判明。`/api/suggest`成功時のみ発火するカスタムメトリクス`Zer0Touring/SuggestCalls`方式に変更した（Fableレビューで発見・修正）
- CloudWatchの日次Period(86400)はUTC 0時境界固定でJST日付とずれる問題も同レビューで発見。Period=1時間で取得しPython側でJST暦日に再集計する方式に修正。呼び出しゼロの日も0件で明示的に埋めた90日分のJSON(`stats.json`)をS3(`zer0-touring-s3`)に書き出す設計（ゼロ埋めしないとグラフのx軸間隔が実カレンダーとずれ利用頻度が実態より高く見えるため）
- EventBridge Scheduler(`zer0-touring-stats-daily`、毎日5:00 JST)で日次起動する構成をCFnに追加。既存`TouringLambdaRole`にCloudWatch読み取り・書き込み・S3書き込み権限を追加、Scheduler専用のIAMロールも新設
- 実デプロイで2件の不具合が判明し修正。①このAWSアカウントのCFn Early Validationフックが`ScheduleExpressionTimeZone`プロパティを値に関わらず拒否するため、UTC基準のcron式(`cron(0 20 * * ? *)`=JST5:00)に変更して回避。②`GetMetricStatistics`は1呼び出き1,440データポイント上限だが90日×1時間=2,160点を要求し実行時エラーになったため、上限がはるかに大きい`GetMetricData`に切り替えて解消（実機invokeで発見）
- Scheduler実行ロールへの`aws:SourceArn`条件は、スケジュール名を完全一致させると（スケジュールARN未確定な時点で行われる）assume role事前チェックに失敗すると判明。2巡目のFableレビューで「defaultグループ単位のワイルドカード(`schedule/default/*`)なら両立できるはず」と指摘を受け検証したところ成功し、confused deputy対策を維持したまま反映
- GetMetricDataは1回答あたり最大100,800データポイントまで返せる仕様のため現状(2,160点)は十分余裕があるが、上限超過時はエラーにならずサイレントに一部データが欠落する仕様と判明。`NextToken`が返った場合に警告ログを出す防御コードを追加（2巡目のFableレビューで指摘）
- pytestに`stats_handler`・メトリクス発火のテストを3件追加（計20件）。CFnスタック更新・Lambdaコードデプロイ・実際の`/api/suggest`呼び出しからstats.json反映までを本番で確認済み
- 004ポートフォリオの`touring-app`プロジェクトページに新規`TouringStatsChart.astro`コンポーネントを追加し、`stats.json`をSSR時にfetchして累計呼び出し回数と日別バーチャートを公開表示（dataviz skillのガイドラインに準拠。日本語/英語両対応、stats.json未生成時は自動的にセクション非表示）。SSR毎回の外部fetchを避けるため5分TTLのメモリキャッシュ(`lib/touringStats.ts`)を追加し、スキーマ検証も強化。本番サイトでグラフ表示を確認済み
- 構成図(`007_architecture.png`)にEventBridge Scheduler・統計集計Lambdaを追加

## 2026-08-09

### 目的地天気「取得中...」固着・ナビ起点まわりの修正

- ユーザーの実機テストで「目的地の天気が取得中のまま変わらない」と報告。原因は、目的地のNominatimジオコーディングが失敗すると`enrich_course`が即returnし天気取得（`fetch_dest_weather`）まで道連れでスキップされ、フロント側が永久に「取得中...」表示のまま止まっていたこと（Fable調査で特定）
- `nominatim_geocode`に`retry`引数を追加し、目的地ジオコーディング（時間予算に余裕がある呼び出し）のみ接続エラー・タイムアウト時に1回だけ再試行するようにした（0件ヒットは対象外）。フロント側は、enrichが完了しても天気が取れなかった場合に「取得できませんでした」という終端表示を追加し、無限「取得中...」状態を解消。geocoding自体が失敗した場合は次回詳細画面を開いた時に再試行できるよう`_enriched`フラグの立て方も見直した
- Googleマップナビ起点について「GPS現在地/手動選択した出発地のどちらを先頭にするか」を調査。`userLat`/`userLon`は両モードとも`findCourses()`内で検索前に同期的に確定しており競合状態は無かったが、`buildMapUrl`が`userLat&&userLon`という真偽値判定をしており、座標が0付近（日本国内では非現実的だが）だと誤って起点なし扱いになる潜在バグを発見・null判定に修正。あわせて目的地・スポット座標も同種の判定に統一
- バックエンドにリトライの回帰防止テストを3件追加（計23件）。フロントはvitest 12件・astro build・ローカル構文チェックで確認
- 本番デプロイ後、フロントエンド`s3 sync --delete`が動的生成物`stats.json`を誤って削除する事故が発生（ビルド成果物に含まれないファイルのため）。即座に再生成し復旧、`deploy-infra.sh`の同期コマンドに`--exclude "stats.json"`を追加して再発防止
- 本番で`/api/suggest`→`/api/enrich`を実際に呼び出し、目的地座標・天気データが正しく返ることを確認
