// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenTelemetry.Trace;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for Activity/TraceId preservation in ChatClientAgent, particularly during tool execution.
/// </summary>
public sealed class ChatClientAgent_ActivityTracingTests
{
    [Fact]
    public async Task ChatClientAgent_WithoutTools_PreservesActivityTraceId()
    {
        // Arrange
        const string sourceName = "TestActivitySource";
        List<Activity> activities = [];
        using TracerProvider tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ActivitySource activitySource = new(sourceName);
        using Activity? parentActivity = activitySource.StartActivity("ParentRequest");
        ActivityTraceId? parentTraceId = parentActivity?.TraceId;

        Assert.NotNull(parentTraceId);

        // Create a simple chat client that records the TraceId when invoked
        string? traceIdDuringLlmCall = null;
        TestChatClient mockChatClient = new()
        {
            GetResponseAsyncFunc = (messages, options, cancellationToken) =>
            {
                traceIdDuringLlmCall = Activity.Current?.TraceId.ToString();
                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Hello!")]));
            }
        };

        ChatClientAgent agent = new(mockChatClient, "You are a helpful assistant.", "TestAgent");

        // Act
        AgentResponse result = await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.NotNull(traceIdDuringLlmCall);
        Assert.Equal(parentTraceId.ToString(), traceIdDuringLlmCall);
        Assert.Single(result.Messages);
    }

    [Fact]
    public async Task ChatClientAgent_WithTools_PreservesActivityTraceId()
    {
        // Arrange
        const string sourceName = "TestActivitySource";
        List<Activity> activities = [];
        using TracerProvider tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ActivitySource activitySource = new(sourceName);
        using Activity? parentActivity = activitySource.StartActivity("ParentRequest");
        ActivityTraceId? parentTraceId = parentActivity?.TraceId;

        Assert.NotNull(parentTraceId);

        // Track TraceIds at different points in execution
        List<string?> traceIds = [];
        List<string> executionPoints = [];

        // Create a tool that simulates an async operation (like HTTP call)
        AIFunction weatherTool = AIFunctionFactory.Create(
            async (string location) =>
            {
                executionPoints.Add("ToolExecution");
                traceIds.Add(Activity.Current?.TraceId.ToString());

                // Simulate async operation like HTTP call
                await Task.Delay(10, CancellationToken.None).ConfigureAwait(false);

                executionPoints.Add("AfterAsyncOperation");
                traceIds.Add(Activity.Current?.TraceId.ToString());

                return $"Weather in {location}: Sunny, 72°F";
            },
            "GetWeather",
            "Gets the current weather for a location");

        // Create a chat client that simulates tool calling
        TestChatClient mockChatClient = new()
        {
            GetResponseAsyncFunc = async (messages, options, cancellationToken) =>
            {
                executionPoints.Add("FirstLlmCall");
                traceIds.Add(Activity.Current?.TraceId.ToString());

                // First response: LLM decides to call a tool
                const string toolCallId = "call_123";
                ChatResponse firstResponse = new([
                    new ChatMessage(ChatRole.Assistant, [
                        new FunctionCallContent(toolCallId, "GetWeather",
                            new Dictionary<string, object?> { ["location"] = "Seattle" })
                    ])
                ]);

                // Simulate tool execution (this is where the issue occurs)
                // In real scenario, FunctionInvokingChatClient would handle this
                await Task.Delay(10, CancellationToken.None).ConfigureAwait(false);

                executionPoints.Add("AfterFirstLlmResponse");
                traceIds.Add(Activity.Current?.TraceId.ToString());

                // Second LLM call after tool execution
                executionPoints.Add("SecondLlmCall");
                traceIds.Add(Activity.Current?.TraceId.ToString());

                return new ChatResponse([
                    new ChatMessage(ChatRole.Assistant, "The weather in Seattle is Sunny, 72°F")
                ]);
            }
        };

        ChatClientAgent agent = new(
            mockChatClient,
            "You are a helpful assistant.",
            "TestAgent",
            tools: [weatherTool]);

        // Act
        AgentResponse result = await agent.RunAsync([new ChatMessage(ChatRole.User, "What's the weather in Seattle?")]);

        // Assert
        Assert.NotEmpty(traceIds);

        // All TraceIds should match the parent
        foreach ((string? traceId, int index) in traceIds.Select((t, i) => (t, i)))
        {
            Assert.NotNull(traceId);
            Assert.True(
                parentTraceId.ToString() == traceId,
                $"TraceId mismatch at execution point '{executionPoints[index]}' (index {index}). Expected: {parentTraceId}, Actual: {traceId}");
        }

        Assert.Single(result.Messages);
    }

