import pytest

from retrying import retry


def test_call_count_equals_attempts():
    calls = {"n": 0}

    @retry(4)
    def broken():
        calls["n"] += 1
        raise ValueError("x")

    with pytest.raises(ValueError):
        broken()
    assert calls["n"] == 4


def test_single_attempt_returns_value():
    @retry(1)
    def fine():
        return 42

    assert fine() == 42


def test_other_exceptions_propagate_immediately():
    calls = {"n": 0}

    @retry(5, exceptions=(KeyError,))
    def wrong_kind():
        calls["n"] += 1
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        wrong_kind()
    assert calls["n"] == 1


def test_none_result_is_a_success():
    calls = {"n": 0}

    @retry(3)
    def returns_none():
        calls["n"] += 1

    assert returns_none() is None
    assert calls["n"] == 1


def test_arguments_are_forwarded():
    @retry(2)
    def add(a, b=0):
        return a + b

    assert add(1, b=2) == 3


def test_last_error_is_the_one_raised():
    errors = [KeyError("first"), KeyError("second")]

    @retry(2, exceptions=(KeyError,))
    def failing():
        raise errors.pop(0)

    with pytest.raises(KeyError, match="second"):
        failing()


def test_metadata_is_preserved():
    @retry(2)
    def documented():
        """doc text"""

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "doc text"
