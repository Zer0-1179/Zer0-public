# 008_Nyusatsu_Notify_Bot 変更履歴

※ バージョン番号の付与は2026-07-14に廃止（実質的なバージョン管理をしておらず、詳細な変更履歴はGitで追跡可能なため）。過去分の番号（vX.Y）は見出しに参照用として残している。

## 2026-07-07

### 企画・事業設計（v0.1）

- プロジェクト企画開始。Fable調査でビジネスモデル（官公庁入札情報の自動収集→フィルタ→メール通知のサブスク）を確定
- 価格帯は月3,000〜5,000円のセルフサーブ帯、第一ターゲット業種は清掃・ビルメンテナンス業に設定
- 決済方針はStripe等の既存サービス利用。法的リスクは公開ページ/公式APIのみ対象・事実データのみ扱う方針で整理
- README.mdを作成。CFn/Lambda等の実装は未着手

### 収集・通知パイプライン（v0.2）

- 横浜市パイロット版を実装・デプロイ・動作確認完了
- 収集Lambda（公告番号取得→未処理判定→「委託」セクション抽出→キーワードフィルタ→SES通知→記録、初回はブートストラップモード）をCFnで構築（SAM不使用）
- 実データでの動作確認完了。アーキテクチャ図・Stripe決済導入ガイドを作成

### SES送信ドメイン（v0.3）

- 送信ドメイン`info.zer0-infra.com`をドメインID（Easy DKIM）として検証・CFn管理化（`cfn-ses-domain.yaml`、スタック`zer0-nyusatsu-ses-domain`）
- DKIM CNAMEレコード3件をお名前.com側DNSに登録して検証成功（`VerificationStatus: SUCCESS`）

### LP・問合せ導線（v0.4）

- LP事前登録（DynamoDB+API Gateway+Lambda）・問合せメール受信転送（SES受信+S3+Lambda）・LP静的サイト・LPホスティング（S3+CloudFront+ACM）を追加
- SES送信元をドメイン認証済みアドレスへ切替。MX/DNS反映・実メール転送確認まで完了
- 教訓: カスタムリソース用LambdaのHandlerは`index`系にする必要あり

### Fableレビュー反映（v0.5）

- 構成図のレイアウト規約違反を修正。メール転送LambdaにDLQを追加
- SESルールセット無効化Lambdaの削除時条件分岐を修正。CSPのAPI IDハードコードを解消
- `certificate.yaml`の命名を修正。その他低優先度指摘に対応し、変更履歴フォーマットを他プロジェクトに統一

## 2026-07-08

### Fable検証レビュー2巡目（v0.6）

- 構成図の矢印アイコン貫通・ラベル重なり・auto-padding発火を修正
- CHANGELOG文字数超過3件を是正。誤字を修正
- LP側API IDのハードコードを解消（deploy.sh側で自動注入）。SES通知失敗時の警告ログを追加
- S3バケットが2つある理由をシステム仕様書に明記

### SES本番アクセス取得（v0.7）

- SES本番アクセスをリクエストし承認・取得。送信上限を200通/日→50,000通/日、1→14通/秒に拡大。任意の宛先へメール送信可能に

### 市場調査の反映（v0.8）

- 2026-07-08のFable市場調査結果を反映
- 通知メールに締切残日数を表示。週次稼働サマリー通知を追加
- 送信者表示・配信停止導線を追加。LPに官公需ポータルとの差別化・入札参加資格の注記を追加

## 2026-07-09

### 購読フロー監査・二重オプトイン（v0.9）

- ユーザー指摘「登録者に通知が届くか」を機に監査。LP登録↔実通知が未接続・確認メール皆無・配信停止が返信頼みと判明
- Fable設計を踏まえ、二重オプトイン（HMAC署名リンク）・確認メール・ワンクリック配信停止・honeypot・プライバシーポリシー・DLQアラーム・時間予算チェックを実装
- 停止中だったmail_forwarder未反映も発見し修正

### メールのHTML化（v0.9.1）

