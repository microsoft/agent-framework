// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

namespace Microsoft.Agents.Orchestration.UnitTest;

/// <summary>
/// Tests for the <see cref="HandoffOrchestration"/> class.
/// </summary>
public sealed class HandoffOrchestrationTests : IDisposable
{
    private readonly List<IDisposable> _disposables;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestrationTests"/> class.
    /// </summary>
    public HandoffOrchestrationTests()
    {
        this._disposables = [];
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        foreach (IDisposable disposable in this._disposables)
        {
            disposable.Dispose();
        }
        GC.SuppressFinalize(this);
    }

    [Fact]
    public async Task HandoffOrchestrationWithSingleAgentAsync()
    {
        // Arrange
        AIAgent mockAgent1 =
            this.CreateMockAgent(
                "Agent1",
                "Test Agent",
                Responses.Message("Final response"));

        // Act: Create and execute the orchestration
        string response = await ExecuteOrchestrationAsync(Handoffs.StartWith(mockAgent1));

        // Assert
        Assert.Equal("Final response", response);
    }

    [Fact(Skip = "Incomplete mock responses")]
    public async Task HandoffOrchestrationWithMultipleAgentsAsync()
    {
        // Arrange
        AIAgent mockAgent1 =
            this.CreateMockAgent(
                "Agent1",
                "Test Agent",
                Responses.Handoff("Agent2"));
        AIAgent mockAgent2 =
            this.CreateMockAgent(
                "Agent2",
                "Test Agent",
                Responses.Result("Final response"));
        AIAgent mockAgent3 =
            this.CreateMockAgent(
                "Agent3",
                "Test Agent",
                Responses.Message("Wrong response"));

        // Act: Create and execute the orchestration
        string response = await ExecuteOrchestrationAsync(
            Handoffs
                .StartWith(mockAgent1)
                .Add(mockAgent1, [mockAgent2, mockAgent3]));

        // Assert
        Assert.Equal("Final response", response);
    }

    private static async Task<string> ExecuteOrchestrationAsync(Handoffs handoffs)
    {
        // Arrange
        HandoffOrchestration orchestration = new(handoffs);

        // Act
        const string InitialInput = "123";
        AgentRunResponse result = await orchestration.RunAsync(InitialInput);

        // Assert
        Assert.NotNull(result);

        // Act
        return result.Text;
    }

    private ChatClientAgent CreateMockAgent(string name, string description, params string[] responses)
    {
        HttpMessageHandlerStub messageHandlerStub = new();
        foreach (string response in responses)
        {
            HttpResponseMessage responseMessage =
                new()
                {
                    StatusCode = System.Net.HttpStatusCode.OK,
                    Content = new StringContent(response),
                };
            messageHandlerStub.ResponseQueue.Enqueue(responseMessage);
            this._disposables.Add(responseMessage);
        }
        HttpClient httpClient = new(messageHandlerStub, disposeHandler: false);

        this._disposables.Add(messageHandlerStub);
        this._disposables.Add(httpClient);

        OpenAIClientOptions clientOptions =
            new()
            {
                Transport = new HttpClientPipelineTransport(httpClient),
                RetryPolicy = new ClientRetryPolicy(maxRetries: 0),
                NetworkTimeout = Timeout.InfiniteTimeSpan,
            };
        IChatClient chatClient =
            new OpenAIClient(new ApiKeyCredential("fake-key"), clientOptions)
                .GetChatClient("Any Model")
                .AsIChatClient()
                .AsBuilder()
                .UseFunctionInvocation()
                .Build();

        ChatClientAgentOptions agentOptions = new() { Name = name, Description = description };
        return new(chatClient, agentOptions);
    }

    private static class Responses
    {
        public static string Message(string content) =>
            $$$"""            
            {
              "id": "chat-123",
              "object": "chat.completion",
              "created": 1699482945,
              "model": "gpt-4.1",
              "choices": [
                {
                  "index": 0,
                  "message": {
                    "role": "assistant",
                    "content": "{{{content}}}",
                    "tool_calls":[]
                  }
                }
              ],
              "usage": {
                "prompt_tokens": 52,
                "completion_tokens": 1,
                "total_tokens": 53
              }
            }      
            """;

        public static string Handoff(string agentName) =>
            $$$"""            
            {
              "id": "chat-123",
              "object": "chat.completion",
              "created": 1699482945,
              "model": "gpt-4.1",
              "choices": [
                {
                  "index": 0,
                  "message": {
                    "role": "assistant",
                    "content": null,
                    "tool_calls":[{
                        "id": "1",
                        "type": "function",
                        "function": {
                          "name": "transfer_to_{{{agentName}}}",
                          "arguments": "{}"
                        }
                      }
                    ]
                  }
                }
              ],
              "usage": {
                "prompt_tokens": 52,
                "completion_tokens": 1,
                "total_tokens": 53
              }
            }      
            """;

        public static string Result(string summary) =>
            $$$"""            
            {
              "id": "chat-234",
              "object": "chat.completion",
              "created": 1699482945,
              "model": "gpt-4.1",
              "choices": [
                {
                  "index": 0,
                  "message": {
                    "role": "assistant",
                    "content": null,
                    "tool_calls":[{
                        "id": "1",
                        "type": "function",
                        "function": {
                          "name": "end_task_with_summary",
                          "arguments": "{ \"summary\": \"{{{summary}}}\" }"
                        }
                      }
                    ]
                  }
                }
              ]
            }      
            """;
    }
}
