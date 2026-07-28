from unittest.mock import MagicMock, patch

from core.app.apps.advanced_chat.generate_task_pipeline import AdvancedChatAppGenerateTaskPipeline
from core.app.entities.queue_entities import (
    QueueAdvancedChatMessageEndEvent,
    QueueWorkflowPartialSuccessEvent,
    QueueWorkflowSucceededEvent,
)
from core.app.entities.task_entities import MessageEndStreamResponse, StreamEvent, StreamResponse
from core.workflow.runtime import GraphRuntimeState


def _build_pipeline(workflow_finish_response: StreamResponse) -> AdvancedChatAppGenerateTaskPipeline:
    pipeline = object.__new__(AdvancedChatAppGenerateTaskPipeline)
    pipeline._workflow_run_id = "workflow-run-id"
    pipeline._workflow_id = "workflow-id"
    pipeline._application_generate_entity = MagicMock(task_id="task-id")
    pipeline._workflow_response_converter = MagicMock()
    pipeline._workflow_response_converter.workflow_finish_to_stream_response.return_value = workflow_finish_response
    pipeline._base_task_pipeline = MagicMock()
    return pipeline


def test_workflow_success_finalizes_message_before_exposing_finished_response() -> None:
    workflow_finish_response = StreamResponse(event=StreamEvent.WORKFLOW_FINISHED, task_id="task-id")
    message_end_response = MessageEndStreamResponse(task_id="task-id", id="message-id")
    runtime_state = MagicMock(spec=GraphRuntimeState)
    pipeline = _build_pipeline(workflow_finish_response)

    with (
        patch.object(pipeline, "_ensure_workflow_initialized"),
        patch.object(pipeline, "_ensure_graph_runtime_initialized", return_value=runtime_state),
        patch.object(
            pipeline,
            "_handle_advanced_chat_message_end_event",
            return_value=iter([message_end_response]),
        ) as finalize_message,
    ):
        responses = pipeline._handle_workflow_succeeded_event(QueueWorkflowSucceededEvent())
        first_response = next(responses)
        responses.close()

    assert first_response is message_end_response
    finalize_message.assert_called_once()
    assert isinstance(finalize_message.call_args.args[0], QueueAdvancedChatMessageEndEvent)
    assert finalize_message.call_args.kwargs == {"graph_runtime_state": runtime_state}


def test_workflow_partial_success_finalizes_message_before_exposing_finished_response() -> None:
    workflow_finish_response = StreamResponse(event=StreamEvent.WORKFLOW_FINISHED, task_id="task-id")
    message_end_response = MessageEndStreamResponse(task_id="task-id", id="message-id")
    runtime_state = MagicMock(spec=GraphRuntimeState)
    pipeline = _build_pipeline(workflow_finish_response)

    with (
        patch.object(pipeline, "_ensure_workflow_initialized"),
        patch.object(pipeline, "_ensure_graph_runtime_initialized", return_value=runtime_state),
        patch.object(
            pipeline,
            "_handle_advanced_chat_message_end_event",
            return_value=iter([message_end_response]),
        ) as finalize_message,
    ):
        responses = pipeline._handle_workflow_partial_success_event(
            QueueWorkflowPartialSuccessEvent(exceptions_count=1)
        )
        first_response = next(responses)
        responses.close()

    assert first_response is message_end_response
    finalize_message.assert_called_once()
    assert isinstance(finalize_message.call_args.args[0], QueueAdvancedChatMessageEndEvent)
    assert finalize_message.call_args.kwargs == {"graph_runtime_state": runtime_state}