- ユーザー指摘「配信停止URLが長い」を受け、通知・週次サマリー・登録確認メールをHTML+テキストのmultipart/alternative化
- 「配信停止はこちら」「登録を確定する」の文字にリンクを埋め込み、生URLはテキスト版フォールバックのみに

### 実配信の接続・バウンス処理（v0.10）

- 実配信を接続（B-1）: 収集Lambdaがactive購読者をScanし個別配信
- SESバウンス・苦情の受け皿（B-3）としてConfiguration Set+SNS+自動配信停止Lambdaを追加
- シミュレーターアドレスで実際にPermanentバウンス・苦情検知→自動unsubscribed化を確認

### 品質レビュー対応（v0.11）

- Fable「課金に値する品質か」レビューを実施。実測で毎週火曜発行・月8-14件と判明
- 通知メールに参加資格情報を追加。登録確認時のバックフィルウェルカムメール、週次サマリーの購読者配信、LP期待値是正を実装
- 副次的にmail_forwarderの件名文字化けも修正

### キーワード拡充（v0.12）

- 既存4語（清掃・美化・害虫防除・ねずみ防除）に消防用設備点検・造園・緑地・街路樹・除草・設備保守点検の6語を追加し計10語に
- SSMパラメータ（キーワード設定）とCFnテンプレートのDefault値を更新し、実行して正常動作を確認

## 2026-07-10

### コードレビュー10件修正（v0.13）

- Fableコードレビュー（高effort）でv0.9〜v0.12の実装コードを初レビューし、10件の不具合を検出・修正
- SES送信失敗の握りつぶし・配信停止意思を無視した復活・第三者による停止バイパス・幽霊レコード生成を解消
- mailto残骸・時間予算の粗さ・HMAC大文字小文字不一致・週次過少報告を解消
- mail_forwarder/bounce_handlerにCloudWatchアラームを追加、`deploy_lambdas.sh`を新設。moto自動テスト41件+本番invokeで確認

### サービス名改称・LP改善（v0.14）

- 「Bot表記の印象」「仕組みが伝わらない」「相場感がほしい」というユーザー指摘を受けFableが調査・改善
- サービス名を「入札情報ウォッチ」に改称。LPに3ステップ図解と横浜市実測の落札価格データ（建物管理・浄化槽等清掃、令和7年度分）を追加
- 構成図にACMを追加。詳細は仕様書8g節参照

### 仕様書の構造化（v0.15）

- ユーザー指摘「文字ばかりで読みにくい」を受け、システム仕様書.mdに目次・設計判断一覧表・購読者ステータス状態遷移図（Mermaid）を追加
- 内容は削除せず構造化のみ

## 2026-07-11

### 横断レビュー・DLQ滞留解消（v0.16）

- ユーザー指示で本日の全変更をFableに横断レビューさせた
- 運用中のDLQ滞留（mail_forwarderのS3重複イベント）をListBucket権限追加+NoSuchKey握りつぶしで解消
- LP対象業種表記（4→10種）・構成図の矢印交差・仕様書の変更履歴重複/状態遷移図欠落を修正。詳細は仕様書8h節参照

### Stripe本番アカウント開設（v0.17）

- 事業情報・銀行口座（ゆうちょ）・明細書表記・本人確認書類・セキュリティ対策措置状況申告書を提出し、アカウント一時停止を解除
- 申告作業中にIAMユーザーのMFA未設定を発見し是正。コンソールパスワードも更新

### 品質レビュー・法務ページ（v0.18）

- Fable品質レビューを反映。キーワード判定にcategoryを追加（取りこぼし対策）、通知メールの締切昇順ソート・非マッチ案件ログを実装
- 構造変化検知・週次持ち越しフラグ・SSMキャッシュ・PITR等も実装
- 特定商取引法に基づく表記・利用規約ページを新設（氏名は開示請求時提供の省略スキームを採用）

## 2026-07-12

### Stripe連携（v0.19）

- 課金者⇔購読者の突合フローを実装。Stripe Webhook受信Lambda（stripe_webhook）を新設し、決済完了/解約/支払い失敗イベントを自前HMAC署名検証で処理
- 決済完了で二重オプトインを省略しactive化。LP未登録アドレスも自動登録。collectorに配信ゲート用SSMフラグを追加
- CloudWatchアラームは007の低優先度分を1つ削除して無料枠内で追加。実機確認済み

