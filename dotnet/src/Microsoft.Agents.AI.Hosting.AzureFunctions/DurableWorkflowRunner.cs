// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal sealed class DurableWorkflowRunner
{
    private readonly DurableWorkflowOptions _options;
    private readonly ILogger<DurableWorkflowRunner> _logger;

    public DurableWorkflowRunner(ILogger<DurableWorkflowRunner> logger, DurableOptions durableOptions)
    {
        this._logger = logger;
        ArgumentNullException.ThrowIfNull(durableOptions);
        this._options = durableOptions.Workflows;
    }

    internal async Task<List<string>> RunWorkflowOrchestrationAsync(TaskOrchestrationContext taskOrchestrationContext, DuableWorkflowRunRequest input, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(taskOrchestrationContext);
        ArgumentNullException.ThrowIfNull(input);

        string workflowName = input.WorkflowName;

        logger.LogAttemptingToRunWorkflow(workflowName);

        if (!this._options.Workflows.TryGetValue(workflowName, out Workflow? wf))
        {
            throw new InvalidOperationException($"Workflow '{workflowName}' not found.");
        }

        logger.LogRunningWorkflow(wf.Name);

        var result = await this.RunExecutorsInWorkFlowAsync(taskOrchestrationContext, wf, input.Input, logger);

        return [result];
    }

    private async Task<string> RunExecutorsInWorkFlowAsync(
        TaskOrchestrationContext taskOrchestrationContext,
        Workflow workflow,
        string initialInput,
        ILogger logger)
    {
        List<string> executorResult = [];

        if (logger.IsEnabled(LogLevel.Information))
        {
            foreach (WorkflowExecutorInfo executorInfo in WorkflowHelper.GetExecutorsFromWorkflowInOrder(workflow))
            {
                string triggerName = this.BuildTriggerName(workflow.Name!, executorInfo.ExecutorId);
                logger.LogInformation(
                    "  Scheduling executor '{ExecutorId}' (IsAgentic: {IsAgentic}) with trigger name '{TriggerName}'",
                    executorInfo.ExecutorId,
                    executorInfo.IsAgenticExecutor,
                    triggerName);

                string input = executorResult.Count == 0 ? initialInput : executorResult.Last()!;
                if (!executorInfo.IsAgenticExecutor)
                {
                    var result = await taskOrchestrationContext.CallActivityAsync<string>(triggerName, input);
                    executorResult.Add(result);
                }
                else
                {
                    string AgentName = this.GetAgentNameFromExecutorId(workflow.Name!, executorInfo.ExecutorId);
                    logger.LogInformation(
                        "  Invoking agentic executor '{ExecutorId}'",
                        AgentName);
                    DurableAIAgent agent = taskOrchestrationContext.GetAgent(AgentName);
                    if (agent != null)
                    {
                        AgentThread destinationThread = agent.GetNewThread();
                        var agentResponse = await agent.RunAsync(input, destinationThread);
                        executorResult.Add(agentResponse.Text);
                        logger.LogInformation(
                            "Agentic executor '{ExecutorId}' completed with response: {AgentResponse}",
                            AgentName,
                            agentResponse);
                    }
                }
            }

            // return final result
            return executorResult.Last();
        }

        return string.Empty;
    }

    private string GetAgentNameFromExecutorId(string workflowName, string executorId)
    {
        // Example: "InspirationBot_edaac621050849efb1a62805fa03d3f8"
        var parts = executorId.Split('_');
        return parts.Length > 0 ? parts[0] : executorId;
    }

    private string BuildTriggerName(string workflowName, string executorName)
    {
        return $"dafx-{workflowName}-{executorName}";
    }

    internal async Task<string> ExecuteActivityAsync(string activityFunctionName, string input, FunctionContext functionContext)
    {
        ArgumentNullException.ThrowIfNull(activityFunctionName);
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(functionContext);

        // Parse the activity function name to extract workflow name and executor name
        // Format: "dafx-{workflowName}-{executorName}"
        if (!activityFunctionName.StartsWith("dafx-", StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Activity function name '{activityFunctionName}' does not start with 'dafx-' prefix.");
        }

        string nameWithoutPrefix = activityFunctionName["dafx-".Length..];
        string[] parts = nameWithoutPrefix.Split('-', 2);

        if (parts.Length != 2)
        {
            throw new InvalidOperationException($"Activity function name '{activityFunctionName}' is not in the expected format 'dafx-{{workflowName}}-{{executorName}}'.");
        }

        string workflowName = parts[0];
        string executorName = parts[1];

        this._logger.LogAttemptingToExecuteActivity(workflowName, executorName);

        // Get the workflow
        if (!this._options.Workflows.TryGetValue(workflowName, out Workflow? workflow))
        {
            throw new InvalidOperationException($"Workflow '{workflowName}' not found.");
        }

        // Get the executor info
        Dictionary<string, ExecutorInfo> executorInfos = workflow.ReflectExecutors();

        // Find the executor by matching the executor name (which may have a GUID suffix)
        KeyValuePair<string, ExecutorInfo> executorPair = executorInfos.FirstOrDefault(e =>
            e.Key.StartsWith(executorName + "_", StringComparison.Ordinal) ||
            string.Equals(e.Key, executorName, StringComparison.Ordinal));

        if (executorPair.Key == null)
        {
            throw new InvalidOperationException($"Executor '{executorName}' not found in workflow '{workflowName}'.");
        }

        this._logger.LogExecutingActivity(executorPair.Key, executorPair.Value.ExecutorType.TypeName);

        // Attempt to invoke the executor using Executor.ExecuteAsync
        // This allows the executor to handle its own execution logic
        try
        {
            // Create the executor instance
            Executor executor = await workflow.CreateExecutorInstanceAsync(
                executorPair.Key,
                "activity-run",
                CancellationToken.None).ConfigureAwait(false);

            // Create a minimal workflow taskOrchestrationContext for the executor
            MinimalActivityContext context = new(executorPair.Key);

            // Execute the executor with the input
            // The executor handles its own routing logic internally
            object? result = await executor.ExecuteAsync(
                input,
                new TypeId(typeof(string)),
                context,
                CancellationToken.None).ConfigureAwait(false);

            // Convert result to string
            string resultString = result?.ToString() ?? string.Empty;

            this._logger.LogActivityExecuted(executorPair.Key, resultString);
            return resultString;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error executing executor '{ExecutorId}' in activity", executorPair.Key);
            throw;
        }
    }
}
