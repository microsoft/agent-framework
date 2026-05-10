// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal record TaskLimits(int MaxStallCount = TaskLimits.DefaultMaxStallCount,
                           int? MaxRoundCount = null,
                           int? MaxResetCount = null,
                           int MaxProgressLedgerRetryCount = TaskLimits.DefaultMaxProgressLedgerRetryCount)
{
    public const int DefaultMaxStallCount = 3;
    public const int DefaultMaxProgressLedgerRetryCount = 3;
}

internal record TaskLedger(ChatMessage CurrentFacts, ChatMessage CurrentPlan);

internal class TaskCounters
{
    public int RoundCount { get; set; }
    public int StallCount { get; set; }
    public int ResetCount { get; set; }
}

internal record MagenticTaskState(List<ChatMessage> TaskDefinition, List<ChatMessage> ChatHistory, TaskLedger? TaskLedger, JsonElement? ProgressLedgerState, TaskCounters Counters, bool Terminated, bool? EmitUpdateEvents)
{
}

internal class MagenticTaskContext(List<ChatMessage> taskDefinition, List<AIAgent> team, TaskLimits limits, bool? emitUpdateEvents, IEnumerable<ProgressLedgerSlot> additionalProgressQuestions)
{
    internal MagenticTaskContext(MagenticTaskState state, List<AIAgent> team, TaskLimits limits, IEnumerable<ProgressLedgerSlot> additionalProgressQuestions)
        : this(state.TaskDefinition, team, limits, state.EmitUpdateEvents, additionalProgressQuestions)
    {
        this.TaskLedger = state.TaskLedger;
        this.TaskCounters = state.Counters;
        this.ChatHistory = state.ChatHistory;
        this.IsTerminated = state.Terminated;

        if (state.ProgressLedgerState.HasValue && !this.ProgressLedger.TryUpdateState(state.ProgressLedgerState.Value))
        {
            throw new InvalidOperationException("Could not load progress ledger state value");
        }
    }

    public string Task { get; } = taskDefinition.GetText();

    public string TeamDescription { get; } = GetTeamDescription(team);

    public List<ChatMessage> ChatHistory { get; internal set; } = new();

    public TaskLedger? TaskLedger { get; internal set; }

    public TaskLimits TaskLimits => limits;

    public bool IsTerminated { get; internal set; }

    public bool IsStalled => this.TaskCounters.StallCount >= this.TaskLimits.MaxStallCount;

    public (bool HitRoundLimit, bool HitResetLimit) CheckLimits()
    {
        return (this.TaskLimits.MaxRoundCount.HasValue && this.TaskLimits.MaxRoundCount.Value <= this.TaskCounters.RoundCount,
                this.TaskLimits.MaxResetCount.HasValue && this.TaskLimits.MaxResetCount.Value <= this.TaskCounters.ResetCount);
    }

    public TaskCounters TaskCounters { get; internal set; } = new();

    public MagenticProgressLedger ProgressLedger { get; } = new(GetTeamNames(team), additionalProgressQuestions);
    public bool? EmitUpdateEvents => emitUpdateEvents;

    public static string GetTeamDescription(IEnumerable<AIAgent> team)
    {
        return string.Join("\n", team.Select(agent => $"- {agent.Name}: {agent.Description}"));
    }

    public static string GetTeamNames(IEnumerable<AIAgent> team)
    {
        return string.Join(", ", team.Select(agent => agent.Name));
    }

    public MagenticTaskState ExportState()
    {
        return new(taskDefinition, this.ChatHistory, this.TaskLedger, this.ProgressLedger.State, this.TaskCounters, this.IsTerminated, this.EmitUpdateEvents);
    }

    internal void Reset()
    {
        this.ChatHistory.Clear();
        this.TaskCounters.ResetCount++;
        this.TaskCounters.StallCount = 0;
    }
}