### 通知メール刷新（v0.20）

- メール全種をモバイル向けに刷新。案件をカード型HTML（見出し・ラベル値・締切強調・詳細ボタン）に変更
- 案件個別の詳細ページへの実URL（GET直リンク）を実測で発見し全通知に追加。プレーンテキスト版・配信停止導線は維持

### LPブラッシュアップ（v0.21）

- LP全体をFableでブラッシュアップ。LP・法務3ページの配色を通知メールと同じ青系（#2b6cb0）に統一。メールサンプルに実物同等の見出しを追加
- 料金表記を特商法と整合（月額3,000円予定）し料金FAQを新設。相場データ更新目安・フォーム改善（二重送信防止等）・モバイル調整も実施
- README/仕様書のv0.18〜0.19記述齟齬も修正

### LP見出しの改行修正（v0.22）

- 「毎朝自動でチェック」が「自」「動」の間で不自然に折り返されていた問題をnowrapスパンで解消（ユーザー指摘）

### FAQアコーディオン変更（v0.23）

- 排他式（1つ開くと他が閉じる）から独立式（それぞれ個別に開閉）に変更。ユーザー指摘で仕様を確認しUX観点で推奨案を採用

### ブランドアセット作成（v0.24）

- 独自ブランドのfavicon（虫眼鏡アイコン）・OGP画像（1200x630）を新規作成し全ページに設定
- README/仕様書の料金表記齟齬（3,000〜5,000円→3,000円）・docs_payment_setup.mdの価格指示のズレも修正

## 2026-07-13

### Fable指摘の高優先度3件（v0.25）

- FAQアコーディオンにARIA属性（aria-expanded/aria-controls/aria-hidden）を追加
- 単一だったJSを機能ごとに4分割し、try/catchで囲んで登録フォームへの巻き込みリスクを解消
- lp_waitlist Lambdaの確認/配信停止ページにviewportメタタグを追加

### Fable指摘の中優先度7件（v0.26）

- .how-flowのrole="img"誤用を解消。prefers-reduced-motionに対応
- CloudFrontにブランド化404.html+CustomErrorResponsesを追加。HTML/画像のCache-Controlを明示
- 他社比較表・中間CTAを追加。確認完了ページに戻る導線を追加

### Fable指摘の低優先度6件（v0.27）

- robots.txt/sitemap.xmlを新設。og:site_nameを追加、法務3ページにfavicon-16を追加
- CSP script-srcをハッシュ化（deploy.shで自動再計算）。execute-apiのfavicon.icoルートを追加
- FAQに解約方法/迷惑メール対策を追加

### LINE通知の追加（v0.28）

- LINE通知をメールと並列の選択肢として追加。LIFFで友だち追加とアカウント連携を1画面で完結
- collector LambdaがLINE Messaging APIでもプッシュ送信。ブロック時は自動配信停止
- 認証情報はユーザー側でLINE公式アカウント開設後に反映（docs/docs_line_setup.md）

## 2026-07-14

### LINE切替バグ修正（v0.29）

- LINE連携の実機テストで発覚したバグを修正
- 既にメールでactive/バウンス抑制済みのアドレスがchannel=lineで登録すると、チャネル分岐より前の早期リターンでliff_urlが発行されず何も起きなかった問題を解消

### LIFF連携ページ

- liff.stateにtoken/emailが格納されるケースに対応（LIFFがログイン画面を経由するとクエリ文字列がliff.stateに丸ごと格納される仕様のため）
- エラー画面に登録ページへ戻るリンクを追加
- ステータス・エラー文言をFableレビューに基づき丁寧な表現に修正。「LP」という業界用語を「登録ページ」に統一し、断定的な表現を柔らかい言い回しへ変更

### LINE残テストの実機確認

