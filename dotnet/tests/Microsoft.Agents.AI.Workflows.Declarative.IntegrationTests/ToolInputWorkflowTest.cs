// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class ToolInputWorkflowTest(ITestOutputHelper output) : IntegrationTest(output)
{
    [Fact]
    public Task ValidateAutoInvoke() =>
        this.RunWorkflowAsync(autoInvoke: true, new MenuPlugin().GetTools());

    [Fact]
    public Task ValidateRequestInvoke() =>
        this.RunWorkflowAsync(autoInvoke: false, new MenuPlugin().GetTools());

    private static string GetWorkflowPath(string workflowFileName) => Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName);

    private async Task RunWorkflowAsync(bool autoInvoke, params IEnumerable<AIFunction> functionTools)
    {
        string workflowPath = GetWorkflowPath("FunctionTool.yaml");
        Dictionary<string, AIFunction> functionMap = autoInvoke ? [] : functionTools.ToDictionary(tool => tool.Name, tool => tool);
        DeclarativeWorkflowOptions workflowOptions = await this.CreateOptionsAsync(externalConversation: false, autoInvoke ? functionTools : []);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(workflowPath, workflowOptions);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync("hi!").ConfigureAwait(false);
        int requestCount = (workflowEvents.InputEvents.Count + 1) / 2;
        int responseCount = 0;
        while (requestCount > responseCount)
        {
            RequestInfoEvent inputEvent = workflowEvents.InputEvents[workflowEvents.InputEvents.Count - 1];
            AgentToolRequest? toolRequest = inputEvent.Request.Data.As<AgentToolRequest>();
            Assert.NotNull(toolRequest);

            List<FunctionResultContent> functionResults = [];
            foreach (FunctionCallContent functionCall in toolRequest.FunctionCalls)
            {
                this.Output.WriteLine($"TOOL REQUEST: {functionCall.Name}");
                Assert.False(autoInvoke);
                if (!functionMap.TryGetValue(functionCall.Name, out AIFunction? functionTool))
                {
                    Assert.Fail($"TOOL FAILURE [{functionCall.Name}] - MISSING");
                    return;
                }
                AIFunctionArguments functionArguments = new(functionCall.Arguments); // %%% PORTABLE
                if (functionArguments.Count > 0) // %%% HAXX
                {
                    functionArguments = new(new Dictionary<string, object?>() { { "menuItem", "Clam Chowder" } });
                }
                object? result = await functionTool.InvokeAsync(functionArguments);
                functionResults.Add(new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result))); // %%% FUNCTION: JSON CONVERSION
            }

            ++responseCount;

            WorkflowEvents runEvents = await harness.ResumeAsync(AgentToolResponse.Create(toolRequest, functionResults)).ConfigureAwait(false);
            workflowEvents = new WorkflowEvents([.. workflowEvents.Events, .. runEvents.Events]);
        }

        if (autoInvoke)
        {
            Assert.Empty(workflowEvents.InputEvents);
        }
        else
        {
            Assert.NotEmpty(workflowEvents.InputEvents);
        }
        // %%% TOOL: MORE VALIDATION
    }
}
