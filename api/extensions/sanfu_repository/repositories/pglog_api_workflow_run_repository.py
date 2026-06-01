from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from core.workflow.entities.pause_reason import PauseReason
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from extensions.sanfu_repository.database import get_sanfu_log_session_maker, sanfu_log_db_enabled
from extensions.sanfu_repository.repositories.base import (
    empty_when_none,
    empty_when_sequence,
    read_with_fallback,
    run_log_write,
)
from models.enums import WorkflowRunTriggeredFrom
from models.workflow import WorkflowRun
from repositories.entities.workflow_pause import WorkflowPauseEntity
from repositories.sqlalchemy_api_workflow_run_repository import (
    DifyAPISQLAlchemyWorkflowRunRepository,
)
from repositories.types import (
    AverageInteractionStats,
    DailyRunsStats,
    DailyTerminalsStats,
    DailyTokenCostStats,
)


class PgLogAPIWorkflowRunRepository:
    def __init__(self, session_maker: sessionmaker[Session]):
        self._main_repository = DifyAPISQLAlchemyWorkflowRunRepository(session_maker=session_maker)
        self._log_repository = (
            DifyAPISQLAlchemyWorkflowRunRepository(session_maker=get_sanfu_log_session_maker())
            if sanfu_log_db_enabled()
            else None
        )

    def get_paginated_workflow_runs(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: WorkflowRunTriggeredFrom | Sequence[WorkflowRunTriggeredFrom],
        limit: int = 20,
        last_id: str | None = None,
        status: str | None = None,
    ) -> InfiniteScrollPagination:
        if self._log_repository is None:
            return self._main_repository.get_paginated_workflow_runs(
                tenant_id, app_id, triggered_from, limit, last_id, status
            )
        return read_with_fallback(
            lambda: self._log_repository.get_paginated_workflow_runs(
                tenant_id, app_id, triggered_from, limit, last_id, status
            ),
            lambda: self._main_repository.get_paginated_workflow_runs(
                tenant_id, app_id, triggered_from, limit, last_id, status
            ),
            operation="api_workflow_run.get_paginated_workflow_runs",
            is_empty=lambda pagination: not pagination.data,
        )

    def get_workflow_run_by_id(
        self,
        tenant_id: str,
        app_id: str,
        run_id: str,
    ) -> WorkflowRun | None:
        if self._log_repository is None:
            return self._main_repository.get_workflow_run_by_id(tenant_id, app_id, run_id)
        return read_with_fallback(
            lambda: self._log_repository.get_workflow_run_by_id(tenant_id, app_id, run_id),
            lambda: self._main_repository.get_workflow_run_by_id(tenant_id, app_id, run_id),
            operation="api_workflow_run.get_workflow_run_by_id",
            is_empty=empty_when_none,
        )

    def get_workflow_run_by_id_without_tenant(self, run_id: str) -> WorkflowRun | None:
        if self._log_repository is None:
            return self._main_repository.get_workflow_run_by_id_without_tenant(run_id)
        return read_with_fallback(
            lambda: self._log_repository.get_workflow_run_by_id_without_tenant(run_id),
            lambda: self._main_repository.get_workflow_run_by_id_without_tenant(run_id),
            operation="api_workflow_run.get_workflow_run_by_id_without_tenant",
            is_empty=empty_when_none,
        )

    def get_workflow_runs_count(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: str,
        status: str | None = None,
        time_range: str | None = None,
    ) -> dict[str, int]:
        if self._log_repository is None:
            return self._main_repository.get_workflow_runs_count(
                tenant_id, app_id, triggered_from, status, time_range
            )
        return read_with_fallback(
            lambda: self._log_repository.get_workflow_runs_count(
                tenant_id, app_id, triggered_from, status, time_range
            ),
            lambda: self._main_repository.get_workflow_runs_count(
                tenant_id, app_id, triggered_from, status, time_range
            ),
            operation="api_workflow_run.get_workflow_runs_count",
            is_empty=lambda counts: counts.get("total", 0) == 0,
        )

    def get_expired_runs_batch(
        self,
        tenant_id: str,
        before_date: datetime,
        batch_size: int = 1000,
    ) -> Sequence[WorkflowRun]:
        if self._log_repository is None:
            return self._main_repository.get_expired_runs_batch(tenant_id, before_date, batch_size)
        return read_with_fallback(
            lambda: self._log_repository.get_expired_runs_batch(tenant_id, before_date, batch_size),
            lambda: self._main_repository.get_expired_runs_batch(
                tenant_id,
                before_date,
                batch_size,
            ),
            operation="api_workflow_run.get_expired_runs_batch",
            is_empty=empty_when_sequence,
        )

    def delete_runs_by_ids(self, run_ids: Sequence[str]) -> int:
        deleted = self._main_repository.delete_runs_by_ids(run_ids)
        if self._log_repository is not None:
            run_log_write(
                lambda: self._log_repository.delete_runs_by_ids(run_ids),
                operation="api_workflow_run.delete_runs_by_ids",
            )
        return deleted

    def delete_runs_by_app(
        self,
        tenant_id: str,
        app_id: str,
        batch_size: int = 1000,
    ) -> int:
        deleted = self._main_repository.delete_runs_by_app(tenant_id, app_id, batch_size)
        if self._log_repository is not None:
            run_log_write(
                lambda: self._log_repository.delete_runs_by_app(tenant_id, app_id, batch_size),
                operation="api_workflow_run.delete_runs_by_app",
            )
        return deleted

    def create_workflow_pause(
        self,
        workflow_run_id: str,
        state_owner_user_id: str,
        state: str,
        pause_reasons: Sequence[PauseReason],
    ) -> WorkflowPauseEntity:
        return self._main_repository.create_workflow_pause(
            workflow_run_id=workflow_run_id,
            state_owner_user_id=state_owner_user_id,
            state=state,
            pause_reasons=pause_reasons,
        )

    def get_workflow_pause(self, workflow_run_id: str) -> WorkflowPauseEntity | None:
        return self._main_repository.get_workflow_pause(workflow_run_id)

    def resume_workflow_pause(
        self,
        workflow_run_id: str,
        pause_entity: WorkflowPauseEntity,
    ) -> WorkflowPauseEntity:
        return self._main_repository.resume_workflow_pause(workflow_run_id, pause_entity)

    def delete_workflow_pause(self, pause_entity: WorkflowPauseEntity) -> None:
        self._main_repository.delete_workflow_pause(pause_entity)

    def prune_pauses(
        self,
        expiration: datetime,
        resumption_expiration: datetime,
        limit: int | None = None,
    ) -> Sequence[str]:
        return self._main_repository.prune_pauses(expiration, resumption_expiration, limit)

    def get_daily_runs_statistics(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        timezone: str = "UTC",
    ) -> list[DailyRunsStats]:
        if self._log_repository is None:
            return self._main_repository.get_daily_runs_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            )
        return read_with_fallback(
            lambda: self._log_repository.get_daily_runs_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            lambda: self._main_repository.get_daily_runs_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            operation="api_workflow_run.get_daily_runs_statistics",
            is_empty=empty_when_sequence,
        )

    def get_daily_terminals_statistics(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        timezone: str = "UTC",
    ) -> list[DailyTerminalsStats]:
        if self._log_repository is None:
            return self._main_repository.get_daily_terminals_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            )
        return read_with_fallback(
            lambda: self._log_repository.get_daily_terminals_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            lambda: self._main_repository.get_daily_terminals_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            operation="api_workflow_run.get_daily_terminals_statistics",
            is_empty=empty_when_sequence,
        )

    def get_daily_token_cost_statistics(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        timezone: str = "UTC",
    ) -> list[DailyTokenCostStats]:
        if self._log_repository is None:
            return self._main_repository.get_daily_token_cost_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            )
        return read_with_fallback(
            lambda: self._log_repository.get_daily_token_cost_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            lambda: self._main_repository.get_daily_token_cost_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            operation="api_workflow_run.get_daily_token_cost_statistics",
            is_empty=empty_when_sequence,
        )

    def get_average_app_interaction_statistics(
        self,
        tenant_id: str,
        app_id: str,
        triggered_from: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        timezone: str = "UTC",
    ) -> list[AverageInteractionStats]:
        if self._log_repository is None:
            return self._main_repository.get_average_app_interaction_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            )
        return read_with_fallback(
            lambda: self._log_repository.get_average_app_interaction_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            lambda: self._main_repository.get_average_app_interaction_statistics(
                tenant_id, app_id, triggered_from, start_date, end_date, timezone
            ),
            operation="api_workflow_run.get_average_app_interaction_statistics",
            is_empty=empty_when_sequence,
        )
