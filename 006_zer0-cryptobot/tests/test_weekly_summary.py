"""weekly_summary Lambda の稼働状況メッセージ・資金増額進捗の整形ロジックのテスト。
SES/S3/SSM等のAWS呼び出しを伴わない純粋関数のみを対象にする。"""
from datetime import datetime, timezone

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


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


class TestSummarizeTrades:
    def test_position_with_tp1_and_closing_reason_counts_as_one_closed_position(self, weekly):
        """TP1部分利確＋トレーリングSLの2レコードは同一ポジションとして正味損益で1勝/1敗に集計する
        （レコード単位で数えると小幅マイナスのトレーリングSLだけで「敗」計上されてしまう）。"""
        now = NOW
        trades = [
            {"ts": "2026-06-23T17:45:18+09:00", "reason": "TP1部分利確", "pnl_jpy": 41.4, "position_id": "eth-1"},
            {"ts": "2026-06-24T21:00:10+09:00", "reason": "トレーリングSL", "pnl_jpy": -2.6, "position_id": "eth-1"},
        ]
        stats = weekly.summarize_trades(trades, now)
        assert stats["closed_count"] == 1
        assert stats["win_rate"] == 100.0

    def test_manual_close_reason_still_counts_as_closed(self, weekly):
        """バグ再発防止（2026-08-20修正）: 旧CLOSING_REASONSの許可リストに
        「手動決済（トレーリング中）」が含まれておらず、手動決済で閉じたポジションが
        勝率・PF・増額判断メトリクスから丸ごと欠落していた。TP1部分利確以外は
        理由文字列によらず全てクローズ扱いにすることで、未知の理由文字列にも耐える。"""
        now = NOW
        trades = [
            {"ts": "2026-07-21T12:15:18+09:00", "reason": "TP1部分利確", "pnl_jpy": 34.5, "position_id": "eth-2"},
            {"ts": "2026-07-21T18:28:22+09:00", "reason": "手動決済（トレーリング中）", "pnl_jpy": 120.5, "position_id": "eth-2"},
        ]
        stats = weekly.summarize_trades(trades, now)
        assert stats["closed_count"] == 1
        assert stats["win_rate"] == 100.0

    def test_tp1_only_position_excluded_from_win_rate(self, weekly):
        """TP1部分利確のみでまだ最終決済が無いポジションは、勝敗が確定していないため
        closed_countに含めない（保有中ポジションを「勝ち」として数えてしまうのを防ぐ）。"""
        now = NOW
        trades = [
            {"ts": "2026-08-19T17:45:18+09:00", "reason": "TP1部分利確", "pnl_jpy": 22.3, "position_id": "sol-1"},
        ]
        stats = weekly.summarize_trades(trades, now)
        assert stats["closed_count"] == 0
        assert stats["win_rate"] is None


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
