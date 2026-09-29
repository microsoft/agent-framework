// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using System.Reflection.Emit;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Specialized;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed record RequestPortSourceRequest(string Value);

internal sealed record RequestPortTargetRequest(string Value);

internal record RequestPortBaseRequest(string Value);

internal sealed record RequestPortDerivedRequest(string Value) : RequestPortBaseRequest(Value);

public abstract class RequestPortDuplicateRequestBase
{
}

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

    [Fact]
    public void ResolveType_SkipsIncompatibleSameNameTypeLoadedBeforeCompatibleType()
    {
        // Arrange
        const string AssemblyName = "RequestPortDuplicateTypes";
        const string TypeName = "Duplicate.Request";
        Type incompatibleType = DefineDuplicateRequestType(AssemblyName, TypeName);
        Type compatibleType = DefineDuplicateRequestType(AssemblyName, TypeName, typeof(RequestPortDuplicateRequestBase));
        TypeId typeId = new($"{AssemblyName}, Version=1.0.0.0", TypeName);

        // Act
        Type? resolvedType = RequestInfoExecutor.ResolveType(typeId, typeof(RequestPortDuplicateRequestBase));

        // Assert
        Assert.NotNull(resolvedType);
        Assert.Same(compatibleType, resolvedType);
        Assert.False(typeof(RequestPortDuplicateRequestBase).IsAssignableFrom(incompatibleType));
    }

    private static Type DefineDuplicateRequestType(string assemblyName, string typeName, Type? baseType = null)
    {
        AssemblyBuilder assemblyBuilder =
            AssemblyBuilder.DefineDynamicAssembly(new AssemblyName(assemblyName), AssemblyBuilderAccess.Run);
        ModuleBuilder moduleBuilder = assemblyBuilder.DefineDynamicModule(assemblyName);
        TypeBuilder typeBuilder =
            moduleBuilder.DefineType(typeName, TypeAttributes.Public | TypeAttributes.Class, baseType);

        TypeInfo? typeInfo = typeBuilder.CreateTypeInfo();
        Assert.NotNull(typeInfo);
        return typeInfo.AsType();
    }
}
