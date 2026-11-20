from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import ParamSpec, TypeVar

from tenacity import retry, stop_after_attempt, wait_exponential


class FEATURE_GENERATION_RUN_STATUS(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    IN_PROGRESS = "IN_PROGRESS"


def update_metadata(status: FEATURE_GENERATION_RUN_STATUS) -> None:
    """Persist the feature generation status. Replace with the metadata store call."""
    del status


P = ParamSpec("P")
R = TypeVar("R")


def feature_generation_runner(func: Callable[P, R]) -> Callable[P, R]:
    """Wrap a feature generator with retries and run-status metadata updates.

    The wrapped function is marked ``IN_PROGRESS`` before execution. It is
    retried up to three times with exponential backoff. On completion, its run
    status is updated to ``SUCCESS``; if it raises an exception after retries,
    the status is updated to ``FAILURE`` and the final exception is reraised.

    Parameters
    ----------
    func : Callable
        Feature-generation function to wrap.

    Returns
    -------
    Callable
        A wrapped function with the same call signature and return value as
        ``func``.

    Raises
    ------
    Exception
        Reraises the final exception if all attempts to run ``func`` fail.
    """
    @wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        update_metadata(FEATURE_GENERATION_RUN_STATUS.IN_PROGRESS)
        try:
            result = retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(),
                reraise=True,
            )(func)(*args, **kwargs)
        except Exception:
            update_metadata(FEATURE_GENERATION_RUN_STATUS.FAILURE)
            raise

        update_metadata(FEATURE_GENERATION_RUN_STATUS.SUCCESS)
        return result

    return wrapped
