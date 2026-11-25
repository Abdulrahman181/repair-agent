import re
from collections import Counter


def top_words(text, n):
    """Return the n most frequent words as (word, count) tuples.

    Words are runs of letters or digits in any script, including Arabic. Underscores and
    punctuation separate words. Words are compared case-insensitively and returned in lower
    case. Results are sorted by count descending and then alphabetically ascending for equal
    counts. Fewer than n entries are returned when there are fewer distinct words. Raises
    ValueError if n < 0.
    """
    if n < 0:
        raise ValueError("n must not be negative")
    words = re.findall(r"[^\W_]+", text.lower())
    counts = Counter(words)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[:n]
