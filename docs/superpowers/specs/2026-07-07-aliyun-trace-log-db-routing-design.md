# Aliyun Trace Log Database Routing Design

## Problem

The Sanfu Dify fork can store `workflow_node_executions` exclusively in the
separate workflow log database. Aliyun tracing still constructs
`SQLAlchemyWorkflowNodeExecutionRepository` with the main `db.engine`, so it
cannot build LLM, retrieval, tool, or task spans after main-database writes are
disabled.

## Goal

Make Aliyun workflow tracing read node executions through Dify's configured
core repository factory so the existing Sanfu log-database routing, read
preference, and fallback behavior are respected.

## Design

`AliyunDataTrace.get_workflow_node_executions()` will create its repository via
`DifyCoreRepositoryFactory.create_workflow_node_execution_repository()` using
the existing service account, application ID, trigger source, and main session
factory arguments. The configured repository remains the official SQLAlchemy
implementation when the Sanfu override is disabled and becomes
`PgLogWorkflowNodeExecutionRepository` when the override is enabled.

The Aliyun provider must not import or instantiate the Sanfu repository
directly. This keeps the provider independent of deployment-specific storage
and preserves existing fallback semantics.

## Error Handling

Repository creation and reads retain their existing exception behavior. The
trace worker's existing failure handling records failed trace tasks; this
change does not introduce a provider-specific fallback path.

## Testing

Add a focused unit test for `get_workflow_node_executions()` that substitutes a
configured repository through `DifyCoreRepositoryFactory`, verifies the
factory receives the expected context, and verifies the method returns the
repository result. The test must fail against the current hard-coded main
database implementation and pass after the routing change.

## Scope

Only Aliyun workflow-node trace loading and its regression test are included.
Database schema, deployment flags, other tracing providers, and workflow-log
cleanup are unchanged.
