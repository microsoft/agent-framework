﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
/// <remarks>
/// This class is used to manage the lifecycle of an agent thread.
/// The thread can be not-start, started or ended.
/// </remarks>
public abstract class AgentThread
{
    /// <summary>
    /// Gets the id of the current thread.
    /// </summary>
    public string? Id { get; protected set; }

    /// <summary>
    /// Gets a value indicating whether the thread has been deleted.
    /// </summary>
    public bool IsDeleted { get; protected set; } = false;

    /// <summary>
    /// Creates the thread and returns the thread id.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the thread has been created.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    internal async Task CreateAsync(CancellationToken cancellationToken = default)
    {
        if (this.IsDeleted)
        {
            throw new InvalidOperationException("This thread has been deleted and cannot be recreated.");
        }

        if (this.Id is not null)
        {
            return;
        }

        this.Id = await this.CreateCoreAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Deletes the current thread.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the thread has been deleted.</returns>
    /// <exception cref="InvalidOperationException">The thread was never created.</exception>
    public async Task DeleteAsync(CancellationToken cancellationToken = default)
    {
        if (this.IsDeleted)
        {
            return;
        }

        if (this.Id is null)
        {
            throw new InvalidOperationException("This thread cannot be deleted, since it has not been created.");
        }

        await this.DeleteCoreAsync(cancellationToken).ConfigureAwait(false);

        this.IsDeleted = true;
    }

    /// <summary>
    /// This method is called when a new message has been contributed to the chat by any participant.
    /// </summary>
    /// <remarks>
    /// Inheritors can use this method to update their context based on the new message.
    /// </remarks>
    /// <param name="newMessage">The new message.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    internal async Task OnNewMessageAsync(ChatMessage newMessage, CancellationToken cancellationToken = default)
    {
        if (this.IsDeleted)
        {
            throw new InvalidOperationException("This thread has been deleted and cannot be used anymore.");
        }

        if (this.Id is null)
        {
            await this.CreateAsync(cancellationToken).ConfigureAwait(false);
        }

        await this.OnNewMessageCoreAsync(newMessage, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates the thread and returns the thread id.
    /// Checks have already been completed in the <see cref="CreateAsync"/> method to ensure that the thread can be created.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The id of the thread that was created if one is available.</returns>
    protected abstract Task<string?> CreateCoreAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Deletes the current thread.
    /// Checks have already been completed in the <see cref="DeleteAsync"/> method to ensure that the thread can be deleted.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the thread has been deleted.</returns>
    protected abstract Task DeleteCoreAsync(CancellationToken cancellationToken);

    /// <summary>
    /// This method is called when a new message has been contributed to the chat by any participant.
    /// Checks have already been completed in the <see cref="OnNewMessageAsync"/> method to ensure that the thread can be updated.
    /// </summary>
    /// <param name="newMessage">The new message.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    protected abstract Task OnNewMessageCoreAsync(ChatMessage newMessage, CancellationToken cancellationToken = default);

    /// <summary>Asks the <see cref="AgentThread"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AgentThread"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        Throw.IfNull(serviceType);

        return
            serviceKey is null && serviceType.IsInstanceOfType(this) ? this :
            null;
    }
}
