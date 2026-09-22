// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Specialized;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed record RequestPortSourceRequest(string Value);

internal sealed record RequestPortTargetRequest(string Value);

internal record RequestPortBaseRequest(string Value);

internal sealed record RequestPortDerivedRequest(string Value) : RequestPortBaseRequest(Value);

public class RequestInfoExecutorTests
{
    [Fact]
    public async Task HandleAsync_RejectsForwardingToRequestPortWithDifferentRequestTypeAsync()
    {
        // Arrange
        RequestPort sourcePort = RequestPort.Create<RequestPortSourceRequest, string>("source");
        RequestPort targetPort = RequestPort.Create<RequestPortTargetRequest, string>("target");
        ExternalRequest originalRequest = ExternalRequest.Create(sourcePort, new RequestPortSourceRequest("value"));
        ExternalRequest serializedRequest = JsonSerializationTests.RunJsonRoundtrip(originalRequest, TestJsonContext.Default.Options);
        RequestInfoExecutor executor = new(targetPort);
        TestRunContext runContext = new();
        runContext.ConfigureExecutor(executor);
        executor.AttachRequestSink(runContext);

        Assert.True(serializedRequest.Data.IsDelayedDeserialization);
        Assert.True(serializedRequest.Data.TypeId.IsMatch<RequestPortSourceRequest>());

        // Act
        async Task ActAsync() => await executor.HandleAsync(serializedRequest, runContext.BindWorkflowContext(executor.Id));

        // Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(ActAsync);
        Assert.Contains(nameof(RequestPortTargetRequest), exception.Message);
        Assert.Contains(nameof(RequestPortSourceRequest), exception.Message);
        Assert.Empty(runContext.ExternalRequests);
    }

    [Fact]
    public async Task HandleAsync_ForwardsDerivedRequestToRequestPortWithBaseRequestTypeAsync()
    {
        // Arrange
        RequestPort sourcePort = RequestPort.Create<RequestPortDerivedRequest, string>("source");
        RequestPort targetPort = RequestPort.Create<RequestPortBaseRequest, string>("target");
        ExternalRequest originalRequest = ExternalRequest.Create(sourcePort, new RequestPortDerivedRequest("value"));
        ExternalRequest serializedRequest = JsonSerializationTests.RunJsonRoundtrip(originalRequest, TestJsonContext.Default.Options);
        RequestInfoExecutor executor = new(targetPort);
        TestRunContext runContext = new();
        runContext.ConfigureExecutor(executor);
        executor.AttachRequestSink(runContext);

        // Act
        ExternalRequest forwardedRequest =
            await executor.HandleAsync(serializedRequest, runContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.Equal(targetPort.ToPortInfo(), forwardedRequest.PortInfo);
        Assert.Equal(originalRequest.RequestId, forwardedRequest.RequestId);
        RequestPortDerivedRequest? forwardedData = forwardedRequest.Data.As<RequestPortDerivedRequest>();
        Assert.NotNull(forwardedData);
        Assert.Equal("value", forwardedData.Value);
        Assert.Same(forwardedRequest, Assert.Single(runContext.ExternalRequests));
    }

    [Fact]
    public async Task HandleAsync_ForwardsToRequestPortWithMatchingRequestTypeAsync()
    {
        // Arrange
        RequestPort sourcePort = RequestPort.Create<RequestPortSourceRequest, string>("source");
        RequestPort targetPort = RequestPort.Create<RequestPortSourceRequest, string>("target");
        ExternalRequest originalRequest = ExternalRequest.Create(sourcePort, new RequestPortSourceRequest("value"));
        ExternalRequest serializedRequest = JsonSerializationTests.RunJsonRoundtrip(originalRequest, TestJsonContext.Default.Options);
        RequestInfoExecutor executor = new(targetPort);
        TestRunContext runContext = new();
        runContext.ConfigureExecutor(executor);
        executor.AttachRequestSink(runContext);

        // Act
        ExternalRequest forwardedRequest =
            await executor.HandleAsync(serializedRequest, runContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.Equal(targetPort.ToPortInfo(), forwardedRequest.PortInfo);
        Assert.Equal(originalRequest.RequestId, forwardedRequest.RequestId);
        Assert.Equal(new RequestPortSourceRequest("value"), forwardedRequest.Data.As<RequestPortSourceRequest>());
        Assert.Same(forwardedRequest, Assert.Single(runContext.ExternalRequests));
    }
}
