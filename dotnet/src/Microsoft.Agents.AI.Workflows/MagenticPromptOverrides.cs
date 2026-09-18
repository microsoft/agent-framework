// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Optional overrides for the internal prompt templates the Magentic manager uses to plan, track progress, and
/// synthesize the final answer. Any property left <see langword="null"/> keeps the built-in English template.
/// </summary>
/// <remarks>
/// <para>
/// Overrides are supplied to <see cref="MagenticWorkflowBuilder.WithPromptOverrides(MagenticPromptOverrides)"/>.
/// Each template may contain named single-brace placeholders that the framework substitutes at render time
/// (e.g. <c>{task}</c>). Unlike Python's <c>str.format</c>, literal braces (such as JSON in the progress-ledger
/// prompt) do <b>not</b> need to be escaped - only the documented placeholders are replaced.
/// </para>
/// <para>
/// The available placeholders differ per prompt and are documented on each property. A placeholder that is not
/// available for a given prompt is left untouched.
/// </para>
/// <para>
/// To base an override on a built-in template (for example, to translate it), read the corresponding member on
/// <see cref="MagenticDefaultPrompts"/>.
/// </para>
/// <para>
/// If <c>MagenticWorkflowBuilder.WithResponseLanguage</c> is also set, its language directive is appended after the
/// (possibly overridden) template body, so overrides and the language pin compose.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record MagenticPromptOverrides
{
    /// <summary>
    /// Overrides the prompt that gathers the initial fact sheet. Placeholders: <c>{task}</c>.
    /// </summary>
    public string? TaskLedgerFactsPrompt { get; init; }

    /// <summary>
    /// Overrides the prompt that creates the initial plan. Placeholders: <c>{team}</c>.
    /// </summary>
    public string? TaskLedgerPlanPrompt { get; init; }

    /// <summary>
    /// Overrides the prompt that renders the full task ledger (the plan-event text combining facts and plan).
    /// Placeholders: <c>{task}</c>, <c>{team}</c>, <c>{facts}</c>, <c>{plan}</c>.
    /// </summary>
    public string? TaskLedgerFullPrompt { get; init; }

    /// <summary>
    /// Overrides the prompt that updates the fact sheet during a replan. Placeholders: <c>{task}</c>, <c>{old_facts}</c>.
    /// </summary>
    public string? TaskLedgerFactsUpdatePrompt { get; init; }

    /// <summary>
    /// Overrides the prompt that updates the plan during a replan. Placeholders: <c>{team}</c>.
    /// </summary>
    public string? TaskLedgerPlanUpdatePrompt { get; init; }

    /// <summary>
    /// Overrides the progress-ledger prompt. Placeholders: <c>{task}</c>, <c>{team}</c>, <c>{questions}</c>,
    /// <c>{schema}</c>. The <c>{schema}</c> placeholder is required - the framework injects the JSON schema the
    /// response is parsed against, so omitting it would break progress-ledger parsing and next-speaker routing.
    /// </summary>
    public string? ProgressLedgerPrompt { get; init; }

    /// <summary>
    /// Overrides the prompt that synthesizes the final answer. Placeholders: <c>{task}</c>.
    /// </summary>
    public string? FinalAnswerPrompt { get; init; }
}
