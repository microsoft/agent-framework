// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Describes the type of action scope.
/// </summary>
internal sealed class WorkflowScopeType
{
    // https://msazure.visualstudio.com/CCI/_git/ObjectModel?path=/src/ObjectModel/Nodes/VariableScopeNames.cs&_a=contents&version=GBmain
    public static readonly WorkflowScopeType Env = new(VariableScopeNames.Environment);
    public static readonly WorkflowScopeType Topic = new(VariableScopeNames.Topic);
    public static readonly WorkflowScopeType Global = new(VariableScopeNames.Global);
    public static readonly WorkflowScopeType System = new(VariableScopeNames.System);

    public static WorkflowScopeType Parse(string? scope)
    {
        return scope switch
        {
            nameof(Env) => Env,
            nameof(Global) => Global,
            nameof(System) => System,
            nameof(Topic) => Topic,
            null => throw new InvalidScopeException("Undefined action scope type."),
            _ => throw new InvalidScopeException($"Unknown action scope type: {scope}."),
        };
    }

    private WorkflowScopeType(string name)
    {
        this.Name = name;
    }

    public string Name { get; }

    public string Format(string name) => $"{this.Name}.{name}";

    public override string ToString() => this.Name;

    public override int GetHashCode() => this.Name.GetHashCode();

    public override bool Equals(object? obj) =>
        (obj is WorkflowScopeType other && this.Name.Equals(other.Name, StringComparison.Ordinal)) ||
        (obj is string name && this.Name.Equals(name, StringComparison.Ordinal));
}
