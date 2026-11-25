import copy


def deep_merge(base, override):
    """Return a new dict that merges override into base recursively.

    Nested dicts are merged key by key. For every other type the value from override wins,
    including lists, which are replaced and not concatenated. Neither input is modified, and
    the result shares no mutable containers with either input.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
