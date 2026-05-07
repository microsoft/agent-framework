// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Maintains a ledger of progress made by the Magentic workflow.
/// </summary>
public class MagenticProgressLedger
{
    internal static readonly BooleanProgressLedgerSlot IsRequestSatisfiedSlot = new("is_request_satisfied",
        "Is the request fully satisfied? (True if complete, or False if the original request has yet to be SUCCESSFULLY and FULLY addressed)");

    internal static readonly BooleanProgressLedgerSlot IsInLoopSlot = new("is_in_loop",
        "Are we in a loop where we are repeating the same requests and or getting the same responses as before? " +
        "Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a handful of times.");

    internal static readonly BooleanProgressLedgerSlot IsProgressBeingMadeSlot = new("is_progress_being_made",
        "Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent " +
        "messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success " +
        "such as the inability to read from a required file)");

    internal readonly StringProgressLedgerSlot NextSpeakerSlot;

    internal static readonly StringProgressLedgerSlot InstructionOrQuestionSlot = new("instruction_or_question",
        "What instruction or question would you give this team member? (Phrase as if speaking directly to them, and " +
        "include any specific information they may need)");

    internal MagenticProgressLedger(string teamNames, IEnumerable<ProgressLedgerSlot> additionalQuestions, JsonElement? state = null)
    {
        this.NextSpeakerSlot = new("next_speaker", $"Who should speak next? (select from: {teamNames})");
        this.AdditionalQuestions = additionalQuestions as ProgressLedgerSlot[] ?? additionalQuestions.ToArray();

        if (state != null)
        {
            this.TryUpdateState(state.Value);
        }
    }

    internal ProgressLedgerSlot[] AdditionalQuestions { get; }

    internal bool TryUpdateState(JsonElement element)
    {
        // In principle all of these should be inlineable, but the CodeAnalysis fails to properly chain through the and-chain to realize that
        // all must be true for `requiredQuestionsAnswered` to be true, meaning all of the out parameters would be initialized properly.
        bool isInLoop = false;
        bool isProgressBeingMade = false;
        string? nextSpeaker = string.Empty;
        string? instructionOrQuestion = string.Empty;

        bool requiredQuestionsAnswered =
            IsRequestSatisfiedSlot.TryGetValueFrom(element, out bool isRequestSatisfied) &&
            IsInLoopSlot.TryGetValueFrom(element, out isInLoop) &&
            IsProgressBeingMadeSlot.TryGetValueFrom(element, out isProgressBeingMade) &&
            this.NextSpeakerSlot.TryGetValueFrom(element, out nextSpeaker) &&
            InstructionOrQuestionSlot.TryGetValueFrom(element, out instructionOrQuestion);

        if (requiredQuestionsAnswered)
        {
            this.State = element;

            this.IsRequestSatisfied = isRequestSatisfied;
            this.IsInLoop = isInLoop;
            this.IsProgressBeingMade = isProgressBeingMade;

            this.NextSpeaker = nextSpeaker!;
            this.InstructionOrQuestion = instructionOrQuestion!;
        }

        // TODO: To what extent do we want to enforce that the additional questions are also answered? 

        return requiredQuestionsAnswered;
    }

    [JsonInclude]
    internal JsonElement? State;

    /// <summary>
    /// Specifies whether plan execution has started.
    /// </summary>
    [JsonIgnore]
    public bool IsStarted => this.State != null;

    /// <summary>
    /// Specifies whether the task has been fully satisfied.
    /// </summary>
    [JsonIgnore]
    public bool IsRequestSatisfied { get; private set; }

    /// <summary>
    /// Specifies whether the team is in a loop.
    /// </summary>
    [JsonIgnore]
    public bool IsInLoop { get; private set; }

    /// <summary>
    /// Specifies whether the team is making progress on the task.
    /// </summary>
    [JsonIgnore]
    public bool IsProgressBeingMade { get; private set; }

    /// <summary>
    /// Gets the next team member to take a turn.
    /// </summary>
    [JsonIgnore]
    public string NextSpeaker { get; private set; } = string.Empty;

    /// <summary>
    /// Gets the instruction or question to send to the next team member.
    /// </summary>
    [JsonIgnore]
    public string InstructionOrQuestion { get; private set; } = string.Empty;

    [JsonIgnore]
    internal IEnumerable<ProgressLedgerSlot> Slots =>
        [
            IsRequestSatisfiedSlot,
            IsInLoopSlot,
            IsProgressBeingMadeSlot,
            this.NextSpeakerSlot,
            InstructionOrQuestionSlot,
            .. this.AdditionalQuestions
        ];

    internal bool TryGetCurrentSlotValue<T>(ProgressLedgerSlot<T> slot, [NotNullWhen(true)] out T? value)
    {
        if (!this.State.HasValue)
        {
            value = default;
            return false;
        }

        return slot.TryGetValueFrom(this.State.Value, out value);
    }

