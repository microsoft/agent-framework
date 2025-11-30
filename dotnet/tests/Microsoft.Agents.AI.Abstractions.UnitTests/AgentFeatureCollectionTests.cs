// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains unit tests for the <see cref="AgentFeatureCollection"/> class.
/// </summary>
public class AgentFeatureCollectionTests
{
    [Fact]
    public void Feature_RoundTrips()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        // Act.
        interfaces.Set<IThing>(thing);
        Assert.True(interfaces.TryGet<IThing>(out var actualThing));

        // Assert.
        Assert.Same(actualThing, thing);
        Assert.Equal(1, interfaces.Revision);
    }

    [Fact]
    public void RemoveOfT_Removes()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces.Set<IThing>(thing);
        Assert.True(interfaces.TryGet<IThing>(out _));

        // Act.
        interfaces.Remove<IThing>();

        // Assert.
        Assert.False(interfaces.TryGet<IThing>(out _));
        Assert.Equal(2, interfaces.Revision);
    }

    [Fact]
    public void Remove_Removes()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces.Set<IThing>(thing);
        Assert.True(interfaces.TryGet<IThing>(out _));

        // Act.
        interfaces.Remove(typeof(IThing));

        // Assert.
        Assert.False(interfaces.TryGet<IThing>(out _));
        Assert.Equal(2, interfaces.Revision);
    }

    [Fact]
    public void TryGetMissingFeature_ReturnsFalse()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();

        // Act & Assert.
        Assert.False(interfaces.TryGet<Thing>(out var actualThing));
        Assert.Null(actualThing);
    }

    [Fact]
    public void Set_Null_Throws()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();

        // Act & Assert.
        Assert.Throws<ArgumentNullException>(() => interfaces.Set<IThing>(null!));
    }

    [Fact]
    public void IsReadOnly_DefaultsToFalse()
    {
        // Arrange.
        var interfaces = new AgentFeatureCollection();

        // Act & Assert.
        Assert.False(interfaces.IsReadOnly);
    }

    [Fact]
    public void TryGetOfT_FallsBackToInnerCollection()
    {
        // Arrange.
        var inner = new AgentFeatureCollection();
        var thing = new Thing();
        inner.Set<IThing>(thing);
        var outer = new AgentFeatureCollection(inner);

        // Act & Assert.
        Assert.True(outer.TryGet<IThing>(out var actualThing));
        Assert.Same(actualThing, thing);
    }

    [Fact]
    public void TryGetOfT_OverridesInnerWithOuterCollection()
    {
        // Arrange.
        var inner = new AgentFeatureCollection();
        var innerThing = new Thing();
        inner.Set<IThing>(innerThing);

        var outer = new AgentFeatureCollection(inner);
        var outerThing = new Thing();
        outer.Set<IThing>(outerThing);

        // Act & Assert.
        Assert.True(outer.TryGet<IThing>(out var actualThing));
        Assert.Same(outerThing, actualThing);
    }

    [Fact]
    public void TryGet_FallsBackToInnerCollection()
    {
        // Arrange.
        var inner = new AgentFeatureCollection();
        var thing = new Thing();
        inner.Set<IThing>(thing);
        var outer = new AgentFeatureCollection(inner);

        // Act & Assert.
        Assert.True(outer.TryGet(typeof(IThing), out var actualThing));
        Assert.Same(actualThing, thing);
    }

    [Fact]
    public void TryGet_OverridesInnerWithOuterCollection()
    {
        // Arrange.
        var inner = new AgentFeatureCollection();
        var innerThing = new Thing();
        inner.Set<IThing>(innerThing);

        var outer = new AgentFeatureCollection(inner);
        var outerThing = new Thing();
        outer.Set<IThing>(outerThing);

        // Act & Assert.
        Assert.True(outer.TryGet(typeof(IThing), out var actualThing));
        Assert.Same(outerThing, actualThing);
    }

    [Fact]
    public void Enumerate_OverridesInnerWithOuterCollection()
    {
        // Arrange.
        var inner = new AgentFeatureCollection();
        var innerThing = new Thing();
        inner.Set<IThing>(innerThing);

        var outer = new AgentFeatureCollection(inner);
        var outerThing = new Thing();
        outer.Set<IThing>(outerThing);

        // Act.
        var items = outer.ToList();

        // Assert.
        Assert.Single(items);
        Assert.Same(outerThing, items.First().Value as IThing);
    }

    private interface IThing
    {
        string Hello();
    }

    private sealed class Thing : IThing
    {
        public string Hello()
        {
            return "World";
        }
    }
}
