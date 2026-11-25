from datetime import date

import pytest

from bizdays import business_days_between


def test_monday_to_friday():
    assert business_days_between(date(2024, 1, 1), date(2024, 1, 5)) == 4


def test_same_day_is_zero():
    assert business_days_between(date(2024, 1, 1), date(2024, 1, 1)) == 0


def test_friday_to_monday_counts_friday_only():
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 8)) == 1


def test_end_before_start_raises():
    with pytest.raises(ValueError):
        business_days_between(date(2024, 1, 5), date(2024, 1, 1))
