# APIリファレンス・セットアップ・運用・コスト・変更履歴

APIリファレンス、初回セットアップ、運用コマンド、トラブルシューティング、コスト内訳、変更履歴。

[← 目次に戻る](../README.md)

---

## API リファレンス

### POST /api/suggest

**リクエスト**  

```json
{
  "latitude": 35.6762,
  "longitude": 139.6503,
  "temperature": 22,
  "weather_condition": "晴れ",
  "preferences": ["峠道", "温泉"]
}
```

`preferences` は省略可（空配列または未指定でAIに完全おまかせ）。指定可能な値: `峠道` / `海沿い` / `温泉` / `グルメ` / `絶景` / `自然` / `歴史` / `ガッツリ走る` / `のんびり`（`ガッツリ走る` と `のんびり` は排他）。

**レスポンス**  

```json
{
  "courses": [{
    "name": "江の島・鎌倉海岸コース",
    "distance_km": 65,
    "duration_hours": 1.5,
    "return_hours": 1.5,
    "return_note": "134号線で帰還、来た道を折り返す",
    "highlights": ["江の島弁財天", "鎌倉大仏"],
    "destination": "江の島",
    "photo_spot": "江の島",
    "difficulty": "初級",
    "road_types": ["国道", "海岸線"],
    "outbound_spots": [
      {"name": "道の駅 湘南江の島", "type": "道の駅", "lat": 35.31, "lon": 139.48}
    ],
    "return_spots": [
      {"name": "しらす料理 食堂", "type": "食事処", "lat": 35.32, "lon": 139.45}
    ],
    "caution": "海岸線は強風注意",
    "best_season": "3月〜10月",
    "tags": ["🌊 海沿い", "🌸 景色良し", "🐟 グルメ"],
    "dest_lat": 35.3013,
    "dest_lon": 139.4797,
    "dest_temp": 21,
    "dest_weather_code": 1
  }]
}
```

**所要時間**：純粋な走行時間のみ（休憩・観光時間は含まない）。Google Routes API / OSRM の実データで AI 推定値を上書き。カード・詳細画面には距離・所要時間の数値は表示しない（2026-09-06〜）が、Xシェア文言・履歴一覧では「約X時間Y分」形式（分は10分単位で切り上げ）で使用する。

### GET /api/status

**レスポンス**  

```json
{ "used": 1, "limit": 3, "remaining": 2 }
```

管理者トークン一致時は `{ "used": 0, "limit": 3, "remaining": 3, "admin": true }`。

### POST /api/share

コースデータを DynamoDB に保存し、短縮URLを返す。`/api/suggest`とは別枠でIP別・日別30回（`SHARE_DAILY_LIMIT`）に制限。

**リクエスト**  

```json
{ "course": { /* POST /api/suggest レスポンスのコースオブジェクト */ } }
```

**レスポンス**  

```json
{ "url": "https://touring.zer0-infra.com/s/abc123" }
```

### GET /s/{id}

OGP メタタグ付き HTML を返しアプリへリダイレクト。SNS シェア時にコース名・目的地・写真がプレビューとして表示される（TTL: 30日）。

### POST /api/history

コース生成結果を端末ID（`x-device-id` ヘッダー）に紐づけて DynamoDB（`zer0-touring-history`）に保存する。1日3回の生成上限で消えてしまう候補コースをあとから見返せるようにする機能。レートリミット対象外、TTL: 180日。

### GET /api/history

端末IDに紐づく履歴一覧を新しい順に最大30件返す。

### POST /api/enrich

`POST /api/suggest`のAI推定値を実データ（Google Routes API優先/OSRMフォールバック）で上書きする二段階レスポンスの後段。詳細画面を開いたタイミングで1コース分呼び出す。IP別・日別`DAILY_LIMIT×3コース分`（既定9回）に制限（`/api/suggest`とは別枠）。

**リクエスト**

```json
{ "course": { /* POST /api/suggest レスポンスのコースオブジェクト */ }, "latitude": 35.6762, "longitude": 139.6503 }
```

**レスポンス**: `{ "course": { /* 実距離・実座標で更新済み */ } }`（外部API失敗時もAI推定値のまま200を返す）

## 初回セットアップ

### Google Maps API キー

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成（または既存選択）
2. **Maps Platform → Geocoding API** と **Routes API** の2つを有効化（2026-09-06〜。旧Directions API（Legacy）は2025年3月の料金改定で新規プロジェクトでは有効化できないため使用しない）
3. 認証情報 → API キーを作成し、API制限でGeocoding API・Routes APIの2つのみ許可することを推奨
4. Lambda 環境変数に設定:

