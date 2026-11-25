def moving_average(values, window):
    """Return the simple moving average of values for the given window size.

    The result has len(values) - window + 1 entries, one per full window, in order. It is an
    empty list when window is larger than len(values). Raises ValueError if window < 1.
    """
    if window < 1:
        raise ValueError("window must be at least 1")
    result = []
    for start in range(len(values) - window + 1):
        chunk = values[start:start + window]
        result.append(sum(chunk) / window)
    return result
