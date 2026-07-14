// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that <see cref="WorkflowSession"/> recognizes an external request as an envelope
/// only when the request's port declares a type that matches the type recorded on the request,
/// resolving that type from the live workflow ports rather than the recorded assembly name.
/// </summary>
public class WorkflowSessionTests
{
    private sealed class TestEnvelope : IExternalRequestEnvelope
    {
        AIContent? IExternalRequestEnvelope.GetInnerRequestContent() => null;

        object IExternalRequestEnvelope.CreateResponse(IList<ChatMessage> messages) => messages;
    }

    [Fact]
    public void ResolveEnvelopeType_ReturnsPortTypeWhenPortDeclaresMatchingType()
    {
        Type live = typeof(TestEnvelope);
        RequestPort port = new("port-1", live, typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };
        RequestPortInfo portInfo = new(new TypeId(live), new TypeId(typeof(object)), port.Id);

        WorkflowSession.ResolveEnvelopeType(portInfo, ports).Should().Be(live);
    }

    [Fact]
    public void ResolveEnvelopeType_ResolvesAcrossAssemblyVersionMutation()
    {
        Type live = typeof(TestEnvelope);
        RequestPort port = new("port-1", live, typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };

        string simpleAssemblyName = live.Assembly.GetName().Name!;
        string mutatedAssemblyName = $"{simpleAssemblyName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";
        RequestPortInfo portInfo = new(new TypeId(mutatedAssemblyName, live.FullName!), new TypeId(typeof(object)), port.Id);

        WorkflowSession.ResolveEnvelopeType(portInfo, ports).Should().Be(live);
    }

    [Fact]
    public void ResolveEnvelopeType_ResolvesAcrossGenericArgumentVersionMutation()
    {
        Type live = typeof(List<ChatMessage>);
        RequestPort port = new("port-1", live, typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };

        string outerSimpleName = live.Assembly.GetName().Name!;
        string innerSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutatedTypeName = $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]]";
        RequestPortInfo portInfo = new(new TypeId(outerSimpleName, mutatedTypeName), new TypeId(typeof(object)), port.Id);

        WorkflowSession.ResolveEnvelopeType(portInfo, ports).Should().Be(live);
    }

    [Fact]
    public void ResolveEnvelopeType_ReturnsNullWhenPortIdIsUnknown()
    {
        Dictionary<string, RequestPort> ports = new()
        {
            ["port-1"] = new RequestPort("port-1", typeof(TestEnvelope), typeof(object)),
        };
        RequestPortInfo portInfo = new(new TypeId(typeof(TestEnvelope)), new TypeId(typeof(object)), "missing-port");

        WorkflowSession.ResolveEnvelopeType(portInfo, ports).Should().BeNull();
    }

    [Fact]
    public void ResolveEnvelopeType_ReturnsNullWhenRecordedTypeDoesNotMatchPortType()
    {
        Dictionary<string, RequestPort> ports = new()
        {
            ["port-1"] = new RequestPort("port-1", typeof(TestEnvelope), typeof(object)),
        };
        RequestPortInfo portInfo = new(new TypeId("Some.Unloaded.Assembly", "Some.Unknown.Type"), new TypeId(typeof(object)), "port-1");

        WorkflowSession.ResolveEnvelopeType(portInfo, ports).Should().BeNull();
    }

    [Fact]
    public void TryGetRequestEnvelope_ReturnsEnvelopeWhenPortDeclaresEnvelopeType()
    {
        RequestPort port = new("port-1", typeof(TestEnvelope), typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };
        ExternalRequest request = ExternalRequest.Create(port, new TestEnvelope());

        WorkflowSession.TryGetRequestEnvelope(request, ports, out IExternalRequestEnvelope? envelope).Should().BeTrue();
        envelope.Should().BeOfType<TestEnvelope>();
    }

    [Fact]
    public void TryGetRequestEnvelope_ReturnsFalseWhenPortTypeIsNotEnvelope()
    {
        RequestPort port = new("port-1", typeof(string), typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };
        ExternalRequest request = ExternalRequest.Create(port, "not-an-envelope");

        WorkflowSession.TryGetRequestEnvelope(request, ports, out IExternalRequestEnvelope? envelope).Should().BeFalse();
        envelope.Should().BeNull();
    }

    [Fact]
    public void TryGetRequestEnvelope_ReturnsFalseWhenRecordedTypeDoesNotMatchPortType()
    {
        RequestPort port = new("port-1", typeof(TestEnvelope), typeof(object));
        Dictionary<string, RequestPort> ports = new() { [port.Id] = port };
        RequestPortInfo recordedPortInfo = new(new TypeId("Some.Unloaded.Assembly", "Some.Unknown.Type"), new TypeId(typeof(object)), port.Id);
        ExternalRequest request = new(recordedPortInfo, "req-1", new PortableValue(new TestEnvelope()));

        WorkflowSession.TryGetRequestEnvelope(request, ports, out IExternalRequestEnvelope? envelope).Should().BeFalse();
        envelope.Should().BeNull();
    }
}
