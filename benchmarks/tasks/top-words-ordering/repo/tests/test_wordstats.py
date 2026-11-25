from wordstats import top_words


def test_basic_counts():
    assert top_words("a b a c b a", 2) == [("a", 3), ("b", 2)]


def test_case_insensitive():
    assert top_words("The the THE cat", 1) == [("the", 3)]


def test_ties_are_alphabetical():
    assert top_words("pear apple pear apple", 2) == [("apple", 2), ("pear", 2)]