```bash
aws lambda update-function-configuration \
  --function-name zer0-touring-suggest \
  --environment "Variables={BEDROCK_MODEL_ID=jp.anthropic.claude-haiku-4-5-20251001-v1:0,GOOGLE_MAPS_API_KEY=YOUR_API_KEY,DAILY_LIMIT=3}" \
  --region ap-northeast-1
```

Geocoding API・Routes APIともに月10,000件の無料枠（別カウンタで独立管理）。それぞれ月9,500件・9,900件超で自動的にNominatim・OSRMフォールバックへ切り替わるため実質0円で運用可能。

### Admin Token（レートリミットバイパス）

テスト時にIP制限（1日3回）を回避するための管理者トークン。

```bash
# Lambda 環境変数に追加（GOOGLE_MAPS_API_KEY等と合わせて設定）
aws lambda update-function-configuration \
  --function-name zer0-touring-suggest \
  --environment "Variables={BEDROCK_MODEL_ID=jp.anthropic.claude-haiku-4-5-20251001-v1:0,GOOGLE_MAPS_API_KEY=YOUR_GMAPS_KEY,DAILY_LIMIT=3,ADMIN_TOKEN=YOUR_ADMIN_TOKEN}" \
  --region ap-northeast-1

# 使用方法（curl）
curl -X POST https://touring.zer0-infra.com/api/suggest \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -d '{"latitude": 35.6762, "longitude": 139.6503, ...}'
```

## 運用コマンド

```bash
# Lambda ログ確認
aws logs tail /aws/lambda/zer0-touring-suggest --follow --region ap-northeast-1

# Google Routes API 月間使用カウント確認（DynamoDB管理）
aws dynamodb get-item --table-name zer0-touring-ratelimit --key '{"pk":{"S":"gmaps#'$(date +%Y-%m)'"}}' --region ap-northeast-1

# Google Geocoding API 月間使用カウント確認（Routes APIとは別カウンタ）
aws dynamodb get-item --table-name zer0-touring-ratelimit --key '{"pk":{"S":"geocode-gmaps#'$(date +%Y-%m)'"}}' --region ap-northeast-1

# フロントエンド再デプロイ（コード変更後、stats.jsonは--excludeで誤削除を防止）
cd 007_Zer0_TouringApp/frontend && npm run build && \
aws s3 sync dist/ s3://zer0-touring-s3 --delete --exclude "stats.json" && \
aws cloudfront create-invalidation --distribution-id E1Z92GZIT4IDGA --paths "/*"
```

> **CFn スタック更新時の注意**: `CertificateArn` を省略するとカスタムドメインが消える。  
> 必ず CLAUDE.md のコマンドを使うこと。

## トラブルシューティング

- **コース提案が返らない**
  - 原因: Bedrock モデルアクセス未承認
  - 対処: AWS Console → Bedrock → モデルアクセスで Claude Haiku 4.5 を有効化
- **Google Maps の時間が表示されない**
  - 原因: API キー未設定 or 枠超過（Routes API）
  - 対処: Lambda 環境変数 `GOOGLE_MAPS_API_KEY` を確認。超過時は翌月自動復帰（OSRMフォールバックで距離自体は表示され続ける）
- **1日3回制限に引っかかる（開発中）**
  - 原因: IP レートリミット
  - 対処: `X-Admin-Token` ヘッダーを付けてリクエスト
- **GPS が取得できない（モバイル）**
  - 原因: HTTP 環境 or 権限拒否
  - 対処: HTTPS（touring.zer0-infra.com）でアクセス。ブラウザの位置情報を許可
- **シェアURLが機能しない**
  - 原因: DynamoDB TTL 30日超過
  - 対処: 再度コース提案 → シェアボタンから新しいURLを生成
- **CloudFront のキャッシュが古い**
  - 原因: デプロイ後のキャッシュ残留
  - 対処: `aws cloudfront create-invalidation ... --paths "/*"` で手動クリア
- **立ち寄りスポットの座標がずれる**
  - 原因: Google Geocoding API の無料枠超過でNominatimへフォールバックした際の誤認識、またはGoogle側の誤マッチ
  - 対処: CloudWatch Logs で `[google-geocode]`/`[geocode]` のログからスポット名と座標・使用APIを確認。日本語正式名称に変更

## コスト内訳

