// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed record TestRequestAgentThreadState(JsonElement ThreadState, Dictionary<string, PortableValue> UnservicedRequests, HashSet<string> ServicedRequests, HashSet<string> PairedRequests);

public enum TestAgentRequestType
{
    FunctionCall,
    UserInputRequest
}

internal sealed class TestRequestAgent(TestAgentRequestType requestType, int unpairedRequestCount, int pairedRequestCount, string? id, string? name) : AIAgent
{
    public Random RNG { get; set; } = new Random(HashCode.Combine(requestType, nameof(TestRequestAgent)));

    public AgentThread? LastThread { get; set; }

    protected override string? IdCore => id;
    public override string? Name => name;

    public override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken)
        => new(requestType switch
        {
            TestAgentRequestType.FunctionCall => new TestRequestAgentThread<FunctionCallContent, FunctionResultContent>(),
            TestAgentRequestType.UserInputRequest => new TestRequestAgentThread<UserInputRequestContent, UserInputResponseContent>(),
            _ => throw new NotSupportedException(),
        });

    public override ValueTask<AgentThread> DeserializeThreadAsync(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(requestType switch
        {
            TestAgentRequestType.FunctionCall => new TestRequestAgentThread<FunctionCallContent, FunctionResultContent>(),
            TestAgentRequestType.UserInputRequest => new TestRequestAgentThread<UserInputRequestContent, UserInputResponseContent>(),
            _ => throw new NotSupportedException(),
        });

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, thread, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

    private static int[] SampleIndicies(Random rng, int n, int c)
    {
        int[] result = Enumerable.Range(0, c).ToArray();

        for (int i = c; i < n; i++)
        {
            int radix = rng.Next(i);
            if (radix < c)
            {
                result[radix] = i;
            }
        }

        return result;
    }

    private async IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync<TRequest, TResponse>(
                IRequestResponseStrategy<TRequest, TResponse> strategy,
                IEnumerable<ChatMessage> messages,
                AgentThread? thread = null,
                AgentRunOptions? options = null,
                [EnumeratorCancellation] CancellationToken cancellationToken = default)
                    where TRequest : AIContent
                    where TResponse : AIContent
    {
        this.LastThread = thread ??= await this.GetNewThreadAsync(cancellationToken);
        TestRequestAgentThread<TRequest, TResponse> traThread = ConvertThread<TRequest, TResponse>(thread);

        if (traThread.HasSentRequests)
        {
            foreach (TResponse response in messages.SelectMany(message => message.Contents).OfType<TResponse>())
            {
                strategy.ProcessResponse(response, traThread);
            }

            if (traThread.UnservicedRequests.Count == 0)
            {
                yield return new(ChatRole.Assistant, "Done");
            }
            else
            {
                yield return new(ChatRole.Assistant, $"Remaining: {traThread.UnservicedRequests.Count}");
            }
        }
        else
        {
            int totalRequestCount = unpairedRequestCount + pairedRequestCount;
            yield return new(ChatRole.Assistant, $"Creating {totalRequestCount} requests, {pairedRequestCount} paired.");

            HashSet<int> servicedIndicies = [.. SampleIndicies(this.RNG, totalRequestCount, pairedRequestCount)];

            (string, TRequest)[] requests = strategy.CreateRequests(unpairedRequestCount + pairedRequestCount).ToArray();
            List<AIContent> pairedResponses = new(capacity: pairedRequestCount);

            for (int i = 0; i < requests.Length; i++)
            {
                (string id, TRequest request) = requests[i];
                if (servicedIndicies.Contains(i))
                {
                    traThread.PairedRequests.Add(id);
                    pairedResponses.Add(strategy.CreatePairedResponse(request));
                }
                else
                {
                    traThread.UnservicedRequests.Add(id, request);
                }

                yield return new(ChatRole.Assistant, [request]);
            }

            yield return new(ChatRole.Assistant, pairedResponses);

            traThread.HasSentRequests = true;
        }
    }

    private static TestRequestAgentThread<TRequest, TResponse> ConvertThread<TRequest, TResponse>(AgentThread thread)
        where TRequest : AIContent
        where TResponse : AIContent
    {
        if (thread is not TestRequestAgentThread<TRequest, TResponse> traThread)
        {
            throw new ArgumentException($"Bad AgentThread type: Expected {typeof(TestRequestAgentThread<TRequest, TResponse>)}, got {thread.GetType()}.", nameof(thread));
        }

        return traThread;
    }

    private sealed class FunctionCallStrategy : IRequestResponseStrategy<FunctionCallContent, FunctionResultContent>
    {
        public FunctionResultContent CreatePairedResponse(FunctionCallContent request)
        {
            return new FunctionResultContent(request.CallId, request);
        }

        public IEnumerable<(string, FunctionCallContent)> CreateRequests(int count)
        {
            for (int i = 0; i < count; i++)
            {
                string callId = Guid.NewGuid().ToString("N");
                FunctionCallContent request = new(callId, "TestFunction");
                yield return (callId, request);
            }
        }

        public void ProcessResponse(FunctionResultContent response, TestRequestAgentThread<FunctionCallContent, FunctionResultContent> thread)
        {
            if (thread.UnservicedRequests.TryGetValue(response.CallId, out FunctionCallContent? request))
            {
                response.Result.As<FunctionCallContent>().Should().Be(request);
                thread.ServicedRequests.Add(response.CallId);
                thread.UnservicedRequests.Remove(response.CallId);
            }
            else if (thread.ServicedRequests.Contains(response.CallId))
            {
                throw new InvalidOperationException($"Seeing duplicate response with id {response.CallId}");
            }
            else if (thread.PairedRequests.Contains(response.CallId))
            {
                throw new InvalidOperationException($"Seeing explicit response to initially paired request with id {response.CallId}");
            }
            else
            {
                throw new InvalidOperationException($"Seeing response to nonexistent request with id {response.CallId}");
            }
        }
    }

    private sealed class FunctionApprovalStrategy : IRequestResponseStrategy<UserInputRequestContent, UserInputResponseContent>
    {
        public UserInputResponseContent CreatePairedResponse(UserInputRequestContent request)
        {
            if (request is not FunctionApprovalRequestContent approvalRequest)
            {
                throw new InvalidOperationException($"Invalid request: Expecting {typeof(FunctionApprovalResponseContent)}, got {request.GetType()}");
            }

            return new FunctionApprovalResponseContent(approvalRequest.Id, true, approvalRequest.FunctionCall);
        }

        public IEnumerable<(string, UserInputRequestContent)> CreateRequests(int count)
        {
            for (int i = 0; i < count; i++)
            {
                string id = Guid.NewGuid().ToString("N");
                UserInputRequestContent request = new FunctionApprovalRequestContent(id, new(id, "TestFunction"));
                yield return (id, request);
            }
        }

        public void ProcessResponse(UserInputResponseContent response, TestRequestAgentThread<UserInputRequestContent, UserInputResponseContent> thread)
        {
            if (thread.UnservicedRequests.TryGetValue(response.Id, out UserInputRequestContent? request))
            {
                if (request is not FunctionApprovalRequestContent approvalRequest)
                {
                    throw new InvalidOperationException($"Invalid request: Expecting {typeof(FunctionApprovalResponseContent)}, got {request.GetType()}");
                }

                if (response is not FunctionApprovalResponseContent approvalResponse)
                {
                    throw new InvalidOperationException($"Invalid response: Expecting {typeof(FunctionApprovalResponseContent)}, got {response.GetType()}");
                }

                approvalResponse.Approved.Should().BeTrue();
                approvalResponse.FunctionCall.As<FunctionCallContent>().Should().Be(approvalRequest.FunctionCall);
                thread.ServicedRequests.Add(response.Id);
                thread.UnservicedRequests.Remove(response.Id);
            }
            else if (thread.ServicedRequests.Contains(response.Id))
            {
                throw new InvalidOperationException($"Seeing duplicate response with id {response.Id}");
            }
            else if (thread.PairedRequests.Contains(response.Id))
            {
                throw new InvalidOperationException($"Seeing explicit response to initially paired request with id {response.Id}");
            }
            else
            {
                throw new InvalidOperationException($"Seeing response to nonexistent request with id {response.Id}");
            }
        }
    }

    private interface IRequestResponseStrategy<TRequest, TResponse>
        where TRequest : AIContent
        where TResponse : AIContent
    {
        IEnumerable<(string, TRequest)> CreateRequests(int count);
        TResponse CreatePairedResponse(TRequest request);

        void ProcessResponse(TResponse response, TestRequestAgentThread<TRequest, TResponse> thread);
    }

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return requestType switch
        {
            TestAgentRequestType.FunctionCall => this.RunStreamingAsync(new FunctionCallStrategy(), messages, thread, options, cancellationToken),
            TestAgentRequestType.UserInputRequest => this.RunStreamingAsync(new FunctionApprovalStrategy(), messages, thread, options, cancellationToken),
            _ => throw new NotSupportedException($"Unknown AgentRequestType {requestType}"),
        };
    }

    private static string RetrieveId<TRequest>(TRequest request)
        where TRequest : AIContent
    {
        return request switch
        {
            FunctionCallContent functionCall => functionCall.CallId,
            UserInputRequestContent userInputRequest => userInputRequest.Id,
            _ => throw new NotSupportedException($"Unknown request type {typeof(TRequest)}"),
        };
    }

    private IEnumerable<TResponse> ValidateUnpairedRequests<TRequest, TResponse>(IEnumerable<TRequest> requests, IRequestResponseStrategy<TRequest, TResponse> strategy)
        where TRequest : AIContent
        where TResponse : AIContent
    {
        this.LastThread.Should().NotBeNull();
        TestRequestAgentThread<TRequest, TResponse> traThread = ConvertThread<TRequest, TResponse>(this.LastThread);

        requests.Should().HaveCount(traThread.UnservicedRequests.Count);
        foreach (TRequest request in requests)
        {
            string requestId = RetrieveId(request);
            traThread.UnservicedRequests.Should().ContainKey(requestId);
            yield return strategy.CreatePairedResponse(request);
        }
    }

    internal IEnumerable<object> ValidateUnpairedRequests<TRequest>(IEnumerable<TRequest> requests)
        where TRequest : AIContent
    {
        switch (requestType)
        {
            case TestAgentRequestType.FunctionCall:
                if (typeof(TRequest) != typeof(FunctionCallContent))
                {
                    throw new ArgumentException($"Invalid request type: Expected {typeof(FunctionCallContent)}, got {typeof(TRequest)}", nameof(requests));
                }

                return this.ValidateUnpairedRequests((IEnumerable<FunctionCallContent>)requests, new FunctionCallStrategy());
            case TestAgentRequestType.UserInputRequest:
                if (!typeof(UserInputRequestContent).IsAssignableFrom(typeof(TRequest)))
                {
                    throw new ArgumentException($"Invalid request type: Expected {typeof(UserInputRequestContent)}, got {typeof(TRequest)}", nameof(requests));
                }

                return this.ValidateUnpairedRequests((IEnumerable<UserInputRequestContent>)requests, new FunctionApprovalStrategy());
            default:
                throw new NotSupportedException($"Unknown AgentRequestType {requestType}");
        }
    }

    internal IEnumerable<ExternalResponse> ValidateUnpairedRequests(List<ExternalRequest> requests)
    {
        List<object> responses;
        switch (requestType)
        {
            case TestAgentRequestType.FunctionCall:
                responses = this.ValidateUnpairedRequests(requests.Select(AssertAndExtractRequestContent<FunctionCallContent>)).ToList();
                break;
            case TestAgentRequestType.UserInputRequest:
                responses = this.ValidateUnpairedRequests(requests.Select(AssertAndExtractRequestContent<UserInputRequestContent>)).ToList();
                break;
            default:
                throw new NotSupportedException($"Unknown AgentRequestType {requestType}");
        }

        return Enumerable.Zip(requests, responses, (ExternalRequest request, object response) => request.CreateResponse(response));

        static TRequest AssertAndExtractRequestContent<TRequest>(ExternalRequest request)
        {
            request.DataIs(out TRequest? content).Should().BeTrue();
            return content!;
        }
    }

    private sealed class TestRequestAgentThread<TRequest, TResponse> : InMemoryAgentThread
        where TRequest : AIContent
        where TResponse : AIContent
    {
        public TestRequestAgentThread()
        {
        }

        public bool HasSentRequests { get; set; }
        public Dictionary<string, TRequest> UnservicedRequests { get; } = new();
        public HashSet<string> ServicedRequests { get; } = new();
        public HashSet<string> PairedRequests { get; } = new();

        private static JsonElement DeserializeAndExtractState(JsonElement serializedState,
                                                              out TestRequestAgentThreadState state,
                                                              JsonSerializerOptions? jsonSerializerOptions = null)
        {
            state = JsonSerializer.Deserialize<TestRequestAgentThreadState>(serializedState, jsonSerializerOptions)
                 ?? throw new ArgumentException("Unable to deserialize thread state.");

            return state.ThreadState;
        }

        public TestRequestAgentThread(JsonElement element, JsonSerializerOptions? jsonSerializerOptions = null)
            : base(DeserializeAndExtractState(element, out TestRequestAgentThreadState state, jsonSerializerOptions))
        {
            this.UnservicedRequests = state.UnservicedRequests.ToDictionary(
                keySelector: item => item.Key,
                elementSelector: item => item.Value.As<TRequest>()!);

            this.ServicedRequests = state.ServicedRequests;
            this.PairedRequests = state.PairedRequests;
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        {
            JsonElement threadState = base.Serialize(jsonSerializerOptions);

            Dictionary<string, PortableValue> portableUnservicedRequests =
                this.UnservicedRequests.ToDictionary(
                    keySelector: item => item.Key,
                    elementSelector: item => new PortableValue(item.Value));

            TestRequestAgentThreadState state = new(threadState, portableUnservicedRequests, this.ServicedRequests, this.PairedRequests);

            return JsonSerializer.SerializeToElement(state, jsonSerializerOptions);
        }
    }
}
