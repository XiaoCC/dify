import logging
from functools import lru_cache
from urllib.parse import parse_qsl, quote_plus

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from configs import dify_config
from models.trigger import WorkflowTriggerLog
from models.workflow import WorkflowAppLog, WorkflowNodeExecutionModel, WorkflowRun

logger = logging.getLogger(__name__)


def sanfu_log_db_enabled() -> bool:
    return dify_config.SANFU_LOG_DB_ENABLED


def sanfu_log_db_read_enabled() -> bool:
    return dify_config.SANFU_LOG_DB_ENABLED and dify_config.SANFU_LOG_REPOSITORY_READ_FROM_LOG_DB


def sanfu_log_db_fallback_enabled() -> bool:
    return dify_config.SANFU_LOG_REPOSITORY_FALLBACK_TO_MAIN_DB


@lru_cache(maxsize=1)
def get_sanfu_log_engine() -> Engine:
    if not dify_config.SANFU_LOG_DB_ENABLED:
        raise RuntimeError("SANFU_LOG_DB_ENABLED is disabled")

    engine = create_engine(
        _build_database_uri(),
        pool_size=dify_config.SANFU_LOG_DB_POOL_SIZE,
        max_overflow=dify_config.SANFU_LOG_DB_MAX_OVERFLOW,
        pool_recycle=dify_config.SANFU_LOG_DB_POOL_RECYCLE,
        pool_pre_ping=dify_config.SANFU_LOG_DB_POOL_PRE_PING,
        pool_timeout=dify_config.SANFU_LOG_DB_POOL_TIMEOUT,
        pool_reset_on_return=None,
        connect_args=_build_connect_args(),
    )
    if dify_config.SANFU_LOG_DB_AUTO_CREATE_TABLES:
        _create_log_tables(engine)
    return engine


@lru_cache(maxsize=1)
def get_sanfu_log_session_maker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_sanfu_log_engine(), expire_on_commit=False)


def _build_database_uri() -> str:
    db_extras = (
        f"{dify_config.SANFU_LOG_DB_EXTRAS}&client_encoding={dify_config.SANFU_LOG_DB_CHARSET}"
        if dify_config.SANFU_LOG_DB_CHARSET
        else dify_config.SANFU_LOG_DB_EXTRAS
    ).strip("&")
    db_extras = f"?{db_extras}" if db_extras else ""
    return (
        "postgresql://"
        f"{quote_plus(dify_config.SANFU_LOG_DB_USERNAME)}:"
        f"{quote_plus(dify_config.SANFU_LOG_DB_PASSWORD)}@"
        f"{dify_config.SANFU_LOG_DB_HOST}:{dify_config.SANFU_LOG_DB_PORT}/"
        f"{dify_config.SANFU_LOG_DB_DATABASE}{db_extras}"
    )


def _build_connect_args() -> dict[str, str]:
    options = dict(parse_qsl(dify_config.SANFU_LOG_DB_EXTRAS)).get("options", "")
    timezone_opt = "-c timezone=UTC"
    merged_options = f"{options} {timezone_opt}" if options else timezone_opt
    return {"options": merged_options}


def _create_log_tables(engine: Engine) -> None:
    WorkflowAppLog.__table__.create(bind=engine, checkfirst=True)
    WorkflowTriggerLog.__table__.create(bind=engine, checkfirst=True)
    WorkflowRun.__table__.create(bind=engine, checkfirst=True)
    WorkflowNodeExecutionModel.__table__.create(bind=engine, checkfirst=True)
    _create_log_indexes(engine)
    logger.info("Ensured Sanfu workflow log tables exist")


def _create_log_indexes(engine: Engine) -> None:
    statements = [
        """
        CREATE INDEX IF NOT EXISTS idx_wfr_tenant_app_trigger_created
        ON workflow_runs (tenant_id, app_id, triggered_from, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wfal_tenant_app_created
        ON workflow_app_logs (tenant_id, app_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wfal_run_created
        ON workflow_app_logs (workflow_run_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wtl_tenant_app_run
        ON workflow_trigger_logs (tenant_id, app_id, workflow_run_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wtl_tenant_app_created
        ON workflow_trigger_logs (tenant_id, app_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wfr_app_status_created
        ON workflow_runs (app_id, status, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wfne_run_index
        ON workflow_node_executions (workflow_run_id, "index")
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_wfne_tenant_app_created
        ON workflow_node_executions (tenant_id, app_id, created_at DESC)
        """,
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(sa.text(statement))
