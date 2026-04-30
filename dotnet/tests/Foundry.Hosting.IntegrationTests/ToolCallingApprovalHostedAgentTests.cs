// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests for the human in the loop tool approval flow: the container declares an AIFunction
/// flagged as requiring approval, and the model raises a <see cref="ToolApprovalRequestContent"/>
/// before the tool executes.
/// </summary>
public sealed class ToolCallingApprovalHostedAgentTests(ToolCallingApprovalHostedAgentFixture fixture)
    : IClassFixture<ToolCallingApprovalHostedAgentFixture>
{
    private readonly ToolCallingApprovalHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ApprovalRequiredTool_RaisesApprovalRequestAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Run the SendEmail tool with subject='hi' to test@example.com.");

        // Assert
        var approvalRequest = response.Messages
            .SelectMany(m => m.Contents.OfType<ToolApprovalRequestContent>())
            .FirstOrDefault();
        Assert.NotNull(approvalRequest);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ApprovalGranted_ToolRunsAndResponseReflectsResultAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();
        var first = await agent.RunAsync("Run the SendEmail tool with subject='ok' to test@example.com.", session);
        var approvalRequest = first.Messages
            .SelectMany(m => m.Contents.OfType<ToolApprovalRequestContent>())
            .First();

        var approvalResponse = approvalRequest.CreateResponse(approved: true);
        var followUp = new ChatMessage(ChatRole.User, [approvalResponse]);

        // Act
        var second = await agent.RunAsync([followUp], session);

        // Assert: model received the tool result and produced a final response.
        Assert.False(string.IsNullOrWhiteSpace(second.Text));
        var hasFurtherApprovalRequest = second.Messages
            .SelectMany(m => m.Contents.OfType<ToolApprovalRequestContent>())
            .Any();
        Assert.False(hasFurtherApprovalRequest, "Did not expect another approval request after granting.");
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ApprovalDenied_ToolDoesNotRunAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();
        var first = await agent.RunAsync("Run the SendEmail tool with subject='no' to test@example.com.", session);
        var approvalRequest = first.Messages
            .SelectMany(m => m.Contents.OfType<ToolApprovalRequestContent>())
            .First();

        var approvalResponse = approvalRequest.CreateResponse(approved: false);
        var followUp = new ChatMessage(ChatRole.User, [approvalResponse]);

        // Act
        var second = await agent.RunAsync([followUp], session);

        // Assert: no FunctionResultContent for SendEmail in the response.
        Assert.False(string.IsNullOrWhiteSpace(second.Text));
        var sendEmailResults = second.Messages
            .SelectMany(m => m.Contents.OfType<FunctionResultContent>())
            .Where(r => r.CallId == approvalRequest.ToolCall?.CallId);
        Assert.Empty(sendEmailResults);
    }
}
