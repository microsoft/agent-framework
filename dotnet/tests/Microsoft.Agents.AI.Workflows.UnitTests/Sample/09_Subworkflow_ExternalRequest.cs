// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal sealed record class UserRequest(string RequestType, string Type, int Amount, string Id, string? Priority = null, string? PolicyType = null)
{
    internal static int RequestCount;

    public static string CreateId()
    {
        string result = Interlocked.Increment(ref RequestCount).ToString();
        Console.Error.WriteLine($"Got Id: {result}");
        return result;
    }

    public static UserRequest CreateResourceRequest(string resourceType = "cpu", int amount = 1, string priority = "normal")
    {
        UserRequest request = new("resource", resourceType, amount, Priority: priority, Id: CreateId());
        Console.Error.WriteLine($"\t{request}");
        return request;
    }

    public static UserRequest CreatePolicyCheckRequest(string resourceType = "cpu", int amount = 1, string policyType = "quota")
    {
        UserRequest request = new("policy", resourceType, amount, PolicyType: policyType, Id: CreateId());
        Console.Error.WriteLine($"\t{request}");
        return request;
    }

    public ResourceResponse CreateResourceResponse(int allocated, string source)
        => new(this.Id, this.Type, allocated, source);

    public PolicyResponse CreatePolicyResponse(bool approved, string reason)
        => new(this.Id, approved, reason);

    public RequestFinished CreateExpected(ResourceResponse response)
        => new(this.Id, RequestType: "resource", ResourceResponse: response with { Id = this.Id });

    public RequestFinished CreateExpectedResourceResponse(int allocated, string source)
        => this.CreateExpected(this.CreateResourceResponse(allocated, source));

    public RequestFinished CreateExpected(PolicyResponse response)
        => new(this.Id, RequestType: "policy", PolicyResponse: response with { Id = this.Id });

    public RequestFinished CreateExpectedPolicyResponse(bool approved, string reason)
        => this.CreateExpected(this.CreatePolicyResponse(approved, reason));
}

internal sealed record class ResourceRequest(string Id, string ResourceType = "cpu", int Amount = 1, string Priority = "normal");
internal sealed record class PolicyCheckRequest(string Id, string ResourceType, int Amount = 0, string PolicyType = "quota");
internal sealed record class ResourceResponse(string Id, string ResourceType, int Allocated, string Source);
internal sealed record class PolicyResponse(string Id, bool Approved, string Reason);
internal sealed record class RequestFinished(string Id, string RequestType, ResourceResponse? ResourceResponse = null, PolicyResponse? PolicyResponse = null);

internal static class Step9EntryPoint
{
    public static WorkflowBuilder AddPassthroughRequestHandler<TRequest, TResponse>(this WorkflowBuilder builder, ExecutorIsh source, ExecutorIsh filter, string? id = null)
    {
        id ??= typeof(TRequest).Name;

        var requestPort = RequestPort.Create<TRequest, TResponse>(id);

        return builder.ForwardMessage<ExternalRequest>(source, executors: [filter], condition: message => message.DataIs<TRequest>())
                      .ForwardMessage<ExternalRequest>(filter, executors: [requestPort], condition: message => message.DataIs<TRequest>())
                      .ForwardMessage<ExternalResponse>(requestPort, executors: [filter], condition: message => message.DataIs<TResponse>())
                      .ForwardMessage<ExternalResponse>(filter, executors: [source], condition: message => message.DataIs<TResponse>());
    }

    public static WorkflowBuilder AddExternalRequest<TRequest, TResponse>(this WorkflowBuilder builder, ExecutorIsh source, string? id = null)
        => builder.AddExternalRequest(source, out RequestPort<TRequest, TResponse> _, id);

    public static WorkflowBuilder AddExternalRequest<TRequest, TResponse>(this WorkflowBuilder builder, ExecutorIsh source, out RequestPort<TRequest, TResponse> inputPort, string? id = null)
    {
        id = id ?? $"{source.Id}.Requests[{typeof(TRequest).Name}=>{typeof(TResponse).Name}]";

        inputPort = RequestPort.Create<TRequest, TResponse>(id);

        return builder.AddExternalRequest(source, inputPort);
    }

    public static WorkflowBuilder AddExternalRequest<TRequest, TResponse>(this WorkflowBuilder builder, ExecutorIsh source, RequestPort<TRequest, TResponse> inputPort)
    {
        return builder.ForwardMessage<TRequest>(source, inputPort)
                      .ForwardMessage<ExternalRequest>(source, inputPort)
                      .ForwardMessage<TResponse>(inputPort, source)
                      .ForwardMessage<ExternalResponse>(inputPort, source);
    }

