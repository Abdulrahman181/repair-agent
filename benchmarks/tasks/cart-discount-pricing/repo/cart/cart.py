from cart.pricing import apply_discount


class Cart:
    """A shopping cart. All prices are integer cents."""

    def __init__(self):
        self._lines = []

    def add(self, name, unit_price_cents, quantity=1, discount_percent=0):
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        self._lines.append((name, unit_price_cents, quantity, discount_percent))

    def total_cents(self):
        total = 0
        for _name, unit, quantity, discount in self._lines:
            total += apply_discount(unit, discount) * quantity
        return total

    def line_count(self):
        return len(self._lines)
