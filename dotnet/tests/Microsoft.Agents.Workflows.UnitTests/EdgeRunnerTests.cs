// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

public class EdgeRunnerTests
{
    private static async Task CreateAndRunDirectedEdgeTestAsync(bool? conditionMatch = null, bool? targetMatch = null)
    {
        const string MessageVariant1 = "test";
        const string MessageVariant2 = "something else";

        Func<object?, bool>? condition
            = conditionMatch.HasValue
            ? message => message is string value && value.Equals(conditionMatch.Value
                                                                ? MessageVariant1
                                                                : MessageVariant2, StringComparison.Ordinal)
            : null;

        string? targetId
            = targetMatch.HasValue
            ? (targetMatch.Value ? "executor2" : "executor1")
            : null;

        TestRunContext runContext = new();

        runContext.Executors["executor1"] = new ForwardMessageExecutor<string>("executor1");
        runContext.Executors["executor2"] = new ForwardMessageExecutor<string>("executor2");

        DirectEdgeData edgeData = new("executor1", "executor2", new EdgeId(0), condition);
        DirectEdgeRunner runner = new(runContext, edgeData);

        MessageEnvelope envelope = new(MessageVariant1, targetId: targetId);

        await runner.ChaseAsync(envelope, tracer: null);

        bool expectMessage = (!conditionMatch.HasValue || conditionMatch.Value)
                             && (!targetMatch.HasValue || targetMatch.Value);

        if (expectMessage)
        {
            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages, ("executor2", [MessageVariant1]));
        }
        else
        {
            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages);
        }
    }

    [Fact]
    public async Task Test_DirectEdgeRunnerAsync()
    {
        // Test matrix:
        //   NoCondition vs Condition(=> true) vs Condition(=> false)
        //   Untargeted vs Targeted(matching) vs Targeted(not matching)

        await CreateAndRunDirectedEdgeTestAsync(); // NoCondition, Untargeted

        await CreateAndRunDirectedEdgeTestAsync(targetMatch: true); // NoCondition, Targeted
        await CreateAndRunDirectedEdgeTestAsync(targetMatch: false); // NoCondition, Targeted(not matching)

        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: true); // Condition(=> true), Untargeted
        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: false); // Condition(=> false), Untargeted

        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: true, targetMatch: true); // Condition(=> true), Targeted(matching)
        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: true, targetMatch: false); // Condition(=> true), Targeted(not matching)
        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: false, targetMatch: true); // Condition(=> false), Targeted(matching)
        await CreateAndRunDirectedEdgeTestAsync(conditionMatch: false, targetMatch: false); // Condition(=> false), Targeted(not matching)
    }

    private static async Task CreateAndRunFanOutEdgeTestAsync(bool? assignerSelectsEmpty = null, bool? targetMatch = null)
    {
        TestRunContext runContext = new();

        runContext.Executors["executor1"] = new ForwardMessageExecutor<string>("executor1");
        runContext.Executors["executor2"] = new ForwardMessageExecutor<string>("executor2");
        runContext.Executors["executor3"] = new ForwardMessageExecutor<string>("executor3");

        Func<object?, int, IEnumerable<int>>? assigner
            = assignerSelectsEmpty.HasValue
            ? (message, count) => assignerSelectsEmpty.Value ? [] : [0]
            : null;

        string? targetId
            = targetMatch.HasValue
            ? (targetMatch.Value ? "executor2" : "executor1")
            : null;

        FanOutEdgeData edgeData = new("executor1", ["executor2", "executor3"], new EdgeId(0), assigner);
        FanOutEdgeRunner runner = new(runContext, edgeData);

        MessageEnvelope envelope = new("test", targetId: targetId);

        await runner.ChaseAsync(envelope, tracer: null);

        bool expectForwardFrom2 = (!assignerSelectsEmpty.HasValue || !assignerSelectsEmpty.Value)
                                    && (!targetMatch.HasValue || targetMatch.Value);
        bool expectForwardFrom3 = !assignerSelectsEmpty.HasValue && !targetMatch.HasValue; // if there is a target, it is never executor3

        List<(string expectedSender, List<string> expectedMessages)> expectedForwards = [];
        if (expectForwardFrom2)
        {
            expectedForwards.Add(("executor2", ["test"]));
        }

        if (expectForwardFrom3)
        {
            expectedForwards.Add(("executor3", ["test"]));
        }

        MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages, expectedForwards.ToArray());
    }

    [Fact]
    public async Task Test_FanOutEdgeRunnerAsync()
    {
        // Test matrix:
        //   NoAssigned vs Assigner(includes output) vs Assigner(does not include output)
        //   Untargeted vs Targeted(matching) vs Targeted(not matching)

        await CreateAndRunFanOutEdgeTestAsync(); // NoAssigner, Untargeted

        await CreateAndRunFanOutEdgeTestAsync(targetMatch: true); // NoAssigner, Targeted(matching)
        await CreateAndRunFanOutEdgeTestAsync(targetMatch: false); // NoAssigner, Targeted(not matching)

        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: false); // Assigner(includes output), Untargeted
        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: true); // Assigner(does not include output), Untargeted

        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: false, targetMatch: true); // Assigner(includes output), Targeted(matching)
        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: false, targetMatch: false); // Assigner(includes output), Targeted(not matching)
        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: true, targetMatch: true); // Assigner(does not include output), Targeted(matching)
        await CreateAndRunFanOutEdgeTestAsync(assignerSelectsEmpty: true, targetMatch: false); // Assigner(does not include output), Targeted(not matching) 
    }

    [Fact]
    public async Task Test_FanInEdgeRunnerAsync()
    {
        TestRunContext runContext = new();

        runContext.Executors["executor1"] = new ForwardMessageExecutor<string>("executor1");
        runContext.Executors["executor2"] = new ForwardMessageExecutor<string>("executor2");
        runContext.Executors["executor3"] = new ForwardMessageExecutor<string>("executor3");

        FanInEdgeData edgeData = new(["executor1", "executor2"], "executor3", new EdgeId(0));
        FanInEdgeRunner runner = new(runContext, edgeData);

        // Step 1: Send message from executor1, should not forward yet.
        // Step 2: Send targeted message to executor1 from executor2, should not forward
        // Step 3: Send message from executor1, should not forward yet.
        // Step 4: Send message from executor2, should forward now.

        FanInEdgeState state = runner.CreateState();
        await RunIterationAsync();

        // Repeat the same sequence, to ensure state is properly reset inside of FanInEdgeState.
        runContext.QueuedMessages.Clear();
        await RunIterationAsync();

        async ValueTask RunIterationAsync()
        {
            await runner.ChaseAsync("executor1", new("part1"), state, tracer: null);

            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages);

            await runner.ChaseAsync("executor2", new("part-for-1", targetId: "executor1"), state, tracer: null);
            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages);

            await runner.ChaseAsync("executor1", new("part2", targetId: "executor3"), state, tracer: null);

            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages);

            await runner.ChaseAsync("executor2", new("final part"), state, tracer: null);

            MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages, ("executor3", ["part1", "part2", "final part"]));
        }
    }
}
