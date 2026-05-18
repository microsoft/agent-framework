// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

// TODO(https://github.com/microsoft/agent-framework/issues/5905): remove these workarounds
// once the Microsoft.Agents.ObjectModel regression that broke PropertyPath parsing of
// dotted references such as "Local.Triage" is fixed and the "Local" scope alias is
// recognized again by VariableScopeNames.IsValidName / GetNamespaceFromName.
internal static class PropertyPathExtensions
{
    // User-facing alias for the canonical "Topic" scope. ObjectModel 2026.2.4.1 no longer
    // accepts this alias in VariableScopeNames.IsValidName, which causes IsManagedScope
    // checks to fail and State.Set to silently skip the update. Translate to canonical form.
    internal const string LocalScopeAlias = "Local";

    /// <summary>
    /// Returns the variable name from <paramref name="variablePath"/>, falling back to the
    /// last segment when <see cref="PropertyPath.VariableName"/> is null (ObjectModel
    /// 2026.2.4.1 returns null for dotted refs like "Local.Triage" even when SegmentCount
    /// is 2 and IsValid is true).
    /// </summary>
    internal static string? GetVariableName(this PropertyPath variablePath)
    {
        if (variablePath.VariableName is { } name)
        {
            return name;
        }

        var segments = variablePath.Segments().ToArray();
        return segments.Length switch
        {
            0 => null,
            1 => segments[0].PropertyName,
            // Variable name is the segment immediately after the scope alias. Any trailing
            // segments are dotted property accessors handled by the PowerFx evaluator and
            // are not part of the addressable variable name.
            _ => segments[1].PropertyName,
        };
    }

    /// <summary>
    /// Returns the namespace alias from <paramref name="variablePath"/>, falling back to the
    /// first segment when <see cref="PropertyPath.NamespaceAlias"/> is null, and remapping
    /// the user-facing "Local" alias to its canonical <see cref="VariableScopeNames.Topic"/>
    /// form (see <see cref="LocalScopeAlias"/>).
    /// </summary>
    internal static string? GetNamespaceAlias(this PropertyPath variablePath)
    {
        string? alias = variablePath.NamespaceAlias;
        if (alias is null && variablePath.SegmentCount >= 2)
        {
            alias = variablePath.Segments().FirstOrDefault().PropertyName;
        }

        return string.Equals(alias, LocalScopeAlias, StringComparison.Ordinal)
            ? VariableScopeNames.Topic
            : alias;
    }
}
