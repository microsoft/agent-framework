// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that <see cref="TypeId.IsMatch(Type)"/> and <see cref="TypeId.Equals(object?)"/>
/// compare on the type full name and the simple assembly name, ignoring version, culture,
/// and public key token both in the outer assembly name and in any assembly-qualified generic
/// arguments embedded in the type full name.
/// </summary>
public class TypeIdVersionToleranceTests
{
    [SuppressMessage("Performance", "CA1812", Justification = "Used via typeof() only; never instantiated.")]
    private sealed class Probe
    {
    }

    private static string ProbeSimpleAssemblyName => typeof(Probe).Assembly.GetName().Name!;
    private static string ProbeTypeFullName => typeof(Probe).FullName!;

    [Fact]
    public void Test_IsMatch_RoundTripsRealType()
    {
        TypeId id = new(typeof(Probe));

        id.IsMatch(typeof(Probe)).Should().BeTrue();
        id.IsMatch<Probe>().Should().BeTrue();
    }

    [Fact]
    public void Test_IsMatch_IgnoresAssemblyVersion()
    {
        string assemblyName = $"{ProbeSimpleAssemblyName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null";
        TypeId id = new(assemblyName, ProbeTypeFullName);

        id.IsMatch(typeof(Probe)).Should().BeTrue("version differences in AssemblyName must not affect matching");
    }

    [Fact]
    public void Test_IsMatch_IgnoresCultureAndPublicKeyToken()
    {
        string assemblyName = $"{ProbeSimpleAssemblyName}, Version=99.0.0.0, Culture=en-US, PublicKeyToken=abcdef0123456789";
        TypeId id = new(assemblyName, ProbeTypeFullName);

        id.IsMatch(typeof(Probe)).Should().BeTrue();
    }

    [Fact]
    public void Test_IsMatch_AcceptsSimpleAssemblyNameOnly()
    {
        TypeId id = new(ProbeSimpleAssemblyName, ProbeTypeFullName);

        id.IsMatch(typeof(Probe)).Should().BeTrue();
    }

    [Fact]
    public void Test_IsMatch_RejectsDifferentSimpleAssemblyName()
    {
        TypeId id = new(
            assemblyName: "Some.Completely.Different.Assembly, Version=1.0.0.0",
            typeName: ProbeTypeFullName);

        id.IsMatch(typeof(Probe)).Should().BeFalse("different simple assembly names must not match");
    }

    [Fact]
    public void Test_IsMatch_RejectsDifferentTypeName()
    {
        TypeId id = new(
            assemblyName: $"{ProbeSimpleAssemblyName}, Version=99.0.0.0",
            typeName: "Some.Other.Namespace.Probe");

        id.IsMatch(typeof(Probe)).Should().BeFalse("different type names must not match");
    }

    [Fact]
    public void Test_IsMatch_ToleratesMalformedAssemblyName()
    {
        TypeId id = new(
            assemblyName: $"{ProbeSimpleAssemblyName}, Version=not-a-version, Culture=??, PublicKeyToken=???",
            typeName: ProbeTypeFullName);

        id.IsMatch(typeof(Probe)).Should().BeTrue("the substring fallback recovers the simple name when AssemblyName parsing fails");
    }

    [Fact]
    public void Test_IsMatchPolymorphic_IgnoresAssemblyVersion()
    {
        TypeId id = new(
            assemblyName: $"{typeof(object).Assembly.GetName().Name}, Version=99.0.0.0",
            typeName: typeof(object).FullName!);

        id.IsMatchPolymorphic(typeof(Probe)).Should().BeTrue("IsMatchPolymorphic uses the same comparison rules as IsMatch");
    }

    [Fact]
    public void Test_Equals_IgnoresAssemblyVersion()
    {
        TypeId v1 = new($"{ProbeSimpleAssemblyName}, Version=1.0.0.0", ProbeTypeFullName);
        TypeId v2 = new($"{ProbeSimpleAssemblyName}, Version=2.0.0.0", ProbeTypeFullName);

        v1.Equals(v2).Should().BeTrue();
        (v1 == v2).Should().BeTrue();
        v1.GetHashCode().Should().Be(v2.GetHashCode());
    }

    [Fact]
    public void Test_Equals_RejectsDifferentSimpleAssemblyName()
    {
        TypeId a = new($"{ProbeSimpleAssemblyName}, Version=1.0.0.0", ProbeTypeFullName);
        TypeId b = new("Some.Other.Assembly, Version=1.0.0.0", ProbeTypeFullName);

        a.Equals(b).Should().BeFalse();
    }

