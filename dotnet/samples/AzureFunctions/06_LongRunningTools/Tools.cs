// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace LongRunningTools;

/// <summary>
/// Tools that demonstrate starting orchestrations from agent tool calls.
/// </summary>
internal sealed class Tools(ILogger<Tools> logger)
{
    private readonly ILogger<Tools> _logger = logger;

    [Description("Starts a content generation workflow and returns the instance ID for tracking.")]
    public string StartContentGenerationWorkflow([Description("The topic for content generation")] string topic)
    {
        this._logger.LogInformation("Starting content generation workflow for topic: {Topic}", topic);

        const int MaxReviewAttempts = 3;
        const float ApprovalTimeoutHours = 72;

        // Schedule the orchestration, which will start running after the tool call completes.
        string instanceId = DurableAgentContext.Current.ScheduleNewOrchestration(
            name: nameof(FunctionTriggers.RunOrchestrationAsync),
            input: new ContentGenerationInput
            {
                Topic = topic,
                MaxReviewAttempts = MaxReviewAttempts,
                ApprovalTimeoutHours = ApprovalTimeoutHours
            });

        this._logger.LogInformation(
            "Content generation workflow scheduled to be started for topic '{Topic}' with instance ID: {InstanceId}",
            topic,
            instanceId);

        return $"Workflow started with instance ID: {instanceId}";
    }

    [Description("Gets the status of a workflow orchestration.")]
    public async Task<object> GetWorkflowStatusAsync(
        [Description("The instance ID of the workflow to check")] string instanceId,
        [Description("Whether to include detailed information")] bool includeDetails = true)
    {
        this._logger.LogInformation("Getting status for workflow instance: {InstanceId}", instanceId);

        // Get the current agent context using the thread-static property
        OrchestrationMetadata? status = await DurableAgentContext.Current.GetOrchestrationStatusAsync(
            instanceId,
            includeDetails);

        if (status is null)
        {
            this._logger.LogInformation("Workflow instance '{InstanceId}' not found.", instanceId);
            return new
            {
                instanceId,
                error = $"Workflow instance '{instanceId}' not found.",
            };
        }

        return new
        {
            instanceId = status.InstanceId,
            createdAt = status.CreatedAt,
            executionStatus = status.RuntimeStatus,
            workflowStatus = status.SerializedCustomStatus,
            lastUpdatedAt = status.LastUpdatedAt,
            failureDetails = status.FailureDetails
        };
    }

    [Description("Raises a feedback event for the content generation workflow.")]
    public async Task SubmitHumanApprovalAsync(
        [Description("The instance ID of the workflow to submit feedback for")] string instanceId,
        [Description("Feedback to submit")] HumanApprovalResponse feedback)
    {
        this._logger.LogInformation("Submitting human approval for workflow instance: {InstanceId}", instanceId);
        await DurableAgentContext.Current.RaiseOrchestrationEventAsync(instanceId, "HumanApproval", feedback);
    }
}
