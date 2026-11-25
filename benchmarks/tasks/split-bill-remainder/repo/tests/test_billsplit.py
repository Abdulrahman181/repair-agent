import pytest

from billsplit import split_bill


def test_even_split():
    assert split_bill(100, 4) == [25, 25, 25, 25]


def test_remainder_goes_to_first_people():
    assert split_bill(100, 3) == [34, 33, 33]


def test_zero_people_raises():
    with pytest.raises(ValueError):
        split_bill(100, 0)
