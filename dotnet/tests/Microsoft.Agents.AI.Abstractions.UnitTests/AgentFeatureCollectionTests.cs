// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains unit tests for the <see cref="AgentFeatureCollection"/> class.
/// </summary>
public class AgentFeatureCollectionTests
{
    [Fact]
    public void AddedInterfaceIsReturned()
    {
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces[typeof(IThing)] = thing;

        var thing2 = interfaces[typeof(IThing)];
        Assert.Equal(thing2, thing);
    }

    [Fact]
    public void IndexerAlsoAddsItems()
    {
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces[typeof(IThing)] = thing;

        Assert.Equal(interfaces[typeof(IThing)], thing);
    }

    [Fact]
    public void SetNullValueRemoves()
    {
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();

        interfaces[typeof(IThing)] = thing;
        Assert.Equal(interfaces[typeof(IThing)], thing);

        interfaces[typeof(IThing)] = null;

        var thing2 = interfaces[typeof(IThing)];
        Assert.Null(thing2);
    }

    [Fact]
    public void GetMissingStructFeatureThrows()
    {
        var interfaces = new AgentFeatureCollection();

        var ex = Assert.Throws<InvalidOperationException>(() => interfaces.Get<int>());
        Assert.Equal("System.Int32 does not exist in the feature collection and because it is a struct the method can't return null. Use 'AgentFeatureCollection[typeof(System.Int32)] is not null' to check if the feature exists.", ex.Message);
    }

    [Fact]
    public void GetMissingFeatureReturnsNull()
    {
        var interfaces = new AgentFeatureCollection();

        Assert.Null(interfaces.Get<Thing>());
    }

    [Fact]
    public void GetStructFeature()
    {
        var interfaces = new AgentFeatureCollection();
        const int Value = 20;
        interfaces.Set(Value);

        Assert.Equal(Value, interfaces.Get<int>());
    }

    [Fact]
    public void GetNullableStructFeatureWhenSetWithNonNullableStruct()
    {
        var interfaces = new AgentFeatureCollection();
        const int Value = 20;
        interfaces.Set(Value);

        Assert.Null(interfaces.Get<int?>());
    }

    [Fact]
    public void GetNullableStructFeatureWhenSetWithNullableStruct()
    {
        var interfaces = new AgentFeatureCollection();
        const int Value = 20;
        interfaces.Set<int?>(Value);

        Assert.Equal(Value, interfaces.Get<int?>());
    }

    [Fact]
    public void GetFeature()
    {
        var interfaces = new AgentFeatureCollection();
        var thing = new Thing();
        interfaces.Set(thing);

        Assert.Equal(thing, interfaces.Get<Thing>());
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
