from datetime import timedelta


def business_days_between(start, end):
    """Count weekdays (Monday to Friday) in the half-open range [start, end).

    start is counted and end is not. Returns 0 when start == end. Raises ValueError if end is
    before start. Both arguments are datetime.date objects.
    """
    if end < start:
        raise ValueError("end must not be before start")
    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count
