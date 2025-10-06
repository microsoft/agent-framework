// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extensions methods for creating <see cref="Configured{TSubject}"/> objects
/// </summary>
public static class ConfigurationExtensions
{
    /// <summary>
    /// Creates a new configuration that treats the subject as its base type, allowing configuration to be applied at
    /// the parent type level.
    /// </summary>
    /// <typeparam name="TSubject">The type of the original subject being configured. Must inherit from or implement TParent.</typeparam>
    /// <typeparam name="TParent">The base type or interface to which the configuration will be upcast.</typeparam>
    /// <param name="configured">The existing configuration for the subject type to be upcast to its parent type. Cannot be null.</param>
    /// <returns>A new <see cref="Configured{TParent}"/> instance that applies the original configuration logic to the parent type.</returns>
    public static Configured<TParent> Super<TSubject, TParent>(this Configured<TSubject> configured) where TSubject : TParent
        => new(async (config, runId) => await configured.FactoryAsync(config, runId).ConfigureAwait(false), configured.Id, configured.Raw);

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
