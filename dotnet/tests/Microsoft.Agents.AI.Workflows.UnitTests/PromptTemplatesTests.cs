// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for the Magentic internal prompt templates: default English rendering with placeholder substitution,
/// the concrete-language pin from WithResponseLanguage, and user prompt overrides (issue #6987).
/// </summary>
public class PromptTemplatesTests
{
    // A concrete language name is pinned by the general directive when WithResponseLanguage is set.
    private const string ConcreteLanguageMarker = "in Esperanto";

    private const string TaskText = "UNIQUE_TASK_TEXT";
    private const string FactsText = "UNIQUE_FACTS_TEXT";
    private const string PlanText = "UNIQUE_PLAN_TEXT";

    private static MagenticTaskContext CreateContext(string? responseLanguage = null, MagenticPromptOverrides? overrides = null)
    {
        TestEchoAgent researcher = new(name: "Researcher");
        TestEchoAgent coder = new(name: "Coder");

        MagenticTaskContext context = new(
            [new(ChatRole.User, TaskText)],
            [researcher, coder],
            new TaskLimits(),
            emitUpdateEvents: null,
            additionalProgressQuestions: [])
        {
            ResponseLanguage = responseLanguage,
            PromptOverrides = overrides,
        };

        // Several prompts require a non-null ledger; set one so every prompt can be rendered.
        context.TaskLedger = new(new(ChatRole.Assistant, FactsText), new(ChatRole.Assistant, PlanText));

        return context;
    }

    private static string RenderProsePrompt(MagenticTaskContext context, string promptName) => promptName switch
    {
        nameof(PromptTemplateExtensions.ToTaskLedgerFactsPrompt) => context.ToTaskLedgerFactsPrompt(),
        nameof(PromptTemplateExtensions.ToTaskLedgerFactsUpdatePrompt) => context.ToTaskLedgerFactsUpdatePrompt(),
        nameof(PromptTemplateExtensions.ToTaskLedgerPlanPrompt) => context.ToTaskLedgerPlanPrompt(),
        nameof(PromptTemplateExtensions.ToTaskLedgerPlanUpdatePrompt) => context.ToTaskLedgerPlanUpdatePrompt(),
        nameof(PromptTemplateExtensions.ToFinalAnswerPrompt) => context.ToFinalAnswerPrompt(),
        _ => throw new ArgumentOutOfRangeException(nameof(promptName), promptName, "Unknown prose prompt."),
    };

    public static TheoryData<string> ProsePromptNames() =>
    [
        nameof(PromptTemplateExtensions.ToTaskLedgerFactsPrompt),
        nameof(PromptTemplateExtensions.ToTaskLedgerFactsUpdatePrompt),
        nameof(PromptTemplateExtensions.ToTaskLedgerPlanPrompt),
        nameof(PromptTemplateExtensions.ToTaskLedgerPlanUpdatePrompt),
        nameof(PromptTemplateExtensions.ToFinalAnswerPrompt),
    ];

    [Theory]
    [MemberData(nameof(ProsePromptNames))]
    public void ProsePrompt_Default_IsEnglish_WithoutLanguageDirective(string promptName)
    {
        // Arrange
        MagenticTaskContext context = CreateContext();

        // Act
        string prompt = RenderProsePrompt(context, promptName);

        // Assert - no language directive by default (built-in English prompts are used as-is).
        Assert.DoesNotContain("Write your entire response in", prompt);
        Assert.DoesNotContain("Do not use any other language", prompt);
    }

    [Fact]
    public void FactsPrompt_Default_UsesOriginalEnglishHeadings_AndSubstitutesTask()
    {
        // Arrange
        MagenticTaskContext context = CreateContext();

        // Act
        string prompt = context.ToTaskLedgerFactsPrompt();

        // Assert - reverted to the original English template (no per-language heading instruction); task substituted.
        Assert.Contains("Your answer should use headings:", prompt);
        Assert.Contains("GIVEN OR VERIFIED FACTS", prompt);
        Assert.Contains(TaskText, prompt);
    }

