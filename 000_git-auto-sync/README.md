# 000 Git Auto Sync

プライベート作業領域（WSL `/root/Zer0`）から公開用 GitHub リポジトリ（`Zer0-public`）へ、機密ファイルを除外しながら自動同期するスクリプト。

## 概要

```
/root/Zer0/  (プライベート・WSL)
    │
    ├── 001_aws-x-poster/
    ├── 002_Zenn_Auto_Article_Bot/
    ├── 003_X_AI_Bot/
    ├── 004_portfolio/
    ├── 005_Zenn_Mid_Article_Bot/
    └── sync_to_public.sh  ← このスクリプト
              │
              │  rsync（機密除外）
              ▼
/mnt/c/.../Zer0-public/  (公開・Git管理)
    │
    ├── 001_aws-x-poster/
    ├── 002_zenn-article-bot/
    ├── 003_x-ai-bot/
    ├── 004_portfolio/
    ├── 005_zenn-mid-article-bot/
    └── README.md
              │
              │  git add / commit / push
              ▼
    GitHub: Zer0-1179/Zer0-public
```

## 使い方

```bash
cd /root/Zer0
bash sync_to_public.sh
```

変更がない場合は自動的にスキップされる。

## 除外ファイル一覧

| パターン | 理由 |
|---|---|
| `*apikey*` | APIキー等の機密ファイル |
| `.env` | 環境変数（RSS URLなど） |
| `システム仕様書.md` | 詳細仕様（公開不要） |
| `.git/` | Gitメタデータ |
| `node_modules/` | 依存パッケージ（巨大） |
| `dist/` | ビルド成果物 |
| `.astro/` | Astroキャッシュ |
| `layer/`, `output/`, `.aws-sam/` | AWSデプロイ成果物 |
| `article/` | 生成記事（公開不要） |
| `*.zip`, `*.pyc`, `__pycache__/` | バイナリ・キャッシュ |

## プロジェクトマッピング

| プライベート名 | 公開名 |
|---|---|
| `001_aws-x-poster` | `001_aws-x-poster` |
| `002_Zenn_Auto_Article_Bot` | `002_zenn-article-bot` |
| `003_X_AI_Bot` | `003_x-ai-bot` |
| `004_portfolio` | `004_portfolio` |
| `005_Zenn_Mid_Article_Bot` | `005_zenn-mid-article-bot` |
