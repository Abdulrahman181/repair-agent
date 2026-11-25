from cart.cart import Cart


def test_total_without_discount():
    cart = Cart()
    cart.add("pen", 250, 2)
    assert cart.total_cents() == 500


def test_total_with_discount():
    cart = Cart()
    cart.add("book", 1000, 1, discount_percent=10)
    assert cart.total_cents() == 900


def test_line_count():
    cart = Cart()
    cart.add("a", 100)
    cart.add("b", 200)
    assert cart.line_count() == 2
