# 007 Zer0 Touring App

> 現在地とリアルタイム天気から Bedrock Claude Haiku が日帰りバイクツーリングコース3ルートを提案する PWA。GPS → Open-Meteo → Bedrock の3ステップを全自動化し、現在地・目的地の天気比較・片道/往復時間・帰路提案・特徴タグ・Googleマップナビ連携まで一括生成する。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20CloudFront-orange)](https://aws.amazon.com)
[![Astro](https://img.shields.io/badge/Astro-Static%20PWA-FF5D01)](https://astro.build)
[![Site](https://img.shields.io/badge/サイト-touring.zer0--infra.com-blue)](https://touring.zer0-infra.com)
[![Cost](https://img.shields.io/badge/月額-~%240.40-green)](https://aws.amazon.com/pricing)

## 概要

| 項目         | 内容                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------- |
| URL          | https://touring.zer0-infra.com                                                              |
| 現在地取得   | ブラウザ Geolocation API（30秒タイムアウト）                                                |
| 天気取得     | Open-Meteo API（現在地・目的地の両方／無料・APIキー不要）                                   |
| AI提案       | Amazon Bedrock Claude Haiku（片道・往復時間・帰路・特徴タグを含む詳細コース生成）           |
| コース内容   | 近距離・中距離・長距離 + タグ・立ち寄りスポット（経路順）・帰路提案                         |
| 距離・時間   | **Google Maps Directions API（優先）** / OSRM（フォールバック）による実道路距離・走行時間   |
| 天気比較     | 詳細画面に現在地 🏍️→ 目的地の天気比較ウィジェット（バイク走行アニメーション付き）           |
| 週間天気     | 現在地・目的地の7日間天気予報ストリップ（狙い目日ハイライト）                               |
| シェア       | Xシェア・URLコピー（`?course=` Base64でコース情報を復元可能）                               |
| ナビ         | Googleマップ連携（立ち寄りスポット含む / 全デバイス統一 Google Maps URL）                   |
| ホスティング | CloudFront + S3（PWA / Service Worker 対応）                                                |
| 月額コスト   | ~$0.40（100回利用想定）/ 1回 ~$0.005（約0.7円）                                             |

## アーキテクチャ

![アーキテクチャ図](images/007_architecture.png)

```text
[スマホ/PC ブラウザ]
  ├─ GPS（Geolocation API）
  ├─ 天気（Open-Meteo API / 直接 fetch）
  └─ POST /api/suggest
        └─▶ CloudFront（touring.zer0-infra.com）
              ├─ /* → S3（Astro static / HTML・CSS・JS）
              └─ /api/* → API Gateway → Lambda → Bedrock Claude Haiku
                                                     ├─ Nominatim（ジオコーディング）
                                                     ├─ Google Maps Directions API（走行時間）
                                                     ├─ OSRM（フォールバック距離）
                                                     └─ Open-Meteo（目的地天気）
```

## 技術スタック

| レイヤー       | 技術                                                                                                            |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| フロントエンド | Astro（`output: 'static'`）+ PWA（Web Manifest + Service Worker）                                               |
| 現在地取得     | ブラウザ Geolocation API                                                                                        |
| 天気取得       | Open-Meteo API（現在地・目的地・7日間予報 / 無料・APIキー不要）                                                 |
| AI提案         | Amazon Bedrock **Claude Haiku 4.5**（`jp.anthropic.claude-haiku-4-5-20251001-v1:0` / max_tokens: 2,048）        |
| 距離・走行時間 | **Google Maps Directions API**（優先・月10,000件無料） + Nominatim（OSM ジオコーディング）→ OSRM フォールバック |
| API            | AWS Lambda（Python 3.14）+ API Gateway HTTP API                                                                 |
| 使用数管理     | AWS SSM Parameter Store（`/zer0-touring/gmaps-usage`：Google Maps 月間使用カウント）                            |
| レートリミット | Amazon DynamoDB（`zer0-touring-ratelimit`：IP 別・日別 3回制限 / TTL で翌々日自動削除）                         |
| 使用回数UI     | GET /api/status でトップ画面にドット形式の残回数バッジを表示（管理者モード対応）                                 |
| ホスティング   | Amazon CloudFront + S3（OAC 署名付きアクセス）                                                                  |
| 写真（詳細）   | Wikipedia REST API（`/api/rest_v1/page/summary/{spot}`）/ 失敗時はグラデーション+🏍️                             |
| IaC            | CloudFormation（2スタック: メイン + ACM 証明書）                                                                |

## UI フロー

```text
Landing（コースを探す）
  └─▶ Loading（GPS取得中 → 天気確認中 → AI生成中）
        └─▶ コース一覧（スワイプカード / 1枚ずつ表示・横スワイプで切り替え）
              │  各カード: 近距離🟢（丘シルエット）/中距離🔵（海シルエット）/長距離🟣（山脈シルエット）
              │            ルートサマリー（📍現在地 → 立ち寄り → 目的地）
              │            片道/往復 約X時間Y分・目的地天気バッジ（📌 ☀️ 22℃）
              │            特徴タグ（🌊 海沿い / 🏔 峠道 / ♨️ 温泉 等）
              │  画面下部: 現在地の週間天気予報ストリップ（最高/最低気温）
              └─▶ コース詳細
                    │  写真 / 現在地⇔目的地 天気比較ウィジェット（🏍️ アニメーション）
                    │  見どころ / 道路タイプ / 立ち寄りスポット / 帰路 / 地図
                    │  目的地の週間天気予報ストリップ（最高/最低気温）
                    ├─ 🗺 Googleマップでナビ開始（立ち寄りスポット含む）
                    ├─ 𝕏 でシェア
                    └─ 🔗 URLをコピー（?course= で復元可能）
```

## 実装のこだわり

### 1. API 設計：CloudFront のパスベースルーティング

フロントエンド（S3）と API（Lambda）を**同一ドメイン**に統合。CloudFront のキャッシュビヘイビアで `/api/*` を API Gateway Origin に振り分けることで、CORS 不要・同一オリジン通信を実現。

### 2. GPS タイムアウト設計

初回 GPS 取得はブラウザの初期化処理があるため時間がかかる。当初10秒タイムアウトで設定したが、初回利用時にタイムアウトエラーが頻発する問題が発生。**30秒に延長**し、エラーコード別のメッセージ（`code=1`: 拒否 / `code=3`: タイムアウト）で UX を改善。

### 3. Bedrock プロンプト設計（構造化 JSON 出力）

プロンプトで JSON スキーマを厳密に定義。立ち寄りスポットは**現在地 → スポット1 → スポット2 → 目的地**の地理的順序で並べること、純粋な走行時間（休憩・観光時間を含まない）で計算することを明示してプロンプトで制御。

### 4. Googleマップナビ：立ち寄りスポット含む全ルート案内

立ち寄りスポットを waypoints として含めた状態で起動。全デバイスで同一の `https://` URL に統一（iOS `comgooglemaps://` は廃止）。

```javascript
// iOS / Android / Web 全デバイス統一
// 目的地・waypoints はジオコード済み座標を優先使用（名前フォールバックあり）
https://www.google.com/maps/dir/?api=1&origin=LAT,LON&destination=DEST_LAT,DEST_LON&waypoints=spot1_lat,spot1_lon|spot2_lat,spot2_lon&travelmode=driving
```

- `comgooglemaps://` は廃止。iOS でも `https://` で開くと Google マップアプリが起動する
- `google.navigation:` スキームは waypoints 非対応のため使用しない
- 行き経由地（`outbound_spots`）を waypoints として含める。帰り立ち寄り（`return_spots`）は別管理

### 5. URLシェア・コース復元（Base64エンコード）

詳細画面を開くと `?course=<Base64>` が URL に付与され、URL をコピーして共有すると受信者がそのコースを直接詳細画面で閲覧できる。

```javascript
// エンコード（日本語対応）
btoa(encodeURIComponent(JSON.stringify(courseData)))
// デコード
JSON.parse(decodeURIComponent(atob(param)))
```

### 6. Google Maps 優先 / OSRM フォールバック（高速対応ルーティング）

AI が推測した距離・時間を実際の道路データで上書きする。**月10,000件の無料枠内は Google Maps Directions API を優先**し、枠超過時は OSRM にフォールバックする。

1. 目的地名を **Nominatim**（OpenStreetMap ジオコーダー）で GPS 座標に変換
2. SSM で今月の Google Maps 使用カウントを確認・予約（9,900 超なら OSRM へ）
3. **Google Maps**: 高速道路を含む実走行時間・距離を取得
4. **OSRM フォールバック**: 実道路距離を取得し、距離帯別平均速度で所要時間を算出
   - ≥80km: 70km/h（高速想定）/ 40〜80km: 55km/h / <40km: 40km/h
5. ジオコーディング失敗・異常値（500km超）は AI 推定値にフォールバック

GMAPS_FREE_LIMIT を 10,000 ではなく **9,900** にしているのは、Lambda が複数インスタンスで並列実行される場合に SSM への読み書きがアトミックでないため、同時アクセス時の二重カウント誤差を吸収するバッファ。

### 7. 天気連動表示（現在地 + 目的地）

現在地の天気を結果画面へフィードバックするだけでなく、Lambda が Nominatim でジオコーディングした目的地座標で **Open-Meteo を再取得**し、目的地の現在天気も返す。

- **カード**: 目的地天気バッジ `📌 ☀️ 22℃` をカードヘッダー左下に表示
- **詳細画面**: 現在地 ↔ 目的地の天気を横並び比較。中央にバイク🏍️が左から右へ走るアニメーション
- **週間予報**: 現在地（コース一覧下部）・目的地（詳細画面内）それぞれに7日間ストリップを表示し、スコア最高日に「★ 狙い目」バッジ

### 8. Service Worker：ネットワークファーストで常に最新を取得

`index.html` はネットワーク優先で取得してキャッシュ更新。ハッシュ付き静的アセット（`_astro/*.js`）はキャッシュファーストで高速配信。

```javascript
// index.html → network-first（デプロイ直後に反映）
// _astro/*.js → cache-first（コンテンツハッシュで変更検知）
```

### 9. Astro `define:vars` ではなく `import.meta.env` を使用

`define:vars` を使うと Astro がスクリプトを IIFE でラップし、Vite のバンドル処理と競合してスクリプト内容が消える問題が発生。`import.meta.env.PUBLIC_API_URL` を直接使うことで Vite がビルド時に環境変数を安全に置換する方式に変更。

### 10. iOS Safari のバックグラウンドリロード対応

iOS Safari はバックグラウンドに回った後に再フォアグラウンドするとページをリロードする。詳細画面の URL `/?course=xxx` でリロードされた場合でもコースを Base64 URL から復元して詳細画面を直接表示できる。また、ブラウザネイティブの戻るジェスチャー（`popstate` イベント）でも詳細 → 一覧への遷移を正しく処理する。

### 11. Waypoint ジオコード＋方向フィルタ

AI が生成した立ち寄りスポット名を Lambda 内で Nominatim（OSM）によりジオコーディングし、`origin → destination` のバウンディングボックス外のスポットを除外する。Google マップには名前ではなく `lat,lon` 座標を渡すことで誤ジオコーディングによるルート崩壊を防ぐ。

行き経由地（`outbound_spots`）と帰り立ち寄り（`return_spots`）を分離することで、往復で異なるスポットを UI に表示できる。

### 12. IPレートリミット（DynamoDB）

DynamoDB の Conditional Update で IP 別・日別のカウントをアトミックに管理。1日3回を超えると 429 を返す。TTL で翌々日0時に自動削除。トップ画面には残回数をドットバッジで表示（3/3 形式）。管理者は `X-Admin-Token` ヘッダーでレート制限をバイパスできる。

### 13. コース別景観シルエット（CSS clip-path）

カードヘッダー背景をコース種別で視覚的に差別化。`::before`/`::after` 擬似要素に `clip-path: polygon()` を使って地形シルエットを描画し、JavaScript による DOM 変更なしに純粋な CSS で実装。

| コース | 背景色 | シルエット形状                   |
| ------ | ------ | -------------------------------- |
| 近距離 | 濃緑   | 低い丘と木立（緩やかな波形）     |
| 中距離 | 紺青   | 海の水平線（波とグラデーション） |
| 長距離 | 深紫   | ギザギザ山脈（2層：前景と背景）  |

## ディレクトリ構成

```text
007_Zer0_TouringApp/
├── frontend/                    # Astro static PWA
│   ├── src/pages/index.astro    # 全画面（Landing/Loading/一覧/詳細/Error）
│   ├── public/
│   │   ├── manifest.json        # PWA マニフェスト
│   │   ├── sw.js                # Service Worker（ネットワークファースト）
│   │   └── icons/               # アプリアイコン（192px / 512px）
│   ├── astro.config.mjs
│   └── package.json
├── backend/
│   ├── lambda_function.py       # Bedrock コース提案 API
│   └── deploy.sh                # Lambda デプロイ
├── infra/
│   ├── cloudformation-certificate.yaml  # ACM（us-east-1）
│   ├── cloudformation-touring.yaml      # メインリソース
│   └── deploy-infra.sh                  # フルデプロイ
├── generate_diagram.py          # アーキテクチャ図生成
└── images/
    └── 007_architecture.png
```

## デプロイ

```bash
# Lambda のみ更新
cd backend && zip -j /tmp/touring.zip lambda_function.py
aws lambda update-function-code --function-name zer0-touring-suggest \
  --zip-file fileb:///tmp/touring.zip --region ap-northeast-1

# フロントエンドのみ更新
cd frontend && npm run build
aws s3 sync dist/ s3://zer0-touring-s3 --delete
aws cloudfront create-invalidation --distribution-id E1Z92GZIT4IDGA --paths "/*"
```

## API リファレンス

### POST /api/suggest

**リクエスト**  

```json
{ "latitude": 35.6762, "longitude": 139.6503, "temperature": 22, "weather_condition": "晴れ" }
```

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

**所要時間**：純粋な走行時間のみ（休憩・観光時間は含まない）。Google Maps / OSRM の実データで AI 推定値を上書き。フロントエンド表示は「約X時間Y分」形式、分は10分単位で切り上げ。

### GET /api/status

**レスポンス**

```json
{ "used": 1, "limit": 3, "remaining": 2 }
```

管理者トークン一致時は `{ "used": 0, "limit": 3, "remaining": 3, "admin": true }`。

## コスト内訳

| サービス                                              | 月額（100回利用）    |
| ----------------------------------------------------- | -------------------- |
| Bedrock Claude Haiku（in: ~720 / out: ~1,200 tokens） | ~$0.40               |
| Lambda 実行（~3秒 / 256MB）                           | ~$0.001              |
| Google Maps Directions API（300回/月以内）            | $0（無料枠内）       |
| DynamoDB（zer0-touring-ratelimit / PAY_PER_REQUEST） | ~$0（無料枠内）      |
| API Gateway・CloudFront・S3                           | ~$0                  |
| **合計**                                              | **~$0.40（約60円）** |
