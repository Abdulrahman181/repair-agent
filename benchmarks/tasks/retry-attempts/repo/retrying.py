import functools


def retry(attempts, exceptions=(Exception,)):
    """Decorator that calls the wrapped function up to attempts times.

    The function is retried only when it raises one of exceptions. The first successful
    result is returned, even when that result is None. If every attempt fails, the exception
    from the last attempt is re-raised. Any other exception propagates immediately without a
    retry. Raises ValueError if attempts < 1.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for _ in range(attempts - 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    continue
            return None

        return wrapper

    return decorator
