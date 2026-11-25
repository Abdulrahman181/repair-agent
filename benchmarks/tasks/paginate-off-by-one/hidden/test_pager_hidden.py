import pytest

from pager import paginate


def test_last_partial_page():
    assert paginate(list(range(10)), 4, 3) == [9]


def test_page_past_end_is_empty():
    assert paginate(list(range(10)), 5, 3) == []


def test_per_page_larger_than_items():
    assert paginate([1, 2], 1, 10) == [1, 2]


def test_empty_items():
    assert paginate([], 1, 5) == []


def test_tuple_input_returns_list():
    assert paginate((1, 2, 3, 4), 2, 2) == [3, 4]


def test_single_item_pages_cover_everything():
    items = list("abcde")
    pages = [paginate(items, n, 1) for n in range(1, 6)]
    assert [p[0] for p in pages] == items


@pytest.mark.parametrize("page,per_page", [(0, 3), (-1, 3), (1, 0), (1, -2)])
def test_invalid_arguments(page, per_page):
    with pytest.raises(ValueError):
        paginate([1, 2, 3], page, per_page)
