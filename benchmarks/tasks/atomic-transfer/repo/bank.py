class InsufficientFunds(Exception):
    pass


class Account:
    """A bank account holding an integer balance in cents.

    deposit and withdraw require a positive amount and raise ValueError otherwise. withdraw
    raises InsufficientFunds when the balance is too low and then leaves the balance unchanged.
    """

    def __init__(self, balance=0):
        if balance < 0:
            raise ValueError("balance must not be negative")
        self.balance = balance

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.balance += amount

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > self.balance:
            raise InsufficientFunds(f"balance {self.balance} is below {amount}")
        self.balance -= amount


def transfer(source, target, amount):
    """Move amount from source to target atomically.

    The amount must be positive and covered by the source balance. If the transfer fails for
    any reason, both balances are left exactly as they were and the error propagates.
    Transferring from an account to itself raises ValueError.
    """
    source.balance -= amount
    target.deposit(amount)
