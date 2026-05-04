// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed record Slot<T>(T? answer, string? reason);

public record TestProgressLedgerState(Slot<bool?>? is_request_satisfied = null,
                                      Slot<bool?>? is_in_loop = null,
                                      Slot<bool?>? is_progress_being_made = null,
                                      Slot<string>? instruction_or_question = null,
                                      Slot<string>? next_speaker = null,
                                      Slot<bool?>? custom1 = null,
                                      Slot<string>? custom2 = null)
{
    public TestProgressLedgerState() : this(new Slot<bool?>(false, "is_request_satisfied_reason"),
                                            new Slot<bool?>(false, "is_in_loop_reason"),
                                            new Slot<bool?>(false, "is_progress_being_made_reason"),
                                            new Slot<string>("Answer", "instruction_or_question_reason"),
                                            new Slot<string>("Lorem Ipsum", "next_speaker_reason"),
                                            new Slot<bool?>(false, "custom1_reason"),
                                            new Slot<string>("Custom2", "custom2_reason"))
    { }

    public string ToJsonString() => this.ToJson().ToString();

    private static readonly JsonSerializerOptions s_options = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public JsonElement ToJson() => JsonSerializer.SerializeToElement(this, s_options);

    internal static BooleanProgressLedgerSlot CustomSlot1 = new("custom1", "Custom Slot 1");
    internal static StringProgressLedgerSlot CustomSlot2 = new("custom2", "Custom Slot 2");

    public static bool TryGetCustom1(MagenticProgressLedger state, out bool result)
        => state.TryGetCurrentSlotValue(CustomSlot1, out result);

    public static bool TryGetCustom2(MagenticProgressLedger state, out string? result)
        => state.TryGetCurrentSlotValue(CustomSlot2, out result);

    public void Validate(MagenticProgressLedger state)
    {
        state.IsRequestSatisfied.Should().Be(this.is_request_satisfied!.answer!.Value);
        state.IsInLoop.Should().Be(this.is_in_loop!.answer!.Value);
        state.IsProgressBeingMade.Should().Be(this.is_progress_being_made!.answer!.Value);
        state.InstructionOrQuestion.Should().Be(this.instruction_or_question!.answer);
        state.NextSpeaker.Should().Be(this.next_speaker!.answer);

        if (this.custom1 != null)
        {
            TryGetCustom1(state, out bool custom1Value).Should().BeTrue();
            custom1Value.Should().Be(this.custom1.answer!.Value);
        }
        else
        {
            TryGetCustom1(state, out _).Should().BeFalse();
        }

        if (this.custom2 != null)
        {
            TryGetCustom2(state, out string? custom2Value).Should().BeTrue();
            custom2Value.Should().Be(this.custom2.answer);
        }
        else
        {
            TryGetCustom2(state, out _).Should().BeFalse();
        }
    }

    public static readonly TestProgressLedgerState Default = new();
    public static readonly TestProgressLedgerState RequiredOnly = Default with { custom1 = null, custom2 = null };

    public static readonly TestProgressLedgerState[] Working = [RequiredOnly, Default];

    public static readonly TestProgressLedgerState[] MissingRequired =
        [
            Default with { is_request_satisfied = null },
            Default with { is_in_loop = null},
            Default with { is_progress_being_made = null},
            Default with { instruction_or_question = null},
            Default with { next_speaker = null},
        ];
}
