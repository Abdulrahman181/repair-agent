def paginate(items, page, per_page):
    """Return the items on a 1-based page.

    Page 1 holds the first per_page items. A page past the end returns an empty list.
    Raises ValueError if page < 1 or per_page < 1.
    """
    if page < 1 or per_page < 1:
        raise ValueError("page and per_page must be positive")
    start = (page - 1) * per_page
    return list(items[start:start + per_page])