    public static Workflow CreateSubWorkflow()
    {
        ResourceRequestor requestor = new();

        return new WorkflowBuilder(requestor)
                   .AddExternalRequest<ResourceRequest, ResourceResponse>(source: requestor)
                   .AddExternalRequest<PolicyCheckRequest, PolicyResponse>(source: requestor)
                   .WithOutputFrom(requestor)
                   .Build();
    }

    public static Workflow CreateWorkflow()
    {
        Coordinator coordinator = new();
        ResourceCache cache = new();
        QuotaPolicyEngine policyEngine = new();
        ExecutorIsh subworkflow = CreateSubWorkflow().ConfigureSubWorkflow("ResourceWorkflow");

        return new WorkflowBuilder(coordinator)
               .AddChain(coordinator, allowRepetition: true, subworkflow, coordinator)
               .AddPassthroughRequestHandler<ResourceRequest, ResourceResponse>(subworkflow, cache)
               .AddPassthroughRequestHandler<PolicyCheckRequest, PolicyResponse>(subworkflow, policyEngine)
               .WithOutputFrom(coordinator)
               .Build();
    }

    public static Workflow WorkflowInstance => CreateWorkflow();

    public static UserRequest ResourceHitRequest1 = UserRequest.CreateResourceRequest(resourceType: "cpu", amount: 2, priority: "normal");
    public static RequestFinished ResourceHitResponse1 = ResourceHitRequest1.CreateExpectedResourceResponse(allocated: 2, "cache");

    public static UserRequest ResourceHitRequest2 = UserRequest.CreateResourceRequest(resourceType: "memory", amount: 15, priority: "normal");
    public static RequestFinished ResourceHitResponse2 = ResourceHitRequest2.CreateExpectedResourceResponse(allocated: 15, "cache");

    public static UserRequest PolicyHitRequest1 = UserRequest.CreatePolicyCheckRequest(resourceType: "cpu", amount: 3, policyType: "quota");
    public static RequestFinished PolicyHitResponse1 = PolicyHitRequest1.CreateExpectedPolicyResponse(approved: true, reason: "Within quota (5)");

    public static UserRequest PolicyHitRequest2 = UserRequest.CreatePolicyCheckRequest(resourceType: "disk", amount: 500, policyType: "quota");
    public static RequestFinished PolicyHitResponse2 = PolicyHitRequest2.CreateExpectedPolicyResponse(approved: true, reason: "Within quota (1000)");

    public static UserRequest ResourceMissRequest = UserRequest.CreateResourceRequest(resourceType: "gpu", amount: 2, priority: "high");
    public static RequestFinished ResourceMissResponse = ResourceMissRequest.CreateExpectedResourceResponse(allocated: 1, "external");

    public static UserRequest PolicyMissRequest1 = UserRequest.CreatePolicyCheckRequest(resourceType: "memory", amount: 100, policyType: "quota");
    public static RequestFinished PolicyMissResponse1 = PolicyMissRequest1.CreateExpectedPolicyResponse(approved: false, reason: "External Rejection");

    public static UserRequest PolicyMissRequest2 = UserRequest.CreatePolicyCheckRequest(resourceType: "cpu", amount: 1, policyType: "security");
    public static RequestFinished PolicyMissResponse2 = PolicyMissRequest2.CreateExpectedPolicyResponse(approved: true, reason: "External Approval");

    public static HashSet<string> PolicyMissIds = [PolicyMissRequest1.Id, PolicyMissRequest2.Id];
    public static HashSet<string> ResourceMissIds = [ResourceMissRequest.Id];

    public static Dictionary<string, RequestFinished> Part1FinishedResponses = new()
    {
        { ResourceHitRequest1.Id, ResourceHitResponse1 },
        { ResourceHitRequest2.Id, ResourceHitResponse2 },

        { PolicyHitRequest1.Id, PolicyHitResponse1 },
        { PolicyHitRequest2.Id, PolicyHitResponse2 },
    };

    public static Dictionary<string, RequestFinished> Part2FinishedResponses = new()
    {
        { ResourceMissRequest.Id, ResourceMissResponse},

        { PolicyMissRequest1.Id, PolicyMissResponse1 },
        { PolicyMissRequest2.Id, PolicyMissResponse2 },
    };

