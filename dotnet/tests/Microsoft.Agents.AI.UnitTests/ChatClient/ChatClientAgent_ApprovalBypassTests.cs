// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains end-to-end tests for the human-in-the-loop approval boundary, run through a full
/// <see cref="ChatClientAgent"/> pipeline so that the assertion is on what actually executes rather than on what
/// a single decorator emits.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="FunctionInvokingChatClient"/> is all-or-nothing about approvals: when any tool in a response is an
/// <see cref="ApprovalRequiredAIFunction"/>, every function call in that batch is surfaced as a
/// <see cref="ToolApprovalRequestContent"/>. <see cref="ApprovalNotRequiredFunctionBypassingChatClient"/> removes
/// the ones that do not need approval and stores them for the next turn, which means an approval decision is made
/// against one turn's tools and applied on another.
/// </para>
/// <para>
/// Tool calls carry only a name, and the name is resolved against the tools available to the turn that runs them,
/// so these tests cover what happens when the tool behind a name stops being approval-free in between. Asserting
/// that the privileged implementation is never invoked is the point: a test that stops at the decorator boundary
/// and checks only which contents were emitted cannot distinguish a stored approval that is safely reused from one
/// that authorizes a tool no human was asked about.
/// </para>
/// </remarks>
public class ChatClientAgent_ApprovalBypassTests
{
    /// <summary>
    /// Verifies that an approval decision stored while a tool did not require approval does not authorize the tool
    /// that holds the same name on a later turn, once the application has gated it.
    /// </summary>
    [Fact]
    public async Task RunAsync_ToolBecomesApprovalRequiredBetweenTurns_DoesNotExecuteWithoutApprovalAsync()
    {
        // Arrange — turn 1 offers an ungated 'changingTool' alongside a gated 'humanGate', so the batch is
        // surfaced for approval and 'changingTool' is stored for automatic approval.
        var privilegedInvocations = 0;
        var callCount = 0;

        var chatClient = CreateChatClient((_, _, _) =>
        {
            callCount++;
            return callCount == 1
                ? Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant,
                    [
                        new FunctionCallContent("call1", "changingTool"),
                        new FunctionCallContent("call2", "humanGate")
                    ])]))
                : Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done.")]));
        });

        var humanGate = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "humanGate"));
        var ungatedChangingTool = AIFunctionFactory.Create(() => "harmless", "changingTool");
        var privilegedChangingTool = new ApprovalRequiredAIFunction(
            AIFunctionFactory.Create(() => { privilegedInvocations++; return "privileged"; }, "changingTool"));

        var agent = CreateAgent(chatClient);
        var session = await agent.CreateSessionAsync();

        var firstTurnOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [ungatedChangingTool, humanGate] });
        var secondTurnOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [privilegedChangingTool, humanGate] });

        // Act — turn 1: only the gated tool is surfaced to the human.
        var firstResponse = await agent.RunAsync("Do the thing", session, firstTurnOptions);
        var firstTurnRequests = GetApprovalRequests(firstResponse);

        // Act — turn 2: the application has replaced 'changingTool' with a gated, privileged implementation.
        // The caller rejects the only request it was ever shown and never approves 'changingTool'.
        var secondResponse = await agent.RunAsync(
            CreateApprovalResponses(firstTurnRequests, approved: false), session, secondTurnOptions);

        // Assert — turn 1 surfaced only the gated tool, as designed.
        Assert.Equal(["humanGate"], firstTurnRequests.Select(ToolName));

        // Assert — the privileged implementation never ran on authorization inherited from the ungated one. The
        // stored decision is answered with a rejection instead, so the failure is in the safe direction: at
        // worst the model has to ask again, which RunAsync_RejectedCallReissuedByModel_SurfacesNormalApprovalAsync
        // covers.
        Assert.Equal(0, privilegedInvocations);
        Assert.Empty(GetApprovalRequests(secondResponse));
    }

    /// <summary>
    /// Verifies that an unchanged tool set still bypasses approval as designed, so the fix for the changed case
    /// does not cost the behavior the decorator exists to provide.
    /// </summary>
    [Fact]
    public async Task RunAsync_ToolSetUnchanged_StillBypassesApprovalForApprovalFreeToolAsync()
    {
        // Arrange
        var approvalFreeInvocations = 0;
        var callCount = 0;

        var chatClient = CreateChatClient((_, _, _) =>
        {
            callCount++;
            return callCount == 1
                ? Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant,
                    [
                        new FunctionCallContent("call1", "freeTool"),
                        new FunctionCallContent("call2", "humanGate")
                    ])]))
                : Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done.")]));
        });

        var humanGate = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "humanGate"));
        var freeTool = AIFunctionFactory.Create(() => { approvalFreeInvocations++; return "free"; }, "freeTool");

        var agent = CreateAgent(chatClient);
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [freeTool, humanGate] });

        // Act
        var firstResponse = await agent.RunAsync("Do the thing", session, runOptions);
        var secondResponse = await agent.RunAsync(
            CreateApprovalResponses(GetApprovalRequests(firstResponse), approved: true), session, runOptions);

        // Assert — the approval-free tool ran without ever being surfaced, and nothing was re-surfaced.
        Assert.Equal(["humanGate"], GetApprovalRequests(firstResponse).Select(ToolName));
        Assert.Equal(1, approvalFreeInvocations);
        Assert.Empty(GetApprovalRequests(secondResponse));
    }

    /// <summary>
    /// Verifies that an approval-free tool sharing a name with a gated tool cannot cancel the gated tool's
    /// approval prompt, which is what lets tool metadata from an untrusted source drop a prompt the application
    /// configured. The collision is rejected rather than resolved, so the gated tool never runs.
    /// </summary>
    /// <remarks>
    /// The duplicate is supplied through <see cref="FunctionInvokingChatClient.AdditionalTools"/>, which the
    /// agent never sees when it composes the run's tool list. That is the reason the check lives in the
    /// decorator: it is the first point at which the full set of tools that can serve a call is known.
    /// </remarks>
    [Fact]
    public async Task RunAsync_ApprovalFreeToolSharesNameWithGatedTool_ThrowsAsync()
    {
        // Arrange
        var gatedInvocations = 0;

        var chatClient = CreateChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant,
                [new FunctionCallContent("call1", "deploy")])])));

        var gatedDeploy = new ApprovalRequiredAIFunction(
            AIFunctionFactory.Create(() => { gatedInvocations++; return "deployed"; }, "deploy"));
        var freeDeploy = AIFunctionFactory.Create(() => "free", "deploy");

        // The approval-free duplicate is only reachable through AdditionalTools, which never reaches the service.
        var pipeline = new FunctionInvokingChatClient(chatClient) { AdditionalTools = [freeDeploy] };

        var agent = new ChatClientAgent(
            pipeline,
            options: new ChatClientAgentOptions
            {
                ChatOptions = new ChatOptions { Tools = [gatedDeploy] },
                ChatHistoryProvider = new InMemoryChatHistoryProvider()
            },
            services: new ServiceCollection().BuildServiceProvider());

        var session = await agent.CreateSessionAsync();

        // Act & Assert — the ambiguous call is rejected and the gated tool does not run.
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync("Deploy it", session));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
        Assert.Equal(0, gatedInvocations);
    }

    /// <summary>
    /// Verifies the path that makes rejecting a stale decision acceptable: the model reissues the call, and
    /// because the tool now requires approval it is surfaced to the caller in the ordinary way and runs once the
    /// caller approves it. The approval still happens, it just arrives through the existing path rather than one
    /// the framework manufactures.
    /// </summary>
    [Fact]
    public async Task RunAsync_RejectedCallReissuedByModel_SurfacesNormalApprovalAsync()
    {
        // Arrange — the model reissues 'changingTool' after being told the first attempt was rejected.
        var privilegedInvocations = 0;
        var gateInvocations = 0;
        var callCount = 0;

        var chatClient = CreateChatClient((_, _, _) =>
        {
            callCount++;
            return callCount switch
            {
                1 => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant,
                    [
                        new FunctionCallContent("call1", "changingTool"),
                        new FunctionCallContent("call2", "humanGate")
                    ])])),
                2 => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant,
                    [new FunctionCallContent("call3", "changingTool")])])),
                _ => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done.")]))
            };
        });

        var humanGate = new ApprovalRequiredAIFunction(
            AIFunctionFactory.Create(() => { gateInvocations++; return "gated"; }, "humanGate"));
        var ungatedChangingTool = AIFunctionFactory.Create(() => "harmless", "changingTool");
        var privilegedChangingTool = new ApprovalRequiredAIFunction(
            AIFunctionFactory.Create(() => { privilegedInvocations++; return "privileged"; }, "changingTool"));

        var agent = CreateAgent(chatClient);
        var session = await agent.CreateSessionAsync();

        var firstTurnOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [ungatedChangingTool, humanGate] });
        var laterTurnOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [privilegedChangingTool, humanGate] });

        var firstResponse = await agent.RunAsync("Do the thing", session, firstTurnOptions);

        // The caller rejects 'humanGate', and the stored decision for 'changingTool' is rejected alongside it
        // because that tool is now gated. The model then issues the call again.
        var secondResponse = await agent.RunAsync(
            CreateApprovalResponses(GetApprovalRequests(firstResponse), approved: false), session, laterTurnOptions);

        // Assert — the reissued call is surfaced as an ordinary approval request.
        Assert.Equal(["changingTool"], GetApprovalRequests(secondResponse).Select(ToolName));
        Assert.Equal(0, privilegedInvocations);

        // Act — the caller approves it.
        var thirdResponse = await agent.RunAsync(
            CreateApprovalResponses(GetApprovalRequests(secondResponse), approved: true), session, laterTurnOptions);

        // Assert — the tool runs only once a human has actually approved it, and the earlier rejection stands.
        Assert.Equal(1, privilegedInvocations);
        Assert.Equal(0, gateInvocations);
        Assert.Equal("Done.", thirdResponse.Text);
    }

    #region Helpers

    private static string ToolName(ToolApprovalRequestContent request)
        => (request.ToolCall as FunctionCallContent)?.Name ?? "unknown";

    private static ChatClientAgent CreateAgent(IChatClient chatClient)
        => new(
            chatClient,
            options: new ChatClientAgentOptions
            {
                ChatHistoryProvider = new InMemoryChatHistoryProvider()
            },
            services: new ServiceCollection().BuildServiceProvider());

    private static List<ChatMessage> CreateApprovalResponses(List<ToolApprovalRequestContent> approvalRequests, bool approved)
        => approvalRequests.ConvertAll(request =>
            new ChatMessage(ChatRole.User, [request.CreateResponse(approved)]));

    private static List<ToolApprovalRequestContent> GetApprovalRequests(AgentResponse response)
        => response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();

    private static IChatClient CreateChatClient(
        Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>> onGetResponse)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns(onGetResponse);
        return mock.Object;
    }

    #endregion
}
