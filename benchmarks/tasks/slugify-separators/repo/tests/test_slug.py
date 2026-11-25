from slug import slugify


def test_simple_words():
    assert slugify("Hello World") == "hello-world"


def test_punctuation_and_spaces():
    assert slugify("  Hello,   World!! ") == "hello-world"


def test_repeated_hyphens_collapse():
    assert slugify("a--b") == "a-b"
