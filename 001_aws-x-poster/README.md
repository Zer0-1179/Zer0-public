# 001_aws-x-poster — AWSニュース自動投稿Bot

AWSの最新ニュースをRSSで取得し、Bedrockで @Zer0_Infra の口調に変換してXに自動投稿するBot。

## フォルダ構成

```text
001_aws-x-poster/
├── README.md                          # このファイル
├── src/                               # 実装コード（デプロイ対象）
│   ├── lambda_function.py             # Lambda本体（RSS取得・Bedrock生成・X投稿）
│   ├── cloudformation.yaml            # インフラ定義（Lambda・EventBridge・IAMロール）
│   └── deploy.sh                      # デプロイスクリプト
└── docs/                              # ドキュメント（参照用）
    ├── aws-x-poster-definition.md     # 構築定義書（設計・手順・運用コマンド集）
    └── x-poster-apikey.md             # APIキー管理メモ（SSM登録済み）
```

## システム構成

```
EventBridge（朝9時 / 夜20時 JST）
  ↓
Lambda（aws-x-poster）
  ├── SSM Parameter Store → X APIキー取得
  ├── SSM Parameter Store → 投稿履歴（used_urls / used_types / used_keywords / used_services）読み込み
  ├── RSS取得（AWS公式ニュース・AWSブログ・クラスメソッド・Zenn・Qiita）
  │   ├── 14日以内の記事のみを対象（古い記事を除外）
  │   ├── 段階的フィルタで重複除外（URL→キーワード→サービスクールダウン）
  │   └── MAINSTREAM_KEYWORDSスコアで記事選択（Zenn・Qiitaはスコア1以上のみ）
  ├── Bedrock（Claude Haiku 4.5 JP）でツイート生成
  │   └── @Zer0_Infra のFew-shot例で口調を再現
  ├── X API v2（OAuth 1.0a）で投稿
  └── SSM Parameter Store → 投稿履歴を更新して保存
```

## 投稿スタイル

| 時間帯       | スタイル                    | URL                | 投稿タイプ                                                                |
| ------------ | --------------------------- | ------------------ | ------------------------------------------------------------------------- |
| 朝 9:00 JST  | ひとこと感想系・100文字以内 | なし（リーチ重視） | `news_reaction` / `aws_tips` / `aws_question`                             |
| 夜 20:00 JST | ニュース紹介系・160文字以内 | あり（ソース明示） | `news_intro` / `aws_failure` / `news_comparison` / `classmethod_reaction` |

- 投稿タイプはSSMに記録した直近6件の使用履歴をもとに、未使用タイプからランダム選択
- `classmethod_reaction` はクラスメソッドの記事固定・日本語タイトル優先
- 記事内容に応じてハッシュタグを動的生成（`#AWS` 固定 + 最大2サービス）
- 重複防止：14日以内の記事のみ対象 + URL（直近28件）・トピックキーワード（直近40件）・サービス別3日クールダウンの段階的フィルタ

## デプロイ

```bash
cd ~/Zer0/001_aws-x-poster/src

# 初回セットアップ（SSM登録 + CloudFormation + コード更新）
bash deploy.sh

# コードのみ再デプロイ
bash deploy.sh --code-only

# DRY RUNテスト（投稿なし・ログ確認）
bash deploy.sh --test
```

## 運用コマンド

```bash
# DRY RUNテスト（実行時刻のスロットで動作）
bash deploy.sh --test

# 朝スロットを強制してテスト（FORCE_SLOT=morning を一時設定→テスト→戻す）
# 詳細は docs/aws-x-poster-definition.md 参照

# ログ確認
aws logs tail /aws/lambda/aws-x-poster --follow --region ap-northeast-1

# 停止 / 再開
aws events disable-rule --name aws-x-poster-morning --region ap-northeast-1
aws events disable-rule --name aws-x-poster-evening --region ap-northeast-1
aws events enable-rule  --name aws-x-poster-morning --region ap-northeast-1
aws events enable-rule  --name aws-x-poster-evening --region ap-northeast-1
```

## コスト概算（月額）

| サービス            | 費用                     |
| ------------------- | ------------------------ |
| Lambda（月60回）    | 無料枠内                 |
| EventBridge         | 無料                     |
| SSM Parameter Store | 無料                     |
| Bedrock（月60回）   | 約$0.6                   |
| X API（月60投稿）   | 約$0.6                   |
| **合計**            | **約$1.2（約180円）/月** |

## トラブルシューティング

| エラー                                      | 原因                                    | 対処                                                     |
| ------------------------------------------- | --------------------------------------- | -------------------------------------------------------- |
| `ValidationException: model ID invalid`     | Bedrockのモデルプレフィックスが違う     | 日本向けは `jp.` プレフィックスを使用                    |
| `402 Payment Required`                      | X APIクレジット不足                     | developer.x.com でクレジットをチャージ（最低$5）         |
| `403 Forbidden`                             | コードに不要な残骸が混在している        | `bash deploy.sh --code-only` でゼロからビルドし直す      |
| `AccessDeniedException: reserved parameter` | SSMパラメータ名が `/aws` で始まっている | `/xposter/` など別のプレフィックスを使う                 |
| `AccessDeniedException` on PutParameter     | IAMロールにSSM書き込み権限がない        | `xposter-history-write` インラインポリシーをロールに追加 |
