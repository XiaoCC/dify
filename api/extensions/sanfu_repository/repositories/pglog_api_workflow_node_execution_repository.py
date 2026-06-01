from collections.abc import Sequence
from datetime import datetime
from typing import TypeVar

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session, attributes, sessionmaker

from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import (
    empty_when_none,
    empty_when_sequence,
    read_with_fallback,
    run_log_write,
)
from models.workflow import WorkflowNodeExecutionModel
from repositories.sqlalchemy_api_workflow_node_execution_repository import (
    DifyAPISQLAlchemyWorkflowNodeExecutionRepository,
)

_T = TypeVar("_T", bound=WorkflowNodeExecutionModel)


class _PgLogAPISQLAlchemyWorkflowNodeExecutionRepository(
    DifyAPISQLAlchemyWorkflowNodeExecutionRepository
):
    @staticmethod
    def _mark_no_offload(model: _T | None) -> _T | None:
        if model is not None:
            attributes.set_committed_value(model, "offload_data", [])
        return model

    @classmethod
    def _mark_many_no_offload(cls, models: Sequence[_T]) -> Sequence[_T]:
        for model in models:
            cls._mark_no_offload(model)
        return models

    def get_node_last_execution(
        self,
        tenant_id: str,
        app_id: str,
        workflow_id: str,
        node_id: str,
    ) -> WorkflowNodeExecutionModel | None:
        stmt = (
            select(WorkflowNodeExecutionModel)
            .where(
                WorkflowNodeExecutionModel.tenant_id == tenant_id,
                WorkflowNodeExecutionModel.app_id == app_id,
                WorkflowNodeExecutionModel.workflow_id == workflow_id,
                WorkflowNodeExecutionModel.node_id == node_id,
            )
            .order_by(desc(WorkflowNodeExecutionModel.created_at))
            .limit(1)
        )
        with self._session_maker() as session:
            return self._mark_no_offload(session.scalar(stmt))

    def get_executions_by_workflow_run(
        self,
        tenant_id: str,
        app_id: str,
        workflow_run_id: str,
    ) -> Sequence[WorkflowNodeExecutionModel]:
        stmt = (
            select(WorkflowNodeExecutionModel)
            .where(
                WorkflowNodeExecutionModel.tenant_id == tenant_id,
                WorkflowNodeExecutionModel.app_id == app_id,
                WorkflowNodeExecutionModel.workflow_run_id == workflow_run_id,
            )
            .order_by(asc(WorkflowNodeExecutionModel.created_at))
        )
        with self._session_maker() as session:
            return self._mark_many_no_offload(session.scalars(stmt).all())

    def get_execution_by_id(
        self,
        execution_id: str,
        tenant_id: str | None = None,
    ) -> WorkflowNodeExecutionModel | None:
        stmt = select(WorkflowNodeExecutionModel).where(
            WorkflowNodeExecutionModel.id == execution_id
        )
        if tenant_id is not None:
            stmt = stmt.where(WorkflowNodeExecutionModel.tenant_id == tenant_id)
        with self._session_maker() as session:
            return self._mark_no_offload(session.scalar(stmt))

    def get_expired_executions_batch(
        self,
        tenant_id: str,
        before_date: datetime,
        batch_size: int = 1000,
    ) -> Sequence[WorkflowNodeExecutionModel]:
        stmt = (
            select(WorkflowNodeExecutionModel)
            .where(
                WorkflowNodeExecutionModel.tenant_id == tenant_id,
                WorkflowNodeExecutionModel.created_at < before_date,
            )
            .limit(batch_size)
        )
        with self._session_maker() as session:
            return self._mark_many_no_offload(session.scalars(stmt).all())


