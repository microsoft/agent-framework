// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// An interface for a class that manages background jobs.
/// </summary>
internal interface IBackgroundJobRunner
{
    /// <summary>
    /// Shutdown the background jobs.
    /// </summary>
    Task ShutdownAsync();
}
