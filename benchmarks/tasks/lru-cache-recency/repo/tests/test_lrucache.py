from lrucache import LRUCache


def test_basic_put_and_get():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None


def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1


def test_len_respects_capacity():
    cache = LRUCache(2)
    for index in range(5):
        cache.put(index, index)
    assert len(cache) == 2
