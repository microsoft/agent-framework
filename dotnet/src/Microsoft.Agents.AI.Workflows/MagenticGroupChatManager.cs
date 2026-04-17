// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A <see cref="GroupChatManager"/> that implements the Magentic One orchestration pattern.
/// </summary>
/// <remarks>
/// <para>
/// Magentic One uses an LLM-powered manager to coordinate multiple agents through dynamic task planning,
/// progress tracking, and adaptive replanning. On each turn the manager:
/// <list type="number">
/// <item><description>Creates an initial task ledger (facts + plan) before the first agent interaction.</description></item>
/// <item><description>Evaluates a JSON progress ledger to determine whether the task is complete, whether the
/// conversation is stalling or looping, and which agent should speak next.</description></item>
/// <item><description>Triggers a replan when stalling is detected, resetting the conversation context with
/// updated facts and a revised plan.</description></item>
/// </list>
/// </para>
/// <para>
/// Use <see cref="AgentWorkflowBuilder.CreateGroupChatBuilderWith"/> to wire this manager into a workflow:
/// <code>
/// var workflow = AgentWorkflowBuilder
///     .CreateGroupChatBuilderWith(agents => new MagenticGroupChatManager(agents, chatClient))
///     .AddParticipants(agent1, agent2)
///     .Build();
/// </code>
/// </para>
/// </remarks>
public partial class MagenticGroupChatManager : GroupChatManager
{
    private readonly IChatClient _chatClient;
    private readonly IReadOnlyList<AIAgent> _agents;
    private readonly int _maxStallCount;
    private readonly int? _maxResetCount;
    private readonly int _progressLedgerRetryCount;

    // Full conversation history accumulated across turns.
    // GroupChatHost only passes new messages each turn, so we maintain the full history here.
    private readonly List<ChatMessage> _fullHistory = [];

