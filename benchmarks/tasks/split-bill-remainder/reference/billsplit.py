def split_bill(total_cents, people):
    """Split an amount in integer cents between people as fairly as possible.

    Returns a list with one share per person. The shares sum exactly to total_cents, differ
    from each other by at most one cent, and the larger shares go to the earliest people.
    Raises ValueError if people < 1 or total_cents < 0.
    """
    if people < 1 or total_cents < 0:
        raise ValueError("invalid arguments")
    base, remainder = divmod(total_cents, people)
    return [base + 1] * remainder + [base] * (people - remainder)