- LINE残テスト6項目を実機確認
- LINE Developers側「Webhookの利用」OFFの設定漏れを発見・修正しブロック検知を復旧。応答メッセージも無効化
- 締切不明案件のLINE通知文言が「締切締切不明」と重複する表示バグを発見・修正し、回帰テストを追加（pytest計53件）

### セキュリティ修正

- Fable追加レビューで発覚したLINEチャネル乗っ取り脆弱性を修正。第三者がメールアドレスを知るだけで既存購読者のchannelを無断でLINEへ切替できた問題を解消
- 既存レコードへのLIFF連携URLはAPIレスポンスで直接返さず、登録済みメールアドレス宛に送信する方式に変更（pytest計54件）

### レビュー対応・障害復旧

- Fable追加レビューの中優先度4件を修正。法務ページのLINE/IP/Stripe未反映・Stripe invoice.paid未処理でpast_due復帰不可・SSMパラメータのSecureStringコメント齟齬・送信失敗宛先への重複通知を解消
- 修正中に発覚したIAM UpdateItem権限漏れの実障害（実データ8件が実際に配信済み）も即時復旧（pytest計56件）

## 2026-07-16

### 低優先度ドキュメント整備

- `docs_payment_setup.md`への相対リンク切れを修正。README.md（`docs-public/`配下）からは`../docs/docs_payment_setup.md`、システム仕様書.md（`docs/`配下、同一ディレクトリ）からは`docs_payment_setup.md`が正しい相対パスだった
- README.md「概要」表・システム仕様書.md「基本情報」表の通知手段が「メール（Amazon SES）」のみのまま古く、v0.28で追加したLINE通知（購読者がメール/LINEを選択）が未反映だったため両方修正
- README.md冒頭のステータス表記（古いバージョン番号「v0.24」が残存）を、バージョン番号を付けない現行方針に沿って実態ベースの説明文に更新
- README.md「今後の進め方」・システム仕様書.md「制約・注意事項」にあった「法務対応（特商法表記・利用規約・プライバシーポリシー）は未着手」という古い記述を修正。実際は`tokushoho.html`/`terms.html`/`privacy.html`として実装済みで、所在地・電話番号は消費者庁Q&A準拠の「開示請求があれば開示」方式を採用しバーチャルオフィス契約は不要と判断済み
- システム仕様書.mdの「mail-forwarder-dlqにアラーム未設定」という記述も古く、`zer0-nyusatsu-mail-forwarder-dlq-alarm-01`として既に設定済みだったため修正
- lp_waitlist Lambda（登録・確認・配信停止・LINE連携・Stripe Webhook全APIの実処理）にエラー検知用CloudWatchアラームが無いことを確認。AWSアカウント全体で無料枠10個中10個が使用中のため、削除候補の妥当性をFableに独立検証してもらった上でユーザー承認を得た

### lp_waitlist LambdaのCloudWatchアラーム追加

- 007(TouringApp)の`Zer0-touring-lambda-errors`を削除して枠を確保（`apigw-5xx`と機能的にほぼ重複、007のLambdaはAPI Gateway同期呼び出し専用のため未処理例外・タイムアウト・スロットリングはいずれも5xxとして検知可能とFableも同結論）
- `infra/cfn-lp-backend.yaml`に`zer0-nyusatsu-lp-waitlist-errors-alarm-01`を追加。007側`infra/cfn-touring.yaml`の変更と合わせて両CFnスタックを更新・デプロイ
- デプロイ後`aws cloudwatch describe-alarms`でアカウント全体のアラーム総数が10個であることを確認。007の本番サイト（`touring.zer0-infra.com`）がHTTP 200で正常応答することも確認

## 2026-08-02

### 神奈川県回答の反映と回答書の非公開化

- 2026-07-24付の神奈川県からの回答受領をREADMEへ反映。「事実上のグリーンライト」とは断定せず、PDL1.0、対象サイト固有規約、出典・加工表示、第三者権利、個別法令の確認が必要と明記
- 公開同期されていた回答PDFを非公開の`docs/`へ移動。同期処理に公文書回答PDFとWindowsの`Zone.Identifier`を除外する防御規則を追加
- 東京都への展開は、同都からの回答待ちであることを明記

