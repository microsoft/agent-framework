// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Sets an environment variable for the lifetime of the scope and restores its previous value on dispose.
/// Used to drive the Foundry hosting-environment gate deterministically inside a non-parallel collection.
/// </summary>
internal sealed class EnvVarScope : IDisposable
{
    private readonly string _name;
    private readonly string? _previous;

    public EnvVarScope(string name, string? value)
    {
        this._name = name;
        this._previous = Environment.GetEnvironmentVariable(name);
        Environment.SetEnvironmentVariable(name, value);
    }

    public void Dispose() => Environment.SetEnvironmentVariable(this._name, this._previous);
}
