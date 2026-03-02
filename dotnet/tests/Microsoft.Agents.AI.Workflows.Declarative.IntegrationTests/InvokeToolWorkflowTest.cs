// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.Mcp;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Integration tests for InvokeFunctionTool and InvokeMcpTool actions.
/// </summary>
public sealed class InvokeToolWorkflowTest(ITestOutputHelper output) : IntegrationTest(output)
{
    #region InvokeFunctionTool Tests

    [Theory]
    [InlineData("InvokeFunctionTool.yaml", new string[] { "GetSpecials", "GetItemPrice" }, "2.95")]
    [InlineData("InvokeFunctionToolWithApproval.yaml", new string[] { "GetItemPrice" }, "4.9")]
    public Task ValidateInvokeFunctionToolAsync(string workflowFileName, string[] expectedFunctionCalls, string? expectedResultContains) =>
        this.RunInvokeFunctionToolTestAsync(workflowFileName, expectedFunctionCalls, expectedResultContains);

    #endregion

    #region InvokeMcpTool Tests

    [Theory]
    [InlineData("InvokeMcpTool.yaml", "Azure OpenAI")]
    public Task ValidateInvokeMcpToolAsync(string workflowFileName, string? expectedResultContains) =>
        this.RunInvokeMcpToolTestAsync(workflowFileName, expectedResultContains, requireApproval: false);

    [Theory]
    [InlineData("InvokeMcpToolWithApproval.yaml", "Azure OpenAI", true)]
    [InlineData("InvokeMcpToolWithApproval.yaml", "MCP tool invocation was not approved by user", false)]
    public Task ValidateInvokeMcpToolWithApprovalAsync(string workflowFileName, string? expectedResultContains, bool approveRequest) =>
        this.RunInvokeMcpToolTestAsync(workflowFileName, expectedResultContains, requireApproval: true, approveRequest: approveRequest);

    #endregion

    #region InvokeFunctionTool Test Helpers

