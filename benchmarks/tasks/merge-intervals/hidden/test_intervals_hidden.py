from intervals import merge_intervals


def test_empty():
    assert merge_intervals([]) == []


def test_single():
    assert merge_intervals([(4, 9)]) == [(4, 9)]


def test_nested_interval_absorbed():
    assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]


def test_chain_of_touching_intervals():
    assert merge_intervals([(5, 6), (1, 2), (3, 4), (2, 3), (4, 5)]) == [(1, 6)]


def test_identical_intervals():
    assert merge_intervals([(1, 2), (1, 2), (1, 2)]) == [(1, 2)]


def test_negative_numbers():
    assert merge_intervals([(-5, -1), (-3, 2), (4, 6)]) == [(-5, 2), (4, 6)]


def test_input_is_not_modified():
    data = [(8, 10), (1, 3), (2, 6)]
    snapshot = list(data)
    merge_intervals(data)
    assert data == snapshot


def test_disjoint_stay_separate():
    assert merge_intervals([(1, 2), (4, 5), (7, 8)]) == [(1, 2), (4, 5), (7, 8)]
