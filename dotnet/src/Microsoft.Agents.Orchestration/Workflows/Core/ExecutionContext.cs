// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Orchestration.Workflows.Core;

/// <summary>
/// Provides services for <see cref="Executor"/> subclasses.
/// </summary>
public interface IExecutionContext
{
    /// <summary>
    /// .
    /// </summary>
    /// <returns></returns>
    Task MagicAsync();
}
