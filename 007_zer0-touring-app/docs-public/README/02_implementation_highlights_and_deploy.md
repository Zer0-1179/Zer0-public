# 実装のこだわり・ディレクトリ構成・デプロイ

実装上のこだわりポイント、ディレクトリ構成、デプロイ手順。

[← 目次に戻る](../README.md)

---

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

### 6. Google Maps Platform 優先 / Nominatim・OSRM フォールバック（高速対応ルーティング）

AI が推測した距離・時間を実際の道路データで上書きする。ジオコーディング・ルーティングともに **Google Maps Platform を優先**し、無料枠超過・APIエラー時のみ OSS 無料公開APIへフォールバックする（2026-09-06、Nominatimの誤マッチによる実障害を機に全面移行。旧Directions API（Legacy）は2025年3月の料金改定で新規プロジェクトでは有効化できないため、ルーティングは新しいRoutes API（`computeRoutes`）を使用）。

1. 目的地名を **Google Geocoding API** で GPS 座標に変換（`bounds`パラメータで現在地周辺に偏らせ、`region=jp`指定）。無料枠超過・0件ヒット・APIエラー時のみ **Nominatim**（OpenStreetMap ジオコーダー）へフォールバック
2. **DynamoDB Conditional Update** で今月の Google Geocoding API・Routes API それぞれの使用カウントを独立してアトミックに確認・予約（Routes APIは9,900超、Geocoding APIは9,500超で自動的にフォールバックへ）
3. **Google Routes API**（`POST https://routes.googleapis.com/directions/v2:computeRoutes`、`routingPreference: TRAFFIC_UNAWARE`で無料枠「Compute Routes - Essentials」の範囲を維持）: 高速道路を含む実走行時間・距離を取得
4. **OSRM フォールバック**: 実道路距離を取得し、距離帯別平均速度で所要時間を算出
   - ≥80km: 70km/h（高速想定）/ 40〜80km: 55km/h / <40km: 40km/h
5. ジオコーディング失敗・異常値（500km超）は AI 推定値にフォールバック

GMAPS_FREE_LIMIT（Routes API）を 10,000 ではなく **9,900**、GEOCODE_FREE_LIMIT（Geocoding API）を **9,500** にしているのは、それぞれバッファを確保するため（Geocoding APIは1リクエストあたりの呼び出し回数が多いためバッファを広めに取る）。DynamoDB Conditional Update によりアトミックに増分するため並列実行時でも上限を正確に守れる。

### 7. 天気連動表示（現在地 + 目的地）

現在地の天気を結果画面へフィードバックするだけでなく、Lambda が Google Geocoding API（優先）/ Nominatim（フォールバック）でジオコーディングした目的地座標で **Open-Meteo を再取得**し、目的地の現在天気も返す。

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

AI が生成した立ち寄りスポット名を Lambda 内で Google Geocoding API（優先）/ Nominatim（フォールバック）によりジオコーディングし、`origin → destination` のバウンディングボックス外のスポットをナビ・地図用の経由点から除外する。表示用の提案スポットは別配列に残すため、ジオコード失敗や方向不一致で観光地・道の駅・温泉／銭湯の表示が消えない。Google マップには検証済みの `lat,lon` 座標を優先して渡すことで誤ジオコーディングによるルート崩壊を防ぐ。

行き経由地（`outbound_spots`）と帰り立ち寄り（`return_spots`）を分離し、目的地を含めた全スポットをコース間でも重複排除する。端末内には直近60件を保存し、次回のAI提案ではデータ境界付きの除外条件として渡すことで、同じ場所の反復も抑える（1回の生成で目的地+スポットが最大12件程度増えるため、18件では2回の再検索で最初の除外対象が押し出され同じコースが再提案される不具合があり、2026-09-04に60件へ拡張）。AI出力は初級・中級・上級の3件すべてが距離帯・必須スポット・重複なしの条件を満たす場合だけ返す。各コースは観光地または展望台を含み、3コース全体では道の駅を1件以上、温泉・日帰り温泉・銭湯を1件以上必須とする。

