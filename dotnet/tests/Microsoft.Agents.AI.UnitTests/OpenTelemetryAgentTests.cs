// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenTelemetry.Trace;

#pragma warning disable CA1861 // Avoid constant arrays as arguments
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.UnitTests;

public class OpenTelemetryAgentTests
{
    [Fact]
    public void Ctor_InvalidArgs_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new OpenTelemetryAgent(null!));
    }

    [Fact]
    public void Ctor_NullSourceName_Valid()
    {
        using var agent = new OpenTelemetryAgent(new TestAIAgent(), null);
        Assert.NotNull(agent);
    }

    [Fact]
    public void Properties_DelegateToInnerAgent()
    {
        TestAIAgent innerAgent = new()
        {
            NameFunc = () => "TestAgent",
            DescriptionFunc = () => "This is a test agent.",
        };

        using var agent = new OpenTelemetryAgent(innerAgent, "MySource");

        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("This is a test agent.", agent.Description);
        Assert.Equal(innerAgent.Id, agent.Id);
    }

    [Fact]
    public void EnableSensitiveData_Roundtrips()
    {
        using var agent = new OpenTelemetryAgent(new TestAIAgent(), "MySource");
        for (int i = 0; i < 2; i++)
        {
            Assert.False(agent.EnableSensitiveData);
            agent.EnableSensitiveData = true;
            Assert.True(agent.EnableSensitiveData);
            agent.EnableSensitiveData = false;
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task WithoutChatOptions_ExpectedInformationLogged_Async(bool enableSensitiveData, bool streaming)
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var innerAgent = new TestAIAgent
        {
            NameFunc = () => "TestAgent",
            DescriptionFunc = () => "This is a test agent.",

            RunAsyncFunc = async (messages, session, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentResponse(new ChatMessage(ChatRole.Assistant, "The blue whale, I think."))
                {
                    ResponseId = "id123",
                    Usage = new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 20,
                        TotalTokenCount = 42,
                    },
                    AdditionalProperties = new()
                    {
                        ["system_fingerprint"] = "abcdefgh",
                        ["AndSomethingElse"] = "value2",
                    },
                };
            },

            RunStreamingAsyncFunc = CallbackAsync,

            GetServiceFunc = (serviceType, serviceKey) =>
                serviceType == typeof(AIAgentMetadata) ? new AIAgentMetadata("TestAgentProviderFromAIAgentMetadata") :
                serviceType == typeof(ChatClientMetadata) ? new ChatClientMetadata("TestAgentProviderFromChatClientMetadata", new Uri("http://localhost:12345/something"), "amazingmodel") :
                null,
        };

        async static IAsyncEnumerable<AgentResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();

            foreach (string text in new[] { "The ", "blue ", "whale,", " ", "", "I", " think." })
            {
                await Task.Yield();
                yield return new AgentResponseUpdate(ChatRole.Assistant, text)
                {
                    ResponseId = "id123",
                };
            }

            yield return new AgentResponseUpdate
            {
                Contents = [new UsageContent(new()
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 20,
                    TotalTokenCount = 42,
                })],
                AdditionalProperties = new()
                {
                    ["system_fingerprint"] = "abcdefgh",
                    ["AndSomethingElse"] = "value2",
                },
            };
        }

        using var agent = new OpenTelemetryAgent(innerAgent, sourceName) { EnableSensitiveData = enableSensitiveData };

        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a close friend."),
            new(ChatRole.User, "Hey!"),
            new(ChatRole.Assistant, [new FunctionCallContent("12345", "GetPersonName")]),
            new(ChatRole.Tool, [new FunctionResultContent("12345", "John")]),
            new(ChatRole.Assistant, "Hey John, what's up?"),
            new(ChatRole.User, "What's the biggest animal?")
        ];

        if (streaming)
        {
            await foreach (var update in agent.RunStreamingAsync(messages))
            {
                await Task.Yield();
            }
        }
        else
        {
            await agent.RunAsync(messages);
        }

        var activity = Assert.Single(activities);

        Assert.NotNull(activity.Id);
        Assert.NotEmpty(activity.Id);

        Assert.Equal("localhost", activity.GetTagItem("server.address"));
        Assert.Equal(12345, (int)activity.GetTagItem("server.port")!);

        Assert.Equal($"invoke_agent {agent.Name}({agent.Id})", activity.DisplayName);
        Assert.Equal("invoke_agent", activity.GetTagItem("gen_ai.operation.name"));
        Assert.Equal("TestAgentProviderFromAIAgentMetadata", activity.GetTagItem("gen_ai.provider.name"));
        Assert.Equal(innerAgent.Name, activity.GetTagItem("gen_ai.agent.name"));
        Assert.Equal(innerAgent.Id, activity.GetTagItem("gen_ai.agent.id"));
        Assert.Equal(innerAgent.Description, activity.GetTagItem("gen_ai.agent.description"));

        Assert.Equal("amazingmodel", activity.GetTagItem("gen_ai.request.model"));

        Assert.Equal("id123", activity.GetTagItem("gen_ai.response.id"));
        Assert.Equal(10, activity.GetTagItem("gen_ai.usage.input_tokens"));
        Assert.Equal(20, activity.GetTagItem("gen_ai.usage.output_tokens"));
        Assert.Equal(enableSensitiveData ? "abcdefgh" : null, activity.GetTagItem("system_fingerprint"));
        Assert.Equal(enableSensitiveData ? "value2" : null, activity.GetTagItem("AndSomethingElse"));

        Assert.True(activity.Duration.TotalMilliseconds > 0);

        var tags = activity.Tags.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);
        if (enableSensitiveData)
        {
            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "role": "system",
                    "parts": [
                      {
                        "type": "text",
                        "content": "You are a close friend."
                      }
                    ]
                  },
                  {
                    "role": "user",
                    "parts": [
                      {
                        "type": "text",
                        "content": "Hey!"
                      }
                    ]
                  },
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "tool_call",
                        "id": "12345",
                        "name": "GetPersonName"
                      }
                    ]
                  },
                  {
                    "role": "tool",
                    "parts": [
                      {
                        "type": "tool_call_response",
                        "id": "12345",
                        "response": "John"
                      }
                    ]
                  },
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "text",
                        "content": "Hey John, what's up?"
                      }
                    ]
                  },
                  {
                    "role": "user",
                    "parts": [
                      {
                        "type": "text",
                        "content": "What's the biggest animal?"
                      }
                    ]
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.input.messages"]));

            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "text",
                        "content": "The blue whale, I think."
                      }
                    ]
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.output.messages"]));
        }
        else
        {
            Assert.False(tags.ContainsKey("gen_ai.input.messages"));
            Assert.False(tags.ContainsKey("gen_ai.output.messages"));
        }

        Assert.False(tags.ContainsKey("gen_ai.system_instructions"));
        Assert.False(tags.ContainsKey("gen_ai.tool.definitions"));
    }

    public static IEnumerable<object[]> WithChatOptions_ExpectedInformationLogged_Async_MemberData() =>
        from enableSensitiveData in new[] { false, true }
        from streaming in new[] { false, true }
        from name in new[] { null, "TestAgent" }
        from description in new[] { null, "This is a test agent." }
        select new object[] { enableSensitiveData, streaming, name, description, true };

    [Theory]
    [MemberData(nameof(WithChatOptions_ExpectedInformationLogged_Async_MemberData))]
    [InlineData(true, false, "TestAgent", "This is a test agent.", false)]
    [InlineData(true, true, "TestAgent", "This is a test agent.", false)]
    public async Task WithChatOptions_ExpectedInformationLogged_Async(
        bool enableSensitiveData, bool streaming, string name, string description, bool hasListener)
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        var builder = OpenTelemetry.Sdk.CreateTracerProviderBuilder();
        if (hasListener)
        {
            builder.AddSource(sourceName);
        }
        using var tracerProvider = builder
            .AddInMemoryExporter(activities)
            .Build();

        var innerAgent = new TestAIAgent
        {
            NameFunc = () => name,
            DescriptionFunc = () => description,

            RunAsyncFunc = async (messages, session, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentResponse(new ChatMessage(ChatRole.Assistant, "The blue whale, I think."))
                {
                    ResponseId = "id123",
                    Usage = new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 20,
                        TotalTokenCount = 42,
                    },
                    AdditionalProperties = new()
                    {
                        ["system_fingerprint"] = "abcdefgh",
                        ["AndSomethingElse"] = "value2",
                    },
                };
            },

            RunStreamingAsyncFunc = CallbackAsync,

            GetServiceFunc = (serviceType, serviceKey) =>
                serviceType == typeof(AIAgentMetadata) ? new AIAgentMetadata("TestAgentProviderFromAIAgentMetadata") :
                serviceType == typeof(ChatClientMetadata) ? new ChatClientMetadata("TestAgentProviderFromChatClientMetadata", new Uri("http://localhost:12345/something"), "amazingmodel") :
                null,
        };

        async static IAsyncEnumerable<AgentResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();

            foreach (string text in new[] { "The ", "blue ", "whale,", " ", "", "I", " think." })
            {
                await Task.Yield();
                yield return new AgentResponseUpdate(ChatRole.Assistant, text)
                {
                    ResponseId = "id123",
                };
            }

            yield return new AgentResponseUpdate
            {
                Contents = [new UsageContent(new()
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 20,
                    TotalTokenCount = 42,
                })],
                AdditionalProperties = new()
                {
                    ["system_fingerprint"] = "abcdefgh",
                    ["AndSomethingElse"] = "value2",
                },
            };
        }

        using var agent = new OpenTelemetryAgent(innerAgent, sourceName) { EnableSensitiveData = enableSensitiveData };

        List<ChatMessage> messages =
        [
            new(ChatRole.System, "You are a close friend."),
            new(ChatRole.User, "Hey!"),
            new(ChatRole.Assistant, [new FunctionCallContent("12345", "GetPersonName")]),
            new(ChatRole.Tool, [new FunctionResultContent("12345", "John")]),
            new(ChatRole.Assistant, "Hey John, what's up?"),
            new(ChatRole.User, "What's the biggest animal?")
        ];

        var options = new ChatClientAgentRunOptions()
        {
            ChatOptions = new ChatOptions
            {
                FrequencyPenalty = 3.0f,
                MaxOutputTokens = 123,
                ModelId = "replacementmodel",
                TopP = 4.0f,
                TopK = 7,
                PresencePenalty = 5.0f,
                ResponseFormat = ChatResponseFormat.Json,
                Temperature = 6.0f,
                Seed = 42,
                StopSequences = ["hello", "world"],
                AdditionalProperties = new()
                {
                    ["service_tier"] = "value1",
                    ["SomethingElse"] = "value2",
                },
                Instructions = "You are helpful.",
                Tools =
                [
                    AIFunctionFactory.Create((string personName) => personName, "GetPersonAge", "Gets the age of a person by name."),
                    new HostedWebSearchTool(),
                    AIFunctionFactory.Create((string location) => "", "GetCurrentWeather", "Gets the current weather for a location.").AsDeclarationOnly(),
                ],
            }
        };

        if (streaming)
        {
            await foreach (var update in agent.RunStreamingAsync(messages, options: options))
            {
                await Task.Yield();
            }
        }
        else
        {
            await agent.RunAsync(messages, options: options);
        }

        if (!hasListener)
        {
            Assert.Empty(activities);
            return;
        }

        var activity = Assert.Single(activities);
        var tags = activity.Tags.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);

        Assert.NotNull(activity.Id);
        Assert.NotEmpty(activity.Id);

        Assert.Equal("localhost", activity.GetTagItem("server.address"));
        Assert.Equal(12345, (int)activity.GetTagItem("server.port")!);

        if (string.IsNullOrWhiteSpace(innerAgent.Name))
        {
            Assert.Equal($"invoke_agent {innerAgent.Id}", activity.DisplayName);
        }
        else
        {
            Assert.Equal($"invoke_agent {innerAgent.Name}({innerAgent.Id})", activity.DisplayName);
        }

        Assert.Equal("invoke_agent", activity.GetTagItem("gen_ai.operation.name"));
        Assert.Equal("TestAgentProviderFromAIAgentMetadata", activity.GetTagItem("gen_ai.provider.name"));
        Assert.Equal(innerAgent.Name, activity.GetTagItem("gen_ai.agent.name"));
        Assert.Equal(innerAgent.Id, activity.GetTagItem("gen_ai.agent.id"));
        if (description is null)
        {
            Assert.False(tags.ContainsKey("gen_ai.agent.description"));
        }
        else
        {
            Assert.Equal(innerAgent.Description, activity.GetTagItem("gen_ai.agent.description"));
        }

        Assert.Equal("replacementmodel", activity.GetTagItem("gen_ai.request.model"));
        Assert.Equal(3.0f, activity.GetTagItem("gen_ai.request.frequency_penalty"));
        Assert.Equal(4.0f, activity.GetTagItem("gen_ai.request.top_p"));
        Assert.Equal(5.0f, activity.GetTagItem("gen_ai.request.presence_penalty"));
        Assert.Equal(6.0f, activity.GetTagItem("gen_ai.request.temperature"));
        Assert.Equal(7, activity.GetTagItem("gen_ai.request.top_k"));
        Assert.Equal(123, activity.GetTagItem("gen_ai.request.max_tokens"));
        Assert.Equal("""["hello", "world"]""", activity.GetTagItem("gen_ai.request.stop_sequences"));
        Assert.Equal(enableSensitiveData ? "value1" : null, activity.GetTagItem("service_tier"));
        Assert.Equal(enableSensitiveData ? "value2" : null, activity.GetTagItem("SomethingElse"));
        Assert.Equal(42L, activity.GetTagItem("gen_ai.request.seed"));

        Assert.Equal("id123", activity.GetTagItem("gen_ai.response.id"));
        Assert.Equal(10, activity.GetTagItem("gen_ai.usage.input_tokens"));
        Assert.Equal(20, activity.GetTagItem("gen_ai.usage.output_tokens"));
        Assert.Equal(enableSensitiveData ? "abcdefgh" : null, activity.GetTagItem("system_fingerprint"));
        Assert.Equal(enableSensitiveData ? "value2" : null, activity.GetTagItem("AndSomethingElse"));

        Assert.True(activity.Duration.TotalMilliseconds > 0);

        if (enableSensitiveData)
        {
            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "role": "system",
                    "parts": [
                      {
                        "type": "text",
                        "content": "You are a close friend."
                      }
                    ]
                  },
                  {
                    "role": "user",
                    "parts": [
                      {
                        "type": "text",
                        "content": "Hey!"
                      }
                    ]
                  },
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "tool_call",
                        "id": "12345",
                        "name": "GetPersonName"
                      }
                    ]
                  },
                  {
                    "role": "tool",
                    "parts": [
                      {
                        "type": "tool_call_response",
                        "id": "12345",
                        "response": "John"
                      }
                    ]
                  },
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "text",
                        "content": "Hey John, what's up?"
                      }
                    ]
                  },
                  {
                    "role": "user",
                    "parts": [
                      {
                        "type": "text",
                        "content": "What's the biggest animal?"
                      }
                    ]
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.input.messages"]));

            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "role": "assistant",
                    "parts": [
                      {
                        "type": "text",
                        "content": "The blue whale, I think."
                      }
                    ]
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.output.messages"]));

            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                      "type": "text",
                      "content": "You are helpful."
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.system_instructions"]));

            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "type": "function",
                    "name": "GetPersonAge",
                    "description": "Gets the age of a person by name.",
                    "parameters": {
                      "type": "object",
                      "properties": {
                        "personName": {
                          "type": "string"
                        }
                      },
                      "required": [
                        "personName"
                      ]
                    }
                  },
                  {
                    "type": "web_search",
                    "name": "web_search"
                  },
                  {
                    "type": "function",
                    "name": "GetCurrentWeather",
                    "description": "Gets the current weather for a location.",
                    "parameters": {
                      "type": "object",
                      "properties": {
                        "location": {
                          "type": "string"
                        }
                      },
                      "required": [
                        "location"
                      ]
                    }
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.tool.definitions"]));
        }
        else
        {
            Assert.False(tags.ContainsKey("gen_ai.input.messages"));
            Assert.False(tags.ContainsKey("gen_ai.output.messages"));
            Assert.False(tags.ContainsKey("gen_ai.system_instructions"));

            // gen_ai.tool.definitions is always emitted regardless of EnableSensitiveData (ME.AI 10.4.0+).
            // ME.AI 10.5.1 omits description/parameters for function tools when sensitive data is disabled.
            Assert.Equal(ReplaceWhitespace("""
                [
                  {
                    "type": "function",
                    "name": "GetPersonAge"
                  },
                  {
                    "type": "web_search",
                    "name": "web_search"
                  },
                  {
                    "type": "function",
                    "name": "GetCurrentWeather"
                  }
                ]
                """), ReplaceWhitespace(tags["gen_ai.tool.definitions"]));
        }
    }

    private static string ReplaceWhitespace(string? input) => Regex.Replace(input ?? "", @"\s+", "").Trim();

    #region AutoWireChatClient

    [Fact]
    public async Task AutoWireChatClient_DefaultsToEnabled_EmitsChatSpan_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        _ = await agent.RunAsync("hi");

        // Expect 2 activities: the inner chat span (from auto-wired OpenTelemetryChatClient) and the invoke_agent span.
        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AutoWireChatClient_Streaming_EmitsChatSpan_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        await foreach (var _ in agent.RunStreamingAsync("hi"))
        {
        }

        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AutoWireChatClient_Disabled_DoesNotEmitChatSpan_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName, autoWireChatClient: false);

        _ = await agent.RunAsync("hi");

        // Only the invoke_agent activity should be emitted; no chat span.
        var activity = Assert.Single(activities);
        Assert.StartsWith("invoke_agent", activity.DisplayName);
    }

    [Fact]
    public async Task AutoWireChatClient_NonChatClientAgent_NoOp_Async()
    {
        // Inner is not a ChatClientAgent — auto-wiring must be a no-op and options must remain null.
        AgentRunOptions? observedOptions = null;
        var inner = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, ct) =>
            {
                observedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            },
        };

        using var agent = new OpenTelemetryAgent(inner);

        _ = await agent.RunAsync("hi");

        Assert.Null(observedOptions);
    }

    [Fact]
    public async Task AutoWireChatClient_UseProvidedChatClientAsIs_DoesNotEmitChatSpan_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient, new ChatClientAgentOptions { UseProvidedChatClientAsIs = true });
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        _ = await agent.RunAsync("hi");

        // UseProvidedChatClientAsIs opts out of auto-wiring, so only the invoke_agent span should be emitted.
        var activity = Assert.Single(activities);
        Assert.StartsWith("invoke_agent", activity.DisplayName);
    }

    [Fact]
    public async Task AutoWireChatClient_AlreadyInstrumented_DoesNotDoubleWrap_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        // Pre-wrap with OpenTelemetryChatClient on the same source so spans flow through the tracer.
        IChatClient preWrapped = fakeChatClient.AsBuilder().UseOpenTelemetry(sourceName: sourceName).Build();
        var inner = new ChatClientAgent(preWrapped);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        _ = await agent.RunAsync("hi");

        // Expect exactly 2 activities (one invoke_agent + one chat from the pre-existing wrapper). If we had double-wrapped, we would see 3.
        Assert.Equal(2, activities.Count);
    }

    [Fact]
    public async Task AutoWireChatClient_PreservesUserChatClientFactory_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        bool userFactoryCalled = false;
        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        var runOptions = new ChatClientAgentRunOptions
        {
            ChatClientFactory = cc =>
            {
                userFactoryCalled = true;
                return cc;
            },
        };

        _ = await agent.RunAsync("hi", options: runOptions);

        Assert.True(userFactoryCalled);
        // Auto-wiring should still produce a chat span on top of the user's factory.
        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AutoWireChatClient_PlainAgentRunOptions_PreservesBaseProperties_Async()
    {
        // The auto-wire no longer rewrites the caller's options (the slot below FICC is activated once at
        // construction), so a plain AgentRunOptions reaches the inner agent unchanged with all base
        // properties (AllowBackgroundResponses, AdditionalProperties, ResponseFormat) intact.
        AgentRunOptions? observedOptions = null;
        var fakeChatClient = new AutoWireTestChatClient();
        var innerChatClientAgent = new ChatClientAgent(fakeChatClient);

        // Wrapping agent: surfaces the ChatClientAgent via GetService (so auto-wiring activates),
        // but captures the AgentRunOptions passed to RunAsync by the OpenTelemetryAgent.
        var wrapper = new TestAIAgent
        {
            GetServiceFunc = (type, key) =>
                type == typeof(ChatClientAgent) ? innerChatClientAgent : null,
            RunAsyncFunc = (messages, session, options, ct) =>
            {
                observedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            },
        };

        using var agent = new OpenTelemetryAgent(wrapper);

        var additionalProps = new AdditionalPropertiesDictionary { ["customKey"] = "customValue" };
        var inputOptions = new AgentRunOptions
        {
            AllowBackgroundResponses = true,
            AdditionalProperties = additionalProps,
            ResponseFormat = ChatResponseFormat.Json,
        };

        _ = await agent.RunAsync("hi", options: inputOptions);

        // Options flow through unchanged (same instance, no conversion to ChatClientAgentRunOptions).
        Assert.NotNull(observedOptions);
        Assert.Same(inputOptions, observedOptions);
        Assert.Equal(true, observedOptions.AllowBackgroundResponses);
        Assert.Same(ChatResponseFormat.Json, observedOptions.ResponseFormat);
        Assert.NotNull(observedOptions.AdditionalProperties);
        Assert.Equal("customValue", observedOptions.AdditionalProperties!["customKey"]);
    }

    [Fact]
    public async Task AutoWireChatClient_UserFactoryAddsOwnOTel_CoexistsWithBelowFiccSlot_Async()
    {
        // This is NOT a single model call counted twice. One model call is observed by two independent
        // OpenTelemetry layers, so each layer emits its own "chat" span:
        //   - the framework's slot, always activated below FICC by OpenTelemetryAgent. This below-FICC layer
        //     is what lets FICC emit execute_tool spans, so it must remain even when the caller adds their own
        //     instrumentation. Dropping it to avoid the second span would reintroduce the missing-tool-span bug.
        //   - the caller's per-run ChatClientFactory, which wraps the pipeline above FICC with its own
        //     OpenTelemetryChatClient.
        // The two chat spans nest and measure different scopes (the above-FICC span covers the whole tool loop,
        // the below-FICC span covers each individual model call), so both coexisting is the intended result.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        // User factory wraps the chat client with OpenTelemetryChatClient itself (above FICC).
        var runOptions = new ChatClientAgentRunOptions
        {
            ChatClientFactory = cc => cc.AsBuilder().UseOpenTelemetry(sourceName: sourceName).Build(),
        };

        _ = await agent.RunAsync("hi", options: runOptions);

        // invoke_agent + two chat spans: one from the caller's above-FICC OTel and one from the slot below FICC.
        Assert.Equal(3, activities.Count);
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Equal(2, activities.Count(a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal)));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("\t")]
    public async Task Ctor_NullOrWhitespaceSourceName_AutoWiredChatClientUsesDefaultSource_Async(string? sourceName)
    {
        // Both the agent-level invoke_agent span and the auto-wired chat span must be emitted under
        // OpenTelemetryConsts.DefaultSourceName when the caller passes null, "", or whitespace, so they reach
        // the same ActivitySource and are not silently dropped by the exporter.
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource("Experimental.Microsoft.Agents.AI")
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        _ = await agent.RunAsync("hi");

        Assert.Equal(2, activities.Count);
        Assert.All(activities, a => Assert.Equal("Experimental.Microsoft.Agents.AI", a.Source.Name));
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

#pragma warning disable MEAI001 // ResponseContinuationToken is experimental.
    [Fact]
    public async Task AutoWireChatClient_PlainAgentRunOptions_PreservesContinuationToken_Async()
    {
        // ContinuationToken on a plain AgentRunOptions must reach the inner agent unchanged now that the
        // auto-wire passes the caller's options straight through (no conversion to ChatClientAgentRunOptions).
        AgentRunOptions? observedOptions = null;
        var fakeChatClient = new AutoWireTestChatClient();
        var innerChatClientAgent = new ChatClientAgent(fakeChatClient);

        var wrapper = new TestAIAgent
        {
            GetServiceFunc = (type, key) =>
                type == typeof(ChatClientAgent) ? innerChatClientAgent : null,
            RunAsyncFunc = (messages, session, options, ct) =>
            {
                observedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            },
        };

        using var agent = new OpenTelemetryAgent(wrapper);

        var token = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        var inputOptions = new AgentRunOptions
        {
            ContinuationToken = token,
        };

        _ = await agent.RunAsync("hi", options: inputOptions);

        Assert.NotNull(observedOptions);
        Assert.Same(inputOptions, observedOptions);
        Assert.Same(token, observedOptions.ContinuationToken);
    }
#pragma warning restore MEAI001

    [Fact]
    public async Task AutoWireChatClient_ChatClientAgentRunOptions_NoUserFactory_PreservesChatOptions_Async()
    {
        // When the caller passes a ChatClientAgentRunOptions without a ChatClientFactory, the auto-wiring
        // must clone (not mutate) the caller's options, set the factory, and preserve nested ChatOptions.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        ChatOptions? observedChatOptions = null;
        var fakeChatClient = new AutoWireTestChatClient
        {
            OnGetResponseAsync = (msgs, opts) => observedChatOptions = opts,
        };
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        var inputChatOptions = new ChatOptions { Temperature = 0.42f, ModelId = "test-model" };
        var inputOptions = new ChatClientAgentRunOptions(inputChatOptions);

        _ = await agent.RunAsync("hi", options: inputOptions);

        // Caller's options must not have been mutated (no factory installed on the caller's instance).
        Assert.Null(inputOptions.ChatClientFactory);

        // Inner chat client must observe the caller-supplied ChatOptions.
        Assert.NotNull(observedChatOptions);
        Assert.Equal(0.42f, observedChatOptions!.Temperature);
        Assert.Equal("test-model", observedChatOptions.ModelId);

        // Auto-wiring still produces a chat span.
        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AutoWireChatClient_StreamingDisabled_DoesNotEmitChatSpan_Async()
    {
        // Symmetry with AutoWireChatClient_Disabled_DoesNotEmitChatSpan_Async for the streaming path.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName, autoWireChatClient: false);

        await foreach (var _ in agent.RunStreamingAsync("hi"))
        {
        }

        var activity = Assert.Single(activities);
        Assert.StartsWith("invoke_agent", activity.DisplayName);
    }

    [Fact]
    public async Task AutoWireChatClient_PlainAgentRunOptions_RealChatClientAgent_EmitsChatSpan_Async()
    {
        // High-level callers may pass the abstract base AgentRunOptions (not ChatClientAgentRunOptions) when
        // wiring a ChatClientAgent. Auto-wiring must still kick in: convert to ChatClientAgentRunOptions,
        // install the OTel-wrapping factory, and produce both the invoke_agent and chat spans end-to-end.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        ChatOptions? observedChatOptions = null;
        var fakeChatClient = new AutoWireTestChatClient
        {
            OnGetResponseAsync = (_, opts) => observedChatOptions = opts,
        };
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        // Pass the base AgentRunOptions, not ChatClientAgentRunOptions.
        var inputOptions = new AgentRunOptions { AllowBackgroundResponses = false };

        _ = await agent.RunAsync("hi", options: inputOptions);

        // Inner chat client was actually invoked (auto-wired factory ran without breaking the pipeline).
        Assert.NotNull(observedChatOptions);

        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AutoWireChatClient_PlainAgentRunOptions_RealChatClientAgent_StreamingEmitsChatSpan_Async()
    {
        // Same as the sync test above but for the streaming path so both invocation paths
        // are covered when callers pass a base AgentRunOptions.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        ChatOptions? observedChatOptions = null;
        var fakeChatClient = new AutoWireTestChatClient
        {
            OnGetResponseAsync = (_, opts) => observedChatOptions = opts,
        };
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        var inputOptions = new AgentRunOptions { AllowBackgroundResponses = false };

        await foreach (var _ in agent.RunStreamingAsync("hi", options: inputOptions))
        {
        }

        Assert.NotNull(observedChatOptions);

        Assert.Equal(2, activities.Count);
        Assert.Contains(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task AutoWireChatClient_EnableSensitiveData_PropagatedToInnerChatClient_Async(bool enableSensitiveData, bool streaming)
    {
        // Regression test (issue #5873): when EnableSensitiveData is set on OpenTelemetryAgent, the auto-wired
        // inner OpenTelemetryChatClient (the below-FICC slot) must also have EnableSensitiveData propagated to it,
        // so the inner chat span captures gen_ai.input.messages / gen_ai.output.messages. The agent sets the value
        // on the slot after construction, since EnableSensitiveData is typically set via the UseOpenTelemetry callback.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var fakeChatClient = new AutoWireTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient);
        using var agent = new OpenTelemetryAgent(inner, sourceName) { EnableSensitiveData = enableSensitiveData };

        if (streaming)
        {
            await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "hello")]))
            {
            }
        }
        else
        {
            _ = await agent.RunAsync([new ChatMessage(ChatRole.User, "hello")]);
        }

        // There should be 2 activities: the invoke_agent span and the inner chat span.
        Assert.Equal(2, activities.Count);

        var chatSpan = activities.Single(a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
        var chatTags = chatSpan.Tags.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);

        if (enableSensitiveData)
        {
            // When EnableSensitiveData=true on the outer agent, the auto-wired inner client must also
            // capture message content in the chat span.
            Assert.True(chatTags.ContainsKey("gen_ai.input.messages"), "gen_ai.input.messages must be present in the inner chat span when EnableSensitiveData=true");
            Assert.True(chatTags.ContainsKey("gen_ai.output.messages"), "gen_ai.output.messages must be present in the inner chat span when EnableSensitiveData=true");
        }
        else
        {
            // By default (EnableSensitiveData=false) message content must NOT be captured.
            Assert.False(chatTags.ContainsKey("gen_ai.input.messages"), "gen_ai.input.messages must NOT be present in the inner chat span when EnableSensitiveData=false");
            Assert.False(chatTags.ContainsKey("gen_ai.output.messages"), "gen_ai.output.messages must NOT be present in the inner chat span when EnableSensitiveData=false");
        }
    }

    [Fact]
    public async Task AutoWireChatClient_EmitsExecuteToolSpans_Async()
    {
        // The core of the OTel-below-FICC fix: with the slot active below FICC, the inner chat span closes
        // before FICC invokes tools, so Activity.Current is the invoke_agent span and FICC emits an
        // execute_tool span on the agent source, parented under invoke_agent.
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var tool = AIFunctionFactory.Create(() => "sunny", "get_weather");
        var fakeChatClient = new ToolCallingTestChatClient();
        var inner = new ChatClientAgent(fakeChatClient, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [tool] },
        });
        using var agent = new OpenTelemetryAgent(inner, sourceName);

        _ = await agent.RunAsync("weather?");

        var invokeAgent = Assert.Single(activities, a => a.DisplayName.StartsWith("invoke_agent", StringComparison.Ordinal));
        var executeTool = Assert.Single(activities, a => a.DisplayName.StartsWith("execute_tool", StringComparison.Ordinal));
        Assert.Equal(sourceName, executeTool.Source.Name);
        Assert.Equal(invokeAgent.SpanId, executeTool.ParentSpanId);
        Assert.Contains(activities, a => string.Equals(a.GetTagItem("gen_ai.operation.name") as string, "chat", StringComparison.Ordinal));
    }

    [Fact]
    public async Task DeferredOpenTelemetryChatClient_InertUntilActivated_Async()
    {
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var leaf = new AutoWireTestChatClient();
        using var slot = new DeferredOpenTelemetryChatClient(leaf);

        // Inert: resolves itself for its own type and forwards other lookups to the inner client. The bare
        // leaf is not instrumented, so the OpenTelemetryChatClient lookup is null and no span is emitted.
        Assert.False(slot.IsActive);
        Assert.Same(slot, slot.GetService(typeof(DeferredOpenTelemetryChatClient)));
        Assert.Null(slot.GetService(typeof(OpenTelemetryChatClient)));
        _ = await slot.GetResponseAsync("hi");
        Assert.Empty(activities);

        // Active: routes through an OpenTelemetryChatClient that emits a chat span on the source.
        slot.Activate(sourceName);
        Assert.True(slot.IsActive);
        Assert.NotNull(slot.GetService(typeof(OpenTelemetryChatClient)));
        _ = await slot.GetResponseAsync("hi");
        var chat = Assert.Single(activities);
        Assert.Equal("chat", chat.GetTagItem("gen_ai.operation.name") as string);

        // Idempotent: a second activation does not replace the existing wrapper.
        var target = slot.GetService(typeof(OpenTelemetryChatClient));
        slot.Activate(sourceName);
        Assert.Same(target, slot.GetService(typeof(OpenTelemetryChatClient)));
    }

    private sealed class AutoWireTestChatClient : IChatClient
    {
        public Action<IEnumerable<ChatMessage>, ChatOptions?>? OnGetResponseAsync { get; set; }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.OnGetResponseAsync?.Invoke(messages, options);
            return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok")));
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.OnGetResponseAsync?.Invoke(messages, options);
            await Task.Yield();
            yield return new ChatResponseUpdate(ChatRole.Assistant, "ok");
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType?.IsInstanceOfType(this) == true ? this : null;

        public void Dispose() { }
    }

    private sealed class ToolCallingTestChatClient : IChatClient
    {
        private int _callCount;

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            // First call returns a tool call so FICC invokes the tool; the second call returns the final text.
            if (Interlocked.Increment(ref this._callCount) == 1)
            {
                var call = new FunctionCallContent("call_1", "get_weather", new Dictionary<string, object?>());
                return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, [call])));
            }

            return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (Interlocked.Increment(ref this._callCount) == 1)
            {
                yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call_1", "get_weather", new Dictionary<string, object?>())]);
                await Task.Yield();
                yield break;
            }

            await Task.Yield();
            yield return new ChatResponseUpdate(ChatRole.Assistant, "done");
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType?.IsInstanceOfType(this) == true ? this : null;

        public void Dispose() { }
    }

    #endregion
}
