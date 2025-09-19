// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Moq;

namespace Microsoft.Agents.Orchestration.UnitTest;

public class HandoffsTests
{
    [Fact]
    public void StartWith_ValidAgent_ReturnsHandoffsInstance()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");

        // Act
        var handoffs = Handoffs.StartWith(agent);

        // Assert
        Assert.NotNull(handoffs);
        Assert.Equal(agent, handoffs.InitialAgent);
        Assert.Contains(agent, handoffs.Agents);
        Assert.Empty(handoffs.Targets);
    }

    [Fact]
    public void StartWith_NullAgent_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("initialAgent", () => Handoffs.StartWith(null!));

    [Fact]
    public void Add_ValidSourceAndTargets_AddsHandoffRelationships()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent1 = CreateAgent("target1", "Target agent 1");
        var targetAgent2 = CreateAgent("target2", "Target agent 2");
        var handoffs = Handoffs.StartWith(sourceAgent);

        // Act
        var result = handoffs.Add(sourceAgent, [targetAgent1, targetAgent2]);

        // Assert
        Assert.Same(handoffs, result); // Should return the same instance for fluent API
        Assert.Contains(sourceAgent, handoffs.Agents);
        Assert.Contains(targetAgent1, handoffs.Agents);
        Assert.Contains(targetAgent2, handoffs.Agents);

        Assert.True(handoffs.Targets.ContainsKey(sourceAgent));
        Assert.Equal(2, handoffs.Targets[sourceAgent].Count);

        var targetNames = handoffs.Targets[sourceAgent].Select(t => t.Target.Id).ToArray();
        Assert.Contains("target1", targetNames);
        Assert.Contains("target2", targetNames);
    }

    [Fact]
    public void Add_NullSource_ThrowsArgumentNullException()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var handoffs = Handoffs.StartWith(agent);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("source", () => handoffs.Add(null!, agent));
    }

    [Fact]
    public void Add_NullTargets_ThrowsArgumentNullException()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var handoffs = Handoffs.StartWith(sourceAgent);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("targets", () => handoffs.Add(sourceAgent, null!));
    }

    [Fact]
    public void Add_SingleTargetWithCustomReason_AddsHandoffWithReason()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        const string CustomReason = "Custom handoff reason";

        // Act
        var result = handoffs.Add(sourceAgent, targetAgent, CustomReason);

        // Assert
        Assert.Same(handoffs, result);
        Assert.True(handoffs.Targets.ContainsKey(sourceAgent));
        var target = handoffs.Targets[sourceAgent].Single();
        Assert.Equal(targetAgent, target.Target);
        Assert.Equal(CustomReason, target.Reason);
    }

    [Fact]
    public void Add_SingleTargetWithNullSource_ThrowsArgumentNullException()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var handoffs = Handoffs.StartWith(agent);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("source", () => handoffs.Add(null!, agent, "reason"));
    }

    [Fact]
    public void Add_SingleTargetWithNullTarget_ThrowsArgumentNullException()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var handoffs = Handoffs.StartWith(sourceAgent);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("target", () => handoffs.Add(sourceAgent, null!, "reason"));
    }

    [Fact]
    public void Add_DuplicateHandoff_ThrowsInvalidOperationException()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => handoffs.Add(sourceAgent, targetAgent));
    }

    [Fact]
    public void Build_WithoutName_ReturnsHandoffOrchestration()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var handoffs = Handoffs.StartWith(agent);

        // Act
        var orchestration = handoffs.Build();

        // Assert
        Assert.NotNull(orchestration);
        Assert.IsType<HandoffOrchestration>(orchestration);
    }

    [Fact]
    public void Build_WithName_ReturnsHandoffOrchestrationWithName()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var handoffs = Handoffs.StartWith(agent);
        const string OrchestrationName = "Test Orchestration";

        // Act
        var orchestration = handoffs.Build(OrchestrationName);

        // Assert
        Assert.NotNull(orchestration);
        Assert.IsType<HandoffOrchestration>(orchestration);
        Assert.Equal(OrchestrationName, orchestration.Name);
    }

    [Fact]
    public void IReadOnlyDictionary_Indexer_ReturnsTargetsForAgent()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var targets = readOnlyDict[sourceAgent];

        // Assert
        Assert.NotNull(targets);
        Assert.Single(targets);
        Assert.Equal(targetAgent, targets.First().Target);
    }

    [Fact]
    public void IReadOnlyDictionary_Keys_ReturnsSourceAgents()
    {
        // Arrange
        var sourceAgent1 = CreateAgent("source1", "Source agent 1");
        var sourceAgent2 = CreateAgent("source2", "Source agent 2");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent1)
            .Add(sourceAgent1, targetAgent)
            .Add(sourceAgent2, targetAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var keys = readOnlyDict.Keys;

        // Assert
        Assert.Equal(2, keys.Count());
        Assert.Contains(sourceAgent1, keys);
        Assert.Contains(sourceAgent2, keys);
    }

    [Fact]
    public void IReadOnlyDictionary_Values_ReturnsAllTargetCollections()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent1 = CreateAgent("target1", "Target agent 1");
        var targetAgent2 = CreateAgent("target2", "Target agent 2");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, [targetAgent1, targetAgent2]);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var values = readOnlyDict.Values;

        // Assert
        Assert.Single(values);
        Assert.Equal(2, values.First().Count());
    }

    [Fact]
    public void IReadOnlyDictionary_Count_ReturnsNumberOfSourceAgents()
    {
        // Arrange
        var sourceAgent1 = CreateAgent("source1", "Source agent 1");
        var sourceAgent2 = CreateAgent("source2", "Source agent 2");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent1)
            .Add(sourceAgent1, targetAgent)
            .Add(sourceAgent2, targetAgent);
        var readOnlyCollection = (IReadOnlyCollection<KeyValuePair<AIAgent, IEnumerable<Handoffs.HandoffTarget>>>)handoffs;

        // Act
        var count = readOnlyCollection.Count;

        // Assert
        Assert.Equal(2, count);
    }

    [Fact]
    public void IReadOnlyDictionary_ContainsKey_ExistingAgent_ReturnsTrue()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var contains = readOnlyDict.ContainsKey(sourceAgent);

        // Assert
        Assert.True(contains);
    }

    [Fact]
    public void IReadOnlyDictionary_ContainsKey_NonExistingAgent_ReturnsFalse()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var otherAgent = CreateAgent("other", "Other agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var contains = readOnlyDict.ContainsKey(otherAgent);

        // Assert
        Assert.False(contains);
    }

    [Fact]
    public void IReadOnlyDictionary_TryGetValue_ExistingAgent_ReturnsTrueAndValue()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var success = readOnlyDict.TryGetValue(sourceAgent, out var targets);

        // Assert
        Assert.True(success);
        Assert.NotNull(targets);
        Assert.Single(targets);
        Assert.Equal(targetAgent, targets.First().Target);
    }

    [Fact]
    public void IReadOnlyDictionary_TryGetValue_NonExistingAgent_ReturnsFalseAndEmptyCollection()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var otherAgent = CreateAgent("other", "Other agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        var readOnlyDict = (IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)handoffs;

        // Act
        var success = readOnlyDict.TryGetValue(otherAgent, out var targets);

        // Assert
        Assert.False(success);
        Assert.NotNull(targets);
        Assert.Empty(targets);
    }

    [Fact]
    public void IEnumerable_GetEnumerator_IteratesOverHandoffs()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);
        var enumerable = (IEnumerable<KeyValuePair<AIAgent, IEnumerable<Handoffs.HandoffTarget>>>)handoffs;

        // Act
        var items = enumerable.ToArray();

        // Assert
        Assert.Single(items);
        Assert.Equal(sourceAgent, items[0].Key);
        Assert.Single(items[0].Value);
        Assert.Equal(targetAgent, items[0].Value.First().Target);
    }

    [Fact]
    public void IEnumerable_NonGeneric_GetEnumerator_IteratesOverHandoffs()
    {
        // Arrange
        var sourceAgent = CreateAgent("source", "Source agent");
        var targetAgent = CreateAgent("target", "Target agent");
        var handoffs = Handoffs.StartWith(sourceAgent);
        handoffs.Add(sourceAgent, targetAgent);
        var enumerable = (IEnumerable)handoffs;

        // Act
        var enumerator = enumerable.GetEnumerator();
        var items = new List<KeyValuePair<AIAgent, IEnumerable<Handoffs.HandoffTarget>>>();
        while (enumerator.MoveNext())
        {
            items.Add((KeyValuePair<AIAgent, IEnumerable<Handoffs.HandoffTarget>>)enumerator.Current);
        }

        // Assert
        Assert.Single(items);
        Assert.Equal(sourceAgent, items[0].Key);
        Assert.Single(items[0].Value);
        Assert.Equal(targetAgent, items[0].Value.First().Target);
    }

    [Fact]
    public void HandoffTarget_Constructor_WithValidTarget_CreatesTarget()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");

        // Act
        var target = new Handoffs.HandoffTarget(agent);

        // Assert
        Assert.Equal(agent, target.Target);
        Assert.Equal("Test agent", target.Reason); // Should use description as reason
    }

    [Fact]
    public void HandoffTarget_Constructor_WithValidTargetAndReason_CreatesTargetWithReason()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        const string Reason = "Custom reason";

        // Act
        var target = new Handoffs.HandoffTarget(agent, Reason);

        // Assert
        Assert.Equal(agent, target.Target);
        Assert.Equal(Reason, target.Reason);
    }

    [Fact]
    public void HandoffTarget_Constructor_WithNullTarget_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new Handoffs.HandoffTarget(null!));

    [Fact]
    public void HandoffTarget_Constructor_WithAgentWithoutDescriptionOrName_ThrowsInvalidOperationException()
    {
        // Arrange
        var agent = CreateAgent("agent1"); // No description or name

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => new Handoffs.HandoffTarget(agent));
    }

    [Fact]
    public void HandoffTarget_Constructor_WithAgentWithNameButNoDescription_UsesName()
    {
        // Arrange
        var agent = CreateAgent("agent1", description: null, name: "Agent Name");

        // Act
        var target = new Handoffs.HandoffTarget(agent);

        // Assert
        Assert.Equal(agent, target.Target);
        Assert.Equal("Agent Name", target.Reason);
    }

    [Fact]
    public void HandoffTarget_Constructor_WithEmptyReason_UsesAgentDescription()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");

        // Act
        var target = new Handoffs.HandoffTarget(agent, "");

        // Assert
        Assert.Equal(agent, target.Target);
        Assert.Equal("Test agent", target.Reason);
    }

    [Fact]
    public void HandoffTarget_Constructor_WithWhitespaceReason_UsesAgentDescription()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");

        // Act
        var target = new Handoffs.HandoffTarget(agent, "   ");

        // Assert
        Assert.Equal(agent, target.Target);
        Assert.Equal("Test agent", target.Reason);
    }

    [Fact]
    public void HandoffTarget_Equals_SameTarget_ReturnsTrue()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var target1 = new Handoffs.HandoffTarget(agent, "Reason 1");
        var target2 = new Handoffs.HandoffTarget(agent, "Reason 2"); // Different reason, same target

        // Act
        var equals = target1.Equals(target2);

        // Assert
        Assert.True(equals);
    }

    [Fact]
    public void HandoffTarget_Equals_DifferentTarget_ReturnsFalse()
    {
        // Arrange
        var agent1 = CreateAgent("agent1", "Test agent 1");
        var agent2 = CreateAgent("agent2", "Test agent 2");
        var target1 = new Handoffs.HandoffTarget(agent1);
        var target2 = new Handoffs.HandoffTarget(agent2);

        // Act
        var equals = target1.Equals(target2);

        // Assert
        Assert.False(equals);
    }

    [Fact]
    public void HandoffTarget_Equals_Object_SameTarget_ReturnsTrue()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var target1 = new Handoffs.HandoffTarget(agent);
        object target2 = new Handoffs.HandoffTarget(agent);

        // Act
        var equals = target1.Equals(target2);

        // Assert
        Assert.True(equals);
    }

    [Fact]
    public void HandoffTarget_Equals_Object_DifferentType_ReturnsFalse()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var target = new Handoffs.HandoffTarget(agent);
        object other = "not a HandoffTarget";

        // Act
        var equals = target.Equals(other);

        // Assert
        Assert.False(equals);
    }

    [Fact]
    public void HandoffTarget_GetHashCode_SameTarget_ReturnsSameHashCode()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var target1 = new Handoffs.HandoffTarget(agent, "Reason 1");
        var target2 = new Handoffs.HandoffTarget(agent, "Reason 2");

        // Act
        var hashCode1 = target1.GetHashCode();
        var hashCode2 = target2.GetHashCode();

        // Assert
        Assert.Equal(hashCode1, hashCode2);
    }

    [Fact]
    public void HandoffTarget_EqualityOperator_SameTarget_ReturnsTrue()
    {
        // Arrange
        var agent = CreateAgent("agent1", "Test agent");
        var target1 = new Handoffs.HandoffTarget(agent);
        var target2 = new Handoffs.HandoffTarget(agent);

        // Act
        var equals = target1 == target2;

        // Assert
        Assert.True(equals);
    }

    [Fact]
    public void HandoffTarget_InequalityOperator_DifferentTarget_ReturnsTrue()
    {
        // Arrange
        var agent1 = CreateAgent("agent1", "Test agent 1");
        var agent2 = CreateAgent("agent2", "Test agent 2");
        var target1 = new Handoffs.HandoffTarget(agent1);
        var target2 = new Handoffs.HandoffTarget(agent2);

        // Act
        var notEquals = target1 != target2;

        // Assert
        Assert.True(notEquals);
    }

    [Fact]
    public void FluentAPI_ChainMultipleAdds_WorksCorrectly()
    {
        // Arrange
        var agent1 = CreateAgent("agent1", "Agent 1");
        var agent2 = CreateAgent("agent2", "Agent 2");
        var agent3 = CreateAgent("agent3", "Agent 3");
        var agent4 = CreateAgent("agent4", "Agent 4");

        // Act
        var handoffs = Handoffs
            .StartWith(agent1)
            .Add(agent1, [agent2, agent3])
            .Add(agent2, agent4)
            .Add(agent3, agent4, "Special handoff reason");

        // Assert
        Assert.Equal(agent1, handoffs.InitialAgent);
        Assert.Equal(4, handoffs.Agents.Count);
        Assert.Equal(3, handoffs.Targets.Count);

        // Verify agent1 handoffs
        Assert.Equal(2, handoffs.Targets[agent1].Count);

        // Verify agent2 handoffs
        Assert.Single(handoffs.Targets[agent2]);
        Assert.Equal(agent4, handoffs.Targets[agent2].First().Target);

        // Verify agent3 handoffs
        Assert.Single(handoffs.Targets[agent3]);
        Assert.Equal(agent4, handoffs.Targets[agent3].First().Target);
        Assert.Equal("Special handoff reason", handoffs.Targets[agent3].First().Reason);
    }

    private static ChatClientAgent CreateAgent(string id, string? description = null, string? name = null)
    {
        Mock<IChatClient> mockClient = new(MockBehavior.Loose);
        ChatClientAgentOptions options =
            new()
            {
                Id = id,
                Name = name,
                Description = description,
            };
        return new(mockClient.Object, options);
    }
}