## 2026-08-09

### 構成図をAWS公式ベストプラクティスに準拠させる

- ユーザー共有のAWS Summit Japan 2025セッション「AWS アーキテクチャ作図入門」（ソラコム松下氏）のチェックリストを参考に、`scripts/generate_diagram.py`を全面的に見直し
- サービス名を正式名称に統一（「Lambda」→「AWS Lambda」、「SSM」→「AWS Systems Manager」、「SQS」→「Amazon SQS」、「ACM」→「AWS Certificate Manager」等）。ラベルは2行以内・単語途中で改行しないルールを徹底
- 図全体を囲む「AWS Cloud」外枠（公式AWS Cloudロゴ付き）を新設し、ap-northeast-1リージョン枠をその内側に配置する2階層構造に変更
- 併せて、EventBridgeノードがap-northeast-1枠からはみ出して配置されていた既存の座標ズレ（今回の見直しで発覚）も修正
- ユーザー指摘を受け、AWS Cloud・ap-northeast-1の二重内包が実質冗長（両クラスターの内包ノードが完全一致）だった点を是正。CloudFront・ACM（us-east-1発行）はリージョンに属さないグローバル/エッジサービスのため、region枠の外・AWS Cloud内に「エッジ/グローバルサービス」クラスターとして独立させ、region枠との境界を越える接続だけがまたぐ構成に変更
- 上記の再配置に伴い、S3(LP静的サイト)がEventBridge/Lambdaと矩形重なりを起こす配置ミスを検出・修正。さらに矢印がノードラベルの文字にかぶる問題（ユーザー指摘）を受け、matplotlibの`get_window_extent`でラベルの実測境界を取得し、全経路がラベル文字と交差しない座標になるまで調整
- ユーザー指摘で「エッジ/グローバルサービス」クラスターとregion枠が重なっていることが判明。原因は`FancyBboxPatch`の`boxstyle='round,pad=0.15'`が指定座標より各辺0.15外側に描画を膨らませる仕様を計算に入れておらず、数値上のギャップ0.7が視覚的には0.4しかなかったこと。パディング分を加味してギャップを1.2に拡大し、CLAUDE.mdの「隣接クラスター間ギャップ0.8以上」を満たすよう修正
- ユーザー指摘でLambda（lp-waitlist・stripe-webhook）2つの配置が雑然として見える点も改善。API Gatewayからの距離をほぼ揃えた対称配置に変更し、DynamoDBの位置も微調整。交差ゼロ・アイコン非接触は引き続きスクリプトで機械的に検証
- ユーザー指摘でさらに2点改善: ①lp-waitlist LambdaをAPI Gateway・SES送信と同じy座標に揃え、一直線の水平経路にした ②S3(LP静的サイト)をCloudFrontの真下(同じx座標)に配置し、垂直経路を一直線にした
- 「矢印は文字の下から始める」ルールの検証に使っていた自作スクリプトに、ラベル位置のアンカーオフセット誤り（本番コードは`y-HALF-0.2`だが検証側は`y-HALF-0.05`を使用）があり、実際にはDynamoDBラベルと交差していたことが発覚。matplotlibの`get_window_extent`を本番コードと同一のオフセットで呼び出す検証スクリプトに作り直し、全ノードラベル・全エッジラベルに対して全経路を再チェックして解消
- ユーザー指摘「配置の感覚がルール化されておらずバラバラ」を受け、水平座標を3.5間隔（CLAUDE.md規定の最低間隔）の統一グリッドに再編。既存の縦列（ssm/cw/apigw/s3mail、x=9.5）を基準に、CloudFront・S3(LP静的サイト)・ACMをそのグリッドへ整列（CloudFront→S3が一直線に）、SES送信とmail-forwarderも同一列（x=20.0）に揃えて一直線にした。ebのみap-northeast-1枠のパディング制約でグリッド外の例外として残る（コメントで理由を明記）
- 「文字の下から矢印」指摘の再検証で、検証スクリプトの2回目の不具合（実際に描画される区間ではなく、shrinkA/shrinkBで消える方の断片をチェックしていた）を発見・修正。正しい検証により、cf→s3lpやlambda_fw→ses_out等「一直線に見える」経路の多くが、実は出発・到着ノード自身のラベル文字を貫通していたことが判明し、いったん9箇所に迂回経由点を追加した
- ユーザーへ確認したところ、「自分自身の送信元・送信先ノードのラベルに矢印がかかるのは問題ない（むしろその文字から矢印が出ているように見えるのが望ましい）。直線を優先し、無関係な他ノードのラベルを横切る場合だけ回避してほしい」という意図が判明。上記9箇所の迂回経由点を撤去し直線に戻した（cf→s3lp、lambda_fw→ses_out等が再び一直線に）。無関係な別ノードのラベルを横切るケース（lambda→ses_outのssm/cw回避等）はそのまま迂回を維持
- さらに「矢印はラベル文字の下から出ているように見せてほしい」との指示で全接続に一律適用したところ、横方向・斜めの接続まで不自然に長い迂回線になってしまい、ユーザーから差し戻し指示を受けて直線版へ復元
- 改めて「直線が自ノードのラベル文字を自然に貫通する接続のみ」という条件を確認し、該当する接続だけ始点/終点をラベル寄りにする対応に変更。判定基準は「中心点どうしを直線で結んだ場合に自分自身のラベル矩形を通過するか」で機械的に特定した
- 初回の機械チェックは直線経路（waypointなし）しか見ておらず、`apigw→lambda_sw`のようにwaypoint経由で最終区間が自ノードのラベルを貫通するケースを見落としていた。waypointを含めた最初/最後の区間で再チェックし、`apigw→lambda_sw`の始点(apigw自身)・終点(lambda_sw自身)双方を追加。なおstripe-webhook Lambda→DynamoDBは着信経路と同じ直下corridorを共有し線が重なってしまうため、自ラベルをわずかに掠める程度のボーダーラインと判断してアイコン基準のまま残した
- ses_out（Amazon SES送信）は複数接続の収束点で、`lambda_wl→ses_out`（水平、「登録通知」ラベル）・`lambda_sw→ses_out`（斜め）も標準shrinkB=42だと矢頭がアイコン手前の隙間で浮いていたのをユーザー指摘で発見。mail-forwarder→ses_outと同様に隙間を詰め、矢印の向き（xy/xytext指定）はそのまま変更していないことを確認済み。最終的な対象は8箇所
- 上記のうち`lambda_fw→ses_out`（mail-forwarderがses_outの真下から接続）だけは、隙間を詰めすぎる（shrinkBを縮小しすぎる）とses_out自身の2行ラベル文字をそのまま突き抜けてしまう問題が発生（ユーザー指摘「文字がかぶっている」で発覚）。この接続だけ「アイコン下端でちょうど止まる」shrinkB≈35pt（他は3pt）を個別に設定し、ラベルの手前で確実に止まるよう修正

