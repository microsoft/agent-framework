// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
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
        this.RunWorkflowAsync();

    [Fact]
    public Task ValidateRequestInvoke() =>
        this.RunWorkflowAsync(autoInvoke: false);

    private static string GetWorkflowPath(string workflowFileName) => Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName);

    private async Task RunWorkflowAsync(bool autoInvoke = true)
    {
        MenuPlugin menuTools = new();
        string workflowPath = GetWorkflowPath("FunctionTool.yaml");
        DeclarativeWorkflowOptions workflowOptions = await this.CreateOptionsAsync(); // %%% TOOL: OPTIONS WITH AIFUNCTION
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(workflowPath, workflowOptions);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync("hi!").ConfigureAwait(false);
        int requestCount = 0;
        while (workflowEvents.InputEvents.Count > requestCount)
        {
            RequestInfoEvent inputEvent = workflowEvents.InputEvents[workflowEvents.InputEvents.Count - 1];
            AgentToolRequest? toolRequest = inputEvent.Request.Data.As<AgentToolRequest>();
            Assert.NotNull(toolRequest);

            List<FunctionResultContent> functionResults = [];
            foreach (FunctionCallContent functionCall in toolRequest.FunctionCalls)
            {
                this.Output.WriteLine($"TOOL REQUEST: {functionCall.Name}");
                // %%% TOOL: INVOKE WHEN AUTOINVOKE FALSE
                Assert.False(autoInvoke);
                AIFunction menuTool = menuTools.GetTools().First();
                object? result = await menuTool.InvokeAsync(new AIFunctionArguments(functionCall.Arguments));
                functionResults.Add(new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result))); // %%% JSON CONVERSION
            }
            WorkflowEvents runEvents = await harness.ResumeAsync(AgentToolResponse.Create(toolRequest, functionResults)).ConfigureAwait(false);
            workflowEvents = new WorkflowEvents([.. workflowEvents.Events, .. runEvents.Events]);
            requestCount = workflowEvents.InputEvents.Count;
            if (requestCount > 0) // TOOL: HAXX
            {
                break;
            }
        }

        Assert.NotEmpty(workflowEvents.InputEvents);
        // %%% TOOL: MORE VALIDATION
    }
}
