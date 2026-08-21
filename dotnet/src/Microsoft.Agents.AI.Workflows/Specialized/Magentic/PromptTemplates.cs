// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal static class PromptTemplateExtensions
{
    // Matches a single-brace placeholder token, e.g. {task} or {old_facts}. Only {word} sequences are treated as
    // placeholders, so literal braces in a prompt (such as JSON in an override) are left untouched.
    private static readonly Regex s_placeholderPattern = new(@"\{(\w+)\}");

    // The built-in English prompt templates live on the public MagenticDefaultPrompts class so callers can read and
    // base overrides on them. Named single-brace placeholders (e.g. {task}) are substituted at render time.
    private static string Substitute(string template, params (string Token, string Value)[] values) =>
        // Single-pass replacement over the template: substituted values are never re-scanned for further
        // placeholders, so content that happens to contain "{token}" text (e.g. in the task) is not corrupted.
        s_placeholderPattern.Replace(template, match =>
        {
            foreach ((string token, string value) in values)
            {
                if (string.Equals(token, match.Groups[1].Value, StringComparison.Ordinal))
                {
                    return value;
                }
            }

            // Not one of the placeholders available for this prompt - leave the original text untouched.
            return match.Value;
        });

    // When a concrete response language is configured via WithResponseLanguage, a directive pinning that language is
    // appended AFTER the (possibly overridden) prompt body. A concrete language name is followed far more reliably than
    // a relative "match the request" instruction, especially for the progress ledger's JSON free-text fields (#6987).
    private static string AppendLanguageDirective(string body, MagenticTaskContext taskContext) =>
        taskContext.ResponseLanguage is { Length: > 0 } language
            ? $"{body}\n\n{GeneralLanguageDirective(language)}"
            : body;

    private static string AppendProgressLedgerLanguageDirective(string body, MagenticTaskContext taskContext) =>
        taskContext.ResponseLanguage is { Length: > 0 } language
            ? $"{body}\n\n{ProgressLedgerLanguageDirective(language)}"
            : body;

    private static string GeneralLanguageDirective(string language) =>
        $"Write your entire response in {language}, including any section headings or labels. Do not use any other language.";

    private static string ProgressLedgerLanguageDirective(string language) =>
        $"When filling in the JSON, write every \"reason\" value and the \"instruction_or_question\" answer in {language}. " +
        "Do not translate the JSON keys - they must remain exactly as shown above. The \"next_speaker\" answer must " +
        "remain exactly one of the provided team member names and must not be translated.";

    public static string ToTaskLedgerFactsPrompt(this MagenticTaskContext taskContext)
    {
        string body = Substitute(taskContext.PromptOverrides?.TaskLedgerFactsPrompt ?? MagenticDefaultPrompts.TaskLedgerFactsPrompt,
            ("task", taskContext.Task));

        return AppendLanguageDirective(body, taskContext);
    }

    public static string ToTaskLedgerFactsUpdatePrompt(this MagenticTaskContext taskContext)
    {
        string body = Substitute(taskContext.PromptOverrides?.TaskLedgerFactsUpdatePrompt ?? MagenticDefaultPrompts.TaskLedgerFactsUpdatePrompt,
            ("task", taskContext.Task),
            ("old_facts", taskContext.TaskLedger?.CurrentFacts.Text ?? string.Empty));

        return AppendLanguageDirective(body, taskContext);
    }

    public static string ToTaskLedgerPlanPrompt(this MagenticTaskContext taskContext)
    {
        string body = Substitute(taskContext.PromptOverrides?.TaskLedgerPlanPrompt ?? MagenticDefaultPrompts.TaskLedgerPlanPrompt,
            ("team", taskContext.TeamDescription));

        return AppendLanguageDirective(body, taskContext);
    }

    public static string ToTaskLedgerPlanUpdatePrompt(this MagenticTaskContext taskContext)
    {
        string body = Substitute(taskContext.PromptOverrides?.TaskLedgerPlanUpdatePrompt ?? MagenticDefaultPrompts.TaskLedgerPlanUpdatePrompt,
            ("team", taskContext.TeamDescription));

        return AppendLanguageDirective(body, taskContext);
    }

    public static string ToTaskLedgerFullPrompt(this MagenticTaskContext taskContext)
    {
        // Assembly-only prompt (emitted as the plan-event text and used as context); no language directive is appended
        // because nothing is generated from it - its facts/plan are already localized by their own generation prompts.
        return Substitute(taskContext.PromptOverrides?.TaskLedgerFullPrompt ?? MagenticDefaultPrompts.TaskLedgerFullPrompt,
            ("task", taskContext.Task),
            ("team", taskContext.TeamDescription),
            ("facts", taskContext.TaskLedger!.CurrentFacts.Text),
            ("plan", taskContext.TaskLedger!.CurrentPlan.Text));
    }

    public static string ToProgressLedgerPrompt(this MagenticTaskContext taskContext)
    {
        (string questions, string schema) = taskContext.ProgressLedger.FormatQuestions();

        string body = Substitute(taskContext.PromptOverrides?.ProgressLedgerPrompt ?? MagenticDefaultPrompts.ProgressLedgerPrompt,
            ("task", taskContext.Task),
            ("team", taskContext.TeamDescription),
            ("questions", questions),
            ("schema", schema));

        return AppendProgressLedgerLanguageDirective(body, taskContext);
    }

    public static string ToFinalAnswerPrompt(this MagenticTaskContext taskContext)
    {
        string body = Substitute(taskContext.PromptOverrides?.FinalAnswerPrompt ?? MagenticDefaultPrompts.FinalAnswerPrompt,
            ("task", taskContext.Task));

        return AppendLanguageDirective(body, taskContext);
    }
}