    private string? _currentTask;
    private string? _taskLedger;
    private int _stallCount;
    private int _resetCount;
    private AIAgent? _nextAgent;
    private bool _taskSatisfied;

#if NET
    [GeneratedRegex(@"```(?:json)?\s*(\{[\s\S]*?\})\s*```", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex JsonCodeFenceRegex();
#else
    private static Regex JsonCodeFenceRegex() => s_jsonCodeFenceRegex;
    private static readonly Regex s_jsonCodeFenceRegex = new(@"```(?:json)?\s*(\{[\s\S]*?\})\s*```", RegexOptions.IgnoreCase | RegexOptions.Compiled);
#endif

    /// <summary>
    /// Initializes a new instance of the <see cref="MagenticGroupChatManager"/> class.
    /// </summary>
    /// <param name="agents">The agents participating in the group chat.</param>
    /// <param name="chatClient">The <see cref="IChatClient"/> used for planning and progress evaluation calls.</param>
    /// <param name="maxStallCount">Maximum consecutive rounds without forward progress before a replan is triggered. Default is 3.</param>
    /// <param name="maxResetCount">Maximum number of replan cycles allowed. <see langword="null"/> means unlimited.</param>
    /// <param name="maxRoundCount">Maximum total coordination rounds. <see langword="null"/> means unlimited.</param>
    /// <param name="progressLedgerRetryCount">Number of retry attempts when the progress ledger JSON cannot be parsed. Default is 3.</param>
    public MagenticGroupChatManager(
        IReadOnlyList<AIAgent> agents,
        IChatClient chatClient,
        int maxStallCount = 3,
        int? maxResetCount = null,
        int? maxRoundCount = null,
        int progressLedgerRetryCount = 3)
    {
        Throw.IfNullOrEmpty(agents);
        foreach (var agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
        }

        _agents = agents;
        _chatClient = Throw.IfNull(chatClient);
        _maxStallCount = maxStallCount;
        _maxResetCount = maxResetCount;
        MaximumIterationCount = maxRoundCount ?? int.MaxValue;
        _progressLedgerRetryCount = progressLedgerRetryCount;
    }

    /// <summary>Gets or sets the prompt used to gather known and unknown facts about the task.</summary>
    public string TaskLedgerFactsPrompt { get; init; } = MagenticPrompts.TaskLedgerFacts;

    /// <summary>Gets or sets the prompt used to generate the initial execution plan.</summary>
    public string TaskLedgerPlanPrompt { get; init; } = MagenticPrompts.TaskLedgerPlan;

    /// <summary>Gets or sets the prompt template that renders the combined task ledger shown to agents.</summary>
    public string TaskLedgerFullPrompt { get; init; } = MagenticPrompts.TaskLedgerFull;

    /// <summary>Gets or sets the prompt used to update facts during a replan cycle.</summary>
    public string TaskLedgerFactsUpdatePrompt { get; init; } = MagenticPrompts.TaskLedgerFactsUpdate;

    /// <summary>Gets or sets the prompt used to generate a revised plan during a replan cycle.</summary>
    public string TaskLedgerPlanUpdatePrompt { get; init; } = MagenticPrompts.TaskLedgerPlanUpdate;

    /// <summary>Gets or sets the prompt used to evaluate progress and select the next speaker.</summary>
    public string ProgressLedgerPrompt { get; init; } = MagenticPrompts.ProgressLedger;

    /// <summary>Gets or sets the prompt used to synthesize the final answer once the task is complete.</summary>
    public string FinalAnswerPrompt { get; init; } = MagenticPrompts.FinalAnswer;

    /// <inheritdoc/>
    protected internal override ValueTask<bool> ShouldTerminateAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default)
    {
        if (_taskSatisfied)
        {
            return new(true);
        }

        if (_maxResetCount.HasValue && _resetCount >= _maxResetCount.Value && _stallCount > _maxStallCount)
        {
            return new(true);
        }

        return base.ShouldTerminateAsync(history, cancellationToken);
    }

    /// <inheritdoc/>
    protected internal override async ValueTask<IEnumerable<ChatMessage>> UpdateHistoryAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default)
    {
        // Accumulate new messages into the full history we maintain across turns.
        _fullHistory.AddRange(history);

        // Extract the task from the first user message.
        _currentTask ??= _fullHistory.FirstOrDefault(m => m.Role == ChatRole.User)?.Text;

        if (_currentTask is null)
        {
            return _fullHistory;
        }

        // Create the initial task ledger on the first turn.
        if (_taskLedger is null)
        {
            _taskLedger = await CreateTaskLedgerAsync(cancellationToken).ConfigureAwait(false);
            _fullHistory.Add(new ChatMessage(ChatRole.Assistant, _taskLedger) { AuthorName = MagenticPrompts.ManagerName });
        }

        // Evaluate current progress and determine the next speaker.
        var progressLedger = await TryCreateProgressLedgerAsync(cancellationToken).ConfigureAwait(false);

        if (progressLedger is null)
        {
            // Progress ledger parse failed — trigger immediate replan.
            await ReplanAndResetAsync(cancellationToken).ConfigureAwait(false);
            progressLedger = await TryCreateProgressLedgerAsync(cancellationToken).ConfigureAwait(false);
        }

        if (progressLedger is null)
        {
            // Still unable to parse — fall back to the first agent with no instruction.
            _nextAgent = _agents[0];
            return _fullHistory;
        }

        // Check whether the task has been fully satisfied.
        if (progressLedger.IsRequestSatisfied.GetBoolAnswer())
        {
            _taskSatisfied = true;
            return _fullHistory;
        }

        // Update stall count based on progress signals.
        bool makingProgress = progressLedger.IsProgressBeingMade.GetBoolAnswer();
        bool inLoop = progressLedger.IsInLoop.GetBoolAnswer();

        if (!makingProgress || inLoop)
        {
            _stallCount++;
        }
        else
        {
            _stallCount = Math.Max(0, _stallCount - 1);
        }

        // Replan inline when stalling threshold is exceeded.
        if (_stallCount > _maxStallCount)
        {
            await ReplanAndResetAsync(cancellationToken).ConfigureAwait(false);
            progressLedger = await TryCreateProgressLedgerAsync(cancellationToken).ConfigureAwait(false) ?? progressLedger;
        }

        // Append the manager's instruction to the history so the selected agent receives it.
        string instruction = progressLedger.InstructionOrQuestion.GetStringAnswer();
        if (!string.IsNullOrWhiteSpace(instruction))
        {
            _fullHistory.Add(new ChatMessage(ChatRole.Assistant, instruction) { AuthorName = MagenticPrompts.ManagerName });
        }

        // Cache the next agent for SelectNextAgentAsync.
        string nextSpeakerName = progressLedger.NextSpeaker.GetStringAnswer();
        _nextAgent = _agents.FirstOrDefault(a => a.Name == nextSpeakerName) ?? _agents[0];

        return _fullHistory;
    }

