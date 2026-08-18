// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides AG-UI event mapping for workflow-hosted agents.
/// </summary>
public static class AGUIWorkflowEventExtensions
{
    /// <summary>
    /// Decorates an agent so supported workflow lifecycle events are exposed as AG-UI events.
    /// </summary>
    /// <param name="agent">The workflow-hosted agent to decorate.</param>
    /// <returns>An agent that maps workflow lifecycle events while preserving ordinary response updates.</returns>
    /// <remarks>
    /// <para>
    /// Supersteps are mapped to AG-UI step events. Workflow warnings, non-chat outputs, and executor
    /// lifecycle events are mapped to structured custom events.
    /// </para>
    /// <para>
    /// Executor lifecycle events are not mapped to AG-UI activity events because workflow events do not
    /// currently expose a stable invocation identifier. Mapping by executor identifier could misattribute
    /// repeated or concurrent invocations.
    /// </para>
    /// <para>
    /// Workflow run lifecycle, request/interrupt content, response-compatible outputs, and errors continue
    /// through their existing mappings. Internal checkpoint/debug state and exception details are not added
    /// to AG-UI event payloads.
    /// </para>
    /// <para>
    /// Non-chat output data is included only when it is a JSON scalar, <see cref="JsonElement"/>, or
    /// <see cref="JsonDocument"/>. Pre-serialize custom output objects to <see cref="JsonElement"/> when their
    /// payload should be sent to the client. Warning messages are intentionally replaced with a stable,
    /// non-sensitive message.
    /// </para>
    /// </remarks>
    public static AIAgent WithAGUIWorkflowEvents(this AIAgent agent)
    {
        ArgumentNullException.ThrowIfNull(agent);
        return new AGUIWorkflowEventAgent(agent);
    }

    internal static async IAsyncEnumerable<ChatResponseUpdate> AsAGUIChatResponseUpdatesAsync(
        this IAsyncEnumerable<AgentResponseUpdate> updates)
    {
        ArgumentNullException.ThrowIfNull(updates);

        await foreach (AgentResponseUpdate update in updates.ConfigureAwait(false))
        {
            ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();
            if (update.RawRepresentation is BaseEvent)
            {
                chatUpdate.RawRepresentation = update.RawRepresentation;
            }

            yield return chatUpdate;
        }
    }
}

