from deepmerge import deep_merge


def test_nested_merge():
    base = {"a": 1, "b": {"x": 1}}
    override = {"b": {"y": 2}, "c": 3}
    assert deep_merge(base, override) == {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}


def test_base_is_not_modified():
    base = {"a": 1, "b": {"x": 1}}
    deep_merge(base, {"a": 2, "b": {"y": 2}})
    assert base == {"a": 1, "b": {"x": 1}}


def test_returns_new_object():
    base = {"a": 1}
    assert deep_merge(base, {}) is not base
