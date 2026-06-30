// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// One AG-UI context entry as forwarded to the agent (description/value pair).
/// </summary>
/// <param name="Description">The optional section heading for the entry.</param>
/// <param name="Value">The entry content.</param>
public sealed record A2UIContextEntry(string? Description, string? Value);

/// <summary>
/// The AG-UI slice of agent state the toolkit reads: forwarded context entries and
/// the component catalog schema, when the host supplied one.
/// </summary>
/// <remarks>
/// Mirrors the <c>state["ag-ui"]</c> contract of the sibling toolkits
/// (<c>context</c> + <c>a2ui_schema</c>). Adapters populate this from the transport,
/// e.g. the AG-UI hosting layer's <c>ag_ui_context</c> additional property.
/// </remarks>
public sealed class A2UIAgentState
{
    /// <summary>
    /// Gets the forwarded AG-UI context entries, when present.
    /// </summary>
    public IReadOnlyList<A2UIContextEntry>? Context { get; init; }

    /// <summary>
    /// Gets the A2UI component catalog schema (serialized JSON), when present.
    /// </summary>
    public string? A2UISchema { get; init; }
}

/// <summary>
/// A conversation-history message as seen by the surface walker. Adapters map their
/// framework's message type onto this shape; only tool-result messages with string
/// content participate in surface reconstruction.
/// </summary>
/// <param name="Role">The message role; tool results carry <c>"tool"</c>.</param>
/// <param name="Content">The raw message content.</param>
public sealed record A2UIHistoryMessage(string? Role, string? Content);

/// <summary>
/// The reconstructed end state of a previously rendered surface, used to seed
/// update-intent prompts and envelopes.
/// </summary>
/// <param name="Components">The last known component array, when seen.</param>
/// <param name="Data">The last known data model, when seen. May be <see langword="null"/>.</param>
/// <param name="CatalogId">The catalog the surface was created against, when seen.</param>
public sealed record A2UIPriorSurface(JsonArray? Components, JsonNode? Data, string? CatalogId);

/// <summary>
/// Prompt-section overrides for the subagent system prompt.
/// </summary>
/// <remarks>
/// Per-field semantics, identical across the sibling toolkits: <see langword="null"/> applies
/// the built-in default block, the empty string suppresses the block entirely, and any other
/// value replaces the default.
/// </remarks>
public sealed class A2UIGuidelines
{
    /// <summary>Gets the protocol/generation rules block override.</summary>
    public string? GenerationGuidelines { get; init; }

    /// <summary>Gets the visual design rules block override.</summary>
    public string? DesignGuidelines { get; init; }

    /// <summary>Gets the host-specific composition guide appended after the context. No built-in default.</summary>
    public string? CompositionGuide { get; init; }
}

/// <summary>
/// The prior-surface context injected into the prompt when editing an existing surface.
/// </summary>
/// <param name="SurfaceId">The id of the surface being edited.</param>
/// <param name="Prior">The reconstructed prior surface state.</param>
/// <param name="Changes">An optional natural-language description of the requested changes.</param>
public sealed record A2UIEditContext(string SurfaceId, A2UIPriorSurface Prior, string? Changes = null);

/// <summary>
/// The outcome of preparing an A2UI generation request: the assembled subagent prompt
/// plus the resolved create/update intent.
/// </summary>
/// <param name="Prompt">The subagent system prompt; empty when <paramref name="Error"/> is set.</param>
/// <param name="IsUpdate">Whether the request edits an existing surface.</param>
/// <param name="Prior">The prior surface state on the update path.</param>
/// <param name="Error">A host-facing error when preparation failed (e.g. update target not found).</param>
public sealed record A2UIPreparedRequest(string Prompt, bool IsUpdate, A2UIPriorSurface? Prior, string? Error);
