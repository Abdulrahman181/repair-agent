import pytest

from lrucache import LRUCache


def test_put_existing_key_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 10
    assert cache.get("c") == 3


def test_update_never_evicts():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("b", 20)
    assert len(cache) == 2
    assert cache.get("a") == 1


def test_capacity_one():
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") is None
    assert cache.get("b") == 2


def test_invalid_capacity():
    with pytest.raises(ValueError):
        LRUCache(0)


def test_eviction_order_over_a_sequence():
    cache = LRUCache(3)
    for key in "abc":
        cache.put(key, key.upper())
    cache.get("a")
    cache.put("d", "D")
    assert cache.get("b") is None
    cache.get("c")
    cache.put("e", "E")
    assert cache.get("a") is None
    assert [cache.get(k) for k in "cde"] == ["C", "D", "E"]


def test_missing_key_does_not_change_size():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("zzz") is None
    assert len(cache) == 1
