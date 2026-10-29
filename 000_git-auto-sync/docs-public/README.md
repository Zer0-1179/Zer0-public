# 000 Git Auto Sync

プライベート作業領域（WSL `/root/Zer0`）から公開用 GitHub リポジトリ（`Zer0-public`）へ、機密ファイルを除外しながら自動同期するスクリプト。

## 概要

```text
/root/Zer0/  (プライベート・WSL)
    │
    ├── 000_git-auto-sync/
    ├── 001_x-poster_zer0-infra/
    ├── 002_Zenn_Auto_Article_Bot/
    ├── 003_x-poster_zer0-0326/
    ├── 004_portfolio/          ※ templates/ は公開側の templates/ へ別途同期
    ├── 005_Zenn_Mid_Article_Bot/
    ├── 006_Zer0_CryptoBot/
    ├── 007_Zer0_TouringApp/
    ├── 008_Nyusatsu_Notify_Bot/
    ├── 009_CloudNote/
    ├── README.md               ← 公開側の README.md へコピー
    └── sync_to_public.sh       ← このスクリプト
              │
              │  rsync（機密除外）
              ▼
/mnt/c/.../Zer0-public/  (公開・Git管理)
    │
    ├── 000_git-auto-sync/
    ├── 001_x-poster-zer0-infra/
    ├── 002_zenn-article-bot/
    ├── 003_x-poster-zer0-0326/
    ├── 004_portfolio/
    ├── 005_zenn-mid-article-bot/
    ├── 006_zer0-cryptobot/
    ├── 007_zer0-touring-app/
    ├── 008_nyusatsu-notify-bot/
    ├── 009_cloudnote/
    ├── templates/
    └── README.md
              │
              │  git add / commit / push
              ▼
    GitHub: Zer0-1179/Zer0-public
```

## 使い方

Claude Code の応答が終わるたびに自動で実行されるほか、各プロジェクトの `deploy.sh` からも呼び出される。手動実行も可能。

```bash
cd /root/Zer0
bash sync_to_public.sh
```

変更がない場合は自動的にスキップされる。

## 自動実行トリガー

主なトリガーは、作業ディレクトリの Claude Code 設定（`.claude/settings.local.json`）の `Stop` フックである。応答が終わるたびに `sync_to_public.sh` を非同期で実行し、ログは `/tmp/zer0-sync.log` に追記する。そのため、ファイルを編集すると数分以内に公開リポジトリへ push される。

これとは別に、以下のデプロイスクリプトの末尾からも呼び出される。各スクリプトは `set -e` / `set -euo pipefail` を設定しているため、**デプロイが失敗した場合はsyncは実行されない**。

| トリガー               | スクリプト                                |
| ---------------------- | ----------------------------------------- |
| X投稿Bot（001）デプロイ | `001_x-poster_zer0-infra/src/deploy.sh`  |
| Zenn初級Botデプロイ    | `002_Zenn_Auto_Article_Bot/src/deploy.sh` |
| ポートフォリオデプロイ | `004_portfolio/scripts/deploy.sh`         |
| Zenn中級Botデプロイ    | `005_Zenn_Mid_Article_Bot/src/deploy.sh`  |
| CryptoBotデプロイ      | `006_Zer0_CryptoBot/scripts/deploy.sh`    |

## 公開前スキャン

rsync 後・push 前に公開先ディレクトリをスキャンし、以下が見つかった場合は push を中止する。

| 検出パターン               | 対象                                             |
| -------------------------- | ------------------------------------------------ |
| AWSアカウントID            | ハードコードされたアカウントID                   |
| AWSアクセスキー            | `AKIA` から始まるキー                            |
| 秘密鍵                     | PEM形式の秘密鍵                                  |
| 個人メールアドレス         | 作者の個人メールアドレス（2026-10-25追加）       |
| Windowsユーザー名を含むパス | `/mnt/c/Users/<ユーザー名>/...` のようなスラッシュ区切りのローカルパス |
| Office原本                 | `*.xls` / `*.xlsx` / `*.xlsm` / `*.xlsb` / `~$*` |

## 除外ファイル一覧

| パターン                                                 | 理由                                   |
| -------------------------------------------------------- | -------------------------------------- |
| `*apikey*`, `*secret*`, `*token*`                        | 機密ファイル                           |
| `.env`                                                   | 環境変数                               |
| `docs/`                                                  | 非公開資料（システム仕様書・下書き等） |
| `.git/`                                                  | Gitメタデータ                          |
| `node_modules/`                                          | 依存パッケージ（巨大）                 |
| `dist/`, `.astro/`                                       | ビルド成果物・Astroキャッシュ          |
| `layer/`, `output/`, `.aws-sam/`                         | AWSデプロイ成果物・生成物              |
| `article/`, `evidence/source/`                           | 生成記事・検証の元データ（公開不要）   |
| `*.xls`, `*.xlsx`, `*.xlsm`, `*.xlsb`                    | Office原本                             |
| `*.zip`, `*.pyc`, `__pycache__/`, `*.ttc`                | バイナリ・キャッシュ・フォント         |
| `*お問い合わせフォーム回答*.pdf`                         | 個人情報を含むPDF                      |
| `*:Zone.Identifier`, `.DS_Store`, drawioの一時ファイル   | OS・エディタの一時ファイル             |
| `images/old/`                                            | 旧版の画像                             |
| `/templates/`                                            | 004配下のテンプレートは公開側の `templates/` へ別途同期するため |

## プロジェクトマッピング

| プライベート名              | 公開名                     |
| --------------------------- | -------------------------- |
| `000_git-auto-sync`         | `000_git-auto-sync`        |
| `001_x-poster_zer0-infra`   | `001_x-poster-zer0-infra`  |
| `002_Zenn_Auto_Article_Bot` | `002_zenn-article-bot`     |
| `003_x-poster_zer0-0326`    | `003_x-poster-zer0-0326`   |
| `004_portfolio`             | `004_portfolio`            |
| `005_Zenn_Mid_Article_Bot`  | `005_zenn-mid-article-bot` |
| `006_Zer0_CryptoBot`        | `006_zer0-cryptobot`       |
| `007_Zer0_TouringApp`       | `007_zer0-touring-app`     |
| `008_Nyusatsu_Notify_Bot`   | `008_nyusatsu-notify-bot`  |
| `009_CloudNote`             | `009_cloudnote`            |
| `004_portfolio/templates`   | `templates`                |
