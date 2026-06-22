// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that <see cref="TypeId"/> identity is independent of the assembly version, culture,
/// and public key token, so that checkpoints written by one SDK version can be restored by another.
/// See issue #6466.
/// </summary>
public class TypeIdVersionMismatchTests
{
    private static string FullNameWithVersion(Type type, string version)
        => $"{type.Assembly.GetName().Name}, Version={version}, Culture=neutral, PublicKeyToken=null";

    [Fact]
    public void IsMatch_IgnoresAssemblyVersion()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        // Simulate a TypeId that was serialized by a different SDK version.
        TypeId legacy = new(FullNameWithVersion(type, "1.8.0.0"), type.FullName!);

        legacy.IsMatch(type).Should().BeTrue();
    }

    [Fact]
    public void Equals_IgnoresAssemblyVersion()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        TypeId legacy = new(FullNameWithVersion(type, "1.8.0.0"), type.FullName!);
        TypeId current = new(type);

        legacy.Equals(current).Should().BeTrue();
        (legacy == current).Should().BeTrue();
        legacy.GetHashCode().Should().Be(current.GetHashCode());
    }

    [Fact]
    public void Equals_DifferentVersions_AreEqual()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        TypeId a = new(FullNameWithVersion(type, "1.3.0.0"), type.FullName!);
        TypeId b = new(FullNameWithVersion(type, "1.10.0.0"), type.FullName!);

        a.Equals(b).Should().BeTrue();
        a.GetHashCode().Should().Be(b.GetHashCode());
    }

    [Fact]
    public void DictionaryLookup_SucceedsAcrossVersionForms()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        // Map keyed by the current (simple-name) TypeId.
        Dictionary<TypeId, string> map = new()
        {
            [new TypeId(type)] = "value",
        };

        // Lookup using a legacy fully-qualified TypeId must still resolve.
        TypeId legacy = new(FullNameWithVersion(type, "1.8.0.0"), type.FullName!);

        map.TryGetValue(legacy, out string? value).Should().BeTrue();
        value.Should().Be("value");
    }

    [Fact]
    public void Equals_DifferentTypeName_NotEqual()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        TypeId a = new(type);
        TypeId b = new(FullNameWithVersion(type, "1.8.0.0"), typeof(TypeId).FullName!);

        a.Equals(b).Should().BeFalse();
    }

    [Fact]
    public void Equals_DifferentSimpleAssemblyName_NotEqual()
    {
        Type type = typeof(TypeIdVersionMismatchTests);

        TypeId a = new(type);
        TypeId b = new("Some.Other.Assembly, Version=1.8.0.0, Culture=neutral, PublicKeyToken=null", type.FullName!);

        a.Equals(b).Should().BeFalse();
    }

    [Fact]
    public void MalformedAssemblyName_FallsBackToRawValue()
    {
        // An unparseable assembly name should not throw; it should compare on the raw value.
        TypeId a = new("not a valid, assembly name", "Some.Type");
        TypeId b = new("not a valid, assembly name", "Some.Type");

        a.Equals(b).Should().BeTrue();
    }
}