### 12. 詳細取得APIの悪用防止

`POST /api/enrich` はGoogle Geocoding API・Google Routes API・Nominatim・OSRMを呼び出すため、IP別・日別に9回（提案3回×各3コース）へ制限する。目的地・経由地点・座標も外部API呼び出し前に検証し、任意地点の検索プロキシとして使えないようにする。地図とGoogleマップナビには座標検証済みの経由地点だけを渡し、詳細取得前は目的地直行にする。

### 13. IPレートリミット（DynamoDB）

DynamoDB の Conditional Update で IP 別・日別のカウントをアトミックに管理。1日3回を超えると 429 を返す。TTL で翌々日0時に自動削除。トップ画面には残回数をドットバッジで表示（3/3 形式）。管理者は `X-Admin-Token` ヘッダーでレート制限をバイパスできる。

### 14. URL短縮 + OGP（DynamoDB + Lambda HTML レスポンス）

静的サイト（S3 + CloudFront）は動的 OGP メタタグを生成できないため、Lambda が `/s/{id}` に対して OGP メタタグ付き HTML を直接返し、その後アプリへリダイレクトする方式で解決。

```text
SNS にシェア → /s/abc123 → Lambda が OGP HTML 返却 → SNS クローラーがプレビュー生成
              → ユーザーがタップ → JS で /?course=... へリダイレクト → アプリがコース復元
```

- 6文字英数字 ID（`random.choices`）を DynamoDB に保存（TTL 30日で自動削除）
- `og:image` は Wikipedia REST API から目的地の写真を取得（失敗時はアプリアイコン）
- コースデータは `base64(url_encode(JSON.stringify()))` 形式でリダイレクト URL に埋め込み（Python/JS で相互変換可能）
- `/s/*` は CloudFront のキャッシュビヘイビアで API Gateway オリジンへルーティング

### 15. コース別景観シルエット（CSS clip-path）

カードヘッダー背景をコース種別で視覚的に差別化。`::before`/`::after` 擬似要素に `clip-path: polygon()` を使って地形シルエットを描画し、JavaScript による DOM 変更なしに純粋な CSS で実装。

| コース | 背景色 | シルエット形状                   |
| ------ | ------ | -------------------------------- |
| 初級 | 濃緑   | 低い丘と木立（緩やかな波形）     |
| 中級 | 紺青   | 海の水平線（波とグラデーション） |
| 上級 | 深紫   | ギザギザ山脈（2層：前景と背景）  |

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
│   ├── cfn-certificate.yaml  # ACM（us-east-1）
│   ├── cfn-touring.yaml      # メインリソース
│   └── deploy-infra.sh                  # フルデプロイ
├── scripts/
│   └── generate_diagram.py      # アーキテクチャ図生成（matplotlib版、2026-08-10以降は未使用）
└── images/
    ├── 007_architecture_plugin.drawio        # 構成図（draw.ioで手動編集する一次情報源）
    └── 007_architecture_plugin_flowdot.svg   # 上記からエクスポートした画像（本ドキュメントで表示）
```

## デプロイ

```bash
# Lambda のみ更新
cd backend && zip -j /tmp/touring.zip lambda_function.py
aws lambda update-function-code --function-name zer0-touring-suggest \
  --zip-file fileb:///tmp/touring.zip --region ap-northeast-1

# フロントエンドのみ更新
cd frontend && npm run build
# stats.jsonはzer0-touring-stats Lambdaが日次生成する動的ファイルでビルド成果物に含まれないため、
# --deleteで誤って消さないよう必ず--excludeすること（2026-08-09に一度誤削除する事故あり）
aws s3 sync dist/ s3://zer0-touring-s3 --delete --exclude "stats.json"
aws cloudfront create-invalidation --distribution-id E1Z92GZIT4IDGA --paths "/*"
```
