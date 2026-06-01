import logging
from collections.abc import Callable
from typing import TypeVar

from configs import dify_config
from extensions.sanfu_repository.database import sanfu_log_db_fallback_enabled

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def run_log_write(action: Callable[[], None], *, operation: str) -> bool:
    try:
        action()
        return True
    except Exception:
        if sanfu_log_db_fallback_enabled():
            logger.exception("Sanfu log database write failed, operation=%s", operation)
            return False
        raise


def read_with_fallback(
    log_read: Callable[[], _T],
    main_read: Callable[[], _T],
    *,
    operation: str,
    is_empty: Callable[[_T], bool],
) -> _T:
    if not dify_config.SANFU_LOG_REPOSITORY_READ_FROM_LOG_DB:
        return main_read()

    try:
        result = log_read()
    except Exception:
        if sanfu_log_db_fallback_enabled():
            logger.exception("Sanfu log database read failed, operation=%s", operation)
            return main_read()
        raise

    if is_empty(result) and sanfu_log_db_fallback_enabled():
        return main_read()
    return result


def empty_when_none(value: object) -> bool:
    return value is None


def empty_when_sequence(value: object) -> bool:
    return not bool(value)

