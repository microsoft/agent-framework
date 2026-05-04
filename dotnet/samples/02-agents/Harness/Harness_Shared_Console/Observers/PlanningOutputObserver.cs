// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Planning observer that configures structured output, collects streamed text,
/// and deserializes it as a <see cref="PlanningResponse"/>. Renders clarification
/// questions and approval prompts, and manages mode switching when the user approves a plan.
/// </summary>
internal sealed class PlanningOutputObserver : ConsoleObserver
{
    private readonly StringBuilder _textCollector = new();
    private readonly AgentModeProvider _modeProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="PlanningOutputObserver"/> class.
    /// </summary>
    /// <param name="modeProvider">The mode provider for switching modes on approval.</param>
    public PlanningOutputObserver(AgentModeProvider modeProvider)
    {
        this._modeProvider = modeProvider;
    }

    /// <inheritdoc/>
    public override void ConfigureRunOptions(AgentRunOptions options)
    {
        options.ResponseFormat = ChatResponseFormat.ForJsonSchema<PlanningResponse>();
    }

    /// <inheritdoc/>
    public override Task OnTextAsync(ConsoleWriter writer, string text)
    {
        // Collect text silently instead of displaying it.
        this._textCollector.Append(text);
        return Task.CompletedTask;
    }

    /// <inheritdoc/>
    public override async Task<IList<ChatMessage>?> OnStreamCompleteAsync(
        ConsoleWriter writer,
        AIAgent agent,
        AgentSession session,
        HarnessConsoleOptions options)
    {
        // Read collected text from our stream observation.
        string collectedText = this._textCollector.ToString();
        this._textCollector.Clear();

        if (string.IsNullOrWhiteSpace(collectedText))
        {
            return null;
        }

        // Deserialize the structured response.
        PlanningResponse? planningResponse;
        try
        {
            planningResponse = JsonSerializer.Deserialize<PlanningResponse>(collectedText);
        }
        catch (JsonException ex)
        {
            await writer.WriteInfoLineAsync($"❌ Failed to parse planning response: {ex.Message}", ConsoleColor.Red);
            await writer.WriteInfoLineAsync($"(raw response) {collectedText}", ConsoleColor.DarkYellow);
            return null;
        }

        if (planningResponse is null)
        {
            await writer.WriteInfoLineAsync("(no structured response from agent)", ConsoleColor.DarkYellow);
            return null;
        }

        // Render based on response type.
        if (planningResponse.Type == PlanningResponseType.Clarification)
        {
            return AsUserMessages(await this.RenderClarificationsAndCollectResponsesAsync(writer, planningResponse));
        }

        if (planningResponse.Type == PlanningResponseType.Approval)
        {
            var question = planningResponse.Questions.FirstOrDefault();
            if (question is null)
            {
                await writer.WriteInfoLineAsync("(approval response had no content)", ConsoleColor.DarkYellow);
                return null;
            }

            string response = await this.RenderApprovalAndCollectResponseAsync(writer, question, options);
            if (response == "Approved")
            {
                this._modeProvider.SetMode(session, options.ExecutionModeName!);

                await writer.WriteInfoLineAsync($"✅ Switched to {options.ExecutionModeName} mode.",
                    ConsoleWriter.GetModeColor(options.ExecutionModeName, options.ModeColors));
            }

            return AsUserMessages(response);
        }

        await writer.WriteInfoLineAsync($"(unexpected response type: {planningResponse.Type})", ConsoleColor.DarkYellow);
        return null;
    }

    private static IList<ChatMessage>? AsUserMessages(string? text) =>
        text is not null ? [new ChatMessage(ChatRole.User, text)] : null;

    private async Task<string?> RenderClarificationsAndCollectResponsesAsync(ConsoleWriter writer, PlanningResponse response)
    {
        var answers = new List<string>();

        foreach (var question in response.Questions)
        {
            await writer.WriteInfoLineAsync(string.Empty);
            await writer.WriteInfoLineAsync(question.Message);

            string? answer;
            if (question.Choices is { Count: > 0 })
            {
                answer = await writer.ReadSelectionAsync(
                    "Choose an option:",
                    question.Choices);
            }
            else
            {
                answer = (await writer.ReadLineAsync("Response: "))?.Trim();
            }

            if (!string.IsNullOrWhiteSpace(answer))
            {
                answers.Add($"Q: {question.Message}\nA: {answer}");
            }
        }

        return answers.Count > 0 ? string.Join("\n\n", answers) : null;
    }

    private async Task<string> RenderApprovalAndCollectResponseAsync(ConsoleWriter writer, PlanningQuestion question, HarnessConsoleOptions options)
    {
        await writer.WriteInfoLineAsync(question.Message);

        var choices = new List<string>
        {
            "Approve and switch to execute mode",
            "Suggest changes",
        };

        string selection = await writer.ReadSelectionAsync("What would you like to do?", choices);

        if (selection == choices[0])
        {
            return "Approved";
        }

        if (selection == choices[1])
        {
            string? feedback = await writer.ReadLineAsync(
                "Your feedback: ",
                ConsoleWriter.GetModeColor(options.PlanningModeName, options.ModeColors));

            if (string.IsNullOrWhiteSpace(feedback))
            {
                // Treat empty feedback as no changes — re-prompt the agent with the plan.
                return "No changes suggested. Please re-present the plan for approval.";
            }

            return feedback;
        }

        // Custom freeform input — treat as suggested changes.
        return selection;
    }
}
