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
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class FunctionCallingWorkflowTest(ITestOutputHelper output) : IntegrationTest(output)
{
    [Fact]
    public Task ValidateAutoInvokeAsync() =>
        this.RunWorkflowAsync(autoInvoke: true, new MenuPlugin().GetTools());

    [Fact]
    public Task ValidateRequestInvokeAsync() =>
        this.RunWorkflowAsync(autoInvoke: false, new MenuPlugin().GetTools());

    private static string GetWorkflowPath(string workflowFileName) => Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName);

    private async Task RunWorkflowAsync(bool autoInvoke, params IEnumerable<AIFunction> functionTools)
    {
        AgentProvider agentProvider = AgentProvider.Create(this.Configuration, AgentProvider.Names.FunctionTool);
        await agentProvider.CreateAgentsAsync().ConfigureAwait(false);

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
            Assert.False(autoInvoke);

            RequestInfoEvent inputEvent = workflowEvents.InputEvents[workflowEvents.InputEvents.Count - 1];
            ExternalInputRequest? toolRequest = inputEvent.Request.Data.As<ExternalInputRequest>();
            Assert.NotNull(toolRequest);

            List<(FunctionCallContent, AIFunction)> functionCalls = [];
            foreach (FunctionCallContent functionCall in toolRequest.AgentResponse.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>())
            {
                this.Output.WriteLine($"TOOL REQUEST: {functionCall.Name}");
                if (!functionMap.TryGetValue(functionCall.Name, out AIFunction? functionTool))
                {
                    Assert.Fail($"TOOL FAILURE [{functionCall.Name}] - MISSING");
                    return;
                }
                functionCalls.Add((functionCall, functionTool));
            }

            IList<AIContent> functionResults = await InvokeToolsAsync(functionCalls);

            ++responseCount;

            ChatMessage resultMessage = new(ChatRole.Tool, functionResults);
            WorkflowEvents runEvents = await harness.ResumeAsync(inputEvent.Request.CreateResponse(new ExternalInputResponse(resultMessage))).ConfigureAwait(false);
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

        Assert.Equal(autoInvoke ? 3 : 4, workflowEvents.AgentResponseEvents.Count);
        Assert.All(workflowEvents.AgentResponseEvents, response => response.Response.Text.Contains("4.95"));
    }

    private static async ValueTask<IList<AIContent>> InvokeToolsAsync(IEnumerable<(FunctionCallContent, AIFunction)> functionCalls)
    {
        List<AIContent> results = [];

        foreach ((FunctionCallContent functionCall, AIFunction functionTool) in functionCalls)
        {
            AIFunctionArguments? functionArguments = functionCall.Arguments is null ? null : new(functionCall.Arguments.NormalizePortableValues());
            object? result = await functionTool.InvokeAsync(functionArguments).ConfigureAwait(false);
            results.Add(new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result)));
        }

        return results;
    }
}
