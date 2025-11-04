// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AzureStorage.Tests.Mock;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;
using ThreadStore = Microsoft.Agents.AI.Hosting.AgentThreadStore;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Tests;

internal sealed class TestRunner
{
    private int _requestCounter = 1;

    private readonly ITestOutputHelper _testOutputHelper;
    public AIHostAgent HostAgent { get; }
    public string ConversationId { get; }

    private TestRunner(ITestOutputHelper testOutputHelper, AIHostAgent hostAgent, string conversationId)
    {
        this._testOutputHelper = testOutputHelper;
        this.HostAgent = hostAgent;
        this.ConversationId = conversationId;
    }

    public static TestRunner Initialize(
        ITestOutputHelper testOutputHelper,
        ThreadStore threadStore,
        IChatClient? chatClient = null)
    {
        chatClient ??= new MockChatClient();

        var chatClientAgent = new ChatClientAgent(chatClient);
        var hostAgent = new AIHostAgent(chatClientAgent, threadStore);

        var conversationId = NewConversationId();

        return new(testOutputHelper, hostAgent, conversationId);
    }

    public Task<HostAgentRunResult> RunAgentAsync(string userMessage)
        => this.RunAgentAsync(new ChatMessage(ChatRole.User, userMessage));

    public async Task<HostAgentRunResult> RunAgentAsync(ChatMessage userMessage)
    {
        if (userMessage.Contents.FirstOrDefault() is TextContent text)
        {
            text.Text = $"Request #{this._requestCounter++}: {text.Text}";
        }

        AgentThread thread = await this.HostAgent.GetOrCreateThreadAsync(this.ConversationId);
        var response = await this.HostAgent.RunAsync(thread: thread, messages: [userMessage]);

        await this.HostAgent.SaveThreadAsync(this.ConversationId, thread);
        this._testOutputHelper.WriteLine($"Saved thread {this.ConversationId}");

        var chatClientAgentThread = thread as ChatClientAgentThread;
        Assert.NotNull(chatClientAgentThread);
        Assert.NotNull(chatClientAgentThread.MessageStore);

        var threadMessages = (await chatClientAgentThread.MessageStore.GetMessagesAsync()).ToList();

        return new()
        {
            Response = response,
            Thread = chatClientAgentThread,
            ThreadMessages = threadMessages
        };
    }

    private static string NewConversationId() => Guid.NewGuid().ToString();
}

internal struct HostAgentRunResult
{
    public AgentRunResponse Response { get; init; }
    public IList<ChatMessage> ResponseMessages => this.Response.Messages;

    public ChatClientAgentThread Thread { get; init; }
    public IList<ChatMessage> ThreadMessages { get; init; }
}
