"""collector Lambda のユニットテスト。
ネットワークI/O(fetch/post)とSES/SSMはモックする。
2026-07-10のFableレビュー修正(v0.13)、2026-07-11の品質レビュー修正の回帰テストを兼ねる。
"""
import email as email_lib
from unittest import mock

MATCHES = [
    {
        "title": "清掃業務委託", "contract_no": "1", "method": "一般競争入札", "dept": "総務課",
        "detail_fn": "detail", "detail_no": "d1",
    },
]

ANKEN_HTML_TEMPLATE = '''
<table border="0" align="center" width="93%"><tr><td>委託</td></tr></table>
<tr>
<td class="inputAreaG1">CN-{n}<br></td>
<td class="inputAreaG2"><a href="javascript:detail('D{n}');">清掃業務委託</a><br></td>
<td class="inputAreaG1">物品<br></td>
<td class="inputAreaG2">一般競争入札<br></td>
<td class="inputAreaG1">総務課<br></td>
<td class="inputAreaG2">本庁<br></td>
</tr>
'''

# 「委託」1セクションに複数行(建物管理案件+清掃案件+無関係案件)を含む実サイト形式のフィクスチャ。
# extract_itaku_cases/filter_by_keywordsのパーサー回帰テストに使う。
ANKEN_HTML_MULTI_ROW = '''
<table border="0" align="center" width="93%"><tr><td>工事</td></tr></table>
<tr>
<td class="inputAreaG1">CN-9<br></td>
<td class="inputAreaG2"><a href="javascript:detail('D9');">植栽剪定工事</a><br></td>
<td class="inputAreaG1">造園<br></td>
<td class="inputAreaG2">見積合わせ<br></td>
<td class="inputAreaG1">公園緑地課<br></td>
<td class="inputAreaG2">本庁<br></td>
</tr>
<table border="0" align="center" width="93%"><tr><td>委託</td></tr></table>
<tr>
<td class="inputAreaG1">CN-1<br></td>
<td class="inputAreaG2"><a href="javascript:detail('D1');">○○庁舎管理業務委託</a><br></td>
<td class="inputAreaG1">建物管理<br></td>
<td class="inputAreaG2">一般競争入札<br></td>
<td class="inputAreaG1">総務課<br></td>
<td class="inputAreaG2">本庁<br></td>
</tr>
<tr>
<td class="inputAreaG1">CN-2<br></td>
<td class="inputAreaG2"><a href="javascript:detail2('D2');">庁舎警備業務委託</a><br></td>
<td class="inputAreaG1">警備<br></td>
<td class="inputAreaG2">一般競争入札<br></td>
<td class="inputAreaG1">総務課<br></td>
<td class="inputAreaG2">本庁<br></td>
</tr>
'''

DETAIL_HTML_TEMPLATE = '''
<td>入札期間</td><td>令和8年7月1日から{deadline}まで</td>
<th class="header pcak4000-header">種目</th><td>建物管理</td>
<th class="header pcak4000-header">所在地区分・順位</th><td>市内A</td>
'''


def test_extract_itaku_cases_only_returns_itaku_section(collector):
    """委託セクション以外(工事セクションの造園案件)は除外し、委託セクション内の
    複数行(category・fn種別違いを含む)を正しく抽出できること。"""
    cases = collector.extract_itaku_cases(ANKEN_HTML_MULTI_ROW)
    assert [c["title"] for c in cases] == ["○○庁舎管理業務委託", "庁舎警備業務委託"]
    assert cases[0]["category"] == "建物管理"
    assert cases[0]["detail_fn"] == "detail"
    assert cases[1]["detail_fn"] == "detail2"


def test_filter_by_keywords_matches_category_not_just_title(collector):
    """案件名に「清掃」を含まなくても、category(工種等区分)が「建物管理」なら
    マッチすること(取りこぼし対策、レビュー2026-07-11)。"""
    cases = collector.extract_itaku_cases(ANKEN_HTML_MULTI_ROW)
    matches = collector.filter_by_keywords(cases, ["建物管理"])
    assert [c["title"] for c in matches] == ["○○庁舎管理業務委託"]


def test_fetch_case_detail_parses_era_date_and_days_left(collector):
    """令和表記の締切日を西暦に変換し、days_leftを含むinfoを返すこと。"""
    detail_html = DETAIL_HTML_TEMPLATE.format(deadline="令和8年7月20日")
    case = {"detail_fn": "detail", "detail_no": "d1"}
    with mock.patch.object(collector, "post", return_value=detail_html), \
         mock.patch.object(collector, "datetime") as dt_mock:
        dt_mock.now.return_value.date.return_value = collector.date(2026, 7, 11)
        info = collector.fetch_case_detail(case)
    assert info["days_left"] == 9
    assert info["deadline_display"] == "入札期間終了: 2026/7/20（あと9日）"
    assert info["category_detail"] == "建物管理"


