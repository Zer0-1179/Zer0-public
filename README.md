# ~/Zer0/ — プロジェクト管理ルート

## フォルダ構成

```text
~/Zer0/
├── README.md                      # このファイル（公開リポジトリと共用）
├── sync_to_public.sh              # プライベート→公開リポジトリ同期スクリプト
├── 000_git-auto-sync/             # git自動同期の仕様書・ドキュメント
├── 001_aws-x-poster/              # AWSニュース自動投稿ボット（@Zer0_Infra）
├── 002_Zenn_Auto_Article_Bot/     # Zenn初級者向け技術記事自動生成ボット（毎週木曜）
├── 003_X_AI_Bot/                  # AI活用術 X自動投稿ボット
├── 004_portfolio/                 # Astro SSR ポートフォリオサイト
├── 005_Zenn_Mid_Article_Bot/      # Zenn中級者向け技術記事自動生成ボット（毎月2回）
└── 006_Zer0_CryptoBot/           # 仮想通貨自動売買Bot（SOL/AVAX/ARB、4時間毎）
```

## 運用ルール

- アプリ・ツール・ボットを作るたびに、このディレクトリ直下に連番フォルダ（001〜999）を追加する
- 各フォルダの内部構成は、そのフォルダ内の README.md で管理する

## プロジェクト一覧

| フォルダ名                  | 内容                                                               | ステータス               |
| --------------------------- | ------------------------------------------------------------------ | ------------------------ |
| `000_git-auto-sync`         | プライベート→公開リポジトリのgit自動同期ドキュメント               | 運用中                   |
| `001_aws-x-poster`          | AWSニュースをRSSで取得しBedrockで加工してX投稿（朝・夜2回/日）     | 稼働中                   |
| `002_Zenn_Auto_Article_Bot` | 毎週木曜21時にBedrockでAWS初心者向けZenn技術記事を自動生成・S3保存 | 稼働中                   |
| `003_X_AI_Bot`              | AI活用術ジャンルのXアカウントを1日2回自動投稿（21時＋日曜10時）    | 稼働中                   |
| `004_portfolio`             | Astro SSR ポートフォリオサイト（CloudFront + Lambda + S3）         | 稼働中                   |
| `005_Zenn_Mid_Article_Bot`  | 毎月1日・15日21時にAWS中級者向けZenn技術記事を自動生成・S3保存     | 稼働中                   |
| `006_Zer0_CryptoBot`        | SOL/AVAX/ARBをBinanceシグナル+bitbank執行で4時間毎に自動売買        | 稼働中                   |
