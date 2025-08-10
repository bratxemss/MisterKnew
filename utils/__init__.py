import functools
import inspect
from typing import Annotated

def log_return(func):
    """
    Decorator that logs the return value of any function to the console.
    Supports both synchronous and asynchronous functions.
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            print(f"[log_return] {func.__name__} returned: {repr(result)}")
            return result

        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            print(f"[log_return] {func.__name__} returned: {repr(result)}")
            return result

        return sync_wrapper

