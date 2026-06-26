// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Resolves persisted assembly-qualified type-name strings to a loaded <see cref="Type"/>,
/// tolerating differences in assembly version, culture, and public key token between the
/// persisted name and the currently loaded assemblies. Results are cached.
/// </summary>
internal static class DurableTaskTypeResolver
{
    private static readonly ConcurrentDictionary<string, Type?> s_cache = new();

    /// <summary>
    /// Resolves <paramref name="typeName"/> using a qualified <see cref="Type.GetType(string, bool)"/>
    /// lookup, then a partial-name fallback that strips embedded version, culture, and public key
    /// token qualifiers.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Workflow message and event types are registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2057:Unrecognized value passed to the parameter of method", Justification = "Workflow message and event types are registered at startup.")]
    internal static Type? Resolve(string typeName)
        => s_cache.GetOrAdd(typeName, static name =>
        {
            Type? type = Type.GetType(name, throwOnError: false);
            if (type is not null)
            {
                return type;
            }

            string normalized = TypeId.NormalizeTypeName(name);
            return ReferenceEquals(normalized, name)
                ? null
                : Type.GetType(normalized, throwOnError: false);
        });
}
