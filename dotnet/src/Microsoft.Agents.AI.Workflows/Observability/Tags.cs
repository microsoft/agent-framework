// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Observability;

internal static class Tags
{
    public const string WorkflowId = "workflow.id";
    public const string WorkflowName = "workflow.name";
    public const string WorkflowDescription = "workflow.description";
    public const string WorkflowDefinition = "workflow.definition";
    public const string BuildErrorMessage = "build.error.message";
    public const string BuildErrorType = "build.error.type";
    public const string ErrorType = "error.type";
    public const string RunId = "run.id";
    public const string ExecutorId = "executor.id";
    public const string ExecutorType = "executor.type";
    public const string MessageType = "message.type";
    public const string EdgeGroupType = "edge_group.type";
    public const string MessageSourceId = "message.source_id";
    public const string MessageTargetId = "message.target_id";
    public const string EdgeGroupDelivered = "edge_group.delivered";
    public const string EdgeGroupDeliveryStatus = "edge_group.delivery_status";
}
