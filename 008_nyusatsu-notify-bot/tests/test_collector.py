"""collector Lambda のユニットテスト。
ネットワークI/O(fetch/post)とSES/SSMはモックする。
2026-07-10のFableレビュー修正(v0.13)の回帰テストを兼ねる。
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
         mock.patch.object(collector, "get_all_recipients", return_value=["a@example.com", "b@example.com"]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", side_effect=[None, Exception("SES throttled")]) as m_send:
        fully_sent, had_failure = collector.send_notification(1001, MATCHES, make_context(300000))

    assert fully_sent is False
    assert had_failure is True
    assert m_send.call_count == 2


def test_send_notification_full_success(collector, make_context):
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=["a@example.com"]), \
         mock.patch.object(collector, "send_email_with_unsubscribe", return_value=None):
        fully_sent, had_failure = collector.send_notification(1002, MATCHES, make_context(300000))

    assert fully_sent is True
    assert had_failure is False


def test_send_notification_time_budget_exhausted_is_not_treated_as_failure(collector, make_context):
    """#6の修正確認: 送信ループ中の時間切れはhad_failure=Falseのまま
    (自己回復動作であり、SES送信失敗とは区別する)。"""
    with mock.patch.object(collector, "fetch_case_detail", return_value={}), \
         mock.patch.object(collector, "record_match_history"), \
         mock.patch.object(collector, "get_all_recipients", return_value=["a@example.com"]), \
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
         mock.patch.object(collector, "ses") as ses_mock, \
         mock.patch.object(collector, "get_all_recipients", return_value=["owner@example.com"]):
        ses_mock.send_raw_email.side_effect = Exception("SES down")
        try:
            collector.lambda_handler({}, make_context(300000))
            assert False, "例外が送出されるはず"
        except RuntimeError:
            pass

    item = collector.dynamodb.Table("test-processed").get_item(Key={"kokoku_no": 5001}).get("Item")
    assert item is None
