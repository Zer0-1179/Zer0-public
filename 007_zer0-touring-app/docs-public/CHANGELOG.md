# 007_Zer0_TouringApp 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-08-09

### 目的地天気「取得中...」固着・ナビ起点まわりの修正

- 実機テストで「目的地の天気が取得中のまま変わらない」と報告。目的地ジオコーディング失敗時に天気取得まで道連れでスキップされる不具合と判明（Fable調査）
- `nominatim_geocode`に目的地ジオコーディング限定の1回リトライを追加。フロントに「取得できませんでした」の終端表示を追加し無限「取得中...」を解消
- `buildMapUrl`のナビ起点判定にfalsy-zero起因の潜在バグを発見・null判定に修正
- 本番デプロイ時`s3 sync --delete`がstats.jsonを誤削除する事故が発生、即復旧しデプロイスクリプトに`--exclude`追加で再発防止。回帰テスト3件追加（計23件）

### 品質向上: フロントエンドのテスト拡充・enrich失敗の可視化

- `buildMapUrl`・`computeEnrichState`を`course-utils.ts`に切り出しテスト9件追加（フロント計21件）、`index.astro`もこの関数を呼ぶよう配線し直した
- `/api/enrich`の目的地ジオコーディング失敗回数を追跡するカスタムメトリクス`Zer0Touring/EnrichGeocodeFailed`を追加。バックエンド回帰テスト2件追加（計25件）

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

### 品質向上: フロントエンドのテスト拡充・enrich失敗の可視化

- ユーザーから「他に問題ないか、クオリティを高めるには」と問われ、今回のバグが未テストのロジックに潜んでいたことを踏まえ2点対応
- `buildMapUrl`と`computeEnrichState`（今回のバグ本体だった状態遷移ロジック）を`course-utils.ts`に切り出しテスト9件を追加（フロント計21件）。`index.astro`側もこの切り出し済み関数を呼ぶよう配線し直し、テストが実コードを保証するようにした
- `/api/enrich`で目的地ジオコーディングが失敗した回数を追跡するカスタムメトリクス`Zer0Touring/EnrichGeocodeFailed`を追加。Nominatim由来の劣化が本番でどれくらいの頻度で起きているか後から追えるようにした（`Zer0Touring/SuggestCalls`と同じ仕組みを流用、IAM権限変更なし）
- バックエンドに回帰テスト2件追加（計25件）。本番デプロイ・疎通確認済み

## 2026-08-10

### 構成図をdraw.ioでの手動編集に移行、AWS公式Cloud/Region枠を導入

- 構成図をユーザー自身がdraw.io(diagrams.net)で手直しする運用に変更。`images/007_architecture.drawio`を新規作成し、以後はこのファイルが構成図の一次情報源(`scripts/generate_diagram.py`によるmatplotlib生成は現状維持だが更新には使わない)
- クラスター枠を独自の色付き角丸四角形から、draw.io標準搭載の公式AWS4シェイプ(`shape=mxgraph.aws4.group`)に変更。最外周に「AWS Cloud」(実線)、その内側に「us-east-1」「ap-northeast-1」の2つの「Region」枠(点線)を入れ子で配置
- 斜め方向の接続のうち他ノードのアイコン・ラベルと交差しうるものを直角配線(`edgeStyle=orthogonalEdgeStyle`)に整理し、線の交差・重なりを解消
- 変更はドキュメント用画像のみでAWSリソース・コードの変更を伴わないため、AWSデプロイ・pytestは対象外

## 2026-08-13

### 8プロジェクト横断のREADME/システム仕様書 記載漏れ監査・修正

