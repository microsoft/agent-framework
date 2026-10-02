// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AGUI.WorkflowMultipleInputs;

/// <summary>
/// Creates the multiple-input travel workflow used by the sample and its integration test.
/// </summary>
public static class MultipleInputsWorkflow
{
    /// <summary>
    /// Creates a workflow that requests three independent pieces of travel information.
    /// </summary>
    /// <returns>The travel-planning workflow.</returns>
    public static Workflow Create()
    {
        TravelPlannerExecutor executor = new();
        return new WorkflowBuilder(executor)
            .AddExternalCall<TravelDatesRequest, JsonElement>(executor, "TravelDates")
            .AddExternalCall<TravelerDetailsRequest, JsonElement>(executor, "TravelerDetails")
            .AddExternalCall<TravelPreferencesRequest, JsonElement>(executor, "TravelPreferences")
            .WithOutputFrom(executor)
            .Build();
    }
}

/// <summary>Requests departure and return dates.</summary>
public sealed record TravelDatesRequest(string Destination);

/// <summary>Requests traveler count and accessibility needs.</summary>
public sealed record TravelerDetailsRequest(string Destination);

/// <summary>Requests budget, cabin, and hotel preferences.</summary>
public sealed record TravelPreferencesRequest(string Destination);

[SendsMessage(typeof(TravelDatesRequest))]
[SendsMessage(typeof(TravelerDetailsRequest))]
[SendsMessage(typeof(TravelPreferencesRequest))]
internal sealed partial class TravelPlannerExecutor()
    : ChatProtocolExecutor("TravelPlanner", new ChatProtocolExecutorOptions { AutoSendTurnToken = false })
{
    private const string StateScope = "TravelInputs";
    private static readonly string[] s_inputKinds = ["dates", "travelers", "preferences"];

    protected override async ValueTask TakeTurnAsync(
        List<ChatMessage> messages,
        IWorkflowContext context,
        bool? emitEvents,
        CancellationToken cancellationToken = default)
    {
        const string Destination = "Seattle";
        await context.SendMessageAsync(new TravelDatesRequest(Destination), cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(new TravelerDetailsRequest(Destination), cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(new TravelPreferencesRequest(Destination), cancellationToken).ConfigureAwait(false);
    }

    [MessageHandler]
    public async ValueTask HandleInputAsync(
        JsonElement response,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        string kind = response.GetProperty("kind").GetString()
            ?? throw new InvalidOperationException("The response kind is required.");
        await context.QueueStateUpdateAsync(kind, response.Clone(), StateScope, cancellationToken).ConfigureAwait(false);

        string[] otherKinds = [.. s_inputKinds.Where(candidate => candidate != kind)];
        bool allOtherInputsAvailable = true;
        foreach (string otherKind in otherKinds)
        {
            JsonElement? value = await context.ReadStateAsync<JsonElement?>(
                otherKind,
                StateScope,
                cancellationToken).ConfigureAwait(false);
            allOtherInputsAvailable &= value.HasValue;
        }

        if (!allOtherInputsAvailable)
        {
            return;
        }

        AgentResponseUpdate update = new(
            ChatRole.Assistant,
            "Travel plan ready for Seattle using all requested dates, traveler details, and preferences.")
        {
            MessageId = "travel-plan",
            ResponseId = "travel-response",
        };
        await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(new TurnToken(false), cancellationToken).ConfigureAwait(false);
    }
}
