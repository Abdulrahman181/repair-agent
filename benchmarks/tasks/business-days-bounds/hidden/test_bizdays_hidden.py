from datetime import date

from bizdays import business_days_between


def test_full_week():
    assert business_days_between(date(2024, 1, 1), date(2024, 1, 8)) == 5


def test_weekend_only():
    assert business_days_between(date(2024, 1, 6), date(2024, 1, 8)) == 0


def test_saturday_to_saturday_same_day():
    assert business_days_between(date(2024, 1, 6), date(2024, 1, 6)) == 0


def test_friday_to_saturday():
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 6)) == 1


def test_whole_month():
    assert business_days_between(date(2024, 1, 1), date(2024, 2, 1)) == 23


def test_two_weeks():
    assert business_days_between(date(2024, 1, 1), date(2024, 1, 15)) == 10


def test_adjacent_days_sum():
    a, b, c = date(2024, 3, 1), date(2024, 3, 12), date(2024, 3, 27)
    assert business_days_between(a, c) == business_days_between(a, b) + business_days_between(b, c)
