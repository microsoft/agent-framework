// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class DynamicRequestPortTests
{
    private sealed class RequestPortTestContext
    {
        private const string PortId = "Port1";
        private const string ExecutorId = "Executor1";

        public RequestPortTestContext()
        {
            this.Executor = new(ExecutorId, PortId);
            this.Executor.AttachRequestContext(this.ExternalRequestContext);
        }

        public TestRunContext RunContext { get; } = new();
        public ExternalRequestContext ExternalRequestContext { get; } = new();

        public DynamicPortsExecutor<string, int> Executor { get; }

        public PortBinding PortBinding => this.Executor.PortBindings[PortId];

        public ExternalRequest Request => this.ExternalRequestContext.ExternalRequests[0];

        public static async ValueTask<RequestPortTestContext> CreateAsync(string requestData = "Request", bool validate = true)
        {
            RequestPortTestContext result = new();

            await result.Executor.PostRequestAsync(PortId, requestData, result.RunContext);

            if (validate)
            {
                result.ExternalRequestContext
                      .ExternalRequests.Should().HaveCount(1)
                                   .And.AllSatisfy(request => request.PortInfo.Should().Be(result.PortBinding.Port.ToPortInfo()));
            }

            return result;
        }

        public ValueTask<object?> InvokeExecutorWithResponseAsync(ExternalResponse response)
            => this.Executor.ExecuteCoreAsync(response, new(typeof(ExternalResponse)), this.RunContext.BindWorkflowContext(this.Executor.Id));
    }

    private sealed class ExternalRequestContext : IExternalRequestContext, IExternalRequestSink
    {
        public List<ExternalRequest> ExternalRequests { get; } = new();

        public ValueTask PostAsync(ExternalRequest request)
        {
            this.ExternalRequests.Add(request);
            return default;
        }

        public IExternalRequestSink RegisterPort(RequestPort port)
        {
            return this;
        }
    }

    [Fact]
    public async Task Test_DynamicRequestPort_DeliversExpectedResponseAsync()
    {
        RequestPortTestContext context = await RequestPortTestContext.CreateAsync();

        ExternalRequest request = context.Request;
        await context.InvokeExecutorWithResponseAsync(request.CreateResponse(13));

        string portId = request.PortInfo.PortId;
        context.Executor.ReceivedResponses.Should().HaveCount(1)
                                               .And.ContainKey(portId);
        context.Executor.ReceivedResponses[portId].Should().HaveCount(1);
        context.Executor.ReceivedResponses[portId].First().Should().Be(13);
    }

    [Fact]
    public async Task Test_DynamicRequestPort_ThrowsOnWrongPortAsync()
    {
        RequestPortTestContext context = await RequestPortTestContext.CreateAsync();

        ExternalRequest request = context.Request;
        ExternalRequest fakeRequest = new(RequestPort.Create<string, int>("port2").ToPortInfo(), request.RequestId, request.Data);

        Func<Task> act = async () => await context.InvokeExecutorWithResponseAsync(fakeRequest.CreateResponse(13));
        (await act.Should().ThrowAsync<TargetInvocationException>())
                           .WithInnerException<InvalidOperationException>();
    }
}
