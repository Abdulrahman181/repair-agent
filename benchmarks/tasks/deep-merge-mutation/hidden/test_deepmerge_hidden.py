from deepmerge import deep_merge


def test_lists_are_replaced():
    assert deep_merge({"k": [1, 2]}, {"k": [3]}) == {"k": [3]}


def test_override_none_wins():
    assert deep_merge({"a": 1}, {"a": None}) == {"a": None}


def test_dict_replaces_scalar():
    assert deep_merge({"a": 1}, {"a": {"b": 2}}) == {"a": {"b": 2}}


def test_scalar_replaces_dict():
    assert deep_merge({"a": {"b": 2}}, {"a": 5}) == {"a": 5}


def test_empty_override_returns_equal_copy():
    base = {"a": {"b": [1, 2]}}
    result = deep_merge(base, {})
    assert result == base
    assert result is not base
    assert result["a"] is not base["a"]
    assert result["a"]["b"] is not base["a"]["b"]


def test_nested_base_not_mutated():
    base = {"a": {"b": {"c": 1}}}
    deep_merge(base, {"a": {"b": {"d": 2}}})
    assert base == {"a": {"b": {"c": 1}}}


def test_override_not_mutated_or_aliased():
    override = {"a": {"b": [1]}}
    result = deep_merge({}, override)
    result["a"]["b"].append(2)
    assert override == {"a": {"b": [1]}}


def test_deeply_nested_merge():
    base = {"a": {"b": {"c": {"d": 1}}}}
    override = {"a": {"b": {"c": {"e": 2}}}}
    assert deep_merge(base, override) == {"a": {"b": {"c": {"d": 1, "e": 2}}}}