| サービス                                              | 月額（100回利用）    |
| ----------------------------------------------------- | -------------------- |
| Bedrock Claude Haiku（in: ~720 / out: ~1,200 tokens） | ~$0.40               |
| Lambda 実行（~3秒 / 256MB）                           | ~$0.001              |
| Google Geocoding API・Routes API（それぞれ300回/月以内） | $0（無料枠内）      |
| DynamoDB（ratelimit + share + history / PAY_PER_REQUEST） | ~$0（無料枠内）      |
| API Gateway・CloudFront・S3                           | ~$0                  |
| **合計**                                              | **~$0.40（約60円）** |

## 変更履歴

直近1日分のみ表示。全履歴は [CHANGELOG.md](../CHANGELOG.md) を参照。

### 2026-09-06

#### コース生成失敗（500エラー）の修正

- 本番でユーザーが「コースの生成に失敗しました」エラーに複数回遭遇し、CloudWatchアラーム`Zer0-touring-apigw-5xx`（API Gatewayの5xx検知）が発報
- 原因はBedrockが生成したJSON自体は正常だが、Lambda側の検証（`_normalize_spots`）が「初級コースには観光地・展望台を最低1箇所含める」条件を満たさない出力（`outbound_spots`が道の駅1件のみ等）を却下し500を返していたこと
- プロンプトのJSON出力例が「道の駅」1件のみを示しており、直後に書かれた「観光地・展望台を最低1箇所含める」ルールと矛盾していたのが根本原因。例を展望台＋道の駅の2件に修正しAIの逸脱頻度を低減
- 加えて、Bedrock呼び出し〜検証を同一リクエスト内で最大2回まで試行するよう変更し、AIが稀に規約を破ってもユーザーへ即座に500エラーを返さないようにした（1回の生成は約9秒・Lambda Timeout=30秒のため2回でも余裕あり）
- 回帰テスト1件追加（バックエンド計38件）。本番デプロイ後、実際に複数回`/api/suggest`を実行し200 OKを確認

#### PCでのコース切り替えがしづらい問題を修正

- 一覧画面のコースカードがスマホのスワイプ操作のみを想定しており、PCでは小さなドットをクリックする以外に次のコースへ移る手段がなかったため、カード両脇に矢印ボタンを追加（マウス操作可能な環境のみ表示）

#### コース距離が指定した帯域と大きくズレる不具合を3件修正

- 初級のつもりで提案したコースが実測往復270km、中級のつもりが実測238kmになる等、AIの自己申告距離と実際の道路距離が大きく乖離する事例が複数発生
- 目的地の直線距離が難易度帯に対して明らかに遠すぎる場合、最初の試行に限り作り直すチェックを`/api/suggest`に追加
- 経由地が実際に経路上にあるかの判定（`_is_on_route`）を、緯度経度の範囲内かではなく「経由することで直行距離の何倍に迂回するか」の比率判定に変更。群馬県が目的地のコースで栃木県の道の駅を経由地に選び実測距離が直行の約1.7倍に膨らむ事例で発覚
- 上記をすり抜けて実測距離が帯域から外れた場合に備え、実測値が別の帯域に収まればその難易度へ再分類する保険を追加したが、`/api/enrich`は1コースずつ個別処理するため他コースの帯域使用状況が分からず重複・欠落が発生し、同日中に撤回した（現在は`distance_range_matched=False`のまま「距離条件外」と表示するのみで難易度ラベルは変えない。詳細は[CHANGELOG.md](../CHANGELOG.md)参照）
- 回帰テスト2件追加（バックエンド計39件）。本番で複数回`/api/suggest`を実行し距離帯逸脱の検知・作り直しをログで確認。詳細は[CHANGELOG.md](../CHANGELOG.md)参照

#### 目的地ジオコーディング失敗時のフェイルオープンと詳細画面の無限ループを追加修正

- 目的地のジオコーディング自体が失敗した場合を「距離不明として許容」していたフェイルオープンな判定を修正し、失敗時も作り直す（フェイルクローズド）よう変更
- 詳細画面を開くたびに無条件でenrichを再試行していたため、遠方すぎて構造的に失敗する目的地では無限ループが発生（同一コースへの`/api/enrich`呼び出しが1分間に100回以上）。一度失敗したら再試行しないガードを追加

#### 中級コースが実測337km・上級が実測363kmになる事故の根本原因調査と目的地アンカー方式の導入