### 構成図の線の交差を解消

- ユーザーから構成図（`008_architecture.png`）の線が交差して見づらいと指摘を受け、`scripts/generate_diagram.py`のノード座標・経路を全面的に再設計
- 主な問題は、Stripe Webhook用Lambda（stripe-webhook）まわりの3本の斜線（apigw→lambda_sw、lambda_sw→DynamoDB、lambda_sw→SES送信）が既存のlp-waitlist系統の線と複数箇所で交差していたこと。加えてStripe→API Gatewayの迂回線がCloudWatch Logsのラベル文字を貫通していたことも判明
- 全エッジの線分交差・アイコン近接をPythonスクリプトで機械的に検証するチェッカーを作成し、交差ゼロ・アイコン/ラベル非接触になるまで座標を反復調整（lp-waitlist系統を上トラック、stripe-webhook系統を下トラックに分離し、それぞれDynamoDB・SES送信への経路を迂回させる設計に変更）
- 変更はドキュメント用画像のみでAWSリソースの変更を伴わないため、AWSデプロイ・pytestは対象外

### Lambdaランタイムのバージョン統一

- 全Lambda関数のPythonランタイムがpython3.13とpython3.14で混在していたため、最新のpython3.14に統一
- 対象は本プロジェクトの6関数（activate-ruleset・bounce-handler・mail-forwarder・collector・lp-waitlist・stripe-webhook）で、他プロジェクトは既にpython3.14だった
- `cfn-nyusatsu-notify-bot.yaml`・`cfn-mail-relay.yaml`・`cfn-lp-backend.yaml`の`Runtime`を変更しCloudFormationで3スタックを更新
- いずれもLayer未使用（標準ライブラリのみ）のため互換性リスクは低いと判断。全スタックがUPDATE_COMPLETE、全関数がState:Active・LastUpdateStatus:Successfulであることを確認
- 本番運用中のため実メール転送・Stripe決済処理を伴うinvokeテストは実施せず、CFn更新成功をもって確認完了とした（ユーザー確認済み）