    [Fact]
    public void ProgressLedgerPrompt_Default_HasSchemaContract_WithoutLanguageDirective()
    {
        // Arrange
        MagenticTaskContext context = CreateContext();

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - schema/routing contract present; no language directive by default.
        Assert.Contains("DO NOT OUTPUT ANYTHING OTHER THAN JSON", prompt);
        Assert.Contains("next_speaker", prompt);
        Assert.Contains("instruction_or_question", prompt);
        Assert.DoesNotContain("Do not translate the JSON keys", prompt);
    }

    [Theory]
    [MemberData(nameof(ProsePromptNames))]
    public void ProsePrompt_WithResponseLanguage_PinsConcreteLanguage(string promptName)
    {
        // Arrange - a distinctive language token that will not collide with other prompt text.
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto");

        // Act
        string prompt = RenderProsePrompt(context, promptName);

        // Assert - the concrete language directive is appended after the body.
        Assert.Contains("Write your entire response in Esperanto", prompt);
    }

    [Fact]
    public void ProgressLedgerPrompt_WithResponseLanguage_PinsConcreteLanguage_AndPreservesSchemaContract()
    {
        // Arrange
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto");

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - concrete language pinned for the free-text values...
        Assert.Contains(ConcreteLanguageMarker, prompt);

        // ...while the JSON-key/next_speaker protections and schema contract remain intact.
        Assert.Contains("Do not translate the JSON keys", prompt);
        Assert.Contains("must not be translated", prompt);
        Assert.Contains("DO NOT OUTPUT ANYTHING OTHER THAN JSON", prompt);
        Assert.Contains("next_speaker", prompt);
        Assert.Contains("instruction_or_question", prompt);
    }

    [Fact]
    public void FullTaskLedgerPrompt_NeverAppendsLanguageDirective_AndSubstitutesFactsAndPlan()
    {
        // Arrange - even with a response language configured, the assembly-only full prompt gets no directive.
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto");

        // Act
        string prompt = context.ToTaskLedgerFullPrompt();

        // Assert
        Assert.DoesNotContain("Write your entire response in", prompt);
        Assert.Contains(TaskText, prompt);
        Assert.Contains(FactsText, prompt);
        Assert.Contains(PlanText, prompt);
    }

    [Fact]
    public void PromptOverride_ReplacesBody_AndSubstitutesPlaceholders()
    {
        // Arrange
        MagenticPromptOverrides overrides = new() { TaskLedgerFactsPrompt = "CUSTOM facts request for {task}" };
        MagenticTaskContext context = CreateContext(overrides: overrides);

        // Act
        string prompt = context.ToTaskLedgerFactsPrompt();

        // Assert - the override body is used with placeholders substituted, and the default template is gone.
        Assert.Contains("CUSTOM facts request for", prompt);
        Assert.Contains(TaskText, prompt);
        Assert.DoesNotContain("Ken Jennings-level", prompt);
    }

    [Fact]
    public void PromptOverride_ComposesWith_ResponseLanguage()
    {
        // Arrange
        MagenticPromptOverrides overrides = new() { FinalAnswerPrompt = "CUSTOM final answer for {task}" };
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto", overrides: overrides);

        // Act
        string prompt = context.ToFinalAnswerPrompt();

        // Assert - override body + the concrete language directive appended after it.
        Assert.Contains("CUSTOM final answer for", prompt);
        Assert.Contains(TaskText, prompt);
        Assert.Contains(ConcreteLanguageMarker, prompt);
    }

    [Fact]
    public void ProgressLedgerOverride_InjectsSchemaViaPlaceholder()
    {
        // Arrange
        MagenticPromptOverrides overrides = new() { ProgressLedgerPrompt = "CUSTOM ledger for {task}\n{schema}" };
        MagenticTaskContext context = CreateContext(overrides: overrides);

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - the framework injects the JSON schema (keys) into the override via {schema}.
        Assert.Contains("CUSTOM ledger for", prompt);
        Assert.Contains(TaskText, prompt);
        Assert.Contains("next_speaker", prompt);
        Assert.Contains("instruction_or_question", prompt);
    }

