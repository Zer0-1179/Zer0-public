# 007 Zer0 Touring App

> 出発地（現在地 or 手動入力）とリアルタイム天気から Bedrock Claude Haiku が日帰りバイクツーリングコース3ルートを提案する PWA。GPS → Open-Meteo → Bedrock の3ステップを全自動化し、好みスタイルタグ（峠道・海沿い・温泉・グルメ・絶景・自然・歴史・ガッツリ走る・のんびり）によるコース調整、現在地・目的地の天気比較・片道/往復時間・帰路提案・特徴タグ・Googleマップナビ連携・OGP付きURL短縮シェアまで一括生成する。

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20CloudFront-orange)](https://aws.amazon.com)
[![Astro](https://img.shields.io/badge/Astro-Static%20PWA-FF5D01)](https://astro.build)
[![Site](https://img.shields.io/badge/サイト-touring.zer0--infra.com-blue)](https://touring.zer0-infra.com)
[![Cost](https://img.shields.io/badge/月額-~%240.40-green)](https://aws.amazon.com/pricing)

## 概要

| 項目 | 内容 |
| --- | --- |
| URL | `https://touring.zer0-infra.com` |
| 出発地取得 | 現在地（ブラウザ Geolocation API）または手動入力（Google Geocoding API優先・Nominatimフォールバック） |
| 天気取得 | Open-Meteo API（現在地・目的地の両方／無料・APIキー不要） |
| AI提案 | Amazon Bedrock Claude Haiku（好みタグ反映・片道/往復時間・帰路・特徴タグ含む詳細コース生成） |
| コース内容 | 初級（往復20〜49km）・中級（往復50〜99km）・上級（往復100km〜） + タグ・立ち寄りスポット（経路順）・帰路提案 |
| 距離・時間 | **Google Routes API（優先）** / OSRM（フォールバック）による往復の実道路距離・走行時間を取得し、距離帯判定・警告表示に反映（画面には具体的な距離数値は表示しない、2026-09-06〜） |
| 天気比較 | 詳細画面に現在地 🏍️→ 目的地の天気比較ウィジェット（バイク走行アニメーション付き） |
| 週間天気 | 現在地・目的地の7日間天気予報ストリップ（狙い目日ハイライト） |
| シェア | Xシェア・URL短縮コピー（`POST /api/share` → `https://touring.zer0-infra.com/s/abc123`。OGP対応でSNS展開時にコース情報プレビューを表示） |
| ナビ | Googleマップ連携（立ち寄りスポット含む / 全デバイス統一 Google Maps URL） |
| ホスティング | CloudFront + S3（PWA / Service Worker 対応） |
| 月額コスト | ~$0.40（100回利用想定）/ 1回 ~$0.005（約0.7円） |

## 詳細ドキュメント

| # | ファイル | 内容 |
| --- | --- | --- |
| 01 | [architecture_stack_and_ui.md](README/01_architecture_stack_and_ui.md) | アーキテクチャ構成図・技術スタック・UIフロー |
| 02 | [implementation_highlights_and_deploy.md](README/02_implementation_highlights_and_deploy.md) | 実装のこだわり・ディレクトリ構成・デプロイ手順 |
| 03 | [api_setup_ops_and_changelog.md](README/03_api_setup_ops_and_changelog.md) | APIリファレンス・初回セットアップ・運用コマンド・トラブルシューティング・コスト内訳・変更履歴 |

全履歴は[CHANGELOG.md](CHANGELOG.md)を参照。

---

2026-09-08時点で単一ファイル（499行）が長大化していたため、テーマ別に分割した（`/root/Zer0/CLAUDE.md`「ドキュメント分割の必須ルール」参照）。内容は全て過不足なく移行済み。
