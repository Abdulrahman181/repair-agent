import pytest

from wordstats import top_words


def test_arabic_words():
    assert top_words("كتاب قلم كتاب", 1) == [("كتاب", 2)]


def test_mixed_scripts_and_digits():
    result = top_words("data 2024 بيانات data بيانات data", 3)
    assert result == [("data", 3), ("بيانات", 2), ("2024", 1)]


def test_underscore_separates_words():
    assert top_words("snake_case snake", 2) == [("snake", 2), ("case", 1)]


def test_punctuation_is_removed():
    assert top_words("Hello, hello! HELLO?", 1) == [("hello", 3)]


def test_fewer_distinct_words_than_n():
    assert top_words("x y", 10) == [("x", 1), ("y", 1)]


def test_zero_n():
    assert top_words("x y", 0) == []


def test_negative_n_raises():
    with pytest.raises(ValueError):
        top_words("x y", -1)


def test_empty_text():
    assert top_words("", 3) == []