- README.mdのデプロイ手順`aws s3 sync`コマンド2箇所に`--exclude "stats.json"`が抜けたままで、この通り実行すると2026-08-09のstats.json誤削除事故が再発するリスクがあったため`infra/deploy-infra.sh`・システム仕様書と同じ形に修正
- `/api/history`（コース履歴保存機能、v2.7で実装済み・本番稼働中）がREADME/システム仕様書のAPIリファレンス・技術スタック・DynamoDBテーブル一覧のいずれからも欠落していたため追記
- 本CHANGELOG.mdで「2026-08-10」のエントリが先頭に誤挿入されていた（プロジェクト共通ルールでは末尾追記）のを、正しい時系列位置に移動

## 2026-08-19

### 通知メールアドレスの変更

- AlarmEmailを`sinnjibaby@gmail.com`から`sj.hatanaka@gmail.com`に変更
- CloudWatchアラーム用SNSトピック`Zer0-touring-alarms`の購読を新アドレスへ切替
- CFnスタック`zer0-touring`を`update-stack`（`CertificateArn`/`AdminToken`/`EdgeSecret`は`UsePreviousValue=true`）でデプロイ

## 2026-08-27

### SSM名前空間の正規化と旧パラメータ削除

- CloudFront→API Gateway間の共有シークレットの運用参照先を`/touring/edge_secret`へ統一
- 専用CloudFormation cleanupスタックで旧SSMパラメータを削除。新SecureString、Lambda、CloudFrontの共有認証ヘッダーを値非表示で確認し、CloudFront経由APIは200、直APIは403となることを実機確認
- 完了済みの移行・削除用CFNテンプレートを作業領域から削除し、通常運用では正規化済みパスのみを管理

### 移行専用CFNスタックの撤去完了

- 移行・cleanup専用のCloudFormationスタックを削除し、一時Lambda、IAM Role、CloudWatch Logsを撤去した
- `/touring/edge_secret`とCloudFront・Lambdaの既存認証構成は維持され、値を出さずに存在を再確認した

## 2026-08-31

### 利用実績の日次更新停止を修正

- EventBridge Scheduler実行ロールの信頼条件を、AWS仕様に従い個別スケジュールARNではなく`default`スケジュールグループARNに修正。Schedulerがロールを引き受けられず統計Lambdaを起動できなかった不具合を解消
- `stats.json`は`no-store`で書き出し、CloudFrontにも同ファイル専用のキャッシュ無効ビヘイビアを追加。004のSSRが日次集計結果を古い配信キャッシュから読まないようにした
- `stats_handler`の回帰テストに`Cache-Control`検証を追加

### ツーリングコースの距離・スポット品質を修正

- コース距離を片道の曖昧な値ではなく往復合計へ統一。初級20〜70km・中級80〜150km・上級160〜250kmをAI提案時と実道路距離取得後の両方で検査し、詳細画面では「往復目安」から「往復実測」へ更新する
- 既存のGoogle Maps Directions API 1リクエストを往復ループ（現在地→行きスポット→目的地→帰りスポット→現在地）に変更し、追加のDirections API呼び出しなしで往路・復路を含む実距離を取得するようにした。失敗時は同じ往復点列をOSRMへ渡す
- 観光地・道の駅・温泉・日帰り温泉・銭湯を表示用スポットと地図／ナビ用の座標検証済みスポットに分離。ジオコード失敗・経路外判定でも提案そのものを画面から消さないようにした
- 目的地と全立ち寄りスポットをNFKC正規化して同一提案内で重複排除し、端末内の直近18地点を次回のAI提案から除外するようにした

### 提案・詳細取得の入力検証と品質保証を強化