class PgLogAPIWorkflowNodeExecutionRepository:
    def __init__(self, session_maker: sessionmaker[Session]):
        self._main_repository = DifyAPISQLAlchemyWorkflowNodeExecutionRepository(
            session_maker=session_maker
        )
        self._log_repository = (
            _PgLogAPISQLAlchemyWorkflowNodeExecutionRepository(
                session_maker=get_sanfu_log_session_maker()
            )
            if sanfu_log_db_enabled()
            else None
        )

    def get_node_last_execution(
        self,
        tenant_id: str,
        app_id: str,
        workflow_id: str,
        node_id: str,
    ) -> WorkflowNodeExecutionModel | None:
        if self._log_repository is None:
            return self._main_repository.get_node_last_execution(
                tenant_id,
                app_id,
                workflow_id,
                node_id,
            )
        return read_with_fallback(
            lambda: self._log_repository.get_node_last_execution(
                tenant_id,
                app_id,
                workflow_id,
                node_id,
            ),
            lambda: self._main_repository.get_node_last_execution(
                tenant_id,
                app_id,
                workflow_id,
                node_id,
            ),
            operation="api_workflow_node_execution.get_node_last_execution",
            is_empty=empty_when_none,
        )

    def get_executions_by_workflow_run(
        self,
        tenant_id: str,
        app_id: str,
        workflow_run_id: str,
    ) -> Sequence[WorkflowNodeExecutionModel]:
        if self._log_repository is None:
            return self._main_repository.get_executions_by_workflow_run(
                tenant_id,
                app_id,
                workflow_run_id,
            )
        return read_with_fallback(
            lambda: self._log_repository.get_executions_by_workflow_run(
                tenant_id,
                app_id,
                workflow_run_id,
            ),
            lambda: self._main_repository.get_executions_by_workflow_run(
                tenant_id,
                app_id,
                workflow_run_id,
            ),
            operation="api_workflow_node_execution.get_executions_by_workflow_run",
            is_empty=empty_when_sequence,
        )

    def get_execution_by_id(
        self,
        execution_id: str,
        tenant_id: str | None = None,
    ) -> WorkflowNodeExecutionModel | None:
        if self._log_repository is None:
            return self._main_repository.get_execution_by_id(execution_id, tenant_id)
        return read_with_fallback(
            lambda: self._log_repository.get_execution_by_id(execution_id, tenant_id),
            lambda: self._main_repository.get_execution_by_id(execution_id, tenant_id),
            operation="api_workflow_node_execution.get_execution_by_id",
            is_empty=empty_when_none,
        )

    def delete_expired_executions(
        self,
        tenant_id: str,
        before_date: datetime,
        batch_size: int = 1000,
    ) -> int:
        deleted = self._main_repository.delete_expired_executions(
            tenant_id,
            before_date,
            batch_size,
        )
        if self._log_repository is not None:
            run_log_write(
                lambda: self._log_repository.delete_expired_executions(
                    tenant_id,
                    before_date,
                    batch_size,
                ),
                operation="api_workflow_node_execution.delete_expired_executions",
            )
        return deleted

    def delete_executions_by_app(
        self,
        tenant_id: str,
        app_id: str,
        batch_size: int = 1000,
    ) -> int:
        deleted = self._main_repository.delete_executions_by_app(tenant_id, app_id, batch_size)
        if self._log_repository is not None:
            run_log_write(
                lambda: self._log_repository.delete_executions_by_app(
                    tenant_id,
                    app_id,
                    batch_size,
                ),
                operation="api_workflow_node_execution.delete_executions_by_app",
            )
        return deleted

    def get_expired_executions_batch(
        self,
        tenant_id: str,
        before_date: datetime,
        batch_size: int = 1000,
    ) -> Sequence[WorkflowNodeExecutionModel]:
        if self._log_repository is None:
            return self._main_repository.get_expired_executions_batch(
                tenant_id,
                before_date,
                batch_size,
            )
        return read_with_fallback(
            lambda: self._log_repository.get_expired_executions_batch(
                tenant_id,
                before_date,
                batch_size,
            ),
            lambda: self._main_repository.get_expired_executions_batch(
                tenant_id,
                before_date,
                batch_size,
            ),
            operation="api_workflow_node_execution.get_expired_executions_batch",
            is_empty=empty_when_sequence,
        )

    def delete_executions_by_ids(self, execution_ids: Sequence[str]) -> int:
        deleted = self._main_repository.delete_executions_by_ids(execution_ids)
        if self._log_repository is not None:
            run_log_write(
                lambda: self._log_repository.delete_executions_by_ids(execution_ids),
                operation="api_workflow_node_execution.delete_executions_by_ids",
            )
        return deleted