def test_case_detail_url_maps_fn_to_get_url(collector):
    """一覧ページのjavascript:detail()/detail2()と同じ詳細ページを開けるGET URLを
    組み立てること(GETで同一内容が返ることは実サイトで確認済み、2026-07-12)。"""
    assert collector.case_detail_url({"detail_fn": "detail", "detail_no": "D1"}) == (
        "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p"
        "?job=HacchuJohoKojiDetail&page=&keiyakuBango=D1"
    )
    assert collector.case_detail_url({"detail_fn": "detail2", "detail_no": "D2"}).endswith(
        "?job=HacchuJohoBuppinDetail&page=&keiyakuBango=D2"
    )
    assert collector.case_detail_url({"detail_fn": "unknown", "detail_no": "D3"}) is None


def test_send_notification_includes_per_case_detail_url(collector, make_context):
    """通知メールに案件ごとの詳細ページURL(テキスト版)とリンクボタン(HTML版)が
    含まれること(モバイル向けメール改善、2026-07-12)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[{"email": "a@example.com", "channel": "email", "line_user_id": None}]), \
         mock.patch.object(collector, "send_email_with_unsubscribe") as m_send:
        collector.send_notification(1004, MATCHES, make_context(300000))

    body = m_send.call_args.args[3]
    html_content = m_send.call_args.kwargs["html_content"]
    assert "案件詳細: https://keiyaku.city.yokohama.lg.jp/epco/servlet/p?job=HacchuJohoKojiDetail&page=&keiyakuBango=d1" in body
    assert "案件詳細を開く" in html_content
    assert "keiyakuBango=d1" in html_content


def test_build_unsubscribe_url_normalizes_email_case(collector):
    """#7の修正確認: HMACトークン生成前にメールアドレスを正規化し、
    lp_waitlist側のlower()検証と一致させる。"""
    url = collector.build_unsubscribe_url("Owner@Example.com")
    assert "email=owner%40example.com" in url
    expected_token = collector.make_unsubscribe_token("owner@example.com")
    assert f"token={expected_token}" in url


def test_send_email_list_unsubscribe_has_no_mailto(collector):
    """List-Unsubscribeのmailto残骸(実際には停止しない)を除去したことの確認。"""
    with mock.patch.object(collector, "ses") as ses_mock:
        collector.send_email_with_unsubscribe("sender@example.com", "user@example.com", "件名", "本文")
        raw_bytes = ses_mock.send_raw_email.call_args.kwargs["RawMessage"]["Data"]

    parsed = email_lib.message_from_bytes(raw_bytes, policy=email_lib.policy.default)
    list_unsub = str(parsed["List-Unsubscribe"])
    assert "mailto:" not in list_unsub
    assert "unsubscribe?email=" in list_unsub


def test_send_notification_partial_failure_reports_had_failure(collector, make_context):
    """#1の修正確認: 一部宛先への送信失敗はhad_failure=Trueとして呼び出し元に伝播する
    (v0.8まではLambda全体を失敗させリトライ/DLQ/アラームに繋がっていた安全網の復元)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[
             {"email": "a@example.com", "channel": "email", "line_user_id": None},
             {"email": "b@example.com", "channel": "email", "line_user_id": None},
         ]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", side_effect=[None, Exception("SES throttled")]) as m_send:
        fully_sent, had_failure = collector.send_notification(1001, MATCHES, make_context(300000))

    assert fully_sent is False
    assert had_failure is True
    assert m_send.call_count == 2


def test_send_notification_sorts_by_deadline_ascending(collector, make_context):
    """締切が近い案件を先頭に表示すること(days_leftが無い案件は末尾、レビュー2026-07-11)。"""
    matches = [
        {"title": "A(締切遠い)", "contract_no": "1", "method": "指名競争入札", "dept": "総務課",
         "detail_fn": "detail", "detail_no": "dA"},
        {"title": "B(締切近い)", "contract_no": "2", "method": "指名競争入札", "dept": "総務課",
         "detail_fn": "detail", "detail_no": "dB"},
        {"title": "C(締切不明)", "contract_no": "3", "method": "指名競争入札", "dept": "総務課",
         "detail_fn": "detail", "detail_no": "dC"},
    ]
    details_by_no = {
        "dA": {"days_left": 20},
        "dB": {"days_left": 3},
        "dC": {},
    }
    with mock.patch.object(collector, "fetch_case_detail", side_effect=lambda c: details_by_no[c["detail_no"]]), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[{"email": "a@example.com", "channel": "email", "line_user_id": None}]), \
         mock.patch.object(collector, "send_email_with_unsubscribe") as m_send:
        collector.send_notification(2001, matches, make_context(300000))

    body = m_send.call_args.args[3]
    assert body.index("B(締切近い)") < body.index("A(締切遠い)") < body.index("C(締切不明)")