- Solの独立レビューで判明した、公開`/api/enrich`の無制限外部API呼び出しを修正。IP別・日別9回（提案3回×3コース）に制限し、目的地・経由地点・座標の構造検証を外部API呼び出し前に行うようにした
- AI出力は初級・中級・上級の正確に3件すべてが距離帯、各コースの観光地／展望台、3コース全体の道の駅と温泉・日帰り温泉・銭湯、目的地を含む全地点の重複なしを満たす場合だけ返す。欠損・重複・帯域外を成功応答として表示しないようにした
- 詳細取得前のGoogleマップナビから未検証のAI地点名を除外し、座標検証済みwaypointだけを使用。詳細地図のOSRM経路も往復の経由順と一致させ、実測後は一覧カードの距離・ラベルも更新するようにした
- スポットのNominatim再試行を廃止し、段階別の残時間ガードを追加。初級の安全・距離条件が「峠道」「ガッツリ走る」より常に優先されるプロンプトへ修正した
- DynamoDB障害時も`/api/enrich`だけはレート制限をfail-closedで扱い、外部APIの無制限呼び出しを防ぐようにした

## 2026-09-05

### コース距離帯の変更（近距離をより短く）

- ユーザーから「近距離コースの表示でも100kmを超える」と報告。初級20〜70km・中級80〜150km・上級160〜250kmだった距離帯を、初級20〜49km（近距離）・中級50〜99km（中距離）・上級100〜300km（長距離）へ変更
- AI提案プロンプトの距離帯指示・実道路距離取得後の帯域検査（`COURSE_PROFILES`）・フロント表示ラベル（`DIST`配列）の3箇所を同時に更新
- バックエンド35件・フロントエンド22件の既存回帰テストの距離値を新帯域に合わせて更新し全件パス確認

### 同じ出発地で毎回同じコースが出る不具合の修正

- ユーザーから「同じ位置からコースを探すと毎回同じコースしか紹介されない」と報告。原因は「直近提案済みの場所」除外リストの上限が18件だったこと。1回の生成で目的地+立ち寄りスポットが最大12件程度増えるため、2回の再検索で最初の除外対象が押し出され、同じコースが再提案されていた
- 除外リストの上限を端末側（`localStorage`の`touring-recent-places`）・Lambda側（`normalize_excluded_places`）ともに18件から60件（約5回分）へ拡張
- AIプロンプトに「目的地は除外リストと大きく異なる方角・地域を選ぶこと」の指示を追加し、除外指示の遵守を強化

### Googleマップナビが目的地「見つかりません」になる不具合の修正

- ユーザーがGoogleマップで目的地「奥多摩湖」を検索した際に「見つかりません」と表示されたスクリーンショットの提供を受け調査。当初は本番`/api/enrich`への直接呼び出しでNominatimが正しい座標（緯度35.7774299・経度139.0102062）を返すことを確認しアプリ側に不具合なしと判断したが、ユーザーから「Googleマップでナビ開始」ボタンから開いた直後に同じ現象が再現すると報告があり再調査
- 真因判明: 詳細画面・一覧カードの「Googleマップでナビ開始」ボタンは、座標取得（enrich）が非同期で完了する前でもクリック可能なままだった。enrich未完了のうちにクリックすると`dest_lat`/`dest_lon`が無いため`buildMapUrl`が座標でなくテキスト名にフォールバックし、湖・峠等の自然地名でGoogleマップ側のテキスト検索が失敗していた。一覧カードのボタンは詳細画面を一度も開いていないと常にこの状態で、確実に再現する不具合だった
- 両ボタンをクリック時にenrich完了（または断念）まで待ってから座標付きURLで開く方式に変更。`enrichCourseDetail`の実行中Promiseをコースオブジェクトにキャッシュし、複数箇所からの呼び出しで二重フェッチしないようにした

### Fableモデルによる徹底コードレビューで発見した不具合7件を修正

