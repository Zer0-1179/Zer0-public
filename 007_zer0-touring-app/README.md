# 007 Zer0 Touring App

バイク乗りが「今すぐ走りたい」とき、現在地と天気をもとにAIが日帰りツーリングコースを3つ提案するPWAアプリ。

## URL

**https://touring.zer0-infra.com**

## アーキテクチャ

![アーキテクチャ図](../images/007_architecture.png)

| レイヤー       | 技術                                                 |
| -------------- | ---------------------------------------------------- |
| フロントエンド | Astro (static) + PWA (Web Manifest + Service Worker) |
| 現在地取得     | ブラウザ Geolocation API                             |
| 天気取得       | Open-Meteo API（無料・APIキー不要）                  |
| AIコース提案   | AWS Bedrock Claude Haiku                             |
| API            | Lambda + API Gateway (HTTP API)                      |
| ホスティング   | CloudFront + S3                                      |
| ドメイン       | touring.zer0-infra.com                               |

月額コスト: ~$0.40/月（100回利用想定）、1回あたり ~$0.005（約0.7円）

## 画面構成

| 画面       | 内容                                                                                |
| ---------- | ----------------------------------------------------------------------------------- |
| Landing    | バイクアイコン + 「コースを探す」ボタン                                             |
| Loading    | GPS取得 → 天気確認 → AI生成中（ステップ表示）                                       |
| コース一覧 | 近距離・中距離・長距離の3カラムグリッド（PC）/ 1列（モバイル）                      |
| コース詳細 | Wikipedia写真・見どころ・道路タイプ・立ち寄りスポット・注意・シーズン・Googleマップ |

## ディレクトリ構成

```texy
007_Zer0_TouringApp/
├── frontend/           # Astro PWA ソース
├── backend/            # Lambda 関数
├── infra/              # CloudFormation テンプレート + デプロイスクリプト
├── generate_diagram.py # アーキテクチャ図生成
└── システム仕様書.md
```

## デプロイ手順

### 通常デプロイ（フルスタック）

```bash
bash infra/deploy-infra.sh
```

### Lambda コードのみ更新

```bash
bash backend/deploy.sh
```

### フロントエンドのみ更新

```bash
cd frontend && npm run build
aws s3 sync dist/ s3://zer0-touring-s3 --delete
aws cloudfront create-invalidation --distribution-id E1Z92GZIT4IDGA --paths "/*"
```

## ローカル開発

```bash
cd frontend
npm install
PUBLIC_API_URL=https://9fhsk9hh5e.execute-api.ap-northeast-1.amazonaws.com npm run dev
```
