"""Published 2026 equity-market closures, available without network access.

Update the covered year when exchanges publish their next annual calendars.
Weekend makeup workdays are never exchange trading days.

Sources:
CN: https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml
HK: https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf
US: https://www.nyse.com/trade/hours-calendars
TW/TWF: https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule
(台指期休市日同證交所;「開始/最後交易日」照常交易,「僅辦理結算交割」不交易)
"""

from datetime import date, time, timedelta


def _dates(*ranges: tuple[str, str]) -> frozenset[date]:
    result = set()
    for start, end in ranges:
        current, last = date.fromisoformat(start), date.fromisoformat(end)
        while current <= last:
            result.add(current)
            current += timedelta(days=1)
    return frozenset(result)


_TW_2026 = frozenset(date.fromisoformat(d) for d in (
    "2026-01-01", "2026-02-12", "2026-02-13", "2026-02-16", "2026-02-17",
    "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-27", "2026-04-03",
    "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25", "2026-09-28",
    "2026-10-09", "2026-10-26", "2026-12-25",
))


HOLIDAYS = {
    ("CN", 2026): _dates(
        ("2026-01-01", "2026-01-03"), ("2026-02-15", "2026-02-23"),
        ("2026-04-04", "2026-04-06"), ("2026-05-01", "2026-05-05"),
        ("2026-06-19", "2026-06-21"), ("2026-09-25", "2026-09-27"),
        ("2026-10-01", "2026-10-07"),
    ),
    ("HK", 2026): frozenset(date.fromisoformat(d) for d in (
        "2026-01-01", "2026-02-17", "2026-02-18", "2026-02-19",
        "2026-04-03", "2026-04-06", "2026-04-07", "2026-05-01",
        "2026-05-25", "2026-06-19", "2026-07-01", "2026-10-01",
        "2026-10-19", "2026-12-25",
    )),
    ("US", 2026): frozenset(date.fromisoformat(d) for d in (
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
        "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
        "2026-11-26", "2026-12-25",
    )),
    ("TW", 2026): _TW_2026,
    ("TWF", 2026): _TW_2026,
}

EARLY_CLOSES = {
    ("HK", date(2026, 2, 16)): time(12),
    ("HK", date(2026, 12, 24)): time(12),
    ("HK", date(2026, 12, 31)): time(12),
    ("US", date(2026, 11, 27)): time(13),
    ("US", date(2026, 12, 24)): time(13),
}