    public static UserRequest[] RequestsToProcess => [
            ResourceHitRequest1,
            PolicyHitRequest1,
            ResourceHitRequest2,
            PolicyMissRequest1, // miss
            ResourceMissRequest, // miss
            PolicyHitRequest2,
            PolicyMissRequest2, // miss
        ];

    public static List<RequestFinished> ExpectedResponsesPart1 =>
        [.. RequestsToProcess.Where(request => Part1FinishedResponses.ContainsKey(request.Id))
                             .Select(request => Part1FinishedResponses[request.Id])
                             .OrderBy(request => request.Id)];

    public static RequestFinished[] ExpectedResponsesPart2 =>
        [.. RequestsToProcess.Where(request => Part2FinishedResponses.ContainsKey(request.Id))
                             .Select(request => Part2FinishedResponses[request.Id])
                             .OrderBy(request => request.Id)];

    public static async ValueTask<List<RequestFinished>> RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        RunStatus runStatus;
        List<RequestFinished> results = [];

        Run workflowRun = await environment.RunAsync(WorkflowInstance, RequestsToProcess.ToList());

        RunStatus part1Status = ExpectedResponsesPart2.Length > 0 ? RunStatus.PendingRequests : RunStatus.Idle;
        runStatus = await workflowRun.GetStatusAsync();
        runStatus.Should().Be(part1Status);

        List<RequestFinished> finishedRequests = [];
        List<ExternalRequest> resourceRequests = [];
        List<ExternalRequest> policyRequests = [];

        foreach (WorkflowEvent evt in workflowRun.NewEvents)
        {
            if (evt is WorkflowOutputEvent outputEvent && outputEvent.Data is RequestFinished finishedRequest)
            {
                finishedRequests.Add(finishedRequest);
            }
            else if (evt is RequestInfoEvent requestInfoEvent)
            {
                if (requestInfoEvent.Request.DataIs<ResourceRequest>())
                {
                    resourceRequests.Add(requestInfoEvent.Request);
                }
                else if (requestInfoEvent.Request.DataIs<PolicyCheckRequest>())
                {
                    policyRequests.Add(requestInfoEvent.Request);
                }
            }
            else if (evt is WorkflowErrorEvent error)
            {
                Assert.Fail(((Exception)error.Data!).ToString());
                Console.Error.WriteLine(error.Data);
            }
        }

        finishedRequests.Sort((left, right) => StringComparer.Ordinal.Compare(left.Id, right.Id));
        finishedRequests.Should().HaveCount(ExpectedResponsesPart1.Count)
                             .And.ContainInOrder(ExpectedResponsesPart1);

        int externalResourceRequests = ExpectedResponsesPart2.Count(finishedRequest => finishedRequest.ResourceResponse != null);
        int externalPolicyRequests = ExpectedResponsesPart2.Count(finishedRequest => finishedRequest.PolicyResponse != null);

        resourceRequests.Should().HaveCount(externalResourceRequests);
        policyRequests.Should().HaveCount(externalPolicyRequests);

        List<ExternalResponse> responses = [];

        foreach (ExternalRequest request in resourceRequests)
        {
            ResourceRequest resourceRequest = request.DataAs<ResourceRequest>()!;
            resourceRequest.Id.Should().BeOneOf(ResourceMissIds);
            responses.Add(request.CreateResponse(Part2FinishedResponses[resourceRequest.Id].ResourceResponse!));
        }

        foreach (ExternalRequest request in policyRequests)
        {
            PolicyCheckRequest policyRequest = request.DataAs<PolicyCheckRequest>()!;
            policyRequest.Id.Should().BeOneOf(PolicyMissIds);
            responses.Add(request.CreateResponse(Part2FinishedResponses[policyRequest.Id].PolicyResponse!));
        }

        if (ExpectedResponsesPart2.Length == 0)
        {
            responses.Should().BeEmpty();
            return results;
        }

        await workflowRun.ResumeAsync(responses: responses).ConfigureAwait(false);
        runStatus = await workflowRun.GetStatusAsync();
        runStatus.Should().Be(RunStatus.Idle);

        results = finishedRequests;

        finishedRequests = workflowRun.NewEvents.OfType<WorkflowOutputEvent>()
                                                .Select(outputEvent => outputEvent.Data)
                                                .Where(value => value is not null)
                                                .OfType<RequestFinished>()
                                                .ToList();

