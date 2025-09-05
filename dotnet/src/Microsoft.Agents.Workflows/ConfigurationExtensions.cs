// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Extensions methods for creating Configured objects
/// </summary>
public static class ConfigurationExtensions
{
    /// <summary>
    /// Creates a <see cref="Configured{TSubject}"/> instance from an existing subject instance.
    /// </summary>
    /// <param name="subject">
    /// The subject instance. If the subject implements <see cref="IIdentified"/>, its ID will be used
    /// and checked against the provided ID (if any).
    /// </param>
    /// <param name="id">
    /// A unique identifier for the configured subject. This is required if the subject does not implement
    /// <see cref="IIdentified"/>
    /// </param>
    /// <param name="raw">
    /// The raw representation of the subject instance.
    /// </param>
    /// <returns></returns>
    public static Configured<TSubject> Configure<TSubject>(this TSubject subject, string? id = null, object? raw = null)
    {
        if (subject is IIdentified identified)
        {
            if (id != null && identified.Id != id)
            {
                throw new ArgumentException($"Provided ID '{id}' does not match subject's ID '{identified.Id}'.", nameof(id));
            }

            return new Configured<TSubject>((_) => new(subject), id: identified.Id, raw: subject);
        }

        if (id == null)
        {
            throw new ArgumentNullException(nameof(id), "ID must be provided when the subject does not implement IIdentified.");
        }

        return new Configured<TSubject>((_) => new(subject), id, raw: subject);
    }

    /// <summary>
    /// Creates a new configuration that treats the subject as its base type, allowing configuration to be applied at
    /// the parent type level.
    /// </summary>
    /// <typeparam name="TSubject">The type of the original subject being configured. Must inherit from or implement TParent.</typeparam>
    /// <typeparam name="TParent">The base type or interface to which the configuration will be upcast.</typeparam>
    /// <param name="configured">The existing configuration for the subject type to be upcast to its parent type. Cannot be null.</param>
    /// <returns>A new <see cref="Configured{TParent}"/> instance that applies the original configuration logic to the parent type.</returns>
    public static Configured<TParent> Super<TSubject, TParent>(this Configured<TSubject> configured) where TSubject : TParent
        => new(async config => await configured.FactoryAsync(config).ConfigureAwait(false), configured.Id, configured.Raw);

    /// <summary>
    /// Creates a new configuration that treats the subject as its base type, allowing configuration to be applied at
    /// the parent type level.
    /// </summary>
    /// <typeparam name="TSubject">The type of the original subject being configured. Must inherit from or implement TParent.</typeparam>
    /// <typeparam name="TParent">The base type or interface to which the configuration will be upcast.</typeparam>
    /// <typeparam name="TSubjectOptions">The type of configuration options for the original subject being configured.</typeparam>
    /// <param name="configured">The existing configuration for the subject type to be upcast to its parent type. Cannot be null.</param>
    /// <returns>A new <see cref="Configured{TParent}"/> instance that applies the original configuration logic to the parent type.</returns>
    public static Configured<TParent> Super<TSubject, TParent, TSubjectOptions>(this Configured<TSubject, TSubjectOptions> configured) where TSubject : TParent
        => configured.Memoize().Super<TSubject, TParent>();
}