- ユーザーから「他にバグがないか徹底的に調査して」と依頼を受け、Fable（`claude-fable-5`）サブエージェントでバックエンド・フロントエンドをそれぞれ独立レビュー。報告された8件のうち7件を実コード読解・本番API検証で裏取りし確認、1件（getDeviceId/apiHeadersのlocalStorage例外未処理）は発生条件未検証のまま念のため対応
- [HIGH] return_spots（帰りの立ち寄り先）の温泉・日帰り温泉・銭湯必須は、プロンプトでは「3コース全体で最低1箇所」という条件だったが、実装は`_normalize_spots(...,1,1,RETURN_SPOT_TYPES)`でコース単位に強制していた。AIが妥当な「食事処」「観光地」等をどれか1コースのreturn_spotに選ぶだけで`normalize_courses`が[]を返し`/api/suggest`全体が500で失敗、レートリミット消費後のため1日3回の生成枠を無駄にしていた。コース単位ではSPOT_TYPES全体を許容する形に修正し、未使用になった`RETURN_SPOT_TYPES`定数を削除。回帰テスト2件追加（バックエンド計37件）
- [HIGH] 目的地マーカーのLeaflet `bindPopup(c.destination)`がescHtml未適用だった（同じ関数内の立ち寄りスポット用マーカーは適用済み）。Leafletの`bindPopup(string)`はデフォルトでinnerHTML解釈するため、細工した`destination`文字列を含む`?course=`共有リンクを介したXSSが理論上可能だった。escHtmlを適用して修正
- [HIGH] `enrichCourseDetail`は`userLat`/`userLon`がnull（GPS/手動検索を一度も行わずに履歴・共有リンクから詳細画面を開いた場合）のとき、`c._enriched`/`c._enrichFailed`を設定せずreturnしていたため、目的地天気ウィジェットが「取得中...」のまま永久に固着していた。2026-08-09に一度解消したのと同種の固着バグの再発。null時も終端状態（取得できませんでした）へ遷移するよう修正
- [MEDIUM] 共有リンク（`/s/{id}`）・自身の`?course=`URL双方で、base64（標準アルファベット、`+` `/`を含みうる）をURLエンコードせずクエリへ埋め込んでいた。`URLSearchParams.get()`は仕様上`+`を半角スペースへデコードするため、base64に`+`が含まれると`atob`が例外を投げ、`catch(_){}`で無言のまま共有リンクが開けなくなっていた。バックエンド（`urllib.parse.quote`）・フロントエンド（`encodeURIComponent`）双方に対策を追加。バックエンド回帰テスト1件追加
- [MEDIUM] ブラウザ・iOSの「戻る」操作（`popstate`）とアプリの「戻る」ボタンの両方が同じ`backFromDetail()`を呼んでおり、`popstate`側でも重ねて`history.pushState()`していたため、戻る操作1回に対しJS側が余分に履歴を積み増し、アプリを完全に離脱するのに余分な操作が必要になっていた。画面切り替え本体を`leaveDetailScreen()`として分離し、`pushState`は明示的なボタン操作からのみ行うよう修正
- [MEDIUM] 詳細画面の写真は共有DOM要素（`#detail-img`）を使い回しており、前/次ボタンを素早く連打すると後発のfetchが先に解決した場合に前のコースの写真が古い結果で上書きされうる競合状態があった。呼び出しごとの通し番号をDOM要素に刻み、最新の呼び出しでなければ結果を適用しないよう修正
- [MEDIUM] 一覧画面表示中に裏で完了した別コースのenrichが`renderSlider({courses})`を無条件に呼び、閲覧中のスライド位置（`currentSlide`）・共有URLキャッシュ（`shortUrlCache`）を毎回リセットしてカードDOM全体を再構築していた。ドット表示の巻き戻りや、共有済みURLキャッシュ消失による`/api/share`への不要な再POSTを引き起こしうる状態だった。バックグラウンド更新時は状態を保持する`preserveState`オプションを追加
- [LOW] `getDeviceId`/`apiHeaders`が`localStorage`アクセスに無防備で、姉妹関数`loadRecentPlaces`/`saveRecentPlaces`と異なりtry/catchが無かった。Safari「すべてのCookieをブロック」等の環境で例外が投げられるとコース生成自体が起動しなくなりうるため、防御的なtry/catchとページ内限定のフォールバックIDを追加