    [Fact]
    public void Substitute_DoesNotReExpandInsertedContent()
    {
        // Arrange - the task text itself contains placeholder-looking tokens that must NOT be re-substituted when
        // the later {team}/{schema} placeholders are filled (single-pass substitution).
        TestEchoAgent researcher = new(name: "Researcher");
        TestEchoAgent coder = new(name: "Coder");
        MagenticTaskContext context = new(
            [new(ChatRole.User, "Design a {schema} for the {team} data")],
            [researcher, coder],
            new TaskLimits(),
            emitUpdateEvents: null,
            additionalProgressQuestions: []);
        context.TaskLedger = new(new(ChatRole.Assistant, FactsText), new(ChatRole.Assistant, PlanText));

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - the task's literal {schema}/{team} tokens survive verbatim (not clobbered by later replacements)...
        Assert.Contains("Design a {schema} for the {team} data", prompt);
        // ...while the real template placeholders were still substituted (team description + schema JSON keys).
        Assert.Contains("Researcher", prompt);
        Assert.Contains("next_speaker", prompt);
    }

    [Fact]
    public void DefaultPrompts_AreThePublicMagenticDefaultPrompts()
    {
        // Arrange - a default (no override) render should be built from the public MagenticDefaultPrompts template,
        // confirming MagenticDefaultPrompts is the single source of truth callers can base overrides on.
        MagenticTaskContext context = CreateContext();

        // Act
        string factsPrompt = context.ToTaskLedgerFactsPrompt();
        string finalAnswerPrompt = context.ToFinalAnswerPrompt();

        // Assert - the rendered prompt is the public default with {task} substituted.
        Assert.Equal(MagenticDefaultPrompts.TaskLedgerFactsPrompt.Replace("{task}", context.Task), factsPrompt);
        Assert.Equal(MagenticDefaultPrompts.FinalAnswerPrompt.Replace("{task}", context.Task), finalAnswerPrompt);
    }

    [Fact]
    public void MagenticDefaultPrompts_ExposeExpectedPlaceholders()
    {
        // Assert - the published defaults keep the placeholders callers rely on when tailoring an override.
        Assert.Contains("{task}", MagenticDefaultPrompts.TaskLedgerFactsPrompt);
        Assert.Contains("{task}", MagenticDefaultPrompts.TaskLedgerFactsUpdatePrompt);
        Assert.Contains("{old_facts}", MagenticDefaultPrompts.TaskLedgerFactsUpdatePrompt);
        Assert.Contains("{team}", MagenticDefaultPrompts.TaskLedgerPlanPrompt);
        Assert.Contains("{team}", MagenticDefaultPrompts.TaskLedgerPlanUpdatePrompt);
        Assert.Contains("{task}", MagenticDefaultPrompts.TaskLedgerFullPrompt);
        Assert.Contains("{team}", MagenticDefaultPrompts.TaskLedgerFullPrompt);
        Assert.Contains("{facts}", MagenticDefaultPrompts.TaskLedgerFullPrompt);
        Assert.Contains("{plan}", MagenticDefaultPrompts.TaskLedgerFullPrompt);
        Assert.Contains("{task}", MagenticDefaultPrompts.ProgressLedgerPrompt);
        Assert.Contains("{team}", MagenticDefaultPrompts.ProgressLedgerPrompt);
        Assert.Contains("{questions}", MagenticDefaultPrompts.ProgressLedgerPrompt);
        Assert.Contains("{schema}", MagenticDefaultPrompts.ProgressLedgerPrompt);
        Assert.Contains("{task}", MagenticDefaultPrompts.FinalAnswerPrompt);
    }
}