- 目的地距離の事前チェックが最初の試行(attempt==0)のみで、リトライ後の最終試行はノーチェックで無条件受理していた構造的な穴をCloudWatchログで特定・修正。最終試行でもチェックし、乖離時はメトリクスで可視化するよう変更
- 根本対策として「目的地アンカー方式」を導入。各帯域の目安距離・ランダムな方角から算出した地点をNominatim逆ジオコーディングで実在の地名まで確定させ、「destinationは必ずこの地名を採用すること」という絶対条件としてプロンプトに埋め込む。座標・距離の説明文だけでは効果不十分だったため、確定済みの実在地名を直接使わせる方式に強化
- 逆ジオコーディング追加によるLambda実行時間の悪化（Duration最大28秒）を、アンカー名と完全一致時のジオコーディング省略・アンカーのリクエスト単位キャッシュで緩和。上級を対象外にする案も試したが実測距離が帯域超過する事例が高頻度（4件中2件）だったため3帯域全てを対象に維持
- 本番で`/api/suggest`を12回実行し全て成功・自己申告距離36/36件が帯域内、うち8コースを`/api/enrich`で実測検証し8/8件が帯域内。Lambda実行時間は最大25,432ms（Timeout30秒に対し約4.6秒の余裕）。回帰テスト8件追加（バックエンド計49件）。詳細は[CHANGELOG.md](../CHANGELOG.md)参照

#### 目的地距離チェックに「近すぎ」の下限判定を追加

- アンカー方式導入後も「上級コースが実測往復17km」という報告。目的地「真鶴岬」（実際は直線約75km）がNominatimの誤マッチで無関係な近隣地点（直線約4km）に解決されていたことが判明。事前チェックは「遠すぎないか」の上限しか見ておらず、この異常な近さを見逃していたため、上限と対称な下限判定を追加。回帰テスト1件追加（バックエンド計50件）。本番で複数回実行し全コース帯域内・Duration最大26秒を確認

#### ジオコーディング・ルーティングをNominatim/OSRMからGoogle Maps Platformへ全面移行

- 上記「真鶴岬」誤マッチ事故を受け、Google Cloud新規プロジェクトでGeocoding API・Routes APIを有効化。既存の`geocode_place`/`reverse_geocode_place`ディスパッチャ（Google優先・Nominatimフォールバック）を、実際にコースを組み立てる`geocode_and_filter_spots`・`enrich_course`（真鶴岬誤マッチの直接の原因箇所）にも適用し、Googleが実際に使われるよう修正
- 旧Directions API（Legacy、2025年3月の料金改定で新規プロジェクトでは有効化不可）を使っていたルーティングを、新しいRoutes API（`computeRoutes`）へ全面書き換え。無料枠「Compute Routes - Essentials」に収めるため`routingPreference: TRAFFIC_UNAWARE`を明示指定
- 回帰テスト17件追加（バックエンド計67件）。本番検証で`/api/suggest`・`/api/enrich`とも正常動作・Duration悪化なし（enrichはOSRM構成の6〜7秒から1.2〜3.9秒へ高速化）を確認。詳細は[CHANGELOG.md](../CHANGELOG.md)参照

#### 目的地アンカー方式の検証漏れ（アンカーからの乖離未チェック）を修正

- 「もえぎの湯（奥多摩町）」コースで実測往復168kmになり毎回「距離条件外」警告が出る不具合を報告受け調査。中級アンカー「小ケ谷」に対しAIがアンカー名を含みつつ実際は直線約41km離れた有名地名「奥多摩湖」を選んでおり、現在地からのマクロな距離帯チェックしか行っていなかったためアンカーからの乖離を検知できていなかった
- `_destination_distance_plausible`にdestinationとアンカー座標の距離検証（`ANCHOR_MAX_DRIFT_KM=15km`）を追加。回帰テスト2件追加（バックエンド計69件）。本番デプロイ後`/api/suggest`を複数回実行し実際に乖離検知のログを確認、`/api/enrich`も正常動作を確認。詳細は[CHANGELOG.md](../CHANGELOG.md)参照

#### コース表示の簡略化（距離数値・警告文言）

- 「🛣 115kmのように数値だけ書いてあると分かりづらい」との指摘を受け、一覧カード・詳細画面の両方から「🛣 距離km」表示・所要時間チップ・「片道」「往復目安/実測」の文言を削除。難易度バッジ（色・アイコン）で概ねの距離感は分かるため、目的地名（🏁）のみを残すシンプルな表示に変更した（Xシェア文言・履歴一覧では引き続き所要時間・距離を文章の一部として使用）
- 実測距離が目標帯から外れた場合の警告文言を「実測距離が目標帯を外れました。別コースをおすすめします。」から「実測距離は目標帯と異なります。」に簡略化（事実のみを伝え、行動の提案は削除）
- `npm run test`22件パス・ビルド確認後、本番デプロイ済み
