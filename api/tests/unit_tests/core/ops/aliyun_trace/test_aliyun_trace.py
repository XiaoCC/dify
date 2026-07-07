from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import sessionmaker

from core.ops.aliyun_trace.aliyun_trace import AliyunDataTrace
from core.ops.entities.trace_entity import WorkflowTraceInfo
from core.repositories import DifyCoreRepositoryFactory, SQLAlchemyWorkflowNodeExecutionRepository
from models import Account, WorkflowNodeExecutionTriggeredFrom


def test_get_workflow_node_executions_uses_configured_repository() -> None:
    trace = object.__new__(AliyunDataTrace)
    service_account = MagicMock(spec=Account)
    service_account.current_tenant_id = "tenant-id"
    trace_info = cast(WorkflowTraceInfo, SimpleNamespace(metadata={"app_id": "app-id"}, workflow_run_id="run-id"))
    session_factory = sessionmaker()
    expected_node_executions = [MagicMock()]
    configured_repository = MagicMock()
    configured_repository.get_by_workflow_run.return_value = expected_node_executions
    main_database = SimpleNamespace(engine=MagicMock())

    with (
        patch.object(trace, "get_service_account_with_tenant", return_value=service_account),
        patch("core.ops.aliyun_trace.aliyun_trace.db", main_database),
        patch("core.ops.aliyun_trace.aliyun_trace.sessionmaker", return_value=session_factory),
        patch.object(
            DifyCoreRepositoryFactory,
            "create_workflow_node_execution_repository",
            return_value=configured_repository,
        ) as create_repository,
        patch.object(SQLAlchemyWorkflowNodeExecutionRepository, "get_by_workflow_run", return_value=[]),
    ):
        result = trace.get_workflow_node_executions(trace_info)

    assert result == expected_node_executions
    create_repository.assert_called_once_with(
        session_factory=session_factory,
        user=service_account,
        app_id="app-id",
        triggered_from=WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN,
    )
    configured_repository.get_by_workflow_run.assert_called_once_with(workflow_run_id="run-id")