    /// <summary>
    /// Runs an InvokeFunctionTool workflow test with the specified configuration.
    /// </summary>
    private async Task RunInvokeFunctionToolTestAsync(
        string workflowFileName,
        string[] expectedFunctionCalls,
        string? expectedResultContains = null)
    {
        // Arrange
        string workflowPath = GetWorkflowPath(workflowFileName);
        IEnumerable<AIFunction> functionTools = new MenuPlugin().GetTools();
        Dictionary<string, AIFunction> functionMap = functionTools.ToDictionary(tool => tool.Name, tool => tool);
        DeclarativeWorkflowOptions workflowOptions = await this.CreateOptionsAsync(externalConversation: false);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(workflowPath, workflowOptions);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));
        List<string> invokedFunctions = [];

        // Act - Run workflow and handle function invocations
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync("start").ConfigureAwait(false);

        while (workflowEvents.InputEvents.Count > 0)
        {
            RequestInfoEvent inputEvent = workflowEvents.InputEvents[^1];
            ExternalInputRequest? toolRequest = inputEvent.Request.Data.As<ExternalInputRequest>();
            Assert.NotNull(toolRequest);

            IList<AIContent> functionResults = await this.ProcessFunctionCallsAsync(
                toolRequest,
                functionMap,
                invokedFunctions).ConfigureAwait(false);

            ChatMessage resultMessage = new(ChatRole.Tool, functionResults);
            WorkflowEvents resumeEvents = await harness.ResumeAsync(
                inputEvent.Request.CreateResponse(new ExternalInputResponse(resultMessage))).ConfigureAwait(false);

            workflowEvents = new WorkflowEvents([.. workflowEvents.Events, .. resumeEvents.Events]);

            // Continue processing until there are no more pending input events from the resumed workflow
            if (resumeEvents.InputEvents.Count == 0)
            {
                break;
            }
        }

        // Assert - Verify function calls were made in expected order
        Assert.Equal(expectedFunctionCalls.Length, invokedFunctions.Count);
        for (int i = 0; i < expectedFunctionCalls.Length; i++)
        {
            Assert.Equal(expectedFunctionCalls[i], invokedFunctions[i]);
        }

        // Assert - Verify executor and action events
        AssertWorkflowEventsEmitted(workflowEvents);

        // Assert - Verify expected result if specified
        if (expectedResultContains is not null)
        {
            AssertResultContains(workflowEvents, expectedResultContains);
        }
    }

    /// <summary>
    /// Processes function calls from an external input request.
    /// Handles both regular function calls and approval requests.
    /// </summary>
    private async Task<IList<AIContent>> ProcessFunctionCallsAsync(
        ExternalInputRequest toolRequest,
        Dictionary<string, AIFunction> functionMap,
        List<string> invokedFunctions)
    {
        List<AIContent> results = [];

        foreach (ChatMessage message in toolRequest.AgentResponse.Messages)
        {
            // Handle approval requests if present
            foreach (FunctionApprovalRequestContent approvalRequest in message.Contents.OfType<FunctionApprovalRequestContent>())
            {
                this.Output.WriteLine($"APPROVAL REQUEST: {approvalRequest.FunctionCall.Name}");
                // Auto-approve for testing
                results.Add(approvalRequest.CreateResponse(approved: true));
            }

            // Handle function calls
            foreach (FunctionCallContent functionCall in message.Contents.OfType<FunctionCallContent>())
            {
                this.Output.WriteLine($"FUNCTION CALL: {functionCall.Name}");

                if (!functionMap.TryGetValue(functionCall.Name, out AIFunction? functionTool))
                {
                    Assert.Fail($"Function not found: {functionCall.Name}");
                    continue;
                }

                invokedFunctions.Add(functionCall.Name);

                // Execute the function
                AIFunctionArguments? functionArguments = functionCall.Arguments is null
                    ? null
                    : new(functionCall.Arguments.NormalizePortableValues());

                object? result = await functionTool.InvokeAsync(functionArguments).ConfigureAwait(false);
                results.Add(new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result)));

                this.Output.WriteLine($"FUNCTION RESULT: {JsonSerializer.Serialize(result)}");
            }
        }

        return results;
    }

    #endregion

    #region InvokeMcpTool Test Helpers

    /// <summary>
    /// Runs an InvokeMcpTool workflow test with the specified configuration.
    /// </summary>
    private async Task RunInvokeMcpToolTestAsync(
        string workflowFileName,
        string? expectedResultContains = null,
        bool requireApproval = false,
        bool approveRequest = true)
    {
        // Arrange
        string workflowPath = GetWorkflowPath(workflowFileName);
        DefaultMcpToolHandler mcpToolProvider = new();
        DeclarativeWorkflowOptions workflowOptions = await this.CreateOptionsAsync(
            externalConversation: false,
            mcpToolProvider: mcpToolProvider);

        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(workflowPath, workflowOptions);
        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));

        // Act - Run workflow and handle MCP tool invocations
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync("start").ConfigureAwait(false);

        while (workflowEvents.InputEvents.Count > 0)
        {
            RequestInfoEvent inputEvent = workflowEvents.InputEvents[^1];
            ExternalInputRequest? toolRequest = inputEvent.Request.Data.As<ExternalInputRequest>();
            Assert.NotNull(toolRequest);

            IList<AIContent> mcpResults = this.ProcessMcpToolRequests(
                toolRequest,
                approveRequest);

            ChatMessage resultMessage = new(ChatRole.Tool, mcpResults);
            WorkflowEvents resumeEvents = await harness.ResumeAsync(
                inputEvent.Request.CreateResponse(new ExternalInputResponse(resultMessage))).ConfigureAwait(false);

            workflowEvents = new WorkflowEvents([.. workflowEvents.Events, .. resumeEvents.Events]);

            // Continue processing until there are no more pending input events from the resumed workflow
            if (resumeEvents.InputEvents.Count == 0)
            {
                break;
            }
        }

        // Assert - Verify executor and action events
        AssertWorkflowEventsEmitted(workflowEvents);

        // Assert - Verify expected result if specified
        if (expectedResultContains is not null)
        {
            AssertResultContains(workflowEvents, expectedResultContains);
        }

        // Cleanup
        await mcpToolProvider.DisposeAsync().ConfigureAwait(false);
    }

    /// <summary>
    /// Processes MCP tool requests from an external input request.
    /// Handles approval requests for MCP tools.
    /// </summary>
    private List<AIContent> ProcessMcpToolRequests(
        ExternalInputRequest toolRequest,
        bool approveRequest)
    {
        List<AIContent> results = [];

        foreach (ChatMessage message in toolRequest.AgentResponse.Messages)
        {
            // Handle MCP approval requests if present
            foreach (McpServerToolApprovalRequestContent approvalRequest in message.Contents.OfType<McpServerToolApprovalRequestContent>())
            {
                this.Output.WriteLine($"MCP APPROVAL REQUEST: {approvalRequest.Id}");

                // Respond based on test configuration
                McpServerToolApprovalResponseContent response = approvalRequest.CreateResponse(approved: approveRequest);
                results.Add(response);

                this.Output.WriteLine($"MCP APPROVAL RESPONSE: {(approveRequest ? "Approved" : "Rejected")}");
            }
        }

        return results;
    }

    #endregion

    #region Shared Helpers

    private static void AssertWorkflowEventsEmitted(WorkflowEvents workflowEvents)
    {
        Assert.NotEmpty(workflowEvents.ExecutorInvokeEvents);
        Assert.NotEmpty(workflowEvents.ExecutorCompleteEvents);
        Assert.NotEmpty(workflowEvents.ActionInvokeEvents);
    }

    private static void AssertResultContains(WorkflowEvents workflowEvents, string expectedResultContains)
    {
        MessageActivityEvent? messageEvent = workflowEvents.Events
            .OfType<MessageActivityEvent>()
            .LastOrDefault();

        Assert.NotNull(messageEvent);
        Assert.Contains(expectedResultContains, messageEvent.Message, StringComparison.OrdinalIgnoreCase);
    }

    private static string GetWorkflowPath(string workflowFileName) =>
        Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName);

    #endregion
}
