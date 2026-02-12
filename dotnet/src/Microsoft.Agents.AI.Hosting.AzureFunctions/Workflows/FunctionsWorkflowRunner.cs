// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.Workflows;

/// <summary>
/// Provides functionality to invoke and manage workflow orchestrations in response to HTTP requests within an Azure
/// Functions environment.
/// </summary>
public sealed class FunctionsWorkflowRunner : DurableWorkflowRunner
{
    /// <summary>
    /// Initializes a new instance of the FunctionsWorkflowRunner class using the specified DurableOptions.
    /// </summary>
    /// <param name="durableOptions">The DurableOptions that configure the behavior of the workflow runner. This parameter cannot be null.</param>
    public FunctionsWorkflowRunner(DurableOptions durableOptions) : base(durableOptions)
    {
    }

    /// <summary>
    /// Invokes a workflow orchestration in response to an HTTP request.
    /// </summary>
    public static async Task<HttpResponseData> RunWorkflowOrechstrtationHttpTriggerAsync(
        [HttpTrigger] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext context)
    {
        var functionName = context.FunctionDefinition.Name;
        var workflowName = functionName.Replace("-http", string.Empty);
        var orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);
        var inputMessage = await req.ReadAsStringAsync();
        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(orchestrationFunctionName, inputMessage);

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteStringAsync($"InvokeWorkflowOrechstrtationAsync is invoked for {workflowName}. Orchestration instanceId: {instanceId}");
        return response;
    }

    internal async Task<string> ExecuteActivityAsync(string activityFunctionName, string input, DurableTaskClient durableTaskClient, FunctionContext functionContext)
    {
        throw new NotImplementedException();
    }
}
