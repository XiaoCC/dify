from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from configs import dify_config
from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import (
    empty_when_none,
    empty_when_sequence,
    read_with_fallback,
    run_log_write,
)
from models.trigger import WorkflowTriggerLog
from repositories.sqlalchemy_workflow_trigger_log_repository import SQLAlchemyWorkflowTriggerLogRepository


def _clone_trigger_log(source: WorkflowTriggerLog) -> WorkflowTriggerLog:
    clone = WorkflowTriggerLog(
        tenant_id=source.tenant_id,
        app_id=source.app_id,
        workflow_id=source.workflow_id,
        workflow_run_id=source.workflow_run_id,
        root_node_id=source.root_node_id,
        trigger_metadata=source.trigger_metadata,
        trigger_type=source.trigger_type,
        trigger_data=source.trigger_data,
        inputs=source.inputs,
        outputs=source.outputs,
        status=source.status,
        error=source.error,
        queue_name=source.queue_name,
        celery_task_id=source.celery_task_id,
        created_by_role=source.created_by_role,
        created_by=source.created_by,
        retry_count=source.retry_count,
        elapsed_time=source.elapsed_time,
        total_tokens=source.total_tokens,
        triggered_at=source.triggered_at,
        finished_at=source.finished_at,
    )
    clone.id = source.id
    if source.created_at is not None:
        clone.created_at = source.created_at
    return clone


class PgLogWorkflowTriggerLogRepository:
    def __init__(self, session: Session):
        self._main_repository = SQLAlchemyWorkflowTriggerLogRepository(session)
        self._log_session_maker = get_sanfu_log_session_maker() if sanfu_log_db_enabled() else None

    def _write_log(self, trigger_log: WorkflowTriggerLog) -> None:
        if self._log_session_maker is None:
            return

        with self._log_session_maker() as session, session.begin():
            session.merge(_clone_trigger_log(trigger_log))
            session.flush()

    def create(self, trigger_log: WorkflowTriggerLog) -> WorkflowTriggerLog:
        if self._log_session_maker is None:
            return self._main_repository.create(trigger_log)

        if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
            created = self._main_repository.create(trigger_log)
            run_log_write(lambda: self._write_log(created), operation="workflow_trigger_log.create")
            return created

        log_succeeded = run_log_write(lambda: self._write_log(trigger_log), operation="workflow_trigger_log.create")
        if not log_succeeded:
            return self._main_repository.create(trigger_log)
        return trigger_log

    def update(self, trigger_log: WorkflowTriggerLog) -> WorkflowTriggerLog:
        if self._log_session_maker is None:
            return self._main_repository.update(trigger_log)

        if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
            updated = self._main_repository.update(trigger_log)
            run_log_write(lambda: self._write_log(updated), operation="workflow_trigger_log.update")
            return updated

        log_succeeded = run_log_write(lambda: self._write_log(trigger_log), operation="workflow_trigger_log.update")
        if not log_succeeded:
            return self._main_repository.update(trigger_log)
        return trigger_log

    def get_by_id(self, trigger_log_id: str, tenant_id: str | None = None) -> WorkflowTriggerLog | None:
        if self._log_session_maker is None:
            return self._main_repository.get_by_id(trigger_log_id, tenant_id)

        return read_with_fallback(
            lambda: self._get_by_id_from_log_db(trigger_log_id, tenant_id),
            lambda: self._main_repository.get_by_id(trigger_log_id, tenant_id),
            operation="workflow_trigger_log.get_by_id",
            is_empty=empty_when_none,
        )

    def _get_by_id_from_log_db(self, trigger_log_id: str, tenant_id: str | None) -> WorkflowTriggerLog | None:
        if self._log_session_maker is None:
            return None

        with self._log_session_maker() as session:
            return SQLAlchemyWorkflowTriggerLogRepository(session).get_by_id(trigger_log_id, tenant_id)

    def get_failed_for_retry(
        self,
        tenant_id: str,
        max_retry_count: int = 3,
        limit: int = 100,
    ) -> Sequence[WorkflowTriggerLog]:
        if self._log_session_maker is None:
            return self._main_repository.get_failed_for_retry(tenant_id, max_retry_count, limit)

        return read_with_fallback(
            lambda: self._get_failed_for_retry_from_log_db(tenant_id, max_retry_count, limit),
            lambda: self._main_repository.get_failed_for_retry(tenant_id, max_retry_count, limit),
            operation="workflow_trigger_log.get_failed_for_retry",
            is_empty=empty_when_sequence,
        )

    def _get_failed_for_retry_from_log_db(
        self,
        tenant_id: str,
        max_retry_count: int,
        limit: int,
    ) -> Sequence[WorkflowTriggerLog]:
        if self._log_session_maker is None:
            return []

        with self._log_session_maker() as session:
            return SQLAlchemyWorkflowTriggerLogRepository(session).get_failed_for_retry(
                tenant_id,
                max_retry_count,
                limit,
            )

    def get_recent_logs(
        self,
        tenant_id: str,
        app_id: str,
        hours: int = 24,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[WorkflowTriggerLog]:
        if self._log_session_maker is None:
            return self._main_repository.get_recent_logs(tenant_id, app_id, hours, limit, offset)

        return read_with_fallback(
            lambda: self._get_recent_logs_from_log_db(tenant_id, app_id, hours, limit, offset),
            lambda: self._main_repository.get_recent_logs(tenant_id, app_id, hours, limit, offset),
            operation="workflow_trigger_log.get_recent_logs",
            is_empty=empty_when_sequence,
        )

    def _get_recent_logs_from_log_db(
        self,
        tenant_id: str,
        app_id: str,
        hours: int,
        limit: int,
        offset: int,
    ) -> Sequence[WorkflowTriggerLog]:
        if self._log_session_maker is None:
            return []

        with self._log_session_maker() as session:
            return SQLAlchemyWorkflowTriggerLogRepository(session).get_recent_logs(
                tenant_id,
                app_id,
                hours,
                limit,
                offset,
            )


def delete_workflow_trigger_logs_by_app(tenant_id: str, app_id: str) -> int:
    if not sanfu_log_db_enabled():
        return 0

    deleted_count = 0

    def delete_from_log_db() -> None:
        nonlocal deleted_count
        with get_sanfu_log_session_maker()() as session, session.begin():
            result = session.execute(
                delete(WorkflowTriggerLog).where(
                    WorkflowTriggerLog.tenant_id == tenant_id,
                    WorkflowTriggerLog.app_id == app_id,
                )
            )
            deleted_count = result.rowcount or 0

    run_log_write(delete_from_log_db, operation="workflow_trigger_log.delete_by_app")
    return deleted_count
