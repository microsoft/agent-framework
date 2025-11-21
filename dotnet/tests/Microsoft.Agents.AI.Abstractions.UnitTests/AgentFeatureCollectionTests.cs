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
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces.Set<IThing>(thing);

        Assert.True(interfaces.TryGet<IThing>(out var actualThing));
        Assert.Same(actualThing, thing);
    }

    [Fact]
    public void Remove_Removes()
    {
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces.Set<IThing>(thing);
        Assert.True(interfaces.TryGet<IThing>(out _));

        interfaces.Remove<IThing>();

        Assert.False(interfaces.TryGet<IThing>(out _));
    }

    [Fact]
    public void TryGetMissingFeature_ReturnsFalse()
    {
        var interfaces = new AgentFeatureCollection();

        Assert.False(interfaces.TryGet<Thing>(out var actualThing));
        Assert.Null(actualThing);
    }

    [Fact]
    public void Set_Null_Throws()
    {
        var interfaces = new AgentFeatureCollection();
        Assert.Throws<ArgumentNullException>(() => interfaces.Set<IThing>(null!));
    }

    [Fact]
    public void IsReadOnly_DefaultsToFalse()
    {
        var interfaces = new AgentFeatureCollection();
        Assert.False(interfaces.IsReadOnly);
    }

    [Fact]
    public void TryGet_FallsBackToInnerCollection()
    {
        var inner = new AgentFeatureCollection();
        var thing = new Thing();
        inner.Set<IThing>(thing);

        var outer = new AgentFeatureCollection(inner);
        Assert.True(outer.TryGet<IThing>(out var actualThing));
        Assert.Same(actualThing, thing);
    }

    [Fact]
    public void TryGet_OverridesInnerWithOuterCollection()
    {
        var inner = new AgentFeatureCollection();
        var innerThing = new Thing();
        inner.Set<IThing>(innerThing);

        var outer = new AgentFeatureCollection(inner);
        var outerThing = new Thing();
        outer.Set<IThing>(outerThing);

        Assert.True(outer.TryGet<IThing>(out var actualThing));
        Assert.Same(outerThing, actualThing);
    }

    [Fact]
    public void Enumerate_OverridesInnerWithOuterCollection()
    {
        var inner = new AgentFeatureCollection();
        var innerThing = new Thing();
        inner.Set<IThing>(innerThing);

        var outer = new AgentFeatureCollection(inner);
        var outerThing = new Thing();
        outer.Set<IThing>(outerThing);

        var items = outer.ToList();
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