internal sealed class AGUIWorkflowEventAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
{
    private const string WarningEventName = "maf.workflow.warning";
    private const string OutputEventName = "maf.workflow.output";
    private const string ExecutorInvokedEventName = "maf.workflow.executor.invoked";
    private const string ExecutorCompletedEventName = "maf.workflow.executor.completed";
    private const string ExecutorFailedEventName = "maf.workflow.executor.failed";

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, session, options, cancellationToken);

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        List<int> activeSteps = [];
        bool terminalErrorForwarded = false;

        await foreach (AgentResponseUpdate update in this.InnerAgent
            .RunStreamingAsync(messages, session, options, cancellationToken)
            .ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case SuperStepStartedEvent started when !activeSteps.Contains(started.StepNumber):
                    activeSteps.Add(started.StepNumber);
                    yield return CloneWithEvent(update, new StepStartedEvent { StepName = GetStepName(started.StepNumber) });
                    break;

                case SuperStepCompletedEvent completed when activeSteps.Remove(completed.StepNumber):
                    yield return CloneWithEvent(update, new StepFinishedEvent { StepName = GetStepName(completed.StepNumber) });
                    break;

                case WorkflowWarningEvent warning:
                    yield return CloneWithEvent(
                        update,
                        CreateCustomEvent(
                            WarningEventName,
                            new AGUIWorkflowWarningPayload("The workflow reported a warning.")));
                    break;

                case WorkflowOutputEvent output when !IsResponseCompatible(output):
                    yield return CloneWithEvent(
                        update,
                        CreateCustomEvent(
                            OutputEventName,
                            new AGUIWorkflowOutputPayload(
                                output.ExecutorId,
                                [.. output.Tags.Select(static tag => tag.Value).Where(static value => value is not null).OrderBy(static value => value, StringComparer.Ordinal)!],
                                TrySerializeOutput(output.Data))));
                    break;

                case ExecutorInvokedEvent invoked:
                    yield return CloneWithEvent(
                        update,
                        CreateCustomEvent(ExecutorInvokedEventName, new AGUIWorkflowExecutorPayload(invoked.ExecutorId)));
                    break;

                case ExecutorCompletedEvent completed:
                    yield return CloneWithEvent(
                        update,
                        CreateCustomEvent(ExecutorCompletedEventName, new AGUIWorkflowExecutorPayload(completed.ExecutorId)));
                    break;

                case ExecutorFailedEvent failed:
                    foreach (AgentResponseUpdate stepFinished in CloseActiveSteps(update, activeSteps))
                    {
                        yield return stepFinished;
                    }

                    yield return CloneWithEvent(
                        update,
                        CreateCustomEvent(ExecutorFailedEventName, new AGUIWorkflowExecutorPayload(failed.ExecutorId)),
                        includeContents: false);
                    AgentResponseUpdate? executorFailure = FilterDuplicateErrorContent(update, ref terminalErrorForwarded);
                    if (executorFailure is not null)
                    {
                        yield return executorFailure;
                    }
                    break;

                case WorkflowErrorEvent:
                    foreach (AgentResponseUpdate stepFinished in CloseActiveSteps(update, activeSteps))
                    {
                        yield return stepFinished;
                    }

                    AgentResponseUpdate? workflowError = FilterDuplicateErrorContent(update, ref terminalErrorForwarded);
                    if (workflowError is not null)
                    {
                        yield return workflowError;
                    }
                    break;

                default:
                    yield return update;
                    break;
            }
        }

        foreach (AgentResponseUpdate stepFinished in CloseActiveSteps(template: null, activeSteps))
        {
            yield return stepFinished;
        }
    }

    private static IEnumerable<AgentResponseUpdate> CloseActiveSteps(AgentResponseUpdate? template, List<int> activeSteps)
    {
        for (int i = activeSteps.Count - 1; i >= 0; i--)
        {
            yield return CloneWithEvent(
                template,
                new StepFinishedEvent { StepName = GetStepName(activeSteps[i]) },
                includeContents: false);
        }

        activeSteps.Clear();
    }

    private static AgentResponseUpdate CloneWithEvent(
        AgentResponseUpdate? update,
        BaseEvent evt,
        bool includeContents = true)
        => new(update?.Role, includeContents ? update?.Contents : [])
        {
            AdditionalProperties = update?.AdditionalProperties,
            AgentId = update?.AgentId,
            AuthorName = update?.AuthorName,
            ContinuationToken = update?.ContinuationToken,
            CreatedAt = update?.CreatedAt,
            FinishReason = update?.FinishReason,
            MessageId = update?.MessageId,
            RawRepresentation = evt,
            ResponseId = update?.ResponseId,
        };

    private static AgentResponseUpdate? FilterDuplicateErrorContent(
        AgentResponseUpdate update,
        ref bool terminalErrorForwarded)
    {
        bool hasError = update.Contents.Any(static content => content is ErrorContent);
        if (!hasError)
        {
            return update;
        }

        if (!terminalErrorForwarded)
        {
            terminalErrorForwarded = true;
            return update;
        }

        AIContent[] remainingContents = [.. update.Contents.Where(static content => content is not ErrorContent)];
        return remainingContents.Length > 0
            ? CloneWithContents(update, remainingContents)
            : null;
    }

    private static AgentResponseUpdate CloneWithContents(
        AgentResponseUpdate update,
        IList<AIContent> contents)
        => new(update.Role, contents)
        {
            AdditionalProperties = update.AdditionalProperties,
            AgentId = update.AgentId,
            AuthorName = update.AuthorName,
            ContinuationToken = update.ContinuationToken,
            CreatedAt = update.CreatedAt,
            FinishReason = update.FinishReason,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation,
            ResponseId = update.ResponseId,
        };

    private static string GetStepName(int stepNumber) => $"superstep:{stepNumber}";

    private static bool IsResponseCompatible(WorkflowOutputEvent output)
        => output is AgentResponseEvent or AgentResponseUpdateEvent
            || output.Data is string
            || output.Data is AIContent
            || output.Data is IEnumerable<AIContent>
            || output.Data is ChatMessage
            || output.Data is IEnumerable<ChatMessage>;

    private static CustomEvent CreateCustomEvent(string name, AGUIWorkflowWarningPayload payload)
        => new()
        {
            Name = name,
            Value = JsonSerializer.SerializeToElement(payload, AGUIWorkflowEventsJsonContext.Default.AGUIWorkflowWarningPayload),
        };

    private static CustomEvent CreateCustomEvent(string name, AGUIWorkflowOutputPayload payload)
        => new()
        {
            Name = name,
            Value = JsonSerializer.SerializeToElement(payload, AGUIWorkflowEventsJsonContext.Default.AGUIWorkflowOutputPayload),
        };

    private static CustomEvent CreateCustomEvent(string name, AGUIWorkflowExecutorPayload payload)
        => new()
        {
            Name = name,
            Value = JsonSerializer.SerializeToElement(payload, AGUIWorkflowEventsJsonContext.Default.AGUIWorkflowExecutorPayload),
        };

    private static JsonElement? TrySerializeOutput(object? value)
        => value switch
        {
            JsonElement element => element.Clone(),
            JsonDocument document => document.RootElement.Clone(),
            bool boolean => SerializeScalar(boolean, AGUIWorkflowEventsJsonContext.Default.Boolean),
            byte number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Byte),
            sbyte number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.SByte),
            short number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Int16),
            ushort number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.UInt16),
            int number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Int32),
            uint number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.UInt32),
            long number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Int64),
            ulong number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.UInt64),
            float number when float.IsFinite(number) => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Single),
            double number when double.IsFinite(number) => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Double),
            decimal number => SerializeScalar(number, AGUIWorkflowEventsJsonContext.Default.Decimal),
            char character => SerializeScalar(character, AGUIWorkflowEventsJsonContext.Default.Char),
            DateTime dateTime => SerializeScalar(dateTime, AGUIWorkflowEventsJsonContext.Default.DateTime),
            DateTimeOffset dateTimeOffset => SerializeScalar(dateTimeOffset, AGUIWorkflowEventsJsonContext.Default.DateTimeOffset),
            Guid guid => SerializeScalar(guid, AGUIWorkflowEventsJsonContext.Default.Guid),
            TimeSpan timeSpan => SerializeScalar(timeSpan, AGUIWorkflowEventsJsonContext.Default.TimeSpan),
            Uri uri => SerializeScalar(uri, AGUIWorkflowEventsJsonContext.Default.Uri),
            _ => null,
        };

    private static JsonElement SerializeScalar<T>(T value, JsonTypeInfo<T> typeInfo)
        => JsonSerializer.SerializeToElement(value, typeInfo);
}