        finishedRequests.Sort((left, right) => StringComparer.Ordinal.Compare(left.Id, right.Id));
        finishedRequests.Should().HaveCount(ExpectedResponsesPart2.Length)
                             .And.ContainInOrder(ExpectedResponsesPart2);

        results.AddRange(finishedRequests);
        return results;
    }
}

internal sealed class ResourceRequestor() : Executor(nameof(ResourceRequestor), declareCrossRunShareable: true)
{
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.AddHandler<List<UserRequest>>(this.RequestResourcesAsync)
                           .AddHandler<UserRequest>(InvokeResourceRequestAsync)
                           .AddHandler<ResourceResponse>(this.HandleResponseAsync)
                           .AddHandler<PolicyResponse>(this.HandleResponseAsync);

        // For some reason, using a lambda here causes the analyzer to generate a spurious
        // VSTHRD110: "Observe the awaitable result of this method call by awaiting it, assigning
        // to a variable, or passing it to another method"
        ValueTask InvokeResourceRequestAsync(UserRequest request, IWorkflowContext context)
            => this.RequestResourcesAsync([request], context);
    }

    private async ValueTask RequestResourcesAsync(List<UserRequest> requests, IWorkflowContext context)
    {
        foreach (UserRequest request in requests)
        {
            switch (request.RequestType)
            {
                case "resource":
                    await context.SendMessageAsync(new ResourceRequest(Id: request.Id, ResourceType: request.Type, Amount: request.Amount, Priority: request.Priority ?? "normal"))
                                 .ConfigureAwait(false);
                    break;
                case "policy":
                    await context.SendMessageAsync(new PolicyCheckRequest(Id: request.Id, PolicyType: request.PolicyType ?? "quota", ResourceType: request.Type, Amount: request.Amount))
                                 .ConfigureAwait(false);
                    break;
            }
        }
    }

    private async ValueTask HandleResponseAsync(ResourceResponse response, IWorkflowContext context)
    {
        await context.YieldOutputAsync(new RequestFinished(response.Id, RequestType: "resource", ResourceResponse: response));
    }

    private async ValueTask HandleResponseAsync(PolicyResponse response, IWorkflowContext context)
    {
        await context.YieldOutputAsync(new RequestFinished(response.Id, RequestType: "policy", PolicyResponse: response));
    }
}
internal sealed class ResourceCache()
    : StatefulExecutor<Dictionary<string, int>>(nameof(ResourceCache),
                                                InitializeResourceCache,
                                                declareCrossRunShareable: true)
{
    private static Dictionary<string, int> InitializeResourceCache()
        => new()
        {
            ["cpu"] = 10,
            ["memory"] = 50,
            ["disk"] = 100,
        };

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        // Note the disbalance here - we could also handle ExternalResponse here instead, but we would have
        // to do the exact same type check on it, so we might as well handle
        return routeBuilder.AddHandler<ExternalRequest>(this.UnwrapAndHandleRequestAsync)
                           .AddHandler<ExternalResponse>(this.CollectResultAsync);
    }

    private async ValueTask UnwrapAndHandleRequestAsync(ExternalRequest request, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (request.DataIs(out ResourceRequest? resourceRequest))
        {
            ResourceResponse? response = await this.TryHandleResourceRequestAsync(resourceRequest, context, cancellationToken)
                                                   .ConfigureAwait(false);

            if (response != null)
            {
                await context.SendMessageAsync(request.CreateResponse(response), cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            else
            {
                // Cache does not have enough resources, forward the request to the external system
                await context.SendMessageAsync(request, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async ValueTask<ResourceResponse?> TryHandleResourceRequestAsync(ResourceRequest request, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.Error.WriteLine($"Handling Resource Request {request.Id}");

        Dictionary<string, int> availableResources = await this.ReadStateAsync(context, cancellationToken: cancellationToken)
                                                               .ConfigureAwait(false);

        Console.Error.WriteLine($"Available Resources: {availableResources}");

        try
        {
            if (availableResources.TryGetValue(request.ResourceType, out int available) && available >= request.Amount)
            {
                // Cache has enough resources, allocate from cache
                availableResources[request.ResourceType] -= request.Amount;

                Console.Error.WriteLine($"Handled Resource Request {request.Id}");
                return new(request.Id, request.ResourceType, request.Amount, Source: "cache");
            }
        }
        finally
        {
            await this.QueueStateUpdateAsync(availableResources, context, cancellationToken)
                      .ConfigureAwait(false);
        }

        Console.Error.WriteLine($"Could not handle Resource Request {request.Id}");
        return null;
    }

    private ValueTask CollectResultAsync(ExternalResponse response, IWorkflowContext context)
    {
        if (response.DataIs<ResourceResponse>())
        {
            // Normally we'd update the cache according to whatever logic we want here.
            return context.SendMessageAsync(response);
        }

        return default;
    }
}

internal sealed class QuotaPolicyEngine()
    : StatefulExecutor<Dictionary<string, int>>(nameof(QuotaPolicyEngine),
                                                InitializePolicyQuotas,
                                                declareCrossRunShareable: true)
{
    private static Dictionary<string, int> InitializePolicyQuotas()
        => new()
        {
            ["cpu"] = 5,
            ["memory"] = 20,
            ["disk"] = 1000,
        };

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.AddHandler<ExternalRequest>(this.UnwrapAndHandleRequestAsync)
                           .AddHandler<ExternalResponse>(this.CollectAndForwardAsync);
    }

    private async ValueTask UnwrapAndHandleRequestAsync(ExternalRequest request, IWorkflowContext context)
    {
        if (request.DataIs(out PolicyCheckRequest? policyRquest))
        {
            PolicyResponse? response = await this.TryHandlePolicyCheckRequestAsync(policyRquest, context)
                                                 .ConfigureAwait(false);

            if (response != null)
            {
                await context.SendMessageAsync(request.CreateResponse(response)).ConfigureAwait(false);
            }
            else
            {
                // QuotaPolicyEngine cannot approve the request, forward to external system
                await context.SendMessageAsync(request).ConfigureAwait(false);
            }
        }
    }

    private async ValueTask<PolicyResponse?> TryHandlePolicyCheckRequestAsync(PolicyCheckRequest request, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.Error.WriteLine($"Handling Policy Request {request.Id}");

        Dictionary<string, int> quotas = await this.ReadStateAsync(context, cancellationToken: cancellationToken)
                                                   .ConfigureAwait(false);

        Console.Error.WriteLine($"Policy Quotas: {quotas}");

        try
        {
            if (request.PolicyType == "quota" &&
                quotas.TryGetValue(request.ResourceType, out int quota) &&
                request.Amount <= quota)
            {
                Console.Error.WriteLine($"Handled Policy Request {request.Id}");

                return new(request.Id, Approved: true, Reason: $"Within quota ({quota})");
            }

            Console.Error.WriteLine($"Could not handle Policy Request {request.Id}");

            return null;
        }
        finally
        {
            await this.QueueStateUpdateAsync(quotas, context, cancellationToken).ConfigureAwait(false);
        }
    }
    private ValueTask CollectAndForwardAsync(ExternalResponse response, IWorkflowContext context)
    {
        if (response.DataIs<PolicyResponse>())
        {
            return context.SendMessageAsync(response);
        }

        return default;
    }
}

internal sealed class Coordinator() : Executor(nameof(Coordinator), declareCrossRunShareable: true)
{
    private const string StateKey = nameof(StateKey);

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.AddHandler<List<UserRequest>>(this.StartAsync)
                           .AddHandler<UserRequest>(InvokeStartAsync)
                           .AddHandler<RequestFinished>(this.HandleFinishedRequestAsync);

        // For some reason, using a lambda here causes the analyzer to generate a spurious
        // VSTHRD110: "Observe the awaitable result of this method call by awaiting it, assigning
        // to a variable, or passing it to another method"
        ValueTask InvokeStartAsync(UserRequest request, IWorkflowContext context, CancellationToken cancellationToken)
            => this.StartAsync([request], context, cancellationToken);
    }

    private ValueTask HandleFinishedRequestAsync(RequestFinished finished, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return context.InvokeWithStateAsync<int>(CountFinishedRequestAndYieldResultAsync, StateKey, cancellationToken: cancellationToken);

        async ValueTask<int> CountFinishedRequestAndYieldResultAsync(int state, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await context.YieldOutputAsync(finished, cancellationToken).ConfigureAwait(false);

            return state - 1;
        }
    }

    private ValueTask StartAsync(List<UserRequest> requests, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return context.InvokeWithStateAsync<int>(CountFinishedRequestAndYieldResultAsync, StateKey, cancellationToken: cancellationToken);

        async ValueTask<int> CountFinishedRequestAndYieldResultAsync(int state, IWorkflowContext context, CancellationToken cancellationToken)
        {
            foreach (UserRequest req in requests)
            {
                await context.SendMessageAsync(req, cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            return state + requests.Count;
        }
    }
}
