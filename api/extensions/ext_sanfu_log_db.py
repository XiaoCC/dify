import logging

from configs import dify_config
from dify_app import DifyApp
from extensions.sanfu_repository.database import get_sanfu_log_engine

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return dify_config.SANFU_LOG_DB_ENABLED and dify_config.SANFU_LOG_DB_AUTO_CREATE_TABLES


def init_app(app: DifyApp) -> None:
    get_sanfu_log_engine()
    logger.info("Initialized Sanfu workflow log database")

