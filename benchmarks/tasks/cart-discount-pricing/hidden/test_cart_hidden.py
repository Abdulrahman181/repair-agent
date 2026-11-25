import pytest

from cart.cart import Cart
from cart.pricing import apply_discount


def test_discount_rounds_half_up():
    assert apply_discount(999, 50) == 500


def test_discount_rounds_down_below_half():
    assert apply_discount(101, 10) == 91


def test_zero_percent_keeps_price():
    assert apply_discount(1234, 0) == 1234


def test_hundred_percent_is_free():
    assert apply_discount(1234, 100) == 0


def test_zero_price():
    assert apply_discount(0, 25) == 0


@pytest.mark.parametrize("price,percent", [(100, -1), (100, 101), (-1, 10)])
def test_invalid_inputs(price, percent):
    with pytest.raises(ValueError):
        apply_discount(price, percent)


def test_mixed_cart_total():
    cart = Cart()
    cart.add("pen", 250, 2)
    cart.add("book", 1999, 1, discount_percent=25)
    cart.add("bag", 5000, 3, discount_percent=50)
    assert cart.total_cents() == 500 + 1499 + 7500


def test_empty_cart_total_is_zero():
    assert Cart().total_cents() == 0


def test_invalid_quantity_rejected():
    with pytest.raises(ValueError):
        Cart().add("x", 100, 0)
