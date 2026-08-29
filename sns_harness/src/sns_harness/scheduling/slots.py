from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def next_available_slots(
    now: datetime,
    occupied: set[datetime],
    slots: tuple[str, ...],
    count: int,
    timezone: ZoneInfo,
) -> list[datetime]:
    local_now = now.astimezone(timezone)
    occupied_local = {item.astimezone(timezone) for item in occupied}
    results: list[datetime] = []
    day = local_now.date()

    for _ in range(366):
        for slot in slots:
            hour, minute = (int(part) for part in slot.split(":", maxsplit=1))
            candidate = datetime.combine(day, time(hour, minute), tzinfo=timezone)
            if candidate <= local_now or candidate in occupied_local:
                continue
            results.append(candidate)
            occupied_local.add(candidate)
            if len(results) == count:
                return results
        day += timedelta(days=1)
    raise RuntimeError("could not allocate publishing slots within one year")
