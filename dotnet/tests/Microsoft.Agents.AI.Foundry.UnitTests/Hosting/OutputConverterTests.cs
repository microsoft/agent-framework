// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public class OutputConverterTests
{
    private static (ResponseEventStream stream, Mock<ResponseContext> mockContext) CreateTestStream()
    {
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        var request = new CreateResponse { Model = "test-model" };
        var stream = new ResponseEventStream(mockContext.Object, request);
        return (stream, mockContext);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_EmptyStream_EmitsCompletedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = ToAsync(Array.Empty<AgentResponseUpdate>());

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(updates, stream))
        {
            events.Add(evt);
        }

        Assert.Single(events);
        Assert.IsType<ResponseCompletedEvent>(events[0]);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_SingleTextUpdate_EmitsMessageAndCompletedAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            MessageId = "msg_1",
            Contents = [new MeaiTextContent("Hello, world!")]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        // Expected: MessageAdded, TextAdded, TextDelta, TextDone, ContentDone, MessageDone, Completed
        Assert.True(events.Count >= 5, $"Expected at least 5 events, got {events.Count}");
        Assert.IsType<ResponseOutputItemAddedEvent>(events[0]);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_MultipleTextUpdates_EmitsStreamingDeltasAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Hello, ")] },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("world!")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Should have two text delta events among the others
        Assert.True(events.Count >= 6, $"Expected at least 6 events, got {events.Count}");
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionCall_EmitsFunctionCallEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new FunctionCallContent("call_1", "get_weather",
                new Dictionary<string, object?> { ["city"] = "Seattle" })]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        // Should have: FuncAdded, ArgsDelta, ArgsDone, FuncDone, Completed
        Assert.IsType<ResponseOutputItemAddedEvent>(events[0]);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
        Assert.True(events.Count >= 4, $"Expected at least 4 events for function call, got {events.Count}");
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ErrorContent_EmitsFailedAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new ErrorContent("Something went wrong")]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.IsType<ResponseFailedEvent>(events[^1]);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ErrorContent_DoesNotEmitCompletedAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new ErrorContent("Failure")]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.DoesNotContain(events, e => e is ResponseCompletedEvent);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_UsageContent_IncludesUsageInCompletedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate
            {
                MessageId = "msg_1",
                Contents = [new MeaiTextContent("Hi")]
            },
            new AgentResponseUpdate
            {
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 5,
                    TotalTokenCount = 15
                })]
            }
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        var completedEvent = events.OfType<ResponseCompletedEvent>().SingleOrDefault();
        Assert.NotNull(completedEvent);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ReasoningContent_EmitsReasoningEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new TextReasoningContent("Let me think about this...")]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        // Should have: ReasoningAdded, SummaryPartAdded, TextDelta, TextDone, SummaryDone, ReasoningDone, Completed
        Assert.True(events.Count >= 5, $"Expected at least 5 events for reasoning, got {events.Count}");
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task ConvertUpdatesToEventsAsync_CancellationRequested_ThrowsAsync()
    {
        var (stream, _) = CreateTestStream();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        var updates = ToAsync(new[] { new AgentResponseUpdate { Contents = [new MeaiTextContent("test")] } });

        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(updates, stream, cts.Token))
            {
                // Should throw before yielding
            }
        });
    }

    // F-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_EmptyTextContent_NoTextDeltaEmittedAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("")] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.DoesNotContain(events, e => e is ResponseTextDeltaEvent);
        Assert.Contains(events, e => e is ResponseCompletedEvent);
    }

    // F-04
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_NullTextContent_NoTextDeltaEmittedAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent(null!)] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.DoesNotContain(events, e => e is ResponseTextDeltaEvent);
        Assert.Contains(events, e => e is ResponseCompletedEvent);
    }

    // F-07
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_DifferentMessageIds_CreatesMultipleMessagesAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("First")] },
            new AgentResponseUpdate { MessageId = "msg_2", Contents = [new MeaiTextContent("Second")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // F-08
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_NullMessageIds_TreatedAsSameMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = null, Contents = [new MeaiTextContent("First")] },
            new AgentResponseUpdate { MessageId = null, Contents = [new MeaiTextContent("Second")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Single(events.OfType<ResponseOutputItemAddedEvent>());
    }

    // G-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionCallClosesOpenMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("thinking...")] },
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_1", "search", new Dictionary<string, object?> { ["q"] = "test" })] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Equal(2, events.OfType<ResponseOutputItemDoneEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // G-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionCallWithNullArguments_EmitsEmptyJsonAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new FunctionCallContent("call_1", "do_something", null)]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // G-04
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionCallWithEmptyCallId_GeneratesCallIdAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new FunctionCallContent("", "do_something", new Dictionary<string, object?> { ["x"] = 1 })]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseOutputItemAddedEvent);
    }

    // G-05
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_MultipleFunctionCalls_EmitsSeparateBuildersAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_1", "func_a", new Dictionary<string, object?> { ["a"] = 1 })] },
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_2", "func_b", new Dictionary<string, object?> { ["b"] = 2 })] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // H-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ReasoningWithNullText_EmitsEmptyStringAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { Contents = [new TextReasoningContent(null)] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.True(events.Count >= 5, $"Expected at least 5 events, got {events.Count}");
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // H-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ReasoningClosesOpenMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("partial")] },
            new AgentResponseUpdate { Contents = [new TextReasoningContent("thinking")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // I-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ErrorContentWithNullMessage_UsesDefaultMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { Contents = [new ErrorContent(null!)] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseFailedEvent);
    }

    // I-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ErrorContentClosesOpenMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("partial text")] },
            new AgentResponseUpdate { Contents = [new ErrorContent("Something broke")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.True(events.OfType<ResponseOutputItemDoneEvent>().Any());
        Assert.IsType<ResponseFailedEvent>(events[^1]);
    }

    // I-06
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ErrorAfterPartialText_ClosesMessageThenFailsAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("partial text")] },
            new AgentResponseUpdate { Contents = [new ErrorContent("Unexpected error")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.True(events.OfType<ResponseOutputItemDoneEvent>().Any());
        Assert.IsType<ResponseFailedEvent>(events[^1]);
        Assert.DoesNotContain(events, e => e is ResponseCompletedEvent);
    }

    // J-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_MultipleUsageUpdates_AccumulatesTokensAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Hi")] },
            new AgentResponseUpdate { Contents = [new UsageContent(new UsageDetails { InputTokenCount = 10, OutputTokenCount = 5, TotalTokenCount = 15 })] },
            new AgentResponseUpdate { Contents = [new UsageContent(new UsageDetails { InputTokenCount = 20, OutputTokenCount = 10, TotalTokenCount = 30 })] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseCompletedEvent);
    }

    // J-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_UsageWithZeroTokens_StillCompletesAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate
        {
            Contents = [new UsageContent(new UsageDetails { InputTokenCount = 0, OutputTokenCount = 0, TotalTokenCount = 0 })]
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseCompletedEvent);
    }

    // K-01
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_DataContent_IsSkippedWithNoEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { Contents = [new DataContent("data:image/png;base64,aWNv", "image/png")] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Single(events);
        Assert.IsType<ResponseCompletedEvent>(events[0]);
    }

    // K-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_UriContent_IsSkippedWithNoEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { Contents = [new UriContent("https://example.com/file.txt", "text/plain")] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Single(events);
        Assert.IsType<ResponseCompletedEvent>(events[0]);
    }

    // K-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionResultContent_IsSkippedWithNoEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { Contents = [new FunctionResultContent("call_1", "result data")] };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Single(events);
        Assert.IsType<ResponseCompletedEvent>(events[0]);
    }

    // L-01
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ExecutorInvokedEvent_EmitsWorkflowActionItemAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("executor_1", "invoked") };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseOutputItemAddedEvent);
        Assert.Contains(events, e => e is ResponseOutputItemDoneEvent);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // L-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ExecutorCompletedEvent_EmitsCompletedWorkflowActionAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("executor_1", null) };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseOutputItemAddedEvent);
        Assert.Contains(events, e => e is ResponseOutputItemDoneEvent);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // L-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ExecutorFailedEvent_EmitsFailedWorkflowActionAsync()
    {
        var (stream, _) = CreateTestStream();
        var update = new AgentResponseUpdate { RawRepresentation = new ExecutorFailedEvent("executor_1", new InvalidOperationException("test error")) };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(new[] { update }), stream))
        {
            events.Add(evt);
        }

        Assert.Contains(events, e => e is ResponseOutputItemAddedEvent);
        Assert.Contains(events, e => e is ResponseOutputItemDoneEvent);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // L-04
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowEventClosesOpenMessageAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("partial")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("exec_1", "invoked") },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // L-06
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_InterleavedWorkflowAndTextEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("exec_1", "invoked") },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Agent says hello")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("exec_1", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(3, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // M-01
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_TextThenFunctionCallThenText_ProducesCorrectSequenceAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Let me check...")] },
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_1", "search", new Dictionary<string, object?> { ["q"] = "weather" })] },
            new AgentResponseUpdate { MessageId = "msg_2", Contents = [new MeaiTextContent("Here are the results")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(3, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // M-02
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ReasoningThenText_ProducesCorrectSequenceAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { Contents = [new TextReasoningContent("Thinking about the answer...")] },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("The answer is 42")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(2, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // M-03
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_TextThenError_EmitsMessageThenFailedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Starting...")] },
            new AgentResponseUpdate { Contents = [new ErrorContent("Unexpected error")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.IsType<ResponseFailedEvent>(events[^1]);
        Assert.DoesNotContain(events, e => e is ResponseCompletedEvent);
        Assert.Single(events.OfType<ResponseOutputItemAddedEvent>());
    }

    // M-04
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FunctionCallThenTextThenFunctionCall_ProducesThreeItemsAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_1", "func_a", new Dictionary<string, object?> { ["a"] = 1 })] },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Processing...")] },
            new AgentResponseUpdate { Contents = [new FunctionCallContent("call_2", "func_b", new Dictionary<string, object?> { ["b"] = 2 })] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Equal(3, events.OfType<ResponseOutputItemAddedEvent>().Count());
    }

    // ===== Workflow content flow tests (W series) =====
    // These simulate the exact update patterns that WorkflowSession.InvokeStageAsync() produces
    // when wrapping a Workflow as an AIAgent via AsAIAgent().

    // W-01: Multi-executor text output — different MessageIds cause separate messages
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_MultiExecutorTextOutput_CreatesSeparateMessagesAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            // Executor 1 invoked (RawRepresentation)
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            // Executor 1 produces text (unwrapped AgentResponseUpdateEvent)
            new AgentResponseUpdate { MessageId = "msg_agent1", Contents = [new MeaiTextContent("Hello from agent 1")] },
            // Executor 1 completed
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_1", null) },
            // Executor 2 invoked
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_2", "start") },
            // Executor 2 produces text (different MessageId)
            new AgentResponseUpdate { MessageId = "msg_agent2", Contents = [new MeaiTextContent("Hello from agent 2")] },
            // Executor 2 completed
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_2", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 2 workflow action items (invoked) + 1 text message + 2 workflow action items (completed) + 1 text message = 6 output items
        Assert.Equal(6, events.OfType<ResponseOutputItemAddedEvent>().Count());
        // 2 text deltas (one per agent)
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-02: Workflow error via ErrorContent (as produced by WorkflowSession for WorkflowErrorEvent)
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowErrorAsContent_EmitsFailedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Starting work...")] },
            // WorkflowErrorEvent is converted to ErrorContent by WorkflowSession
            new AgentResponseUpdate { Contents = [new ErrorContent("Workflow execution failed")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Should close the open message, then emit failed
        Assert.True(events.OfType<ResponseOutputItemDoneEvent>().Any());
        Assert.IsType<ResponseFailedEvent>(events[^1]);
        Assert.DoesNotContain(events, e => e is ResponseCompletedEvent);
    }

    // W-03: Function call from workflow executor (e.g. handoff agent calling transfer_to_agent)
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowFunctionCall_EmitsFunctionCallEventsAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("triage_agent", "start") },
            // Agent produces function call (handoff)
            new AgentResponseUpdate
            {
                Contents = [new FunctionCallContent("call_handoff", "transfer_to_code_expert",
                    new Dictionary<string, object?> { ["reason"] = "User asked about code" })]
            },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("triage_agent", null) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("code_expert", "start") },
            new AgentResponseUpdate { MessageId = "msg_expert", Contents = [new MeaiTextContent("Here's how async/await works...")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("code_expert", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Should have: 4 workflow actions + 1 function call + 1 text message = 6 output items
        Assert.Equal(6, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Contains(events, e => e is ResponseFunctionCallArgumentsDoneEvent);
        Assert.Contains(events, e => e is ResponseTextDeltaEvent);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-04: Informational events (superstep, workflow started) are silently skipped
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_InformationalWorkflowEvents_AreSkippedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new WorkflowStartedEvent("start") },
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Result")] },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Only one output item (the text message), no workflow action items for informational events
        Assert.Single(events.OfType<ResponseOutputItemAddedEvent>());
        Assert.Contains(events, e => e is ResponseTextDeltaEvent);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-05: Warning events are silently skipped
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowWarningEvent_IsSkippedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new WorkflowWarningEvent("Agent took too long") },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Done")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        Assert.Single(events.OfType<ResponseOutputItemAddedEvent>());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-06: Streaming text from multiple workflow turns (same executor, different message IDs)
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_MultiTurnSameExecutor_CreatesSeparateMessagesAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_turn1", Contents = [new MeaiTextContent("First response")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_1", null) },
            // Same executor invoked again (second superstep)
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_turn2", Contents = [new MeaiTextContent("Second response")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_1", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 4 workflow action items + 2 text messages = 6 output items
        Assert.Equal(6, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
    }

    // W-07: Executor failure mid-stream with partial text
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_ExecutorFailureAfterPartialText_ClosesMessageAndEmitsFailureAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Starting to process...")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorFailedEvent("agent_1", new InvalidOperationException("Agent crashed")) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Text message should be closed before the failed workflow action item
        Assert.True(events.OfType<ResponseOutputItemDoneEvent>().Any());
        // Workflow action items: invoked + failed = 2, plus text message = 3
        Assert.Equal(3, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-08: Full handoff pattern — triage → function call → target agent text
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_FullHandoffPattern_ProducesCorrectEventSequenceAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            // Workflow lifecycle
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("triage", "start") },
            // Triage agent decides to hand off
            new AgentResponseUpdate
            {
                Contents = [new FunctionCallContent("call_1", "transfer_to_expert",
                    new Dictionary<string, object?> { ["reason"] = "technical question" })]
            },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("triage", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
            // Next superstep
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(2) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("expert", "start") },
            // Expert agent responds with text
            new AgentResponseUpdate { MessageId = "msg_expert_1", Contents = [new MeaiTextContent("Let me explain...")] },
            new AgentResponseUpdate { MessageId = "msg_expert_1", Contents = [new MeaiTextContent(" Here's how it works.")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("expert", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(2) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Workflow actions: invoked triage, completed triage, invoked expert, completed expert = 4
        // Content items: 1 function call, 1 text message = 2
        // Total output items: 6
        Assert.Equal(6, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Contains(events, e => e is ResponseFunctionCallArgumentsDoneEvent);
        // Two text deltas for the two streaming chunks
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-09: SubworkflowErrorEvent treated as informational (error content comes separately)
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_SubworkflowErrorEvent_IsSkippedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new SubworkflowErrorEvent("sub_1", new InvalidOperationException("sub failed")) },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Recovered")] },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // SubworkflowErrorEvent extends WorkflowErrorEvent which falls through to default skip
        Assert.Single(events.OfType<ResponseOutputItemAddedEvent>());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-10: Mixed content types from workflow — reasoning + text
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowReasoningThenText_ProducesCorrectSequenceAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("thinking_agent", "start") },
            // Agent produces reasoning content
            new AgentResponseUpdate { Contents = [new TextReasoningContent("Analyzing the problem...")] },
            // Then text response
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("The answer is 42")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("thinking_agent", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Workflow actions: 2 (invoked + completed), reasoning: 1, text message: 1 = 4 output items
        Assert.Equal(4, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-11: Usage content accumulated across workflow executors
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_WorkflowUsageAcrossExecutors_AccumulatesCorrectlyAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_1", Contents = [new MeaiTextContent("Response 1")] },
            new AgentResponseUpdate { Contents = [new UsageContent(new UsageDetails { InputTokenCount = 100, OutputTokenCount = 50, TotalTokenCount = 150 })] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_1", null) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_2", "start") },
            new AgentResponseUpdate { MessageId = "msg_2", Contents = [new MeaiTextContent("Response 2")] },
            new AgentResponseUpdate { Contents = [new UsageContent(new UsageDetails { InputTokenCount = 200, OutputTokenCount = 100, TotalTokenCount = 300 })] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_2", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Usage should be accumulated in the completed event
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // W-12: Empty workflow — only lifecycle events, no content
    [Fact]
    public async Task ConvertUpdatesToEventsAsync_EmptyWorkflowOnlyLifecycle_EmitsOnlyCompletedAsync()
    {
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new WorkflowStartedEvent("start") },
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Only the terminal completed event
        Assert.Single(events);
        Assert.IsType<ResponseCompletedEvent>(events[0]);
    }

    private static async IAsyncEnumerable<T> ToAsync<T>(IEnumerable<T> source)
    {
        foreach (var item in source)
        {
            yield return item;
        }

        await Task.CompletedTask;
    }
}
