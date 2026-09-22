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

### 2026-09-22

#### 構成図ダークモード対策が再発していたのを発見・再修正（本番）

- 100_Ritsuan配下プロジェクトの構成図調査を機に001〜008・010を横断確認したところ、本番公開SVG（004_portfolioの`src/public/images/007_architecture.svg`）に`light-dark(`が23箇所残存し、2026-09-07に修正したはずのダークモード表示崩れバグ（そもそも007で最初に見つかったバグ）が再発していたことが判明した
- 原因はプロジェクトローカル版`build_architecture_flowdot.py`の`force_light_mode()`が2026-09-07の`_strip_light_dark()`強化を取り込んでおらず、後日の構成図再編集時に古いロジックで再生成し修正が上書きされていたこと。`_strip_light_dark()`を直接適用して除去（23箇所→0）、ローカル版スクリプトも最新ロジックへ更新した
- `bash 004_portfolio/scripts/deploy.sh`で本番デプロイ後、本番URLから画像を取得しローカルとのMD5一致・`light-dark(`残存数0件を確認済み。詳細は[CHANGELOG.md](../CHANGELOG.md)参照
