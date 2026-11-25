import pytest

from smoothing import moving_average


def test_window_equal_to_length():
    assert moving_average([2, 4, 6], 3) == [4.0]


def test_window_larger_than_length():
    assert moving_average([1, 2], 5) == []


def test_empty_values():
    assert moving_average([], 2) == []


def test_negative_numbers():
    assert moving_average([-1, 1, -1, 1], 2) == [0.0, 0.0, 0.0]


def test_floats():
    assert moving_average([0.5, 1.5, 2.5], 2) == pytest.approx([1.0, 2.0])


def test_length_formula():
    values = list(range(20))
    for window in range(1, 21):
        assert len(moving_average(values, window)) == len(values) - window + 1


def test_negative_window_raises():
    with pytest.raises(ValueError):
        moving_average([1, 2, 3], -1)
