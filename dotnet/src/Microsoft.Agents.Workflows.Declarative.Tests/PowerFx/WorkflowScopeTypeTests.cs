// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Xunit;

namespace Microsoft.Agents.Workflows.Declarative.Tests.PowerFx;

public class WorkflowScopeTypeTests
{
    [Fact]
    public void StaticFieldsHaveCorrectNames()
    {
        Assert.Equal(VariableScopeNames.Environment, WorkflowScopeType.Env.Name);
        Assert.Equal(VariableScopeNames.Topic, WorkflowScopeType.Topic.Name);
        Assert.Equal(VariableScopeNames.Global, WorkflowScopeType.Global.Name);
        Assert.Equal(VariableScopeNames.System, WorkflowScopeType.System.Name);
    }

    [Fact]
    public void ParseReturnsCorrectScopeType()
    {
        WorkflowScopeType envScope = WorkflowScopeType.Parse("Env");
        WorkflowScopeType topicScope = WorkflowScopeType.Parse("Topic");
        WorkflowScopeType globalScope = WorkflowScopeType.Parse("Global");
        WorkflowScopeType systemScope = WorkflowScopeType.Parse("System");

        Assert.Same(WorkflowScopeType.Env, envScope);
        Assert.Same(WorkflowScopeType.Topic, topicScope);
        Assert.Same(WorkflowScopeType.Global, globalScope);
        Assert.Same(WorkflowScopeType.System, systemScope);
    }

    [Fact]
    public void ParseThrowsForNullScope()
    {
        InvalidScopeException exception = Assert.Throws<InvalidScopeException>(() => WorkflowScopeType.Parse(null));
        Assert.Equal("Undefined action scope type.", exception.Message);
    }

    [Fact]
    public void ParseThrowsForUnknownScope()
    {
        string unknownScope = "Unknown";
        InvalidScopeException exception = Assert.Throws<InvalidScopeException>(() => WorkflowScopeType.Parse(unknownScope));
        Assert.Equal($"Unknown action scope type: {unknownScope}.", exception.Message);
    }

    [Fact]
    public void FormatReturnsScopedName()
    {
        string variableName = "myVariable";
        
        string formattedEnv = WorkflowScopeType.Env.Format(variableName);
        string formattedTopic = WorkflowScopeType.Topic.Format(variableName);
        string formattedGlobal = WorkflowScopeType.Global.Format(variableName);
        string formattedSystem = WorkflowScopeType.System.Format(variableName);

        Assert.Equal($"{VariableScopeNames.Environment}.{variableName}", formattedEnv);
        Assert.Equal($"{VariableScopeNames.Topic}.{variableName}", formattedTopic);
        Assert.Equal($"{VariableScopeNames.Global}.{variableName}", formattedGlobal);
        Assert.Equal($"{VariableScopeNames.System}.{variableName}", formattedSystem);
    }

    [Fact]
    public void ToStringReturnsName()
    {
        Assert.Equal(VariableScopeNames.Environment, WorkflowScopeType.Env.ToString());
        Assert.Equal(VariableScopeNames.Topic, WorkflowScopeType.Topic.ToString());
        Assert.Equal(VariableScopeNames.Global, WorkflowScopeType.Global.ToString());
        Assert.Equal(VariableScopeNames.System, WorkflowScopeType.System.ToString());
    }

    [Fact]
    public void GetHashCodeReturnsNameHashCode()
    {
        Assert.Equal(VariableScopeNames.Environment.GetHashCode(), WorkflowScopeType.Env.GetHashCode());
        Assert.Equal(VariableScopeNames.Topic.GetHashCode(), WorkflowScopeType.Topic.GetHashCode());
        Assert.Equal(VariableScopeNames.Global.GetHashCode(), WorkflowScopeType.Global.GetHashCode());
        Assert.Equal(VariableScopeNames.System.GetHashCode(), WorkflowScopeType.System.GetHashCode());
    }

    [Fact]
    public void EqualsReturnsTrueForSameType()
    {
        Assert.True(WorkflowScopeType.Env.Equals(WorkflowScopeType.Env));
        Assert.False(WorkflowScopeType.Env.Equals(WorkflowScopeType.Topic));
    }

    [Fact]
    public void EqualsReturnsTrueForMatchingString()
    {
        Assert.True(WorkflowScopeType.Env.Equals(VariableScopeNames.Environment));
        Assert.False(WorkflowScopeType.Env.Equals(VariableScopeNames.Topic));
    }

    [Fact]
    public void EqualsReturnsFalseForNonMatchingTypes()
    {
        Assert.False(WorkflowScopeType.Env.Equals(42));
        Assert.False(WorkflowScopeType.Env.Equals(null));
    }
}
