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

internal sealed record TestRequestAgentSessionState(JsonElement SessionState, Dictionary<string, PortableValue> UnservicedRequests, HashSet<string> ServicedRequests, HashSet<string> PairedRequests);

public enum TestAgentRequestType
{
    FunctionCall,
    UserInputRequest
}

internal sealed class TestRequestAgent(TestAgentRequestType requestType, int unpairedRequestCount, int pairedRequestCount, string? id, string? name) : AIAgent
{
    public Random RNG { get; set; } = new Random(HashCode.Combine(requestType, nameof(TestRequestAgent)));

    public AgentSession? LastSession { get; set; }

    protected override string? IdCore => id;
    public override string? Name => name;

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken)
        => new(requestType switch
        {
            TestAgentRequestType.FunctionCall => new TestRequestAgentSession<FunctionCallContent, FunctionResultContent>(),
            TestAgentRequestType.UserInputRequest => new TestRequestAgentSession<UserInputRequestContent, UserInputResponseContent>(),
            _ => throw new NotSupportedException(),
        });

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(requestType switch
        {
            TestAgentRequestType.FunctionCall => new TestRequestAgentSession<FunctionCallContent, FunctionResultContent>(),
            TestAgentRequestType.UserInputRequest => new TestRequestAgentSession<UserInputRequestContent, UserInputResponseContent>(),
            _ => throw new NotSupportedException(),
        });

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => default;

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

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
                AgentSession? session = null,
                AgentRunOptions? options = null,
                [EnumeratorCancellation] CancellationToken cancellationToken = default)
                    where TRequest : AIContent
                    where TResponse : AIContent
    {
        this.LastSession = session ??= await this.CreateSessionAsync(cancellationToken);
        TestRequestAgentSession<TRequest, TResponse> traSessin = ConvertSession<TRequest, TResponse>(session);

        if (traSessin.HasSentRequests)
        {
            foreach (TResponse response in messages.SelectMany(message => message.Contents).OfType<TResponse>())
            {
                strategy.ProcessResponse(response, traSessin);
            }

            if (traSessin.UnservicedRequests.Count == 0)
            {
                yield return new(ChatRole.Assistant, "Done");
            }
            else
            {
                yield return new(ChatRole.Assistant, $"Remaining: {traSessin.UnservicedRequests.Count}");
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
                    traSessin.PairedRequests.Add(id);
                    pairedResponses.Add(strategy.CreatePairedResponse(request));
                }
                else
                {
                    traSessin.UnservicedRequests.Add(id, request);
                }

                yield return new(ChatRole.Assistant, [request]);
            }

            yield return new(ChatRole.Assistant, pairedResponses);

            traSessin.HasSentRequests = true;
        }
    }

    private static TestRequestAgentSession<TRequest, TResponse> ConvertSession<TRequest, TResponse>(AgentSession session)
        where TRequest : AIContent
        where TResponse : AIContent
    {
        if (session is not TestRequestAgentSession<TRequest, TResponse> traSession)
        {
            throw new ArgumentException($"Bad AgentSession type: Expected {typeof(TestRequestAgentSession<TRequest, TResponse>)}, got {session.GetType()}.", nameof(session));
        }

        return traSession;
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

        public void ProcessResponse(FunctionResultContent response, TestRequestAgentSession<FunctionCallContent, FunctionResultContent> session)
        {
            if (session.UnservicedRequests.TryGetValue(response.CallId, out FunctionCallContent? request))
            {
                response.Result.As<FunctionCallContent>().Should().Be(request);
                session.ServicedRequests.Add(response.CallId);
                session.UnservicedRequests.Remove(response.CallId);
            }
            else if (session.ServicedRequests.Contains(response.CallId))
            {
                throw new InvalidOperationException($"Seeing duplicate response with id {response.CallId}");
            }
            else if (session.PairedRequests.Contains(response.CallId))
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

        public void ProcessResponse(UserInputResponseContent response, TestRequestAgentSession<UserInputRequestContent, UserInputResponseContent> session)
        {
            if (session.UnservicedRequests.TryGetValue(response.Id, out UserInputRequestContent? request))
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
                session.ServicedRequests.Add(response.Id);
                session.UnservicedRequests.Remove(response.Id);
            }
            else if (session.ServicedRequests.Contains(response.Id))
            {
                throw new InvalidOperationException($"Seeing duplicate response with id {response.Id}");
            }
            else if (session.PairedRequests.Contains(response.Id))
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

        void ProcessResponse(TResponse response, TestRequestAgentSession<TRequest, TResponse> session);
    }

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return requestType switch
        {
            TestAgentRequestType.FunctionCall => this.RunStreamingAsync(new FunctionCallStrategy(), messages, session, options, cancellationToken),
            TestAgentRequestType.UserInputRequest => this.RunStreamingAsync(new FunctionApprovalStrategy(), messages, session, options, cancellationToken),
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
        this.LastSession.Should().NotBeNull();
        TestRequestAgentSession<TRequest, TResponse> traSession = ConvertSession<TRequest, TResponse>(this.LastSession);

        requests.Should().HaveCount(traSession.UnservicedRequests.Count);
        foreach (TRequest request in requests)
        {
            string requestId = RetrieveId(request);
            traSession.UnservicedRequests.Should().ContainKey(requestId);
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
            request.TryGetDataAs(out TRequest? content).Should().BeTrue();
            return content!;
        }
    }

    private sealed class TestRequestAgentSession<TRequest, TResponse> : AgentSession
        where TRequest : AIContent
        where TResponse : AIContent
    {
        public TestRequestAgentSession()
        {
        }

        public bool HasSentRequests { get; set; }
        public Dictionary<string, TRequest> UnservicedRequests { get; } = new();
        public HashSet<string> ServicedRequests { get; } = new();
        public HashSet<string> PairedRequests { get; } = new();

        public TestRequestAgentSession(JsonElement element, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            var state = JsonSerializer.Deserialize<TestRequestAgentSessionState>(element, jsonSerializerOptions)
                 ?? throw new ArgumentException("Unable to deserialize session state.");

            this.StateBag = AgentSessionStateBag.Deserialize(state.SessionState);

            this.UnservicedRequests = state.UnservicedRequests.ToDictionary(
                keySelector: item => item.Key,
                elementSelector: item => item.Value.As<TRequest>()!);

            this.ServicedRequests = state.ServicedRequests;
            this.PairedRequests = state.PairedRequests;
        }

        internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        {
            JsonElement sessionState = this.StateBag.Serialize();

            Dictionary<string, PortableValue> portableUnservicedRequests =
                this.UnservicedRequests.ToDictionary(
                    keySelector: item => item.Key,
                    elementSelector: item => new PortableValue(item.Value));

            TestRequestAgentSessionState state = new(sessionState, portableUnservicedRequests, this.ServicedRequests, this.PairedRequests);

            return JsonSerializer.SerializeToElement(state, jsonSerializerOptions);
        }
    }
}
