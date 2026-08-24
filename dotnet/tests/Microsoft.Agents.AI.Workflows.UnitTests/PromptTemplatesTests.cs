// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;
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
        prompt.Should().NotContain("Write your entire response in");
        prompt.Should().NotContain("Do not use any other language");
    }

    [Fact]
    public void FactsPrompt_Default_UsesOriginalEnglishHeadings_AndSubstitutesTask()
    {
        // Arrange
        MagenticTaskContext context = CreateContext();

        // Act
        string prompt = context.ToTaskLedgerFactsPrompt();

        // Assert - reverted to the original English template (no per-language heading instruction); task substituted.
        prompt.Should().Contain("Your answer should use headings:");
        prompt.Should().Contain("GIVEN OR VERIFIED FACTS");
        prompt.Should().Contain(TaskText);
    }

    [Fact]
    public void ProgressLedgerPrompt_Default_HasSchemaContract_WithoutLanguageDirective()
    {
        // Arrange
        MagenticTaskContext context = CreateContext();

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - schema/routing contract present; no language directive by default.
        prompt.Should().Contain("DO NOT OUTPUT ANYTHING OTHER THAN JSON");
        prompt.Should().Contain("next_speaker");
        prompt.Should().Contain("instruction_or_question");
        prompt.Should().NotContain("Do not translate the JSON keys");
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
        prompt.Should().Contain("Write your entire response in Esperanto");
    }

    [Fact]
    public void ProgressLedgerPrompt_WithResponseLanguage_PinsConcreteLanguage_AndPreservesSchemaContract()
    {
        // Arrange
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto");

        // Act
        string prompt = context.ToProgressLedgerPrompt();

        // Assert - concrete language pinned for the free-text values...
        prompt.Should().Contain(ConcreteLanguageMarker);

        // ...while the JSON-key/next_speaker protections and schema contract remain intact.
        prompt.Should().Contain("Do not translate the JSON keys");
        prompt.Should().Contain("must not be translated");
        prompt.Should().Contain("DO NOT OUTPUT ANYTHING OTHER THAN JSON");
        prompt.Should().Contain("next_speaker");
        prompt.Should().Contain("instruction_or_question");
    }

    [Fact]
    public void FullTaskLedgerPrompt_NeverAppendsLanguageDirective_AndSubstitutesFactsAndPlan()
    {
        // Arrange - even with a response language configured, the assembly-only full prompt gets no directive.
        MagenticTaskContext context = CreateContext(responseLanguage: "Esperanto");

        // Act
        string prompt = context.ToTaskLedgerFullPrompt();

        // Assert
        prompt.Should().NotContain("Write your entire response in");
        prompt.Should().Contain(TaskText);
        prompt.Should().Contain(FactsText);
        prompt.Should().Contain(PlanText);
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
        prompt.Should().Contain("CUSTOM facts request for");
        prompt.Should().Contain(TaskText);
        prompt.Should().NotContain("Ken Jennings-level");
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
        prompt.Should().Contain("CUSTOM final answer for");
        prompt.Should().Contain(TaskText);
        prompt.Should().Contain(ConcreteLanguageMarker);
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
        prompt.Should().Contain("CUSTOM ledger for");
        prompt.Should().Contain(TaskText);
        prompt.Should().Contain("next_speaker");
        prompt.Should().Contain("instruction_or_question");
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
        prompt.Should().Contain("Design a {schema} for the {team} data");
        // ...while the real template placeholders were still substituted (team description + schema JSON keys).
        prompt.Should().Contain("Researcher");
        prompt.Should().Contain("next_speaker");
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
        factsPrompt.Should().Be(MagenticDefaultPrompts.TaskLedgerFactsPrompt.Replace("{task}", context.Task));
        finalAnswerPrompt.Should().Be(MagenticDefaultPrompts.FinalAnswerPrompt.Replace("{task}", context.Task));
    }

    [Fact]
    public void MagenticDefaultPrompts_ExposeExpectedPlaceholders()
    {
        // Assert - the published defaults keep the placeholders callers rely on when tailoring an override.
        MagenticDefaultPrompts.TaskLedgerFactsPrompt.Should().Contain("{task}");
        MagenticDefaultPrompts.TaskLedgerFactsUpdatePrompt.Should().Contain("{task}").And.Contain("{old_facts}");
        MagenticDefaultPrompts.TaskLedgerPlanPrompt.Should().Contain("{team}");
        MagenticDefaultPrompts.TaskLedgerPlanUpdatePrompt.Should().Contain("{team}");
        MagenticDefaultPrompts.TaskLedgerFullPrompt.Should().Contain("{task}").And.Contain("{team}").And.Contain("{facts}").And.Contain("{plan}");
        MagenticDefaultPrompts.ProgressLedgerPrompt.Should().Contain("{task}").And.Contain("{team}").And.Contain("{questions}").And.Contain("{schema}");
        MagenticDefaultPrompts.FinalAnswerPrompt.Should().Contain("{task}");
    }
}