def test_send_notification_retry_does_not_resend_to_already_notified_recipient(collector, make_context):
    """中優先度の修正確認(2026-07-14): 一部宛先の送信失敗で号が持ち越された後、
    同じkokoku_noでsend_notificationが再実行されても、既に成功した宛先へは
    再送しない(以前は宛先粒度の送信済み記録がなく、持ち越しのたびに成功済みの
    全宛先へ同じ通知が再送されていた)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[
             {"email": "a@example.com", "channel": "email", "line_user_id": None},
             {"email": "b@example.com", "channel": "email", "line_user_id": None},
         ]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", side_effect=[None, Exception("SES throttled")]) as m_send:
        fully_sent, had_failure = collector.send_notification(3001, MATCHES, make_context(300000))
    assert fully_sent is False
    assert had_failure is True
    assert m_send.call_count == 2

    # 号は持ち越されmark_processedされていない状態を再現し、同じkokoku_noで再実行する
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[
             {"email": "a@example.com", "channel": "email", "line_user_id": None},
             {"email": "b@example.com", "channel": "email", "line_user_id": None},
         ]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", return_value=None) as m_send_retry:
        fully_sent, had_failure = collector.send_notification(3001, MATCHES, make_context(300000))
    assert fully_sent is True
    assert had_failure is False
    assert m_send_retry.call_count == 1
    assert m_send_retry.call_args.args[1] == "b@example.com"


def test_send_notification_full_success(collector, make_context):
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[{"email": "a@example.com", "channel": "email", "line_user_id": None}]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", return_value=None):
        fully_sent, had_failure = collector.send_notification(1002, MATCHES, make_context(300000))

    assert fully_sent is True
    assert had_failure is False


def test_send_notification_time_budget_exhausted_is_not_treated_as_failure(collector, make_context):
    """#6の修正確認: 送信ループ中の時間切れはhad_failure=Falseのまま
    (自己回復動作であり、SES送信失敗とは区別する)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[{"email": "a@example.com", "channel": "email", "line_user_id": None}]), \
         mock.patch.object(collector, "send_email_with_unsubscribe") as m_send:
        # 詳細取得チェック通過(300000)、送信ループ1件目チェックで時間切れ(margin未満)
        fully_sent, had_failure = collector.send_notification(1003, MATCHES, make_context([300000, 10000]))

    assert fully_sent is False
    assert had_failure is False
    assert m_send.call_count == 0


def test_lambda_handler_raises_on_send_failure_and_defers_kokoku_no(collector, make_context):
    """#1の修正確認: 送信失敗があった号はmark_processedされず、Lambda呼び出し自体が
    例外で失敗する(既存のリトライ→DLQ→アラームに繋げるため)。"""

    def fake_fetch(url):
        if "job=KokokuList" in url:
            return "kokoku_no=9999&kokoku_no=5001"
        if "kokoku_no=5001" in url:
            return ANKEN_HTML_TEMPLATE.format(n=1)
        raise AssertionError(f"unexpected fetch url: {url}")

    collector.mark_processed(9999)  # bootstrapを避けるため既存処理済みを1件用意

    with mock.patch.object(collector, "fetch", side_effect=fake_fetch), \
         mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "ses") as ses_mock, \
         mock.patch.object(collector, "get_all_recipients", return_value=[
             {"email": "owner@example.com", "channel": "email", "line_user_id": None},
         ]):
        ses_mock.send_raw_email.side_effect = Exception("SES down")
        try:
            collector.lambda_handler({}, make_context(300000))
            assert False, "例外が送出されるはず"
        except RuntimeError:
            pass

    item = collector.dynamodb.Table("test-processed").get_item(Key={"kokoku_no": 5001}).get("Item")
    assert item is None


def test_digest_pending_flag_roundtrip(collector):
    """weekly-stats未作成時はFalse、set後はTrue、reset_weekly_statsで自動的に
    Falseへ戻ること(月曜の持ち越し解消フロー、レビュー2026-07-11)。"""
    assert collector.get_digest_pending() is False

    collector.update_weekly_stats(matches_today=0, cases_today=1)  # itemを作成
    collector.set_digest_pending(True)
    assert collector.get_digest_pending() is True

    collector.reset_weekly_stats()
    assert collector.get_digest_pending() is False