    private (string QuestionBlock, string AnswerSchema)? _questionFormatCache;
    internal (string QuestionBlock, string AnswerSchema) FormatQuestions()
    {
        if (!this._questionFormatCache.HasValue)
        {
            StringBuilder questionBuilder = new(), schemaBuilder = new();

            schemaBuilder.AppendLine("{");
            foreach (ProgressLedgerSlot slot in this.Slots)
            {
                questionBuilder.AppendLine(slot.FormattedQuestion);

                schemaBuilder.AppendLine($"\"{slot.Key}\": {{")
                             .AppendLine($"   \"{ProgressLedgerSlot.ValueKey}\": {slot.SchemaType}{slot.SuffixString},")
                             .AppendLine($"   \"{ProgressLedgerSlot.ReasonKey}\": string")
                             .AppendLine("}");
            }
            schemaBuilder.AppendLine("}");

            this._questionFormatCache = (questionBuilder.ToString(), schemaBuilder.ToString());
        }

        return this._questionFormatCache.Value;
    }
}

internal abstract record ProgressLedgerSlot(string Key, string Question, string? SchemaTypeSuffix = null)
{
    public const string ValueKey = "answer";
    public const string ReasonKey = "reason";

    internal string SuffixString => this.SchemaTypeSuffix == null ? string.Empty : $"({this.SchemaTypeSuffix})";

    protected internal abstract string SchemaType { get; }

    public string FormattedQuestion
    {
        get
        {
            if (field == null)
            {
                IEnumerable<string> questionLines = this.Question.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
                                                                 .Select(line => line.TrimEnd());

                field = $"    - {string.Join("\n      ", questionLines)}";
            }

            return field;
        }
    }
}

internal abstract record ProgressLedgerSlot<T>(string Key, string Question, string? SchemaTypeSuffix = null, JsonSerializerOptions? SerializerOptions = null)
    : ProgressLedgerSlot(Key, Question, SchemaTypeSuffix)
{
    protected internal virtual JsonTypeInfo<T> GetJsonTypeInfo() =>
        ((this.SerializerOptions ?? WorkflowsJsonUtilities.DefaultOptions).TryGetTypeInfo(typeof(T), out JsonTypeInfo? typeInfo)
            ? typeInfo as JsonTypeInfo<T> : null)
        ?? throw new InvalidOperationException($"Cannot get TypeInfo for {typeof(T)} from {(this.SerializerOptions == null ? "provided" : "default")} SerializationOptions.");

    public bool TryGetValueFrom(JsonElement answers, [NotNullWhen(true)] out T? value)
    {
        if (answers.TryGetProperty(this.Key, out JsonElement slotElement) &&
            slotElement.ValueKind != JsonValueKind.Null &&
            slotElement.TryGetProperty(ValueKey, out JsonElement answerValue))
        {
            try
            {
                T? result = answerValue.Deserialize(this.GetJsonTypeInfo());
                if (result != null)
                {
                    value = result;
                    return true;
                }
            }
            catch
            {
            }
        }

        value = default;
        return false;
    }

    public bool TryGetReasonFrom(JsonElement answers, [NotNullWhen(true)] out string? value)
    {
        if (answers.TryGetProperty(this.Key, out JsonElement slotElement) &&
            slotElement.ValueKind != JsonValueKind.Null &&
            slotElement.TryGetProperty(ReasonKey, out JsonElement reasonValue))
        {
            try
            {
                string? result = reasonValue.Deserialize(WorkflowsJsonUtilities.JsonContext.Default.String);
                if (result != null)
                {
                    value = result;
                    return true;
                }
            }
            catch
            {
            }
        }

        value = default;
        return false;
    }
}

internal sealed record BooleanProgressLedgerSlot(string Key, string Question, string? SchemaTypeSuffix = null) : ProgressLedgerSlot<bool>(Key, Question, SchemaTypeSuffix)
{
    // Since we know the type statically, we can directly return the JsonTypeInfo for string from our JsonContext,
    // which is more efficient than looking it up via the options.
    protected internal override JsonTypeInfo<bool> GetJsonTypeInfo() => WorkflowsJsonUtilities.JsonContext.Default.Boolean;

    protected internal override string SchemaType => "boolean";
}

internal sealed record StringProgressLedgerSlot(string Key, string Question, string? SchemaTypeSuffix = null) : ProgressLedgerSlot<string>(Key, Question, SchemaTypeSuffix)
{
    // Since we know the type statically, we can directly return the JsonTypeInfo for string from our JsonContext,
    // which is more efficient than looking it up via the options.
    protected internal override JsonTypeInfo<string> GetJsonTypeInfo() => WorkflowsJsonUtilities.JsonContext.Default.String;

    protected internal override string SchemaType => "string";
}
