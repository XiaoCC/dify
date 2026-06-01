from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Union

from sqlalchemy import UnaryExpression, asc, desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import attributes, sessionmaker

from configs import dify_config
from core.repositories.sqlalchemy_workflow_node_execution_repository import (
    SQLAlchemyWorkflowNodeExecutionRepository,
)
from core.workflow.entities import WorkflowNodeExecution
from core.workflow.repositories.workflow_node_execution_repository import OrderConfig
from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import run_log_write
from models import Account, EndUser, WorkflowNodeExecutionModel, WorkflowNodeExecutionTriggeredFrom


class _PgLogSQLAlchemyWorkflowNodeExecutionRepository(SQLAlchemyWorkflowNodeExecutionRepository):
    def save_execution_data(self, execution: WorkflowNodeExecution) -> None:
        db_model = self._to_db_model(execution)
        with self._session_factory() as session, session.begin():
            session.merge(db_model)
            session.flush()

    def get_db_models_by_workflow_run(
        self,
        workflow_run_id: str,
        order_config: OrderConfig | None = None,
        triggered_from: WorkflowNodeExecutionTriggeredFrom = (
            WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN
        ),
    ) -> Sequence[WorkflowNodeExecutionModel]:
        with self._session_factory() as session:
            stmt = select(WorkflowNodeExecutionModel).where(
                WorkflowNodeExecutionModel.workflow_run_id == workflow_run_id,
                WorkflowNodeExecutionModel.tenant_id == self._tenant_id,
                WorkflowNodeExecutionModel.triggered_from == triggered_from,
            )

            if self._app_id:
                stmt = stmt.where(WorkflowNodeExecutionModel.app_id == self._app_id)

            if order_config and order_config.order_by:
                order_columns: list[UnaryExpression] = []
                for field in order_config.order_by:
                    column = getattr(WorkflowNodeExecutionModel, field, None)
                    if column is None:
                        continue
                    if order_config.order_direction == "desc":
                        order_columns.append(desc(column))
                    else:
                        order_columns.append(asc(column))

                if order_columns:
                    stmt = stmt.order_by(*order_columns)

            db_models = session.scalars(stmt).all()

            for model in db_models:
                attributes.set_committed_value(model, "offload_data", [])
                if model.node_execution_id:
                    self._node_execution_cache[model.node_execution_id] = model

            return db_models


class PgLogWorkflowNodeExecutionRepository:
    def __init__(
        self,
        session_factory: sessionmaker | Engine,
        user: Union[Account, EndUser],
        app_id: str | None,
        triggered_from: WorkflowNodeExecutionTriggeredFrom | None,
    ):
        self._main_repository = SQLAlchemyWorkflowNodeExecutionRepository(
            session_factory=session_factory,
            user=user,
            app_id=app_id,
            triggered_from=triggered_from,
        )
        self._log_repository = (
            _PgLogSQLAlchemyWorkflowNodeExecutionRepository(
                session_factory=get_sanfu_log_session_maker(),
                user=user,
                app_id=app_id,
                triggered_from=triggered_from,
            )
            if sanfu_log_db_enabled()
            else None
        )

    def save(self, execution: WorkflowNodeExecution) -> None:
        if self._log_repository is None:
            self._main_repository.save(execution)
            return

        if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
            self._main_repository.save(execution)
            run_log_write(
                lambda: self._log_repository.save(execution),
                operation="workflow_node_execution.save",
            )
            return

        log_succeeded = run_log_write(
            lambda: self._log_repository.save(execution),
            operation="workflow_node_execution.save",
        )
        if not log_succeeded:
            self._main_repository.save(execution)

    def save_execution_data(self, execution: WorkflowNodeExecution) -> None:
        if self._log_repository is None:
            self._main_repository.save_execution_data(execution)
            return

        if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
            run_log_write(
                lambda: self._log_repository.save_execution_data(execution),
                operation="workflow_node_execution.save_execution_data",
            )
            self._main_repository.save_execution_data(execution)
            return

        log_succeeded = run_log_write(
            lambda: self._log_repository.save_execution_data(execution),
            operation="workflow_node_execution.save_execution_data",
        )
        if not log_succeeded:
            self._main_repository.save_execution_data(execution)

    def get_db_models_by_workflow_run(
        self,
        workflow_run_id: str,
        order_config: OrderConfig | None = None,
        triggered_from: WorkflowNodeExecutionTriggeredFrom = (
            WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN
        ),
    ) -> Sequence[WorkflowNodeExecutionModel]:
        if self._log_repository is None or not dify_config.SANFU_LOG_REPOSITORY_READ_FROM_LOG_DB:
            return self._main_repository.get_db_models_by_workflow_run(
                workflow_run_id=workflow_run_id,
                order_config=order_config,
                triggered_from=triggered_from,
            )

        try:
            db_models = self._log_repository.get_db_models_by_workflow_run(
                workflow_run_id=workflow_run_id,
                order_config=order_config,
                triggered_from=triggered_from,
            )
        except Exception:
            if dify_config.SANFU_LOG_REPOSITORY_FALLBACK_TO_MAIN_DB:
                return self._main_repository.get_db_models_by_workflow_run(
                    workflow_run_id=workflow_run_id,
                    order_config=order_config,
                    triggered_from=triggered_from,
                )
            raise

        if not db_models and dify_config.SANFU_LOG_REPOSITORY_FALLBACK_TO_MAIN_DB:
            return self._main_repository.get_db_models_by_workflow_run(
                workflow_run_id=workflow_run_id,
                order_config=order_config,
                triggered_from=triggered_from,
            )
        return db_models

    def get_by_workflow_run(
        self,
        workflow_run_id: str,
        order_config: OrderConfig | None = None,
        triggered_from: WorkflowNodeExecutionTriggeredFrom = (
            WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN
        ),
    ) -> Sequence[WorkflowNodeExecution]:
        db_models = self.get_db_models_by_workflow_run(
            workflow_run_id,
            order_config,
            triggered_from,
        )
        with ThreadPoolExecutor(max_workers=10) as executor:
            domain_models = executor.map(
                self._main_repository._to_domain_model,
                db_models,
                timeout=30,
            )
        return list(domain_models)
