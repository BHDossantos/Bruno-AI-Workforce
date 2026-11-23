"""UTC range metadata for the read-only outreach panel."""
from datetime import datetime, timedelta, timezone

from conftest import requires_db


@requires_db
def test_outreach_summary_exposes_server_utc_bounds(client, auth_headers):
    response = client.get("/analytics/outreach-summary", headers=auth_headers)
    assert response.status_code == 200
    window = response.json()["window"]
    assert window["timezone"] == "UTC"
    start = datetime.fromisoformat(window["today_start"])
    seven_day_start = datetime.fromisoformat(window["seven_day_start"])
    snapshot = datetime.fromisoformat(window["snapshot_at"])
    assert start.tzinfo == snapshot.tzinfo == timezone.utc
    assert start == snapshot.replace(hour=0, minute=0, second=0, microsecond=0)
    assert start - seven_day_start == timedelta(days=6)