    /// <inheritdoc/>
    protected internal override ValueTask<AIAgent> SelectNextAgentAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default)
    {
        // The agent is selected during UpdateHistoryAsync where we have full context.
        return new(_nextAgent ?? _agents[0]);
    }

    /// <inheritdoc/>
    protected internal override void Reset()
    {
        base.Reset();
        _fullHistory.Clear();
        _currentTask = null;
        _taskLedger = null;
        _stallCount = 0;
        _resetCount = 0;
        _nextAgent = null;
        _taskSatisfied = false;
    }

    private async Task ReplanAndResetAsync(CancellationToken cancellationToken)
    {
        _resetCount++;
        _stallCount = 0;

        _taskLedger = await CreateUpdatedTaskLedgerAsync(cancellationToken).ConfigureAwait(false);

        _fullHistory.Clear();
        _fullHistory.Add(new ChatMessage(ChatRole.User, _currentTask!));
        _fullHistory.Add(new ChatMessage(ChatRole.Assistant, _taskLedger) { AuthorName = MagenticPrompts.ManagerName });
    }

    private async Task<string> CreateTaskLedgerAsync(CancellationToken cancellationToken)
    {
        string teamBlock = BuildTeamDescription();

        // Gather facts.
        var factsHistory = new List<ChatMessage>(_fullHistory)
        {
            new ChatMessage(ChatRole.User, FormatTemplate(TaskLedgerFactsPrompt, ("task", _currentTask!)))
        };
        var factsResponse = await _chatClient.GetResponseAsync(factsHistory, null, cancellationToken).ConfigureAwait(false);
        string factsText = factsResponse.Messages.LastOrDefault()?.Text ?? string.Empty;
        ChatMessage factsMessage = factsResponse.Messages.LastOrDefault() ?? new ChatMessage(ChatRole.Assistant, string.Empty);

        // Generate plan.
        factsHistory.Add(factsMessage);
        factsHistory.Add(new ChatMessage(ChatRole.User, FormatTemplate(TaskLedgerPlanPrompt, ("team", teamBlock))));
        var planResponse = await _chatClient.GetResponseAsync(factsHistory, null, cancellationToken).ConfigureAwait(false);
        string planText = planResponse.Messages.LastOrDefault()?.Text ?? string.Empty;

        return FormatTemplate(
            TaskLedgerFullPrompt,
            ("task", _currentTask!),
            ("team", teamBlock),
            ("facts", factsText),
            ("plan", planText));
    }

    private async Task<string> CreateUpdatedTaskLedgerAsync(CancellationToken cancellationToken)
    {
        string teamBlock = BuildTeamDescription();

        // Update facts given what we've learned so far.
        var factsUpdateHistory = new List<ChatMessage>(_fullHistory)
        {
            new ChatMessage(ChatRole.User, FormatTemplate(
                TaskLedgerFactsUpdatePrompt,
                ("task", _currentTask!),
                ("old_facts", _taskLedger ?? string.Empty)))
        };
        var factsResponse = await _chatClient.GetResponseAsync(factsUpdateHistory, null, cancellationToken).ConfigureAwait(false);
        string updatedFacts = factsResponse.Messages.LastOrDefault()?.Text ?? string.Empty;
        ChatMessage factsMessage = factsResponse.Messages.LastOrDefault() ?? new ChatMessage(ChatRole.Assistant, string.Empty);

        // Generate revised plan.
        factsUpdateHistory.Add(factsMessage);
        factsUpdateHistory.Add(new ChatMessage(ChatRole.User, FormatTemplate(TaskLedgerPlanUpdatePrompt, ("team", teamBlock))));
        var planResponse = await _chatClient.GetResponseAsync(factsUpdateHistory, null, cancellationToken).ConfigureAwait(false);
        string updatedPlan = planResponse.Messages.LastOrDefault()?.Text ?? string.Empty;

        return FormatTemplate(
            TaskLedgerFullPrompt,
            ("task", _currentTask!),
            ("team", teamBlock),
            ("facts", updatedFacts),
            ("plan", updatedPlan));
    }

    private async Task<MagenticProgressLedger?> TryCreateProgressLedgerAsync(CancellationToken cancellationToken)
    {
        string agentNames = string.Join(", ", _agents.Select(a => a.Name ?? a.Id));
        string progressPrompt = FormatTemplate(
            ProgressLedgerPrompt,
            ("task", _currentTask!),
            ("team", BuildTeamDescription()),
            ("names", agentNames));

        var messages = new List<ChatMessage>(_fullHistory)
        {
            new ChatMessage(ChatRole.User, progressPrompt)
        };

        for (int attempt = 0; attempt < _progressLedgerRetryCount; attempt++)
        {
            try
            {
                var completion = await _chatClient.GetResponseAsync(messages, null, cancellationToken).ConfigureAwait(false);
                string responseText = completion.Messages.LastOrDefault()?.Text ?? string.Empty;
                string json = ExtractJson(responseText);
                return JsonSerializer.Deserialize(json, WorkflowsJsonUtilities.JsonContext.Default.MagenticProgressLedger);
            }
            catch (Exception)
            {
                if (attempt < _progressLedgerRetryCount - 1)
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(250 * (attempt + 1)), cancellationToken).ConfigureAwait(false);
                }
            }
        }

        return null;
    }

    private string BuildTeamDescription()
    {
        var sb = new StringBuilder();
        foreach (var agent in _agents)
        {
            sb.AppendLine($"- {agent.Name ?? agent.Id}: {agent.Description ?? "(no description)"}");
        }

        return sb.ToString();
    }

    private static string FormatTemplate(string template, params (string name, string value)[] args)
    {
        string result = template;
        foreach (var (name, value) in args)
        {
            result = result.Replace("{" + name + "}", value);
        }

        return result;
    }

    private static string ExtractJson(string text)
    {
        // Try markdown code fence first.
        Match fenceMatch = JsonCodeFenceRegex().Match(text);
        if (fenceMatch.Success)
        {
            return fenceMatch.Groups[1].Value;
        }

        // Find the first balanced JSON object.
        int start = text.IndexOf('{');
        if (start == -1)
        {
            throw new InvalidOperationException("No JSON object found in model response.");
        }

        int depth = 0;
        for (int i = start; i < text.Length; i++)
        {
            char c = text[i];
            if (c == '{')
            {
                depth++;
            }
            else if (c == '}')
            {
                depth--;
                if (depth == 0)
                {
                    return text[start..(i + 1)];
                }
            }
        }

        throw new InvalidOperationException("Unbalanced JSON braces in model response.");
    }
}

