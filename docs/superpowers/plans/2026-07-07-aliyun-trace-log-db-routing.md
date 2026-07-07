# Aliyun Trace Log Database Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Aliyun workflow tracing load node executions through Dify's configured repository so Sanfu log-database-only executions produce ARMS spans.

**Architecture:** Keep the Aliyun tracing provider storage-agnostic by replacing its direct SQLAlchemy repository construction with `DifyCoreRepositoryFactory`. Preserve the existing session factory, service account, application ID, trigger source, return value, and error behavior.

**Tech Stack:** Python 3, SQLAlchemy, pytest, unittest.mock, Dify repository factories

---

### Task 1: Route Aliyun workflow-node reads through the configured repository

**Files:**
- Create: `api/tests/unit_tests/core/ops/aliyun_trace/__init__.py`
- Create: `api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py`
- Modify: `api/core/ops/aliyun_trace/aliyun_trace.py:44-47,268-283`

- [x] **Step 1: Write the failing regression test**

```python
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
```

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
uv run --project api --group dev pytest api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py -q
```

Expected: FAIL because the result comes from the hard-coded `SQLAlchemyWorkflowNodeExecutionRepository` and the configured repository factory is not called.

- [x] **Step 3: Implement the minimal repository routing change**

Replace the direct repository import:

```python
from core.repositories import DifyCoreRepositoryFactory
```

Create the repository through the factory:

```python
workflow_node_execution_repository = DifyCoreRepositoryFactory.create_workflow_node_execution_repository(
    session_factory=session_factory,
    user=service_account,
    app_id=app_id,
    triggered_from=WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN,
)
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
uv run --project api --group dev pytest api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py -q
```

Expected: `1 passed`.

- [x] **Step 5: Run related repository and tracing tests**

Run:

```bash
uv run --project api --group dev pytest api/tests/unit_tests/core/ops api/tests/unit_tests/core/repositories/test_factory.py -q
```

Expected: all selected tests pass.

- [x] **Step 6: Run static checks for the changed Python files**

Run:

```bash
uv run --project api --group dev ruff check api/core/ops/aliyun_trace/aliyun_trace.py api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py
uv run --project api --group dev ruff format --check api/core/ops/aliyun_trace/aliyun_trace.py api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py
```

Expected: both commands exit successfully with no findings.

- [x] **Step 7: Commit the verified fix**

```bash
git add docs/superpowers/plans/2026-07-07-aliyun-trace-log-db-routing.md api/core/ops/aliyun_trace/aliyun_trace.py api/tests/unit_tests/core/ops/aliyun_trace/__init__.py api/tests/unit_tests/core/ops/aliyun_trace/test_aliyun_trace.py
git commit -m "fix: route aliyun trace reads to log repository"
```