## 2026-08-10

### 構成図をdraw.ioでの手動編集に移行、AWS公式Cloud/Region枠を導入

- matplotlib(`scripts/generate_diagram.py`)での矢印微調整では意図した見た目にならなかったため、構成図をユーザー自身がdraw.io(diagrams.net)で手直しする運用に変更。`images/008_architecture.drawio`を新規作成し、以後はこのファイルが構成図の一次情報源
- クラスター枠を独自の色付き角丸四角形から、draw.io標準搭載の公式AWS4シェイプ(`shape=mxgraph.aws4.group`)に変更。最外周に「AWS Cloud」(実線)、その内側に「us-east-1」「ap-northeast-1」の2つの「Region」枠(点線)を入れ子で配置
- 斜め方向の接続のうち他ノードのアイコン・ラベルと交差しうるものを直角配線(`edgeStyle=orthogonalEdgeStyle`)に整理し、線の交差・重なりを解消
- 変更はドキュメント用画像のみでAWSリソース・コードの変更を伴わないため、AWSデプロイ・pytestは対象外

## 2026-08-13

### 8プロジェクト横断のREADME/システム仕様書 記載漏れ監査・修正

- README.mdの「全リソースは5つのCloudFormationスタックで管理」という本文が、直後のスタック一覧表（6件）と矛盾していたため、実際の総数7（ap-northeast-1に6＋us-east-1のlp-certで1）に修正
- 受信用ドメイン`zer0-infra.com`（apex）のSES EmailIdentityを管理する`zer0-nyusatsu-ses-domain-apex`スタックがREADME/システム仕様書のどちらのスタック一覧にも未記載だったため追加
- 本CHANGELOG.mdで「2026-08-10」「2026-08-09」「2026-08-02」の3エントリが逆順のまま先頭に誤挿入されていた（プロジェクト共通ルールでは末尾追記）のを、正しい時系列位置に並べ替え

## 2026-08-19

### 通知メールアドレスの変更

- オーナー通知先(NotifyEmail)を旧アドレスから現行アドレスへ変更（個人メールアドレスは記録しない）
- SSMパラメータ（通知先メール）を更新（`mail_forwarder` Lambdaは実行時にこの値を`ssm:GetParameter`で参照するため即時反映）
- CFnスタック`zer0-nyusatsu-notify-bot`のNotifyEmailパラメータ更新・デプロイ。`zer0-nyusatsu-mail-relay`もパラメータ型`AWS::SSM::Parameter::Value<String>`の再解決のため再デプロイし、SNS購読(`zer0-nyusatsu-alarm-topic`/`zer0-nyusatsu-mail-relay-alarm-topic`/`zer0-nyusatsu-ses-events-topic`)を新アドレスへ切替

## 2026-08-27

### SSMパラメータ名前空間を`/nyusatsu/`へ移行

- 専用CloudFormationスタックで、稼働中の4 Lambdaが正規化後の`/nyusatsu/`パスだけを参照するよう切替。旧パスと新パスの値一致、およびLambda設定を値を出さずに検証した
- 切替完了後、不要になった旧名前空間配下の11パラメータを、対象を固定した別のCloudFormationカスタムリソースで削除した
- 削除後に旧11件が存在しないこと、新10件と4 Lambdaの新パス参照が維持されていることを確認した