/// <summary>
/// Represents a single field in a <see cref="MagenticProgressLedger"/>, combining a reason with a typed answer.
/// </summary>
public sealed class MagenticProgressLedgerItem
{
    /// <summary>Gets the reasoning behind this ledger item's answer.</summary>
    [JsonPropertyName("reason")]
    public string Reason { get; init; } = string.Empty;

    /// <summary>
    /// Gets the answer value. May be a <see cref="bool"/> (for yes/no fields) or a <see cref="string"/>
    /// (for agent name or instruction fields).
    /// </summary>
    [JsonPropertyName("answer")]
    public JsonElement Answer { get; init; }

    internal bool GetBoolAnswer() =>
        Answer.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.String => Answer.GetString()?.Equals("true", StringComparison.OrdinalIgnoreCase) is true
                || Answer.GetString()?.Equals("yes", StringComparison.OrdinalIgnoreCase) is true,
            _ => false,
        };

    internal string GetStringAnswer() =>
        Answer.ValueKind == JsonValueKind.String
            ? Answer.GetString() ?? string.Empty
            : Answer.ToString();
}

/// <summary>
/// Represents the structured progress assessment produced by the Magentic manager each orchestration round.
/// </summary>
public sealed class MagenticProgressLedger
{
    /// <summary>Gets whether the original request has been fully and successfully addressed.</summary>
    [JsonPropertyName("is_request_satisfied")]
    public MagenticProgressLedgerItem IsRequestSatisfied { get; init; } = new();

    /// <summary>Gets whether the conversation is repeating the same requests or responses.</summary>
    [JsonPropertyName("is_in_loop")]
    public MagenticProgressLedgerItem IsInLoop { get; init; } = new();

    /// <summary>Gets whether meaningful forward progress is being made toward completing the task.</summary>
    [JsonPropertyName("is_progress_being_made")]
    public MagenticProgressLedgerItem IsProgressBeingMade { get; init; } = new();

    /// <summary>Gets the name of the agent that should speak next.</summary>
    [JsonPropertyName("next_speaker")]
    public MagenticProgressLedgerItem NextSpeaker { get; init; } = new();

    /// <summary>Gets the instruction or question to give to the next speaker.</summary>
    [JsonPropertyName("instruction_or_question")]
    public MagenticProgressLedgerItem InstructionOrQuestion { get; init; } = new();
}
