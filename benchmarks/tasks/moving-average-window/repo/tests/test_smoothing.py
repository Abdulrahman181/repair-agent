import pytest

from smoothing import moving_average


def test_window_three():
    assert moving_average([1, 2, 3, 4, 5], 3) == [2.0, 3.0, 4.0]


def test_window_one_returns_values():
    assert moving_average([1, 2, 3], 1) == [1.0, 2.0, 3.0]


def test_zero_window_raises():
    with pytest.raises(ValueError):
        moving_average([1, 2, 3], 0)
