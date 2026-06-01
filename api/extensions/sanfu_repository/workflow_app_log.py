from sqlalchemy import delete
from sqlalchemy.orm import Session

from configs import dify_config
from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import run_log_write
from models.workflow import WorkflowAppLog


def _clone_workflow_app_log(source: WorkflowAppLog) -> WorkflowAppLog:
    clone = WorkflowAppLog(
        tenant_id=source.tenant_id,
        app_id=source.app_id,
        workflow_id=source.workflow_id,
        workflow_run_id=source.workflow_run_id,
        created_from=source.created_from,
        created_by_role=source.created_by_role,
        created_by=source.created_by,
    )
    clone.id = source.id
    if source.created_at is not None:
        clone.created_at = source.created_at
    return clone


def _save_workflow_app_log_to_log_db(workflow_app_log: WorkflowAppLog) -> None:
    with get_sanfu_log_session_maker()() as session, session.begin():
        session.merge(_clone_workflow_app_log(workflow_app_log))


def save_workflow_app_log(main_session: Session, workflow_app_log: WorkflowAppLog) -> None:
    if not sanfu_log_db_enabled():
        main_session.add(workflow_app_log)
        return

    if dify_config.SANFU_LOG_REPOSITORY_DUAL_WRITE:
        main_session.add(workflow_app_log)
        run_log_write(
            lambda: _save_workflow_app_log_to_log_db(workflow_app_log),
            operation="workflow_app_log.save",
        )
        return

    log_succeeded = run_log_write(
        lambda: _save_workflow_app_log_to_log_db(workflow_app_log),
        operation="workflow_app_log.save",
    )
    if not log_succeeded:
        main_session.add(workflow_app_log)


def delete_workflow_app_logs_by_app(tenant_id: str, app_id: str) -> int:
    if not sanfu_log_db_enabled():
        return 0

    deleted_count = 0

    def delete_from_log_db() -> None:
        nonlocal deleted_count
        with get_sanfu_log_session_maker()() as session, session.begin():
            result = session.execute(
                delete(WorkflowAppLog).where(
                    WorkflowAppLog.tenant_id == tenant_id,
                    WorkflowAppLog.app_id == app_id,
                )
            )
            deleted_count = result.rowcount or 0

    run_log_write(delete_from_log_db, operation="workflow_app_log.delete_by_app")
    return deleted_count
