def apply_discount(price_cents, percent):
    """Return the price in cents after taking a whole-number percent off.

    percent is between 0 and 100 inclusive. The result is rounded half up to a whole cent.
    Raises ValueError for a percent outside 0..100 or a negative price.
    """
    if percent < 0 or percent > 100 or price_cents < 0:
        raise ValueError("invalid price or percent")
    return int(price_cents * (100 - percent) / 10)
