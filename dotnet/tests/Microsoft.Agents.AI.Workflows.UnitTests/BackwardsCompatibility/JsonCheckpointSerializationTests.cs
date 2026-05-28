// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests.BackwardsCompatibility;

/// <summary>
/// Tests pinning the JSON shape of checkpoint-adjacent types so older payloads keep
/// deserializing correctly after the Outputs overhaul (see implementation-plan §5.7).
/// </summary>
public class JsonCheckpointSerializationTests
{
    private static readonly JsonSerializerOptions s_options = WorkflowsJsonUtilities.DefaultOptions;

    private static WorkflowInfo BuildInfoWithOutputExecutors(Dictionary<string, HashSet<OutputTag>> outputs)
        => new(
            executors: new Dictionary<string, ExecutorInfo>(),
            edges: new Dictionary<string, List<EdgeInfo>>(),
            requestPorts: [],
            startExecutorId: "start",
            outputExecutorIds: outputs);

    // ---------- WorkflowOutputEvent.Tags in-process round-trip (no JSON) ----------

    [Fact]
    public void Test_WorkflowOutputEvent_SingleTagCtorPopulatesTags()
    {
        WorkflowOutputEvent evt = new(data: "hello", executorId: "e1", tag: OutputTag.Intermediate);

        evt.ExecutorId.Should().Be("e1");
        evt.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate });
        evt.HasTag(OutputTag.Intermediate).Should().BeTrue();
        evt.IsIntermediate().Should().BeTrue();
    }

    [Fact]
    public void Test_WorkflowOutputEvent_NoTagsCtorIsUntagged()
    {
        WorkflowOutputEvent evt = new(data: "hello", executorId: "e1");

        evt.Tags.Should().BeEmpty();
        evt.IsIntermediate().Should().BeFalse("an event with no tags is a terminal/regular output");
    }

    [Fact]
    public void Test_WorkflowOutputEvent_MultiTagCtorPreservesAllTags()
    {
        OutputTag customTag = JsonSerializer.Deserialize<OutputTag>("\"custom\"", s_options);

        WorkflowOutputEvent evt = new(data: "hello", executorId: "e1", tags: new[] { OutputTag.Intermediate, customTag });

        evt.Tags.Should().HaveCount(2);
        evt.HasTag(OutputTag.Intermediate).Should().BeTrue();
        evt.HasTag(customTag).Should().BeTrue();
        evt.IsIntermediate().Should().BeTrue();
    }

    // ---------- WorkflowInfo.OutputExecutorIds shape ----------
    //
    // Note: per the comment in WorkflowsJsonUtilities, WorkflowEvent / WorkflowOutputEvent
    // is *not* currently a serialized checkpoint shape (events are not persisted into
    // checkpoints today), so we do not pin a JSON round-trip for Tags on the event itself
    // here. The tag JSON round-trip is exercised by OutputTagTests; the
    // OutputExecutorIds map shape is the actually-load-bearing back-compat surface.

    [Fact]
    public void Test_JsonCheckpoint_WorkflowOutputExecutorsReadsLegacyArrayShape()
    {
        const string LegacyJson = """
            {
              "executors": {},
              "edges": {},
              "requestPorts": [],
              "startExecutorId": "start",
              "outputExecutorIds": ["a", "b"]
            }
            """;

        WorkflowInfo? info = JsonSerializer.Deserialize<WorkflowInfo>(LegacyJson, s_options);

        info.Should().NotBeNull();
        info!.OutputExecutorIds.Should().HaveCount(2);
        info.OutputExecutorIds["a"].Should().BeEmpty("legacy ids are untagged regular outputs");
        info.OutputExecutorIds["b"].Should().BeEmpty();
    }

    [Fact]
    public void Test_JsonCheckpoint_WorkflowOutputExecutorsWritesMapShape()
    {
        Dictionary<string, HashSet<OutputTag>> outputs = new()
        {
            ["a"] = [],
            ["b"] = [OutputTag.Intermediate],
        };

        WorkflowInfo info = BuildInfoWithOutputExecutors(outputs);

        string json = JsonSerializer.Serialize(info, s_options);

        WorkflowInfo? back = JsonSerializer.Deserialize<WorkflowInfo>(json, s_options);

        back.Should().NotBeNull();
        back!.OutputExecutorIds.Should().HaveCount(2);
        back.OutputExecutorIds["a"].Should().BeEmpty();
        back.OutputExecutorIds["b"].Should().BeEquivalentTo(new[] { OutputTag.Intermediate });

        // The map shape is detectable in the serialized JSON: the property value starts with `{`, not `[`.
        int idx = json.IndexOf("\"outputExecutorIds\"", System.StringComparison.Ordinal);
        idx.Should().BeGreaterThan(-1);
        int colon = json.IndexOf(':', idx);
        int firstNonSpace = colon + 1;
        while (firstNonSpace < json.Length && char.IsWhiteSpace(json[firstNonSpace]))
        {
            firstNonSpace++;
        }
        json[firstNonSpace].Should().Be('{', "OutputExecutorIds is written in the new map shape");
    }
}
