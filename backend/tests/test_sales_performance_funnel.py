"""A draft, follow-up task or suppressed lead must not manufacture engagement."""
from app.sales_performance import funnel


class StatusDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args):
        return self

    def group_by(self, *args):
        return self

    def all(self):
        return self.rows


def test_followup_lost_and_unknown_statuses_do_not_inflate_funnel():
    result = funnel(StatusDB([
        ("New", 5), ("Drafted", 7), ("Follow-up Needed", 3),
        ("Closed Lost", 4), ("Unsubscribed", 2), ("Bounced", 1),
        ("Contacted", 6), ("Replied", 2), ("Interested", 1), ("Closed Won", 1),
    ]))
    assert [s["count"] for s in result["stages"]] == [32, 10, 4, 1]
    assert result["current"]["new"] == 12
    assert result["current"]["follow_up"] == 3
    assert result["current"]["other"] == 3
    assert result["rates"] == {
        "contact_rate": 31.2, "response_rate": 40.0,
        "close_rate": 20.0, "win_from_contacted": 10.0,
    }
    assert "not historical" in result["basis"]


def test_empty_and_only_unconfirmed_leads_have_zero_conversion():
    for rows in ([], [("Drafted", 3), ("Follow-up Needed", 2), ("Closed Lost", 1)]):
        result = funnel(StatusDB(rows))
        assert all(stage["count"] == 0 for stage in result["stages"][1:])
        assert set(result["rates"].values()) == {0.0}


def test_current_status_buckets_account_for_every_lead():
    result = funnel(StatusDB([("New", 2), ("Future status", 5), ("Closed Won", 1)]))
    current = result["current"]
    assert sum(value for key, value in current.items() if key != "total") == current["total"]
    assert [s["count"] for s in result["stages"]] == [8, 1, 1, 1]


def test_sent_and_opened_are_contacted_but_not_human_responses():
    result = funnel(StatusDB([("Sent", 3), ("Opened", 2)]))
    assert [s["count"] for s in result["stages"]] == [5, 5, 0, 0]
    assert result["current"]["contacted"] == 5
    assert result["current"]["other"] == 0
    assert result["rates"]["response_rate"] == 0
