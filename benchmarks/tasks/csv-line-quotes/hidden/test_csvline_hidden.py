import pytest

from csvline import parse_line


def test_empty_fields():
    assert parse_line("a,,b") == ["a", "", "b"]


def test_trailing_comma_gives_empty_last_field():
    assert parse_line("a,b,") == ["a", "b", ""]


def test_empty_line():
    assert parse_line("") == [""]


def test_whitespace_is_preserved():
    assert parse_line(" a , b ") == [" a ", " b "]


def test_quoted_empty_field():
    assert parse_line('a,"",b') == ["a", "", "b"]


def test_quoted_field_ending_with_comma():
    assert parse_line('"a,",b') == ["a,", "b"]


def test_only_a_quoted_field():
    assert parse_line('"just one, field"') == ["just one, field"]


def test_unterminated_quote_raises():
    with pytest.raises(ValueError):
        parse_line('a,"abc')


def test_arabic_text():
    assert parse_line('اسم,"المدينة, الدولة"') == ["اسم", "المدينة, الدولة"]


def test_quote_pair_only():
    assert parse_line('""""') == ['"']