    [Fact]
    public void Test_Equals_RejectsDifferentTypeName()
    {
        TypeId a = new($"{ProbeSimpleAssemblyName}, Version=1.0.0.0", ProbeTypeFullName);
        TypeId b = new($"{ProbeSimpleAssemblyName}, Version=1.0.0.0", "Some.Other.Type");

        a.Equals(b).Should().BeFalse();
    }

    [Fact]
    public void Test_Dictionary_LookupAcrossVersions()
    {
        TypeId live = new(typeof(Probe));
        TypeId mutated = new(
            assemblyName: $"{ProbeSimpleAssemblyName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null",
            typeName: ProbeTypeFullName);

        Dictionary<TypeId, string> map = new() { [live] = "value" };
        map.TryGetValue(mutated, out string? value).Should().BeTrue();
        value.Should().Be("value");

        HashSet<TypeId> set = new() { live };
        set.Contains(mutated).Should().BeTrue();
    }

    [Fact]
    public void Test_Equals_TreatsIdenticalStringsAsEqual()
    {
        TypeId a = new(typeof(Probe));
        TypeId b = new(typeof(Probe));

        a.Equals(b).Should().BeTrue();
        a.GetHashCode().Should().Be(b.GetHashCode());
    }

    [Fact]
    public void Test_NormalizeTypeName_ReturnsInputWhenNoAssemblyQualifier()
    {
        const string TypeName = "Microsoft.Agents.AI.Workflows.Checkpointing.TypeId";

        TypeId.NormalizeTypeName(TypeName).Should().BeSameAs(TypeName);
    }

    [Fact]
    public void Test_NormalizeTypeName_StripsVersionCultureAndPublicKeyTokenTriplets()
    {
        const string TypeName = "System.Collections.Generic.List`1[[Some.Type, Some.Asm, Version=1.2.3.4, Culture=neutral, PublicKeyToken=abcdef0123456789]]";
        const string Expected = "System.Collections.Generic.List`1[[Some.Type, Some.Asm]]";

        TypeId.NormalizeTypeName(TypeName).Should().Be(Expected);
    }

    [Fact]
    public void Test_NormalizeTypeName_StripsTripletsFromNestedGenericArguments()
    {
        const string TypeName = "System.Collections.Generic.Dictionary`2[[System.String, mscorlib, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089],[System.Collections.Generic.List`1[[Some.Type, Some.Asm, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null]], mscorlib, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089]]";
        const string Expected = "System.Collections.Generic.Dictionary`2[[System.String, mscorlib],[System.Collections.Generic.List`1[[Some.Type, Some.Asm]], mscorlib]]";

        TypeId.NormalizeTypeName(TypeName).Should().Be(Expected);
    }

    [Fact]
    public void Test_IsMatch_IgnoresVersionInGenericArguments()
    {
        Type live = typeof(List<ChatMessage>);
        string simpleAssemblyName = live.Assembly.GetName().Name!;

        // Hand-craft a TypeName as if persisted under a different version of the generic
        // argument assembly (Microsoft.Extensions.AI.Abstractions).
        string innerArgSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutatedTypeName = $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerArgSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]]";

        TypeId id = new(simpleAssemblyName, mutatedTypeName);

        id.IsMatch(live).Should().BeTrue("version differences inside generic argument names must not affect matching");
    }

    [Fact]
    public void Test_Equals_IgnoresVersionInGenericArguments()
    {
        Type live = typeof(List<ChatMessage>);
        TypeId fromLive = new(live);

        string simpleAssemblyName = live.Assembly.GetName().Name!;
        string innerArgSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutatedTypeName = $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerArgSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]]";
        TypeId fromMutated = new(simpleAssemblyName, mutatedTypeName);

        fromLive.Equals(fromMutated).Should().BeTrue();
        fromLive.GetHashCode().Should().Be(fromMutated.GetHashCode());
    }

    [Fact]
    public void Test_Dictionary_LookupAcrossGenericArgumentVersions()
    {
        Type live = typeof(List<ChatMessage>);
        TypeId fromLive = new(live);

        string simpleAssemblyName = live.Assembly.GetName().Name!;
        string innerArgSimpleName = typeof(ChatMessage).Assembly.GetName().Name!;
        string mutatedTypeName = $"System.Collections.Generic.List`1[[Microsoft.Extensions.AI.ChatMessage, {innerArgSimpleName}, Version=99.0.0.0, Culture=neutral, PublicKeyToken=null]]";
        TypeId fromMutated = new(simpleAssemblyName, mutatedTypeName);

        Dictionary<TypeId, string> map = new() { [fromLive] = "value" };
        map.TryGetValue(fromMutated, out string? value).Should().BeTrue();
        value.Should().Be("value");
    }
}