def test_send_weekly_digest_pending_uses_period_label(collector):
    """digest_pending解消時に送るメールは「先週は」ではなく「直近の集計期間は」と
    表記すること(月曜以外に送られるため、レビュー2026-07-11)。"""
    with mock.patch.object(collector, "get_all_recipients", return_value=[{"email": "a@example.com", "channel": "email", "line_user_id": None}]), \
         mock.patch.object(collector, "send_email_with_unsubscribe") as m_send:
        collector.send_weekly_digest(3, 10, 2, pending=True)

    body = m_send.call_args.args[3]
    assert body.startswith("直近の集計期間は")


def test_get_active_subscribers_ignores_payment_status_by_default(collector):
    """PAYMENT_REQUIRED_PARAM_NAMEが"false"(デフォルト)の間は、payment_statusに
    関わらずstatus=activeなら通知対象に含める(既存の無料テスト購読者への配信を
    変えないための後方互換、v0.19)。"""
    table = collector.dynamodb.Table("test-waitlist")
    table.put_item(Item={"email": "free@example.com", "status": "active", "registered_at": 1})
    table.put_item(
        Item={"email": "paid@example.com", "status": "active", "payment_status": "paid", "registered_at": 1}
    )

    emails = {s["email"] for s in collector.get_active_subscribers()}

    assert emails == {"free@example.com", "paid@example.com"}


def test_get_active_subscribers_requires_paid_when_payment_required(collector):
    """PAYMENT_REQUIRED_PARAM_NAMEを"true"に切り替えると、status=activeでも
    payment_status=paidでない購読者は通知対象から除外される(課金必須化、v0.19)。"""
    ssm = __import__("boto3").client("ssm", region_name="ap-northeast-1")
    ssm.put_parameter(Name="/test/payment-required", Value="true", Type="String", Overwrite=True)
    collector._param_cache.pop("/test/payment-required", None)
    try:
        table = collector.dynamodb.Table("test-waitlist")
        table.put_item(Item={"email": "free@example.com", "status": "active", "registered_at": 1})
        table.put_item(
            Item={"email": "paid@example.com", "status": "active", "payment_status": "paid", "registered_at": 1}
        )

        subscribers = collector.get_active_subscribers()

        assert [s["email"] for s in subscribers] == ["paid@example.com"]
    finally:
        ssm.put_parameter(Name="/test/payment-required", Value="false", Type="String", Overwrite=True)
        collector._param_cache.pop("/test/payment-required", None)


def test_get_active_subscribers_includes_line_channel_fields(collector):
    """channel="line"の購読者はline_user_idを含めて返される(v0.28)。
    channel未設定の旧レコードは後方互換で"email"扱いになること。"""
    table = collector.dynamodb.Table("test-waitlist")
    table.put_item(Item={"email": "legacy@example.com", "status": "active", "registered_at": 1})
    table.put_item(Item={
        "email": "line-user@example.com", "status": "active", "registered_at": 1,
        "channel": "line", "line_user_id": "U999",
    })

    subscribers = {s["email"]: s for s in collector.get_active_subscribers()}

    assert subscribers["legacy@example.com"]["channel"] == "email"
    assert subscribers["line-user@example.com"]["channel"] == "line"
    assert subscribers["line-user@example.com"]["line_user_id"] == "U999"


def test_send_notification_pushes_line_channel_via_line_api(collector, make_context):
    """channel="line"の宛先にはSESではなくsend_line_pushで送られる(v0.28)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=[
             {"email": "line-user@example.com", "channel": "line", "line_user_id": "U999"},
         ]), \
         mock.patch.object(collector, "send_email_with_unsubscribe") as m_email, \
         mock.patch.object(collector, "send_line_push") as m_line:
        fully_sent, had_failure = collector.send_notification(1005, MATCHES, make_context(300000))

    assert fully_sent is True
    assert had_failure is False
    assert m_email.call_count == 0
    assert m_line.call_count == 1
    assert m_line.call_args.args[0] == "U999"


def test_build_line_notification_text_deadline_unknown_not_duplicated(collector):
    """days_leftが取れない案件で「締切締切不明」のような重複表示にならないこと
    (2026-07-14 実機テストで発覚したバグの再発防止)。"""
    text = collector.build_line_notification_text(
        kokoku_no=1,
        case_details=[({"title": "A"}, {"days_left": 3}), ({"title": "B"}, {"days_left": None})],
        detail_url="https://example.com",
    )
    assert "A(締切あと3日)" in text
    assert "B(締切不明)" in text
    assert "締切締切" not in text
