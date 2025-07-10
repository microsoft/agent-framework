// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

// TODO: Why is this interface needed? It's inherited by IAgentRuntime and IRuntimeActor.
// Is the former needed (does IAgentRuntime need to not only persist every actor but do so via
// this interface)? If not, these methods could be moved to IRuntimeActor.

/// <summary>
/// Defines a contract for saving and loading the state of an object as JSON.
/// </summary>
public interface ISaveState
{
    /// <summary>
    /// Saves the current state of the object.
    /// </summary>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>
    /// A task representing the asynchronous operation, returning a dictionary
    /// containing the saved state. The structure of the state is implementation-defined
    /// but must be JSON serializable.
    /// </returns>
    ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Loads a previously saved state into the object.
    /// </summary>
    /// <param name="state">
    /// A dictionary representing the saved state. The structure of the state
    /// is implementation-defined but must be JSON serializable.
    /// </param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default);
}
