from typing import Union

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from configs import dify_config
from core.repositories.sqlalchemy_workflow_execution_repository import (
    SQLAlchemyWorkflowExecutionRepository,
)
from core.workflow.entities import WorkflowExecution
from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import run_log_write
from models import Account, EndUser
from models.enums import WorkflowRunTriggeredFrom


class PgLogWorkflowExecutionRepository:
    def __init__(
        self,
        session_factory: sessionmaker | Engine,
        user: Union[Account, EndUser],
        app_id: str | None,
        triggered_from: WorkflowRunTriggeredFrom | None,
    ):
        self._main_repository = SQLAlchemyWorkflowExecutionRepository(
            session_factory=session_factory,
            user=user,
            app_id=app_id,
            triggered_from=triggered_from,
        )
        self._log_repository = (
            SQLAlchemyWorkflowExecutionRepository(
                session_factory=get_sanfu_log_session_maker(),
                user=user,
                app_id=app_id,
                triggered_from=triggered_from,
            )
            if sanfu_log_db_enabled()
            else None
        )

    def save(self, execution: WorkflowExecution) -> None:
        if self._log_repository is None:
            self._main_repository.save(execution)
            return

        if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
            self._main_repository.save(execution)
            run_log_write(
                lambda: self._log_repository.save(execution),
                operation="workflow_execution.save",
            )
            return

        log_succeeded = run_log_write(
            lambda: self._log_repository.save(execution),
            operation="workflow_execution.save",
        )
        if not log_succeeded:
            self._main_repository.save(execution)
