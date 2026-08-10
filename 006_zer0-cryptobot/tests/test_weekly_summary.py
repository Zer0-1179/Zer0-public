"""weekly_summary Lambda の稼働状況メッセージ・資金増額進捗の整形ロジックのテスト。
SES/S3/SSM等のAWS呼び出しを伴わない純粋関数のみを対象にする。"""


def _stats(weekly_count=0, closed_count=0, win_rate=None, pf=None, max_dd_jpy=0.0,
           weekly_pnl=0.0, total_pnl=0.0):
    return {
        "weekly_count": weekly_count,
        "closed_count": closed_count,
        "win_rate": win_rate,
        "pf": pf,
        "max_dd_jpy": max_dd_jpy,
        "weekly_pnl": weekly_pnl,
        "total_pnl": total_pnl,
    }


class TestBuildStatusMessage:
    def test_no_trade_history_yet(self, weekly):
        msg = weekly.build_status_message(None)
        assert "定期実行" in msg
        assert "正常" in msg

    def test_quiet_week_reassures_not_broken(self, weekly):
        msg = weekly.build_status_message(_stats(weekly_count=0))
        assert "異常ではありません" in msg
        assert "アラームメール" in msg

    def test_active_week_reports_count(self, weekly):
        msg = weekly.build_status_message(_stats(weekly_count=3))
        assert "3件" in msg
        assert "正常に稼働" in msg


class TestComputeScaleUpMetrics:
    def test_no_closed_positions_yet(self, weekly):
        m = weekly.compute_scale_up_metrics(_stats(closed_count=0, win_rate=None, pf=None))
        assert m["win_mark"] == ""
        assert m["pf_mark"] == ""
        assert "クローズ済みポジションなし" in m["win_str"]

    def test_undefeated_pf_shows_infinity_with_ok_mark(self, weekly):
        m = weekly.compute_scale_up_metrics(_stats(closed_count=2, win_rate=100.0, pf=None))
        assert m["pf_mark"] == "○"
        assert "∞" in m["pf_str"]

    def test_marks_reflect_thresholds(self, weekly):
        below_min  = weekly.compute_scale_up_metrics(_stats(closed_count=10, win_rate=40.0, pf=0.8))
        min_only   = weekly.compute_scale_up_metrics(_stats(closed_count=10, win_rate=57.0, pf=1.2))
        recommended = weekly.compute_scale_up_metrics(_stats(closed_count=10, win_rate=65.0, pf=1.5))
        assert below_min["win_mark"] == "×" and below_min["pf_mark"] == "×"
        assert min_only["win_mark"] == "△" and min_only["pf_mark"] == "○"
        assert recommended["win_mark"] == "○"


class TestBuildScaleUpProgressFormats:
    def test_text_and_html_agree_on_counts(self, weekly):
        stats = _stats(closed_count=18, win_rate=61.1, pf=1.42, max_dd_jpy=320.0)
        text_lines = weekly.build_scale_up_progress(stats)
        html = weekly.build_scale_up_progress_html(stats)
        assert any("18/20" in line and "18/30" in line for line in text_lines)
        assert "18/20" in html and "18/30" in html
        assert "61.1%" in html
        assert "1.42" in html

    def test_html_is_well_formed_table_rows(self, weekly):
        html = weekly.build_scale_up_progress_html(_stats(closed_count=0))
        assert html.count("<tr>") == html.count("</tr>") == 4