internal sealed record AGUIWorkflowWarningPayload(string Message);

internal sealed record AGUIWorkflowOutputPayload(string ExecutorId, string[] Tags, JsonElement? Data);

internal sealed record AGUIWorkflowExecutorPayload(string ExecutorId);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(AGUIWorkflowWarningPayload))]
[JsonSerializable(typeof(AGUIWorkflowOutputPayload))]
[JsonSerializable(typeof(AGUIWorkflowExecutorPayload))]
[JsonSerializable(typeof(bool))]
[JsonSerializable(typeof(byte))]
[JsonSerializable(typeof(sbyte))]
[JsonSerializable(typeof(short))]
[JsonSerializable(typeof(ushort))]
[JsonSerializable(typeof(int))]
[JsonSerializable(typeof(uint))]
[JsonSerializable(typeof(long))]
[JsonSerializable(typeof(ulong))]
[JsonSerializable(typeof(float))]
[JsonSerializable(typeof(double))]
[JsonSerializable(typeof(decimal))]
[JsonSerializable(typeof(char))]
[JsonSerializable(typeof(DateTime))]
[JsonSerializable(typeof(DateTimeOffset))]
[JsonSerializable(typeof(Guid))]
[JsonSerializable(typeof(TimeSpan))]
[JsonSerializable(typeof(Uri))]
internal sealed partial class AGUIWorkflowEventsJsonContext : JsonSerializerContext;
