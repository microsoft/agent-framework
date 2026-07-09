// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that <see cref="WorkflowSession.ResolveTypeLenient(TypeId)"/> resolves a
/// <see cref="TypeId"/> to a loaded <see cref="Type"/> even when the stored assembly
/// name carries a different <c>Version=</c> than the loaded assembly.
/// </summary>
public class WorkflowSessionResolveTypeLenientTests
{
    [SuppressMessage("Performance", "CA1812", Justification = "Instantiated via Type.GetType in the production code path under test.")]
    private sealed class TestEnvelope : IExternalRequestEnvelope
    {
        AIContent? IExternalRequestEnvelope.GetInnerRequestContent() => null;

        object IExternalRequestEnvelope.CreateResponse(IList<ChatMessage> messages) => messages;
    }

    [Fact]
    public void Test_ResolveTypeLenient_ResolvesWhenAssemblyNameMatchesLoadedVersion()
    {
        Type live = typeof(TestEnvelope);
        TypeId id = new(live);

        WorkflowSession.ResolveTypeLenient(id).Should().Be(live);
    }

    [Fact]
    public void Test_ResolveTypeLenient_ResolvesAcrossAssemblyVersionMutation()
    {
        Type live = typeof(TestEnvelope);
        string simpleAssemblyName = live.Assembly.GetName().Name!;
        string mutatedAssemblyName = $"{simpleAssemblyName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";
        TypeId mutated = new(mutatedAssemblyName, live.FullName!);

        WorkflowSession.ResolveTypeLenient(mutated).Should().Be(live);
    }

    [Fact]
    public void Test_ResolveTypeLenient_ReturnsNullForUnknownType()
    {
        TypeId id = new("Some.Unloaded.Assembly", "Some.Unknown.Type");

        WorkflowSession.ResolveTypeLenient(id).Should().BeNull();
    }

    [Fact]
    public void Test_ResolveTypeLenient_ResolvesAcrossGenericArgumentVersionMutation()
    {
        Type live = typeof(List<ChatMessage>);
        string outerSimpleName = live.Assembly.GetName().Name!;
        string innerSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutatedTypeName = $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]]";

        TypeId mutated = new(outerSimpleName, mutatedTypeName);

        WorkflowSession.ResolveTypeLenient(mutated).Should().Be(live);
    }
}
