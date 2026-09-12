// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace ClawAgent;

/// <summary>
/// Contains the built production-ready claw agent and resources that must live as long as the agent.
/// </summary>
public sealed class ClawAgentBuild : IAsyncDisposable
{
    private readonly List<IDisposable> _disposables;
    private readonly List<IAsyncDisposable> _asyncDisposables;
    private bool _disposed;

    internal ClawAgentBuild(
        AIAgent agent,
        bool foundrySkillsEnabled,
        bool purviewEnabled,
        IEnumerable<IDisposable> disposables,
        IEnumerable<IAsyncDisposable> asyncDisposables)
    {
        this.Agent = agent;
        this.FoundrySkillsEnabled = foundrySkillsEnabled;
        this.PurviewEnabled = purviewEnabled;
        this._disposables = [.. disposables];
        this._asyncDisposables = [.. asyncDisposables];
    }

    /// <summary>
    /// Gets the fully configured claw agent.
    /// </summary>
    public AIAgent Agent { get; }

    /// <summary>
    /// Gets a value indicating whether Foundry Toolbox MCP skills were enabled.
    /// </summary>
    public bool FoundrySkillsEnabled { get; }

    /// <summary>
    /// Gets a value indicating whether Purview governance was enabled.
    /// </summary>
    public bool PurviewEnabled { get; }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        foreach (IAsyncDisposable disposable in this._asyncDisposables)
        {
            await disposable.DisposeAsync().ConfigureAwait(false);
        }

        foreach (IDisposable disposable in this._disposables)
        {
            disposable.Dispose();
        }
    }
}
