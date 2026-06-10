// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Shared behavior knobs for A2UI tool factories. Every framework adapter accepts this
/// exact shape, so a new knob reaches all adapters without signature changes.
/// </summary>
/// <remarks>
/// Mirrors <c>A2UIToolParams</c> in the sibling toolkits, minus the <c>model</c> field:
/// in .NET the subagent chat client is a framework concern owned by the adapter's own
/// factory signature, not by this parameter object.
/// </remarks>
public sealed class A2UIToolParams
{
    /// <summary>Gets the prompt-section overrides.</summary>
    public A2UIGuidelines? Guidelines { get; init; }

    /// <summary>Gets the fallback surface id. Empty or unset falls back to <see cref="A2UIConstants.DefaultSurfaceId"/>.</summary>
    public string? DefaultSurfaceId { get; init; }

    /// <summary>Gets the catalog id for created surfaces. Empty or unset falls back to <see cref="A2UIConstants.BasicCatalogId"/>.</summary>
    public string? DefaultCatalogId { get; init; }

    /// <summary>Gets the planner-facing tool name. Empty or unset falls back to <see cref="A2UIConstants.GenerateA2UIToolName"/>.</summary>
    public string? ToolName { get; init; }

    /// <summary>Gets the planner-facing tool description. Empty or unset falls back to the canonical description.</summary>
    public string? ToolDescription { get; init; }

    /// <summary>Gets the catalog used for semantic validation in the recovery loop.</summary>
    public A2UIValidationCatalog? Catalog { get; init; }

    /// <summary>Gets the recovery-loop configuration.</summary>
    public A2UIRecoveryConfig? Recovery { get; init; }

    /// <summary>Gets the per-attempt observability callback.</summary>
    public Action<A2UIAttemptRecord>? OnAttempt { get; init; }
}

/// <summary>
/// <see cref="A2UIToolParams"/> with every defaultable field resolved to its effective value.
/// </summary>
/// <param name="Guidelines">The prompt-section overrides, passed through.</param>
/// <param name="DefaultSurfaceId">The effective fallback surface id.</param>
/// <param name="DefaultCatalogId">The effective default catalog id.</param>
/// <param name="ToolName">The effective planner-facing tool name.</param>
/// <param name="ToolDescription">The effective planner-facing tool description.</param>
/// <param name="Catalog">The validation catalog, passed through.</param>
/// <param name="Recovery">The recovery configuration, passed through.</param>
/// <param name="OnAttempt">The per-attempt callback, passed through.</param>
public sealed record A2UIResolvedToolParams(
    A2UIGuidelines? Guidelines,
    string DefaultSurfaceId,
    string DefaultCatalogId,
    string ToolName,
    string ToolDescription,
    A2UIValidationCatalog? Catalog,
    A2UIRecoveryConfig? Recovery,
    Action<A2UIAttemptRecord>? OnAttempt);

/// <summary>
/// Canonical tool definitions and descriptions shared by all A2UI adapters.
/// </summary>
public static class A2UIToolDefinitions
{
    /// <summary>
    /// Gets the planner-facing description of the <c>generate_a2ui</c> tool.
    /// </summary>
    public static string GenerateA2UIToolDescription
        => "[[A2UI_GENERATE_TOOL_DESCRIPTION_PLACEHOLDER]]"; // TODO(a2ui-port): verbatim text from sibling toolkits.

    /// <summary>
    /// Creates the OpenAI-style function definition of the inner <c>render_a2ui</c>
    /// structured-output tool (<c>surfaceId</c>, <c>components</c>, <c>data</c>;
    /// <c>surfaceId</c> and <c>components</c> required).
    /// </summary>
    /// <returns>A fresh, caller-owned <see cref="JsonObject"/> with the tool definition.</returns>
    public static JsonObject CreateRenderA2UIToolDefinition()
        => throw new NotImplementedException();

    /// <summary>
    /// Fills canonical defaults for every unset or empty-string field of
    /// <paramref name="parameters"/>. Empty strings fall back to defaults rather than
    /// propagating into tool advertisements or emitted operations.
    /// </summary>
    /// <param name="parameters">The raw parameters, or <see langword="null"/> for all defaults.</param>
    /// <returns>The resolved parameters.</returns>
    public static A2UIResolvedToolParams ResolveA2UIToolParams(A2UIToolParams? parameters)
        => throw new NotImplementedException();
}

/// <summary>
/// The built-in default prompt blocks shared by all adapters. The exact text is part of
/// the cross-language contract and is ported verbatim from the sibling toolkits.
/// </summary>
public static class A2UIPromptDefaults
{
    /// <summary>
    /// Gets the default generation-guidelines block (A2UI protocol rules: ids, paths,
    /// bindings, data model).
    /// </summary>
    public static string GenerationGuidelines
        => "[[A2UI_DEFAULT_GENERATION_GUIDELINES_PLACEHOLDER]]"; // TODO(a2ui-port): verbatim text from sibling toolkits.

    /// <summary>
    /// Gets the default design-guidelines block (visual hierarchy, layout patterns).
    /// </summary>
    public static string DesignGuidelines
        => "[[A2UI_DEFAULT_DESIGN_GUIDELINES_PLACEHOLDER]]"; // TODO(a2ui-port): verbatim text from sibling toolkits.
}
