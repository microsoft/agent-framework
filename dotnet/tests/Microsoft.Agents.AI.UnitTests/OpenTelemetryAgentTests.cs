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
        Assert.Equal(innerAgent.DisplayName, agent.DisplayName);
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

            RunAsyncFunc = async (messages, thread, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "The blue whale, I think."))
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

        async static IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();

            foreach (string text in new[] { "The ", "blue ", "whale,", " ", "", "I", " think." })
            {
                await Task.Yield();
                yield return new AgentRunResponseUpdate(ChatRole.Assistant, text)
                {
                    ResponseId = "id123",
                };
            }

            yield return new AgentRunResponseUpdate
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

        Assert.Equal("invoke_agent TestAgent", activity.DisplayName);
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

            RunAsyncFunc = async (messages, thread, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "The blue whale, I think."))
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

        async static IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();

            foreach (string text in new[] { "The ", "blue ", "whale,", " ", "", "I", " think." })
            {
                await Task.Yield();
                yield return new AgentRunResponseUpdate(ChatRole.Assistant, text)
                {
                    ResponseId = "id123",
                };
            }

            yield return new AgentRunResponseUpdate
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

        Assert.Equal($"invoke_agent {innerAgent.DisplayName}", activity.DisplayName);
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
                    "type": "web_search"
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
            Assert.False(tags.ContainsKey("gen_ai.tool.definitions"));
        }
    }

    private static string ReplaceWhitespace(string? input) => Regex.Replace(input ?? "", @"\s+", "").Trim();
}
