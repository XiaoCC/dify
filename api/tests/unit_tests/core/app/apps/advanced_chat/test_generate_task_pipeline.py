from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from core.app.apps.advanced_chat.generate_task_pipeline import AdvancedChatAppGenerateTaskPipeline
from core.app.entities.queue_entities import (
    QueueAdvancedChatMessageEndEvent,
    QueueWorkflowPartialSuccessEvent,
    QueueWorkflowSucceededEvent,
)
from core.app.entities.task_entities import MessageEndStreamResponse, StreamEvent, StreamResponse, WorkflowTaskState
from core.workflow.runtime import GraphRuntimeState


def _build_pipeline(workflow_finish_response: StreamResponse) -> AdvancedChatAppGenerateTaskPipeline:
    pipeline = object.__new__(AdvancedChatAppGenerateTaskPipeline)
    pipeline._workflow_run_id = "workflow-run-id"
    pipeline._workflow_id = "workflow-id"
    pipeline._message_id = "message-id"
    pipeline._task_state = WorkflowTaskState()
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
    answers_seen_while_finalizing: list[str] = []

    def finalize_message_side_effect(
        event: QueueAdvancedChatMessageEndEvent, *, graph_runtime_state: GraphRuntimeState
    ) -> Iterator[MessageEndStreamResponse]:
        _ = event, graph_runtime_state
        answers_seen_while_finalizing.append(pipeline._task_state.answer)
        return iter([message_end_response])

    with (
        patch.object(pipeline, "_ensure_workflow_initialized"),
        patch.object(pipeline, "_ensure_graph_runtime_initialized", return_value=runtime_state),
        patch.object(
            pipeline,
            "_handle_advanced_chat_message_end_event",
            side_effect=finalize_message_side_effect,
        ) as finalize_message,
    ):
        responses = list(
            pipeline._handle_workflow_partial_success_event(
                QueueWorkflowPartialSuccessEvent(
                    exceptions_count=1,
                    outputs={"answer": "partial answer from workflow output"},
                )
            )
        )

    assert answers_seen_while_finalizing == ["partial answer from workflow output"]
    assert responses == [message_end_response, workflow_finish_response]
    finalize_message.assert_called_once()
    assert isinstance(finalize_message.call_args.args[0], QueueAdvancedChatMessageEndEvent)
    assert finalize_message.call_args.kwargs == {"graph_runtime_state": runtime_state}
    pipeline._base_task_pipeline.queue_manager.stop_listen.assert_called_once_with()


def test_workflow_success_recovers_terminal_answer_before_finalizing_and_stops_listener() -> None:
    workflow_finish_response = StreamResponse(event=StreamEvent.WORKFLOW_FINISHED, task_id="task-id")
    message_end_response = MessageEndStreamResponse(task_id="task-id", id="message-id")
    runtime_state = MagicMock(spec=GraphRuntimeState)
    pipeline = _build_pipeline(workflow_finish_response)
    answers_seen_while_finalizing: list[str] = []

    def finalize_message(
        event: QueueAdvancedChatMessageEndEvent, *, graph_runtime_state: GraphRuntimeState
    ) -> Iterator[MessageEndStreamResponse]:
        _ = event, graph_runtime_state
        answers_seen_while_finalizing.append(pipeline._task_state.answer)
        return iter([message_end_response])

    with (
        patch.object(pipeline, "_ensure_workflow_initialized"),
        patch.object(pipeline, "_ensure_graph_runtime_initialized", return_value=runtime_state),
        patch.object(pipeline, "_handle_advanced_chat_message_end_event", side_effect=finalize_message),
    ):
        responses = list(
            pipeline._handle_workflow_succeeded_event(
                QueueWorkflowSucceededEvent(outputs={"answer": "answer from workflow output"})
            )
        )

    assert answers_seen_while_finalizing == ["answer from workflow output"]
    assert responses == [message_end_response, workflow_finish_response]
    pipeline._base_task_pipeline.queue_manager.stop_listen.assert_called_once_with()


def test_workflow_success_preserves_streamed_answer_when_terminal_output_differs() -> None:
    workflow_finish_response = StreamResponse(event=StreamEvent.WORKFLOW_FINISHED, task_id="task-id")
    message_end_response = MessageEndStreamResponse(task_id="task-id", id="message-id")
    runtime_state = MagicMock(spec=GraphRuntimeState)
    pipeline = _build_pipeline(workflow_finish_response)
    pipeline._task_state.answer = "answer accumulated from message chunks"
    answers_seen_while_finalizing: list[str] = []

    def finalize_message(
        event: QueueAdvancedChatMessageEndEvent, *, graph_runtime_state: GraphRuntimeState
    ) -> Iterator[MessageEndStreamResponse]:
        _ = event, graph_runtime_state
        answers_seen_while_finalizing.append(pipeline._task_state.answer)
        return iter([message_end_response])

    with (
        patch.object(pipeline, "_ensure_workflow_initialized"),
        patch.object(pipeline, "_ensure_graph_runtime_initialized", return_value=runtime_state),
        patch.object(pipeline, "_handle_advanced_chat_message_end_event", side_effect=finalize_message),
    ):
        responses = list(
            pipeline._handle_workflow_succeeded_event(
                QueueWorkflowSucceededEvent(outputs={"answer": "different terminal output"})
            )
        )

    assert answers_seen_while_finalizing == ["answer accumulated from message chunks"]
    assert responses == [message_end_response, workflow_finish_response]
