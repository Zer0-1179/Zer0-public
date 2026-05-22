# 007 Zer0 Touring App

> 現在地とリアルタイム天気から Bedrock Claude Haiku が日帰りバイクツーリングコース3ルートを提案する PWA。GPS → Open-Meteo → Bedrock の3ステップを全自動化し、道路タイプ・立ち寄りスポット・走行注意までAIが生成する。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20CloudFront-orange)](https://aws.amazon.com)
[![Astro](https://img.shields.io/badge/Astro-Static%20PWA-FF5D01)](https://astro.build)
[![Site](https://img.shields.io/badge/サイト-touring.zer0--infra.com-blue)](https://touring.zer0-infra.com)
[![Cost](https://img.shields.io/badge/月額-~%240.40-green)](https://aws.amazon.com/pricing)

## 概要

| 項目 | 内容 |
|------|------|
| URL | https://touring.zer0-infra.com |
| 現在地取得 | ブラウザ Geolocation API（許可後30秒タイムアウト） |
| 天気取得 | Open-Meteo API（無料・APIキー不要） |
| AI提案 | Amazon Bedrock Claude Haiku（3コース生成・~1,000 tokens出力） |
| コース内容 | 近距離・中距離・長距離 + 道路タイプ・立ち寄りスポット・走行注意・ベストシーズン |
| 写真 | Wikipedia API でサムネイル非同期ロード（フォールバック: グラデーション） |
| ホスティング | CloudFront + S3（PWA / Service Worker 対応） |
| 月額コスト | ~$0.40（100回利用想定）/ 1回 ~$0.005（約0.7円） |

## アーキテクチャ

![アーキテクチャ図](images/007_architecture.png)

```
[スマホ/PC ブラウザ]
  ├─ GPS（Geolocation API）
  ├─ 天気（Open-Meteo API / 直接 fetch）
  └─ POST /api/suggest
        └─▶ CloudFront（touring.zer0-infra.com）
              ├─ /* → S3（Astro static / HTML・CSS・JS）
              └─ /api/* → API Gateway → Lambda → Bedrock Claude Haiku
```

## 技術スタック

| レイヤー | 技術 |
|----------|------|
| フロントエンド | Astro（`output: 'static'`）+ PWA（Web Manifest + Service Worker） |
| 現在地取得 | ブラウザ Geolocation API |
| 天気取得 | Open-Meteo API（無料・APIキー不要） |
| AI提案 | Amazon Bedrock（Claude Haiku / max_tokens: 2,048） |
| API | AWS Lambda（Python 3.14）+ API Gateway HTTP API |
| ホスティング | Amazon CloudFront + S3（OAC 署名付きアクセス） |
| 写真 | Wikipedia REST API（`/api/rest_v1/page/summary/{spot}`） |
| IaC | CloudFormation（2スタック: メイン + ACM 証明書） |

## UI フロー

```
Landing（コースを探す）
  └─▶ Loading（GPS取得中 → 天気確認中 → AI生成中）
        └─▶ コース一覧（近距離/中距離/長距離 × 3カラムグリッド）
              └─▶ コース詳細（Wikipedia写真 + 見どころ + 道路タイプ + スポット + 地図）
```

## 実装のこだわり

### 1. API 設計：CloudFront のパスベースルーティング
フロントエンド（S3）と API（Lambda）を**同一ドメイン**に統合。CloudFront のキャッシュビヘイビアで `/api/*` を API Gateway Origin に振り分けることで、CORS 不要・同一オリジン通信を実現。

### 2. GPS タイムアウト設計
初回 GPS 取得はブラウザの初期化処理があるため時間がかかる。当初10秒タイムアウトで設定したが、初回利用時にタイムアウトエラーが頻発する問題が発生。**30秒に延長**し、エラーコード別のメッセージ（`code=1`: 拒否 / `code=3`: タイムアウト）で UX を改善。

### 3. Bedrock プロンプト設計（構造化 JSON 出力）
プロンプトで JSON スキーマを厳密に定義し、コース名・距離・時間・道路タイプ・立ち寄りスポット（name + type）・注意・シーズン・写真スポット名を一括生成。`re.search(r'\{.*\}', text, re.DOTALL)` で JSON を確実に抽出し、パース失敗時は 500 でフォールバック。

### 4. Wikipedia 写真の非同期フェードイン
```javascript
// グラデーション背景を先に表示（即座にカードが描画される）
// Wikipedia から写真ロード成功後に opacity:0 → 1 でフェードイン
img.onload = () => img.classList.add('loaded');
```
写真のロード待ちで画面がブランクになることなく、スムーズな体験を提供。

### 5. Astro `define:vars` ではなく `import.meta.env` を使用
`define:vars` を使うと Astro がスクリプトを IIFE でラップし、Vite のバンドル処理と競合してスクリプト内容が消える問題が発生。`import.meta.env.PUBLIC_API_URL` を直接使うことで Vite がビルド時に環境変数を安全に置換する方式に変更。

### 6. カード画像の統一（`aspect-ratio: 16/9`）
固定 `height: 176px` では PC 3列グリッド（~290px幅）とモバイル1列（~380px幅）で縦横比が変わり、画像が「棒状」に見える問題があった。`aspect-ratio: 16/9` に変更することでどの画面サイズでも統一された比率を保証。

## ディレクトリ構成

```
007_Zer0_TouringApp/
├── frontend/                    # Astro static PWA
│   ├── src/pages/index.astro    # 全画面（Landing/Loading/一覧/詳細/Error）
│   ├── public/
│   │   ├── manifest.json        # PWA マニフェスト
│   │   ├── sw.js                # Service Worker（オフライン対応）
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
# フルスタック（CFn + Lambda + フロントエンド）
bash infra/deploy-infra.sh

# Lambda のみ更新
bash backend/deploy.sh

# フロントエンドのみ更新
cd frontend && npm run build
aws s3 sync dist/ s3://zer0-touring-s3 --delete
aws cloudfront create-invalidation --distribution-id E1Z92GZIT4IDGA --paths "/*"
```

## ローカル開発

```bash
cd frontend && npm install

# API は API Gateway の URL を直接指定
PUBLIC_API_URL=https://9fhsk9hh5e.execute-api.ap-northeast-1.amazonaws.com npm run dev
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
    "distance_km": 80, "duration_hours": 4.0,
    "highlights": ["江の島弁財天", "鎌倉大仏"],
    "destination": "江の島",
    "photo_spot": "江の島",
    "difficulty": "初級",
    "road_types": ["国道", "海岸線"],
    "rest_spots": [{"name": "道の駅 江の島", "type": "道の駅"}],
    "caution": "海岸線は強風注意",
    "best_season": "3月〜10月"
  }]
}
```

## コスト内訳

| サービス | 月額（100回利用） |
|----------|------------------|
| Bedrock Claude Haiku（in: ~720 / out: ~1,000 tokens） | ~$0.40 |
| Lambda 実行（~3秒 / 256MB） | ~$0.001 |
| API Gateway・CloudFront・S3 | ~$0 |
| **合計** | **~$0.40（約60円）** |
