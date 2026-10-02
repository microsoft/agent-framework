// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.Server;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

public sealed class ForwardedPropertiesTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task Context_IsIncludedInModelMessagesAsUntrustedUserContextAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-context",
                "runId": "run-context",
                "messages": [{ "id": "msg-1", "role": "user", "content": "Generate topics" }],
                "context": [{ "description": "Writing intent", "value": "AI agents for writers" }]
            }
            """;
        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.NotNull(fakeAgent.ReceivedMessages);
        Assert.Equal("Generate topics", fakeAgent.ReceivedMessages[0].Text);
        Assert.Equal(ChatRole.User, fakeAgent.ReceivedMessages[1].Role);
        Assert.Contains("Writing intent", fakeAgent.ReceivedMessages[1].Text);
        Assert.Contains("AI agents for writers", fakeAgent.ReceivedMessages[1].Text);
    }

    [Fact]
    public async Task Context_WithMultipleItems_PreservesEachItemAndOrderAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        const string RequestJson = """
            {
                "threadId": "session-multiple-context",
                "runId": "run-multiple-context",
                "messages": [{ "id": "msg-1", "role": "user", "content": "Plan a trip" }],
                "context": [
                    { "description": "Destination", "value": "Kyoto" },
                    { "description": "Duration", "value": "3 days" }
                ]
            }
            """;
        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.NotNull(fakeAgent.ReceivedMessages);
        Assert.Equal("Plan a trip", fakeAgent.ReceivedMessages[0].Text);
        ChatMessage contextMessage = fakeAgent.ReceivedMessages[1];
        Assert.Equal(ChatRole.User, contextMessage.Role);
        Assert.Contains("Destination", contextMessage.Text);
        Assert.Contains("Kyoto", contextMessage.Text);
        Assert.Contains("Duration", contextMessage.Text);
        Assert.Contains("3 days", contextMessage.Text);
        Assert.True(contextMessage.Text.IndexOf("Destination", StringComparison.Ordinal) <
            contextMessage.Text.IndexOf("Duration", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Context_WithEmptySpecialAndUnicodeValues_PreservesValuesAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        const string RequestJson = """
            {
                "threadId": "session-context-boundaries",
                "runId": "run-context-boundaries",
                "messages": [{ "id": "msg-1", "role": "user", "content": "Check context" }],
                "context": [
                    { "description": "", "value": "" },
                    { "description": "line\nbreak: colon", "value": "第一行\n第二行: 中文 😀 \"quoted\"" },
                    { "description": "Unicode Ω", "value": "こんにちは — café" }
                ]
            }
            """;
        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.NotNull(fakeAgent.ReceivedMessages);
        string contextText = fakeAgent.ReceivedMessages[^1].Text;
        string[] serializedItems = contextText[(contextText.IndexOf('\n') + 1)..].Split('\n');
        using JsonDocument firstContextDocument = JsonDocument.Parse(serializedItems[0]);
        using JsonDocument secondContextDocument = JsonDocument.Parse(serializedItems[1]);
        using JsonDocument thirdContextDocument = JsonDocument.Parse(serializedItems[2]);
        JsonElement firstContext = firstContextDocument.RootElement;
        JsonElement secondContext = secondContextDocument.RootElement;
        JsonElement thirdContext = thirdContextDocument.RootElement;
        Assert.Equal(string.Empty, firstContext.GetProperty("description").GetString());
        Assert.Equal(string.Empty, firstContext.GetProperty("value").GetString());
        Assert.Equal("line\nbreak: colon", secondContext.GetProperty("description").GetString());
        Assert.Equal("第一行\n第二行: 中文 😀 \"quoted\"", secondContext.GetProperty("value").GetString());
        Assert.Equal("Unicode Ω", thirdContext.GetProperty("description").GetString());
        Assert.Equal("こんにちは — café", thirdContext.GetProperty("value").GetString());
    }

    [Fact]
    public async Task EmptyContext_DoesNotAddAnExtraMessageAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        const string RequestJson = """
            {
                "threadId": "session-empty-context",
                "runId": "run-empty-context",
                "messages": [{ "id": "msg-1", "role": "user", "content": "Hello" }],
                "context": []
            }
            """;
        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.NotNull(fakeAgent.ReceivedMessages);
        ChatMessage onlyMessage = Assert.Single(fakeAgent.ReceivedMessages);
        Assert.Equal("Hello", onlyMessage.Text);
        Assert.Null(fakeAgent.ReceivedInstructions);
    }

    [Fact]
    public async Task Context_IsInjectedOncePerRequestWhenResentAcrossTurnsAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        const string FirstRequestJson = """
            {
                "threadId": "session-context-turns",
                "runId": "run-1",
                "messages": [{ "id": "msg-1", "role": "user", "content": "First turn" }],
                "context": [{ "description": "Preference", "value": "quiet hotels" }]
            }
            """;
        using StringContent firstContent = new(FirstRequestJson, Encoding.UTF8, "application/json");

        // Act - the client sends the same context again on a continuation request.
        HttpResponseMessage firstResponse = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), firstContent);
        const string SecondRequestJson = """
            {
                "threadId": "session-context-turns",
                "runId": "run-2",
                "parentRunId": "run-1",
                "messages": [
                    { "id": "msg-1", "role": "user", "content": "First turn" },
                    { "id": "context-1", "role": "user", "content": "AG-UI context (client-provided data):\n{\"description\":\"Preference\",\"value\":\"quiet hotels\"}" },
                    { "id": "assistant-1", "role": "assistant", "content": "First response" },
                    { "id": "msg-2", "role": "user", "content": "Second turn" }
                ],
                "context": [{ "description": "Preference", "value": "quiet hotels" }]
            }
            """;
        using StringContent secondContent = new(SecondRequestJson, Encoding.UTF8, "application/json");
        HttpResponseMessage secondResponse = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), secondContent);

        // Assert - each request contains one injected context message, not duplicate copies within that request.
        Assert.True(firstResponse.IsSuccessStatusCode);
        Assert.True(secondResponse.IsSuccessStatusCode);
        Assert.Equal(1, fakeAgent.ReceivedRuns[0].Count(message => message.Text.Contains("Preference", StringComparison.Ordinal)));
        Assert.Single(fakeAgent.ReceivedRuns[1], message =>
            message.GetAgentRequestMessageSourceType() == new AgentRequestMessageSourceType("AGUIContext"));
        Assert.Single(fakeAgent.ReceivedRuns[1], message => message.Text.Contains("Second turn", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Context_RevertedToOlderValue_IsAppendedAfterMostRecentGeneratedContextAsync()
    {
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string Run1 = """
            {"threadId":"context-revert","runId":"run-1","messages":[{"id":"msg-1","role":"user","content":"First"}],"context":[{"description":"Preference","value":"A"}]}
            """;
        using (HttpResponseMessage run1Response = await this.PostRunAsync(Run1))
        {
            Assert.True(run1Response.IsSuccessStatusCode);
        }

        const string Run2 = """
            {"threadId":"context-revert","runId":"run-2","parentRunId":"run-1","messages":[{"id":"msg-1","role":"user","content":"First"},{"id":"context-a","role":"user","content":"AG-UI context (client-provided data):\n{\"description\":\"Preference\",\"value\":\"A\"}"},{"id":"assistant-1","role":"assistant","content":"Response A"}],"context":[{"description":"Preference","value":"B"}]}
            """;
        using (HttpResponseMessage run2Response = await this.PostRunAsync(Run2))
        {
            Assert.True(run2Response.IsSuccessStatusCode);
        }

        const string Run3 = """
            {"threadId":"context-revert","runId":"run-3","parentRunId":"run-2","messages":[{"id":"msg-1","role":"user","content":"First"},{"id":"context-a","role":"user","content":"AG-UI context (client-provided data):\n{\"description\":\"Preference\",\"value\":\"A\"}"},{"id":"assistant-1","role":"assistant","content":"Response A"},{"id":"context-b","role":"user","content":"AG-UI context (client-provided data):\n{\"description\":\"Preference\",\"value\":\"B\"}"},{"id":"assistant-2","role":"assistant","content":"Response B"}],"context":[{"description":"Preference","value":"A"}]}
            """;
        using HttpResponseMessage response = await this.PostRunAsync(Run3);

        Assert.True(response.IsSuccessStatusCode);
        ChatMessage newestGenerated = Assert.Single(fakeAgent.ReceivedRuns[2], m => IsAGUIContextMessage(m));
        Assert.Contains("\"value\":\"A\"", newestGenerated.Text, StringComparison.Ordinal);
        Assert.DoesNotContain("\"value\":\"B\"", newestGenerated.Text, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Context_OrdinaryUserMessageWithSameText_DoesNotSuppressInjectionAsync()
    {
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        const string Request = """
            {"threadId":"context-user-collision","runId":"run-1","messages":[{"id":"ordinary-user","role":"user","content":"AG-UI context (client-provided data):\n{\"description\":\"Preference\",\"value\":\"A\"}"}],"context":[{"description":"Preference","value":"A"}]}
            """;
        using HttpResponseMessage response = await this.PostRunAsync(Request);

        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(2, fakeAgent.ReceivedRuns[0].Count(m => m.Text.Contains("\"value\":\"A\"", StringComparison.Ordinal)));
        Assert.Single(fakeAgent.ReceivedRuns[0], m => IsAGUIContextMessage(m));
    }

    private async Task<HttpResponseMessage> PostRunAsync(string requestJson)
    {
        using StringContent content = new(requestJson, Encoding.UTF8, "application/json");
        return await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);
    }

    private static bool IsAGUIContextMessage(ChatMessage message) =>
        message.GetAgentRequestMessageSourceType() == new AgentRequestMessageSourceType("AGUIContext");

    [Fact]
    public async Task ChatClient_ForwardsContextAndForwardedPropsFromRawRepresentationFactoryAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(new(this._client!, "/agent"));
        JsonElement forwardedProperties = JsonSerializer.SerializeToElement(new { tenantId = "tenant-123" });
        ChatOptions options = new()
        {
            RawRepresentationFactory = _ => new RunAgentInput
            {
                Context = [new AGUIContext { Description = "Current user", Value = "Ada Lovelace" }],
                ForwardedProperties = forwardedProperties,
            },
        };

        await foreach (ChatResponseUpdate _ in chatClient.GetStreamingResponseAsync(
            [new ChatMessage(ChatRole.User, "test client forwarding")], options))
        {
        }

        Assert.Single(fakeAgent.ReceivedContext ?? []);
        Assert.Equal("Current user", fakeAgent.ReceivedContext![0].Description);
        Assert.Equal("Ada Lovelace", fakeAgent.ReceivedContext[0].Value);
        Assert.Equal("tenant-123", fakeAgent.ReceivedForwardedProperties.GetProperty("tenantId").GetString());
    }

    [Fact]
    public async Task ForwardedProps_AreParsedAndPassedToAgent_WhenProvidedInRequestAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        // Create request JSON with forwardedProps (per AG-UI protocol spec)
        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test forwarded props" }],
                "forwardedProps": { "customProp": "customValue", "sessionId": "test-session-123" }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(JsonValueKind.Object, fakeAgent.ReceivedForwardedProperties.ValueKind);
        Assert.Equal("customValue", fakeAgent.ReceivedForwardedProperties.GetProperty("customProp").GetString());
        Assert.Equal("test-session-123", fakeAgent.ReceivedForwardedProperties.GetProperty("sessionId").GetString());
    }

    [Fact]
    public async Task ForwardedProps_WithNestedObjects_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test nested props" }],
                "forwardedProps": {
                    "user": { "id": "user-1", "name": "Test User" },
                    "metadata": { "version": "1.0", "feature": "test" }
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(JsonValueKind.Object, fakeAgent.ReceivedForwardedProperties.ValueKind);

        JsonElement user = fakeAgent.ReceivedForwardedProperties.GetProperty("user");
        Assert.Equal("user-1", user.GetProperty("id").GetString());
        Assert.Equal("Test User", user.GetProperty("name").GetString());

        JsonElement metadata = fakeAgent.ReceivedForwardedProperties.GetProperty("metadata");
        Assert.Equal("1.0", metadata.GetProperty("version").GetString());
        Assert.Equal("test", metadata.GetProperty("feature").GetString());
    }

    [Fact]
    public async Task ForwardedProps_WithArrays_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test array props" }],
                "forwardedProps": {
                    "tags": ["tag1", "tag2", "tag3"],
                    "scores": [1, 2, 3, 4, 5]
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(JsonValueKind.Object, fakeAgent.ReceivedForwardedProperties.ValueKind);

        JsonElement tags = fakeAgent.ReceivedForwardedProperties.GetProperty("tags");
        Assert.Equal(3, tags.GetArrayLength());
        Assert.Equal("tag1", tags[0].GetString());

        JsonElement scores = fakeAgent.ReceivedForwardedProperties.GetProperty("scores");
        Assert.Equal(5, scores.GetArrayLength());
        Assert.Equal(3, scores[2].GetInt32());
    }

    [Fact]
    public async Task ForwardedProps_WhenEmpty_DoesNotCauseErrorsAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test empty props" }],
                "forwardedProps": {}
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
    }

    [Fact]
    public async Task ForwardedProps_WhenNotProvided_AgentStillWorksAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test no props" }]
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(JsonValueKind.Undefined, fakeAgent.ReceivedForwardedProperties.ValueKind);
    }

    [Fact]
    public async Task ForwardedProps_ReturnsValidSSEResponse_WithTextDeltaEventsAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test response" }],
                "forwardedProps": { "customProp": "value" }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();

        Stream stream = await response.Content.ReadAsStreamAsync();
        List<SseItem<string>> events = [];
        await foreach (SseItem<string> item in SseParser.Create(stream).EnumerateAsync())
        {
            events.Add(item);
        }

        // Assert
        Assert.NotEmpty(events);

        // SSE events have EventType = "message" and the actual type is in the JSON data
        // Should have run_started event
        Assert.Contains(events, e => e.Data?.Contains("\"type\":\"RUN_STARTED\"") == true);

        // Should have text_message_start event
        Assert.Contains(events, e => e.Data?.Contains("\"type\":\"TEXT_MESSAGE_START\"") == true);

        // Should have text_message_content event with the response text
        Assert.Contains(events, e => e.Data?.Contains("\"type\":\"TEXT_MESSAGE_CONTENT\"") == true);

        // Should have run_finished event
        Assert.Contains(events, e => e.Data?.Contains("\"type\":\"RUN_FINISHED\"") == true);
    }

    [Fact]
    public async Task ForwardedProps_WithMixedTypes_AreCorrectlyParsedAsync()
    {
        // Arrange
        FakeForwardedPropsAgent fakeAgent = new();
        await this.SetupTestServerAsync(fakeAgent);

        const string RequestJson = """
            {
                "threadId": "session-123",
                "runId": "run-456",
                "messages": [{ "id": "msg-1", "role": "user", "content": "test mixed types" }],
                "forwardedProps": {
                    "stringProp": "text",
                    "numberProp": 42,
                    "boolProp": true,
                    "nullProp": null,
                    "arrayProp": [1, "two", false],
                    "objectProp": { "nested": "value" }
                }
            }
            """;

        using StringContent content = new(RequestJson, Encoding.UTF8, "application/json");

        // Act
        HttpResponseMessage response = await this._client!.PostAsync(new Uri("/agent", UriKind.Relative), content);

        // Assert
        Assert.True(response.IsSuccessStatusCode);
        Assert.Equal(JsonValueKind.Object, fakeAgent.ReceivedForwardedProperties.ValueKind);

        Assert.Equal("text", fakeAgent.ReceivedForwardedProperties.GetProperty("stringProp").GetString());
        Assert.Equal(42, fakeAgent.ReceivedForwardedProperties.GetProperty("numberProp").GetInt32());
        Assert.True(fakeAgent.ReceivedForwardedProperties.GetProperty("boolProp").GetBoolean());
        Assert.Equal(JsonValueKind.Null, fakeAgent.ReceivedForwardedProperties.GetProperty("nullProp").ValueKind);
        Assert.Equal(3, fakeAgent.ReceivedForwardedProperties.GetProperty("arrayProp").GetArrayLength());
        Assert.Equal("value", fakeAgent.ReceivedForwardedProperties.GetProperty("objectProp").GetProperty("nested").GetString());
    }

    private async Task SetupTestServerAsync(FakeForwardedPropsAgent fakeAgent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUIServer();
        builder.WebHost.UseTestServer();

        this._app = builder.Build();

        this._app.MapAGUIServer("/agent", fakeAgent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }
}

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated in tests")]
internal sealed class FakeForwardedPropsAgent : AIAgent
{
    public FakeForwardedPropsAgent()
    {
    }

    public override string? Description => "Agent for forwarded properties testing";

    public IList<AGUIContext>? ReceivedContext { get; private set; }

    public IList<ChatMessage>? ReceivedMessages { get; private set; }

    public string? ReceivedInstructions { get; private set; }

    public List<List<ChatMessage>> ReceivedRuns { get; } = [];

    public JsonElement ReceivedForwardedProperties { get; private set; }

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this.RunCoreStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.ReceivedInstructions = (options as ChatClientAgentRunOptions)?.ChatOptions?.Instructions;
        this.ReceivedMessages = messages.ToList();
        this.ReceivedRuns.Add(this.ReceivedMessages.ToList());

        // Recover the originating AG-UI input from the request options (set by the hosting layer).
        if (options is ChatClientAgentRunOptions { ChatOptions: { } chatOptions } &&
            chatOptions.TryGetRunAgentInput(out RunAgentInput? agentInput))
        {
            this.ReceivedContext = agentInput.Context;

            if (agentInput.ForwardedProperties is { ValueKind: not JsonValueKind.Undefined } forwardedProps)
            {
                this.ReceivedForwardedProperties = forwardedProps;
            }
        }

        // Always return a text response
        string messageId = Guid.NewGuid().ToString("N");
        yield return new AgentResponseUpdate
        {
            MessageId = messageId,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Forwarded props processed")]
        };

        await Task.CompletedTask;
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeAgentSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(serializedState.Deserialize<FakeAgentSession>(jsonSerializerOptions)!);

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (session is not FakeAgentSession fakeSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(FakeAgentSession)}' can be serialized by this agent.");
        }

        return new(JsonSerializer.SerializeToElement(fakeSession, jsonSerializerOptions));
    }

    private sealed class FakeAgentSession : AgentSession
    {
        public FakeAgentSession()
        {
        }

        [JsonConstructor]
        public FakeAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }

    public override object? GetService(Type serviceType, object? serviceKey = null) => null;
}
