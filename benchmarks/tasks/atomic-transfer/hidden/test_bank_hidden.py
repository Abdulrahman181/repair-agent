import pytest

from bank import Account, InsufficientFunds, transfer


def test_negative_amount_rejected_without_changes():
    a, b = Account(100), Account(100)
    with pytest.raises(ValueError):
        transfer(a, b, -5)
    assert (a.balance, b.balance) == (100, 100)


def test_zero_amount_rejected():
    a, b = Account(100), Account(100)
    with pytest.raises(ValueError):
        transfer(a, b, 0)
    assert (a.balance, b.balance) == (100, 100)


def test_transfer_entire_balance():
    a, b = Account(70), Account(5)
    transfer(a, b, 70)
    assert (a.balance, b.balance) == (0, 75)


def test_failure_in_target_restores_source():
    class BrokenTarget(Account):
        def deposit(self, amount):
            raise RuntimeError("target unavailable")

    a, b = Account(100), BrokenTarget(0)
    with pytest.raises(RuntimeError):
        transfer(a, b, 40)
    assert a.balance == 100
    assert b.balance == 0


def test_money_is_conserved_over_many_transfers():
    accounts = [Account(100), Account(200), Account(300)]
    total = sum(acc.balance for acc in accounts)
    moves = [(0, 1, 50), (1, 2, 500), (2, 0, 300), (0, 2, 999), (1, 0, 250)]
    for src, dst, amount in moves:
        try:
            transfer(accounts[src], accounts[dst], amount)
        except InsufficientFunds:
            pass
    assert sum(acc.balance for acc in accounts) == total
    assert all(acc.balance >= 0 for acc in accounts)


def test_insufficient_error_type_is_specific():
    a, b = Account(1), Account(1)
    with pytest.raises(InsufficientFunds):
        transfer(a, b, 2)
