from slug import slugify


def test_empty_string():
    assert slugify("") == ""


def test_only_punctuation():
    assert slugify("!!!") == ""


def test_numbers_are_kept():
    assert slugify("Python 3.12 Release") == "python-3-12-release"


def test_already_a_slug():
    assert slugify("already-slugged") == "already-slugged"


def test_whitespace_kinds():
    assert slugify("Tabs\tand\nnewlines") == "tabs-and-newlines"


def test_underscore_is_a_separator():
    assert slugify("UPPER_case") == "upper-case"


def test_leading_and_trailing_separators():
    assert slugify("---x---") == "x"


def test_non_ascii_letters_are_separators():
    assert slugify("café au lait") == "caf-au-lait"
