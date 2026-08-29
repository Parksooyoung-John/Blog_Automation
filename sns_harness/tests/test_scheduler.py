from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sns_harness.scheduling.slots import next_available_slots


def test_allocates_two_daily_kst_slots_skipping_occupied() -> None:
    timezone = ZoneInfo("Asia/Seoul")
    now = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)  # 09:00 KST
    occupied = {datetime(2026, 8, 23, 18, 30, tzinfo=timezone)}

    result = next_available_slots(now, occupied, ("08:30", "18:30"), 2, timezone)

    assert result == [
        datetime(2026, 8, 24, 8, 30, tzinfo=timezone),
        datetime(2026, 8, 24, 18, 30, tzinfo=timezone),
    ]