### 移行専用CFNスタックの撤去完了

- 移行・cleanup専用のCloudFormationスタックを削除し、一時Lambda、IAM Role、CloudWatch Logsを撤去した
- `/nyusatsu/`配下の10パラメータと恒久SSM参照ポリシーは維持され、値を出さずに存在を再確認した

### 運用安全性と個人情報ログの是正

- 購読登録、配信、バウンス処理のCloudWatch Logsからメールアドレスを除外し、送信失敗時も例外本文を記録しない実装へ変更
- Versioning有効S3のLambda artifactをCloudFormationの`S3ObjectVersion`で参照するローカルソースへ変更した。本番反映は独立レビュー・費用承認後に行う
- LPデプロイスクリプトに対象バケット・必須値・未解決プレースホルダー・同期差分の事前検証を追加し、更新がない場合はCloudFront invalidationを実行しないようにした
- Stripe Webhook署名シークレットの旧移行手順を廃止し、CloudFormationの置換競合を起こさない段階的な所有権移行方針へ更新

### アーティファクト基盤の作成と本番反映の安全停止

- Versioning有効・SSE-S3・公開アクセス遮断・TLS拒否ポリシーを持つLambda artifact用S3バケットをCloudFormationで作成し、5 LambdaのZIPをバージョン付きで配置
- アプリケーションスタックのChange Setに想定外の変更が混在したため、実行せず削除。Lambda、API、EventBridge、SNS、SSM値、Stripe設定は変更していない
- 本体スタックの過去ドリフトを回避するため、既存5 Lambdaのコードだけをバージョン付きS3 artifactへ更新する専用CloudFormationスタックを追加

### 5 Lambdaコード更新の完了

- 独立レビュー済みの単独Change Setで、bounce-handler、collector、lp-waitlist、stripe-webhook、mail-forwarderを1関数ずつ無停止更新した
- 各更新後に専用CFNスタックの`UPDATE_COMPLETE`と対象Lambdaの`Active`・`LastUpdateStatus=Successful`を確認した。API、EventBridge、SNS、SSM値、DynamoDB、Stripe設定には変更なし
- 明示承認後、対象4関数の旧CloudWatchログストリームを削除し、各ロググループの残存ストリームが0件であることを確認した

### 正規SSM設定値のCloudFormation所有化

- 正規`/nyusatsu/`配下の9件の`String`を、既存値を変更せず専用`nyusatsu-ssm`スタックへImportした。各リソースは削除・置換とも`Retain`とし、9件すべてのドリフトが`IN_SYNC`であることを確認した
- 稼働中4 Lambdaが正規パスだけを参照し続けることを、値を取得せず確認した
- Stripe Webhook署名用の`SecureString`は、値をCloudFormationへ保持しない方針のため今回のnative Import対象外とした。採用型検証リソースは別段階で追加する

### Stripe署名用SecureStringのCloudFormation統制

- 値を読み取らない採用型カスタムリソースを`nyusatsu-ssm`スタックへ追加し、署名用`SecureString`の存在・型・Tier・DataType・タグを検証した
- 検証Lambdaは`GetParameter`・更新・削除権限を持たず、必要なメタデータ・タグ参照だけを許可した。値・Stripe設定・決済・Webhook送信には触れていない
- 専用スタックは`UPDATE_COMPLETE`。native管理対象と検証Lambda/IAM/ロググループはドリフト`IN_SYNC`であることを確認した

### 旧SSM論理ID整理の安全停止

- 削除済み旧パスを記録するアプリ本体スタックの論理IDを整理するため、対象SSMだけへ`Retain`を加えるChange Setを作成して検査した
- メイン側にはAlarm・Lambda・EventBridge・SNS、LP側にはAlarm・Lambda・API Gatewayの想定外差分が混在したため、いずれも実行せずChange Setを削除した
- 実リソース、稼働Lambda、正規`/nyusatsu/`パラメータ、SSM所有スタックへの影響はない。旧論理IDの削除は、アプリ本体の過去ドリフトを解消する別作業として保留する
