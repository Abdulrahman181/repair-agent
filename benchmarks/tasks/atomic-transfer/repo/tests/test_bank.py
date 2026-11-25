import pytest

from bank import Account, InsufficientFunds, transfer


def test_transfer_moves_money():
    a, b = Account(100), Account(10)
    transfer(a, b, 40)
    assert (a.balance, b.balance) == (60, 50)


def test_insufficient_funds_leaves_balances_unchanged():
    a, b = Account(30), Account(0)
    with pytest.raises(InsufficientFunds):
        transfer(a, b, 50)
    assert (a.balance, b.balance) == (30, 0)


def test_transfer_to_same_account_raises():
    a = Account(100)
    with pytest.raises(ValueError):
        transfer(a, a, 10)
    assert a.balance == 100
