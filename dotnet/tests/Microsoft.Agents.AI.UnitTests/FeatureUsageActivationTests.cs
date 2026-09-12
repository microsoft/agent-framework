// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

[Collection(nameof(FeatureUsageActivationTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests()
    {
        ResetFeatureUsage();
    }

    [Fact]
    public void Construction_DoesNotActivateCoreFeatures()
    {
        // Arrange
        var agent = new TestAIAgent { NameFunc = () => "worker" };

        // Act
        _ = new ChatClientAgent(new Mock<IChatClient>().Object, options: new() { ChatHistoryProvider = new NoOpChatHistoryProvider() });
        _ = new ToolApprovalAgent(agent);
        _ = new FileMemoryProvider(new InMemoryAgentFileStore());
        _ = new FileAccessProvider(new InMemoryAgentFileStore());
        _ = new TextSearchProvider((_, _) => Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]));
        _ = new AgentSkillsProvider(new StaticSkillsSource([]));
        _ = new CompactionProvider(new TruncationCompactionStrategy(_ => false));
        _ = new TodoProvider();
        _ = new AgentModeProvider();
        _ = new BackgroundAgentsProvider([agent]);
        _ = new AgentFileSkillsSource(Path.Combine(AppContext.BaseDirectory, $"missing-skills-{Guid.NewGuid():N}"), (_, _, _, _, _) => Task.FromResult<object?>(null));
        _ = new AgentInMemorySkillsSource([]);
        _ = new AgentInlineSkill("inline", "Inline skill.", "Instructions.");
        _ = new TestClassSkill();

        // Assert
        Assert.Null(GetFeatureToken());
    }

    [Fact]
    public async Task ChatClientAgent_NonStreamingExecution_ActivatesCoreAgentAsync()
    {
        // Arrange
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        var agent = new ChatClientAgent(chatClient.Object, options: new() { ChatHistoryProvider = new NoOpChatHistoryProvider() });
        Assert.Null(GetFeatureToken());

        // Act
        _ = await agent.RunAsync("hello");

        // Assert
        Assert.Equal("v1.1", GetFeatureToken());
    }

    [Fact]
    public async Task ChatClientAgent_StreamingExecution_IsColdUntilFirstEnumerationAsync()
    {
        // Arrange
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(EmptyChatResponseUpdatesAsync());
        var agent = new ChatClientAgent(chatClient.Object, options: new() { ChatHistoryProvider = new NoOpChatHistoryProvider() });

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream = agent.RunStreamingAsync("hello");

        // Assert
        Assert.Null(GetFeatureToken());
        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = stream.GetAsyncEnumerator();
        Assert.False(await enumerator.MoveNextAsync());
        Assert.Equal("v1.1", GetFeatureToken());
    }

    [Fact]
    public async Task ToolApprovalAgent_Execution_ActivatesOnlyToolApprovalAsync()
    {
        // Arrange
        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = (_, _, _, _) => Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]))
        };
        var agent = new ToolApprovalAgent(innerAgent);

        // Act
        _ = await agent.RunAsync("hello", new TestAgentSession());

        // Assert
        Assert.Equal("v1.8", GetFeatureToken());
    }

    [Fact]
    public async Task CoreProviders_ActivateTheirAssignedFeaturesAsync()
    {
        var agent = new TestAIAgent { NameFunc = () => "worker" };
        var session = new TestAgentSession();

        await VerifyActivationAsync(4, async () =>
        {
            Mock<VectorStoreCollection<object, Dictionary<string, object?>>> collection = new();
            Mock<VectorStore> store = new();
            store.Setup(value => value.GetDynamicCollection(
                It.IsAny<string>(),
                It.IsAny<VectorStoreCollectionDefinition>())).Returns(collection.Object);
            var provider = new ChatHistoryMemoryProvider(
                store.Object,
                "memory",
                1,
                _ => new ChatHistoryMemoryProvider.State(new ChatHistoryMemoryProviderScope { UserId = "user" }),
                new ChatHistoryMemoryProviderOptions { SearchTime = ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling });
            await provider.InvokingAsync(CreateContext(agent, session));
        });
        await VerifyActivationAsync(5, async () =>
            await new FileMemoryProvider(new InMemoryAgentFileStore()).InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(6, async () =>
            await new TextSearchProvider(
                (_, _) => Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]),
                new TextSearchProviderOptions { SearchTime = TextSearchProviderOptions.TextSearchBehavior.OnDemandFunctionCalling })
                .InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(7, async () =>
            await new FileAccessProvider(new InMemoryAgentFileStore()).InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(8, async () =>
            await new AgentSkillsProvider(new StaticSkillsSource([new StaticSkill()])).InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(9, async () =>
            await new CompactionProvider(new TruncationCompactionStrategy(_ => false))
                .InvokingAsync(CreateContext(agent, session, [new ChatMessage(ChatRole.User, "hello")])));
        await VerifyActivationAsync(10, async () =>
            await new TodoProvider().InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(11, async () =>
            await new AgentModeProvider().InvokingAsync(CreateContext(agent, session)));
        await VerifyActivationAsync(12, async () =>
            await new BackgroundAgentsProvider([agent]).InvokingAsync(CreateContext(agent, session)));
    }

    [Fact]
    public async Task SkillSourcesAndProgrammaticSkills_ActivateOnLoadOrUseAsync()
    {
        await VerifyActivationAsync(15, async () =>
        {
            var source = new AgentFileSkillsSource(
                Path.Combine(AppContext.BaseDirectory, $"missing-skills-{Guid.NewGuid():N}"),
                (_, _, _, _, _) => Task.FromResult<object?>(null));
            _ = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        });
        await VerifyActivationAsync(16, async () =>
        {
            var source = new AgentInMemorySkillsSource([new StaticSkill()]);
            _ = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        });
        await VerifyActivationAsync(17, async () =>
        {
            var skill = new AgentInlineSkill("inline", "Inline skill.", "Instructions.");
            _ = await skill.GetContentAsync();
        });
        await VerifyActivationAsync(18, async () =>
        {
            var skill = new TestClassSkill();
            _ = await skill.GetContentAsync();
        });
    }

    public void Dispose()
    {
        ResetFeatureUsage();
    }

    private static AIContextProvider.InvokingContext CreateContext(
        AIAgent agent,
        AgentSession session,
        IEnumerable<ChatMessage>? messages = null)
        => new(agent, session, new AIContext { Messages = messages });

    private static async Task VerifyActivationAsync(int index, Func<Task> action)
    {
        // Arrange
        ResetFeatureUsage();
        Assert.Null(GetFeatureToken());

        // Act
        await action();

        // Assert
        Assert.Equal($"v1.{1L << index:x}", GetFeatureToken());
    }

    private static string? GetFeatureToken()
        => (string?)typeof(FeatureUsage)
            .GetMethod("GetToken", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);

    private static void ResetFeatureUsage()
        => typeof(FeatureUsage)
            .GetMethod("ResetStateForTests", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);

    private static async IAsyncEnumerable<ChatResponseUpdate> EmptyChatResponseUpdatesAsync()
    {
        await Task.CompletedTask;
        yield break;
    }

    private sealed class NoOpChatHistoryProvider : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(
            InvokingContext context,
            CancellationToken cancellationToken = default)
            => new([]);

        protected override ValueTask StoreChatHistoryAsync(
            InvokedContext context,
            CancellationToken cancellationToken = default)
            => default;
    }

    private sealed class StaticSkillsSource(IList<AgentSkill> skills) : AgentSkillsSource
    {
        public override Task<IList<AgentSkill>> GetSkillsAsync(
            AgentSkillsSourceContext context,
            CancellationToken cancellationToken = default)
            => Task.FromResult(skills);
    }

    private sealed class StaticSkill : AgentSkill
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("static", "Static skill.");

        public override ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
            => new("content");
    }

    private sealed class TestClassSkill : AgentClassSkill<TestClassSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("class", "Class skill.");

        protected override string Instructions => "Instructions.";
    }

    private sealed class TestAgentSession : AgentSession;
}

[CollectionDefinition(nameof(FeatureUsageActivationTestGroup), DisableParallelization = true)]
public sealed class FeatureUsageActivationTestGroup;
