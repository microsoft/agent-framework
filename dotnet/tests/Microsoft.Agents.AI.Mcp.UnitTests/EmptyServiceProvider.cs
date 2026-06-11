// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

/// <summary>
/// Minimal empty <see cref="IServiceProvider"/> for in-memory fixtures that don't use DI.
/// </summary>
internal sealed class EmptyServiceProvider : IServiceProvider
{
    public static EmptyServiceProvider Instance { get; } = new();

    public object? GetService(Type serviceType) => null;
}
