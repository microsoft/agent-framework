// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

/// <summary>
/// Verifies that <see cref="DurableTaskTypeResolver.Resolve(string)"/> resolves persisted
/// assembly-qualified type-name strings to a loaded <see cref="Type"/> across assembly
/// version, culture, and public key token mutations.
/// </summary>
public sealed class DurableTaskTypeResolverTests
{
    [Fact]
    public void Resolve_LoadedAssemblyQualifiedName_ReturnsLiveType()
    {
        Type live = typeof(List<ChatMessage>);
        string aqn = live.AssemblyQualifiedName!;

        Type? resolved = DurableTaskTypeResolver.Resolve(aqn);

        Assert.Same(live, resolved);
    }

    [Fact]
    public void Resolve_MutatedOuterAssemblyVersion_ReturnsLiveType()
    {
        Type live = typeof(ChatMessage);
        string outerSimpleName = live.Assembly.GetName().Name!;
        string mutated = $"{live.FullName}, {outerSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";

        Type? resolved = DurableTaskTypeResolver.Resolve(mutated);

        Assert.Same(live, resolved);
    }

    [Fact]
    public void Resolve_MutatedGenericArgumentVersion_ReturnsLiveType()
    {
        Type live = typeof(List<ChatMessage>);
        string outerSimpleName = live.Assembly.GetName().Name!;
        string innerSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutated =
            $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerSimpleName}, " +
            "Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]], " +
            $"{outerSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";

        Type? resolved = DurableTaskTypeResolver.Resolve(mutated);

        Assert.Same(live, resolved);
    }

    [Fact]
    public void Resolve_UnknownType_ReturnsNull()
    {
        Type? resolved = DurableTaskTypeResolver.Resolve(
            "Some.Unknown.Namespace.MissingType, Some.Unloaded.Assembly, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null");

        Assert.Null(resolved);
    }

    [Fact]
    public void Resolve_CachesResults()
    {
        Type live = typeof(ChatMessage);
        string aqn = live.AssemblyQualifiedName!;

        Type? first = DurableTaskTypeResolver.Resolve(aqn);
        Type? second = DurableTaskTypeResolver.Resolve(aqn);

        Assert.Same(first, second);
        Assert.Same(live, second);
    }
}
