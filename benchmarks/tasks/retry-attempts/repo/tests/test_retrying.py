import pytest

from retrying import retry


def test_succeeds_after_failures():
    calls = {"n": 0}

    @retry(3)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("not yet")
        return "ok"

    assert flaky() == "ok"


def test_raises_last_error_when_all_attempts_fail():
    @retry(2)
    def broken():
        raise RuntimeError("always")

    with pytest.raises(RuntimeError, match="always"):
        broken()


def test_zero_attempts_invalid():
    with pytest.raises(ValueError):
        retry(0)
