def merge_intervals(intervals):
    """Merge overlapping or touching closed intervals.

    Each interval is a (start, end) tuple with start <= end. Intervals that overlap, or touch
    because one ends exactly where the next starts, are merged. The input may be unsorted and
    must not be modified. Returns a list of (start, end) tuples sorted by start.
    """
    merged = []
    for start, end in intervals:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
