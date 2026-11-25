import pytest

from billsplit import split_bill


def test_small_remainder():
    assert split_bill(10, 3) == [4, 3, 3]


def test_more_people_than_cents():
    assert split_bill(2, 5) == [1, 1, 0, 0, 0]


def test_zero_total():
    assert split_bill(0, 3) == [0, 0, 0]


def test_one_person_gets_everything():
    assert split_bill(1234, 1) == [1234]


def test_sum_and_spread_invariants():
    for total in range(0, 60):
        for people in range(1, 9):
            shares = split_bill(total, people)
            assert len(shares) == people
            assert sum(shares) == total
            assert max(shares) - min(shares) <= 1
            assert shares == sorted(shares, reverse=True)


def test_negative_total_raises():
    with pytest.raises(ValueError):
        split_bill(-1, 2)
