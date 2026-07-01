// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

/// <summary>
/// Verifies that <see cref="DurableActivityExecutor.ResolveInputType(string?, ISet{Type})"/>
/// matches persisted assembly-qualified type-name strings against the executor's supported
/// input types even when the persisted name carries a different assembly version, culture,
/// or public key token than the loaded assemblies.
/// </summary>
public sealed class DurableActivityExecutorResolveInputTypeTests
{
    [Fact]
    public void ResolveInputType_NullInput_ReturnsFirstSupportedType()
    {
        Type result = DurableActivityExecutor.ResolveInputType(null, new HashSet<Type> { typeof(int) });

        Assert.Equal(typeof(int), result);
    }

    [Fact]
    public void ResolveInputType_EmptyInputAndNoSupportedTypes_FallsBackToString()
    {
        Type result = DurableActivityExecutor.ResolveInputType(string.Empty, new HashSet<Type>());

        Assert.Equal(typeof(string), result);
    }

    [Fact]
    public void ResolveInputType_LoadedAssemblyQualifiedName_ReturnsSupportedType()
    {
        Type supported = typeof(ChatMessage);
        ISet<Type> supportedTypes = new HashSet<Type> { supported };

        Type result = DurableActivityExecutor.ResolveInputType(supported.AssemblyQualifiedName, supportedTypes);

        Assert.Same(supported, result);
    }

    [Fact]
    public void ResolveInputType_MutatedAssemblyVersion_ReturnsSupportedType()
    {
        Type supported = typeof(ChatMessage);
        string simpleAssemblyName = supported.Assembly.GetName().Name!;
        string mutated = $"{supported.FullName}, {simpleAssemblyName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";
        ISet<Type> supportedTypes = new HashSet<Type> { supported };

        Type result = DurableActivityExecutor.ResolveInputType(mutated, supportedTypes);

        Assert.Same(supported, result);
    }

    [Fact]
    public void ResolveInputType_MutatedGenericArgumentVersion_ReturnsSupportedType()
    {
        Type supported = typeof(List<ChatMessage>);
        string outerSimple = supported.Assembly.GetName().Name!;
        string innerSimple = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutated =
            $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerSimple}, " +
            "Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]], " +
            $"{outerSimple}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";
        ISet<Type> supportedTypes = new HashSet<Type> { supported };

        Type result = DurableActivityExecutor.ResolveInputType(mutated, supportedTypes);

        Assert.Same(supported, result);
    }

    [Fact]
    public void ResolveInputType_ShortNameMatch_ReturnsSupportedType()
    {
        Type supported = typeof(ChatMessage);
        ISet<Type> supportedTypes = new HashSet<Type> { supported };

        Type result = DurableActivityExecutor.ResolveInputType(supported.Name, supportedTypes);

        Assert.Same(supported, result);
    }

    [Fact]
    public void ResolveInputType_FullNameMatch_ReturnsSupportedType()
    {
        Type supported = typeof(ChatMessage);
        ISet<Type> supportedTypes = new HashSet<Type> { supported };

        Type result = DurableActivityExecutor.ResolveInputType(supported.FullName, supportedTypes);

        Assert.Same(supported, result);
    }

    [Fact]
    public void ResolveInputType_StringFallback_ReturnsFirstSupportedTypeWhenStringUnsupported()
    {
        ISet<Type> supportedTypes = new HashSet<Type> { typeof(int) };

        Type result = DurableActivityExecutor.ResolveInputType(typeof(string).AssemblyQualifiedName, supportedTypes);

        Assert.Equal(typeof(int), result);
    }
}