    [Fact]
    public async Task ChatClientAgent_WithToolsStreaming_PreservesActivityTraceId_InConsumerCode()
    {
        // Arrange
        const string sourceName = "TestActivitySource";
        List<Activity> activities = [];
        using TracerProvider tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ActivitySource activitySource = new(sourceName);
        using Activity? parentActivity = activitySource.StartActivity("ParentRequest");
        ActivityTraceId? parentTraceId = parentActivity?.TraceId;

        Assert.NotNull(parentTraceId);

        // Track TraceIds in consumer code (where user's code runs)
        List<string?> consumerTraceIds = [];

        // Create a simple chat client that returns streaming responses
        TestChatClient mockChatClient = new()
        {
            GetStreamingResponseAsyncFunc = (messages, options, cancellationToken) =>
            {
                async IAsyncEnumerable<ChatResponseUpdate> GenerateUpdatesAsync()
                {
                    await Task.Yield();
                    yield return new ChatResponseUpdate { Contents = [new TextContent("The weather")] };

                    await Task.Delay(10, CancellationToken.None).ConfigureAwait(false);
                    yield return new ChatResponseUpdate { Contents = [new TextContent(" is sunny")] };

                    await Task.Yield();
                    yield return new ChatResponseUpdate { Contents = [new TextContent("!")] };
                }

                return GenerateUpdatesAsync();
            }
        };

        ChatClientAgent agent = new(
            mockChatClient,
            "You are a helpful assistant.",
            "TestAgent");

        // Act - Process streaming updates in consumer code
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            // This is where user code runs - Activity.Current should be preserved here
            consumerTraceIds.Add(Activity.Current?.TraceId.ToString());
        }

        // Assert
        Assert.NotEmpty(consumerTraceIds);

        // All TraceIds in consumer code should match the parent
        foreach ((string? traceId, int index) in consumerTraceIds.Select((t, i) => (t, i)))
        {
            Assert.NotNull(traceId);
            Assert.True(
                parentTraceId.ToString() == traceId,
                $"TraceId mismatch in consumer code at index {index}. Expected: {parentTraceId}, Actual: {traceId}");
        }
    }

    [Fact]
    public async Task OpenTelemetryAgent_WithTools_PreservesActivityTraceId()
    {
        // Arrange
        const string sourceName = "TestOTelSource";
        List<Activity> activities = [];
        using TracerProvider tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ActivitySource activitySource = new(sourceName);
        using Activity? parentActivity = activitySource.StartActivity("ParentRequest");
        ActivityTraceId? parentTraceId = parentActivity?.TraceId;

        Assert.NotNull(parentTraceId);

        // Track TraceIds at different points in execution
        List<string?> traceIds = [];

        // Create a simple inner agent
        TestAIAgent innerAgent = new()
        {
            RunAsyncFunc = async (messages, thread, options, cancellationToken) =>
            {
                traceIds.Add(Activity.Current?.TraceId.ToString());
                await Task.Delay(10, CancellationToken.None);
                traceIds.Add(Activity.Current?.TraceId.ToString());
                return new AgentResponse(new ChatMessage(ChatRole.Assistant, "Response"));
            }
        };

        using OpenTelemetryAgent otelAgent = new(innerAgent, sourceName);

        // Act
        await otelAgent.RunAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.NotEmpty(traceIds);

        // All TraceIds should match the parent
        foreach ((string? traceId, int index) in traceIds.Select((t, i) => (t, i)))
        {
            Assert.NotNull(traceId);
            Assert.True(
                parentTraceId.ToString() == traceId,
                $"TraceId mismatch at index {index}. Expected: {parentTraceId}, Actual: {traceId}");
        }
    }

    /// <summary>
    /// Simple test chat client for testing purposes.
    /// </summary>
    private sealed class TestChatClient : IChatClient
    {
        public Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>>? GetResponseAsyncFunc { get; set; }
        public Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, IAsyncEnumerable<ChatResponseUpdate>>? GetStreamingResponseAsyncFunc { get; set; }

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            if (this.GetResponseAsyncFunc is null)
            {
                throw new NotImplementedException();
            }

            return this.GetResponseAsyncFunc(messages, options, cancellationToken);
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            if (this.GetStreamingResponseAsyncFunc is null)
            {
                throw new NotImplementedException();
            }

            return this.GetStreamingResponseAsyncFunc(messages, options, cancellationToken);
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }
}
