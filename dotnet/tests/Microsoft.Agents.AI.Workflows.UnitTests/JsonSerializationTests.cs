// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Linq.Expressions;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class JsonSerializationTests
{
    private static JsonSerializerOptions TestCustomSerializedJsonOptions
    {
        get
        {
            JsonSerializerOptions options = new(TestJsonContext.Default.Options);
            options.MakeReadOnly();

            return options;
        }
    }

    private static int s_nextEdgeId;

    private static EdgeId TakeEdgeId() => new(Interlocked.Increment(ref s_nextEdgeId));

    private static T RunJsonRoundtrip<T>(T value, JsonSerializerOptions? externalOptions = null, Expression<Func<T, bool>>? predicate = null)
    {
        JsonMarshaller marshaller = new(externalOptions);

        JsonElement element = marshaller.Marshal(value);
        T deserialized = marshaller.Marshal<T>(element);

        if (deserialized is not null)
        {
            if (predicate is not null)
            {
                deserialized.Should().Match(predicate);
            }

            return deserialized;
        }

        Debug.Fail($"Could not roundtrip type '{typeof(T).Name}'. JSON = '{element}'.");
        throw new NotSupportedException($"Could not roundtrip type '{typeof(T).Name}'.");
    }

    [Fact]
    public void Test_EdgeConnection_JsonRoundtrip()
    {
        EdgeConnection connection = new(["Source1", "Source2"], ["Sink1", "Sink2"]);
        RunJsonRoundtrip(connection, predicate: connection.CreateValidator());
    }

    [Fact]
    public void Test_TypeId_JsonRoundtrip()
    {
        TypeId type = new(typeof(Type));
        RunJsonRoundtrip(type, predicate: CreateValidator());

        Expression<Func<TypeId, bool>> CreateValidator()
        {
            return deserialized => deserialized.AssemblyName == type.AssemblyName &&
                                   deserialized.TypeName == type.TypeName &&
                                   deserialized.IsMatch<Type>();
        }
    }

    [Fact]
    public void Test_ExecutorInfo_JsonRoundtrip()
    {
        ExecutorInfo executorInfo = new(new(typeof(ForwardMessageExecutor<string>)), "ForwardString");
        RunJsonRoundtrip(executorInfo, predicate: CreateValidator());

        Expression<Func<ExecutorInfo, bool>> CreateValidator()
        {
            return deserialized => deserialized.ExecutorId == executorInfo.ExecutorId &&
                                   // Rely on the TypeId test to probe TypeId serialization - just validate that we got a functional TypeId
                                   deserialized.ExecutorType.IsMatch<ForwardMessageExecutor<string>>();
        }
    }

    private static RequestPort TestPort => RequestPort.Create<string, int>("StringToInt");
    private static RequestPortInfo TestPortInfo => TestPort.ToPortInfo();

    [Fact]
    public void Test_RequestPortInfo_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestPortInfo, predicate: TestPort.CreatePortInfoValidator());
    }

    private static DirectEdgeInfo TestDirectEdgeInfo_NoCondition => new(new("SourceExecutor", "TargetExecutor", TakeEdgeId(), condition: null));
    private static DirectEdgeInfo TestDirectEdgeInfo_Condition => new(new("SourceExecutor", "TargetExecutor", TakeEdgeId(), condition: msg => msg is not null));

    [Fact]
    public void Test_DirectEdgeInfo_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestDirectEdgeInfo_NoCondition, predicate: TestDirectEdgeInfo_NoCondition.CreateValidator());
        RunJsonRoundtrip(TestDirectEdgeInfo_Condition, predicate: TestDirectEdgeInfo_Condition.CreateValidator());
    }

    private static FanOutEdgeInfo TestFanOutEdgeInfo_NoAssigner => new(new("SourceExecutor", ["TargetExecutor1", "TargetExecutor2"], TakeEdgeId(), assigner: null));
    private static FanOutEdgeInfo TestFanOutEdgeInfo_Assigner => new(new("SourceExecutor", ["TargetExecutor1", "TargetExecutor2"], TakeEdgeId(), assigner: (msg, count) => []));

    [Fact]
    public void Test_FanOutEdgeInfo_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestFanOutEdgeInfo_NoAssigner, predicate: TestFanOutEdgeInfo_NoAssigner.CreateValidator());
        RunJsonRoundtrip(TestFanOutEdgeInfo_Assigner, predicate: TestFanOutEdgeInfo_Assigner.CreateValidator());
    }

    private static FanInEdgeData TestFanInEdgeData => new(["SourceExecutor1", "SourceExecutor2"], "TargetExecutor", TakeEdgeId());
    private static FanInEdgeInfo TestFanInEdgeInfo => new(TestFanInEdgeData);

    [Fact]
    public void Test_FanInEdgeInfo_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestFanInEdgeInfo, predicate: TestFanInEdgeInfo.CreateValidator());
    }

    private static EdgeInfo TestEdgeInfo_DirectNoCondition { get; } = TestDirectEdgeInfo_NoCondition;
    private static EdgeInfo TestEdgeInfo_DirectCondition { get; } = TestDirectEdgeInfo_Condition;
    private static EdgeInfo TestEdgeInfo_FanOutNoAssigner { get; } = TestFanOutEdgeInfo_NoAssigner;
    private static EdgeInfo TestEdgeInfo_FanOutAssigner { get; } = TestFanOutEdgeInfo_Assigner;
    private static EdgeInfo TestEdgeInfo_FanIn { get; } = TestFanInEdgeInfo;

    [Fact]
    public void Test_EdgeInfoPolymorphism_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestEdgeInfo_DirectNoCondition, predicate: TestEdgeInfo_DirectNoCondition.CreatePolyValidator());
        RunJsonRoundtrip(TestEdgeInfo_DirectCondition, predicate: TestEdgeInfo_DirectCondition.CreatePolyValidator());
        RunJsonRoundtrip(TestEdgeInfo_FanOutNoAssigner, predicate: TestEdgeInfo_FanOutNoAssigner.CreatePolyValidator());
        RunJsonRoundtrip(TestEdgeInfo_FanOutAssigner, predicate: TestEdgeInfo_FanOutAssigner.CreatePolyValidator());
        RunJsonRoundtrip(TestEdgeInfo_FanIn, predicate: TestEdgeInfo_FanIn.CreatePolyValidator());
    }

    private const string ForwardStringId = nameof(s_forwardString);
    private const string ForwardIntId = nameof(s_forwardInt);

    private static readonly ExecutorIdentity s_forwardString = new() { Id = ForwardStringId };
    private static readonly ExecutorIdentity s_forwardInt = new() { Id = ForwardIntId };

    private const string IntToStringId = nameof(IntToString);
    private const string StringToIntId = nameof(StringToInt);

    private static RequestPortInfo IntToString => RequestPort.Create<int, string>(IntToStringId).ToPortInfo();
    private static RequestPortInfo StringToInt => RequestPort.Create<string, int>(StringToIntId).ToPortInfo();

    private static ValueTask<Workflow<string>> CreateTestWorkflowAsync()
    {
        ForwardMessageExecutor<string> forwardString = new(ForwardStringId);
        ForwardMessageExecutor<int> forwardInt = new(ForwardIntId);

        RequestPort stringToInt = RequestPort.Create<string, int>(StringToIntId);
        RequestPort intToString = RequestPort.Create<int, string>(IntToStringId);

        WorkflowBuilder builder = new(forwardString);
        builder.AddEdge(forwardString, stringToInt)
               .AddEdge(stringToInt, forwardInt)
               .AddEdge(forwardInt, intToString)
               .AddEdge(intToString, StreamingAggregators.Last<int>().AsExecutor("Aggregate"));

        return builder.BuildAsync<string>();
    }

    private static async ValueTask<WorkflowInfo> CreateTestWorkflowInfoAsync()
    {
        Workflow<string> testWorkflow = await CreateTestWorkflowAsync().ConfigureAwait(false);
        return testWorkflow.ToWorkflowInfo();
    }

    private static void ValidateWorkflowInfo(WorkflowInfo actual, WorkflowInfo prototype)
    {
        ValidateExecutorDictionary(prototype.Executors, prototype.Edges, actual.Executors, actual.Edges);
        ValidateRequestPorts(prototype.RequestPorts, actual.RequestPorts);

        actual.InputType.Should().Match(prototype.InputType.CreateValidator());
        actual.StartExecutorId.Should().Be(prototype.StartExecutorId);

        actual.OutputExecutorIds.Should().HaveCount(prototype.OutputExecutorIds.Count)
                            .And.AllSatisfy(id => prototype.OutputExecutorIds.Contains(id));

        void ValidateExecutorDictionary(Dictionary<string, ExecutorInfo> expected,
                                        Dictionary<string, List<EdgeInfo>> expectedEdges,
                                        Dictionary<string, ExecutorInfo> actual,
                                        Dictionary<string, List<EdgeInfo>> actualEdges)
        {
            actual.Should().HaveCount(expected.Count);
            actualEdges.Should().HaveCount(expectedEdges.Count);

            foreach (string key in expected.Keys)
            {
                actual.Should().ContainKey(key);

                ExecutorInfo actualValue = actual[key];
                ExecutorInfo expectedValue = expected[key];

                actualValue.Should().Match(expectedValue.CreateValidator());

                if (expectedEdges.TryGetValue(key, out List<EdgeInfo>? expectedEdgeList))
                {
                    List<EdgeInfo>? actualEdgeList = actualEdges.Should().ContainKey(key).WhoseValue;
                    actualEdgeList.Should().NotBeNull();

                    ValidateExecutorEdges(expectedEdgeList, actualEdgeList);
                }
            }
        }

        void ValidateExecutorEdges(List<EdgeInfo> expected, List<EdgeInfo> actual)
        {
            actual.Should().HaveCount(expected.Count);
            foreach (EdgeInfo expectedEdge in expected)
            {
                actual.Should().ContainSingle(edge => edge.CreatePolyValidator().Compile()(edge));
            }
        }

        void ValidateRequestPorts(HashSet<RequestPortInfo> expected, HashSet<RequestPortInfo> actual)
            => actual.Should().HaveCount(expected.Count).And.IntersectWith(expected);
    }

    [Fact]
    public async Task Test_WorkflowInfo_JsonRoundtripAsync()
    {
        WorkflowInfo prototype = await CreateTestWorkflowInfoAsync();

        JsonMarshaller marshaller = new();

        JsonElement jsonElement = marshaller.Marshal(prototype);
        WorkflowInfo deserialized = marshaller.Marshal<WorkflowInfo>(jsonElement);

        ValidateWorkflowInfo(deserialized, prototype);
    }

    private static ExecutorIdentity TestIdentity => new() { Id = "Executor1" };

    [Fact]
    public void Test_ExecutorIdentity_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestIdentity, predicate: TestIdentity.CreateValidator());
        RunJsonRoundtrip(ExecutorIdentity.None, predicate: ExecutorIdentity.None.CreateValidator());
    }

    private static ScopeId TestScopeId_Private => new("Executor1", null);
    private static ScopeId TestScopeId_Public => new("Executor1", "Scope1");

    [Fact]
    public void Test_ScopeId_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestScopeId_Private, predicate: TestScopeId_Private.CreateValidator());
        RunJsonRoundtrip(TestScopeId_Public, predicate: TestScopeId_Public.CreateValidator());
    }

    private static ScopeKey TestScopeKey_Private => new(TestScopeId_Private, "Key1");
    private static ScopeKey TestScopeKey_Public => new(TestScopeId_Public, "Key1");

    [Fact]
    public void Test_ScopeKey_JsonRoundtrip()
    {
        RunJsonRoundtrip(TestScopeKey_Private, predicate: TestScopeKey_Private.CreateValidator());
        RunJsonRoundtrip(TestScopeKey_Public, predicate: TestScopeKey_Public.CreateValidator());
    }

    private static ExternalRequest TestExternalRequest => ExternalRequest.Create(TestPort, "Request1", "TestData");

    [Fact]
    public void SanityCheck_JsonTypeInfo()
    {
        JsonTypeInfo? info = WorkflowsJsonUtilities.JsonContext.Default.GetTypeInfo(typeof(string));
        info.Should().NotBeNull();
    }

    [Fact]
    public void Test_PortableValue_JsonRoundtrip_BuiltInType()
    {
        PortableValue value = new("TestString");
        PortableValue result = RunJsonRoundtrip(value);

        result.Should().Be(value);

        // Also validate that we can extract the value as the correct type
        string? extracted = result.As<string>();

        extracted.Should().Be("TestString");

        // And that we can't extract it as an incorrect type
        result.Is<int>().Should().BeFalse();
    }

    [Fact]
    public void Test_PortableValue_JsonRoundTrip_InternalType()
    {
        ChatMessage message = new(ChatRole.User, "Hello, world!");

        PortableValue value = new(message);
        PortableValue result = RunJsonRoundtrip(value);

        result.Should().Be(value);

        // Also validate that we can extract the value as the correct type
        ChatMessage? chatMessage = result.As<ChatMessage>();

        chatMessage.Should().NotBeNull();
        chatMessage.Role.Should().Be(ChatRole.User);
        chatMessage.Text.Should().Be("Hello, world!");

        // And that we can't extract it as an incorrect type
        result.Is<int>().Should().BeFalse();
    }

    [Fact]
    public void Test_PortableValue_JsonRoundTrip_CustomType()
    {
        TestJsonSerializable test = new() { Id = 42, Name = "Test" };

        PortableValue value = new(test);
        PortableValue result = RunJsonRoundtrip(value, TestCustomSerializedJsonOptions);

        result.Should().Be(value);

        // Also validate that we can extract the value as the correct type
        TestJsonSerializable? extracted = result.As<TestJsonSerializable>();

        extracted.Should().NotBeNull();
        extracted.Id.Should().Be(42);
        extracted.Name.Should().Be("Test");

        // And that we can't extract it as an incorrect type
        result.Is<int>().Should().BeFalse();
    }

    private static void ValidateExternalRequest(ExternalRequest actual, ExternalRequest expected)
    {
        bool isIdEqual = actual.RequestId == expected.RequestId;
        bool isPortEqual = actual.PortInfo == expected.PortInfo;
        bool isDataEqual = actual.Data == expected.Data;

        isIdEqual.Should().BeTrue();
        isPortEqual.Should().BeTrue();
        isDataEqual.Should().BeTrue();
    }

    [Fact]
    public void Test_ExternalRequest_JsonRoundtrip()
    {
        ExternalRequest result = RunJsonRoundtrip(TestExternalRequest);
        ValidateExternalRequest(result, TestExternalRequest);
    }

    private static ExternalResponse TestExternalResponse => TestExternalRequest.CreateResponse(123);

    [Fact]
    public void Test_ExternalResponse_JsonRoundtrip()
    {
        ExternalResponse result = RunJsonRoundtrip(TestExternalResponse);

        bool isIdEqual = result.RequestId == TestExternalResponse.RequestId;
        bool isPortEqual = result.PortInfo == TestExternalResponse.PortInfo;
        bool isDataEqual = result.Data == TestExternalResponse.Data;

        isIdEqual.Should().BeTrue();
        isPortEqual.Should().BeTrue();
        isDataEqual.Should().BeTrue();
    }

    [Fact]
    public void Test_PortableMessageEnvelope_JsonRoundtrip_BuiltInType()
    {
        const string Message = "TestMessage";

        MessageEnvelope envelope = new(Message, "Source1", new TypeId(typeof(object)), targetId: "Target1");
        PortableMessageEnvelope value = new(envelope);
        PortableMessageEnvelope result = RunJsonRoundtrip(value);

        bool isTypeEqual = result.MessageType == value.MessageType;
        bool isTargetEqual = result.TargetId == value.TargetId;
        bool isMessageEqual = result.Message == value.Message;

        isTypeEqual.Should().BeTrue();
        isTargetEqual.Should().BeTrue();
        isMessageEqual.Should().BeTrue();

        MessageEnvelope reconstructed = result.ToMessageEnvelope();

        reconstructed.MessageType.Should().Be(envelope.MessageType);
        reconstructed.TargetId.Should().Be(envelope.TargetId);
        reconstructed.Message.Should().Be(envelope.Message);
    }

    [Fact]
    public void Test_PortableMessageEnvelope_JsonRoundtrip_InternalType()
    {
        ChatMessage message = new(ChatRole.User, "Hello, world!");

        MessageEnvelope envelope = new(message, "Source1", new TypeId(typeof(object)), targetId: "Target1");
        PortableMessageEnvelope value = new(envelope);
        PortableMessageEnvelope result = RunJsonRoundtrip(value);

        bool isTypeEqual = result.MessageType == value.MessageType;
        bool isTargetEqual = result.TargetId == value.TargetId;
        bool isMessageEqual = result.Message == value.Message;

        isTypeEqual.Should().BeTrue();
        isTargetEqual.Should().BeTrue();
        isMessageEqual.Should().BeTrue();

        MessageEnvelope reconstructed = result.ToMessageEnvelope();

        reconstructed.MessageType.Should().Be(envelope.MessageType);
        reconstructed.TargetId.Should().Be(envelope.TargetId);

        // Unfortunately, ChatMessage does not contain an "equality" comparer, so we need to explicitly pull it out
        // Simulate what PortableValue does in .Equals()
        Type expectedType = envelope.Message.GetType();
        object? maybeReconstructedMessage = ((PortableValue)reconstructed.Message)!.AsType(expectedType);
        maybeReconstructedMessage.Should().NotBeNull()
                                      .And.BeOfType<ChatMessage>()
                                      .And.Match(message.CreateValidatorCheckingText());
    }

    [Fact]
    public void Test_PortableMessageEnvelope_JsonRoundtrip_CustomType()
    {
        TestJsonSerializable message = new() { Id = 42, Name = "Test" };

        MessageEnvelope envelope = new(message, "Source1", new TypeId(typeof(object)), targetId: "Target1");
        PortableMessageEnvelope value = new(envelope);
        PortableMessageEnvelope result = RunJsonRoundtrip(value, TestCustomSerializedJsonOptions);

        bool isTypeEqual = result.MessageType == value.MessageType;
        bool isTargetEqual = result.TargetId == value.TargetId;
        bool isMessageEqual = result.Message == value.Message;

        isTypeEqual.Should().BeTrue();
        isTargetEqual.Should().BeTrue();
        isMessageEqual.Should().BeTrue();

        MessageEnvelope reconstructed = result.ToMessageEnvelope();

        reconstructed.MessageType.Should().Be(envelope.MessageType);
        reconstructed.TargetId.Should().Be(envelope.TargetId);
        reconstructed.Message.Should().Be(envelope.Message);
    }

    private static RunnerStateData TestRunnerStateData
    {
        get
        {
            return new(
                [ForwardStringId, ForwardIntId],
                CreateQueuedMessages(),
                outstandingRequests: [TestExternalRequest]
            );

            static Dictionary<string, List<PortableMessageEnvelope>> CreateQueuedMessages()
            {
                Dictionary<string, List<PortableMessageEnvelope>> result = [];

                MessageEnvelope internalEnvelope = new("InternalMessage", "TestExecutor1");
                result.Add("TestExecutor2", [new(internalEnvelope)]);

                return result;
            }
        }
    }

    private static void ValidateRunnerStateData(RunnerStateData result, RunnerStateData prototype)
    {
        Assert.Collection(result.InstantiatedExecutors,
                          prototype.InstantiatedExecutors.Select(
                              prototype =>
                              (Action<string>)(actual => actual.Should().Be(prototype))).ToArray());

        result.QueuedMessages.Should().HaveCount(prototype.QueuedMessages.Count);
        foreach (string key in prototype.QueuedMessages.Keys)
        {
            result.QueuedMessages.Should().ContainKey(key);

            List<PortableMessageEnvelope> actualList = result.QueuedMessages[key];
            List<PortableMessageEnvelope> expectedList = prototype.QueuedMessages[key];

            actualList.Should().HaveCount(expectedList.Count);
            for (int i = 0; i < expectedList.Count; i++)
            {
                PortableMessageEnvelope actual = actualList[i];
                PortableMessageEnvelope expected = expectedList[i];
                actual.MessageType.Should().Be(expected.MessageType);
                actual.TargetId.Should().Be(expected.TargetId);
                actual.Message.Should().Be(expected.Message);
            }
        }

        result.OutstandingRequests.Should().HaveCount(prototype.OutstandingRequests.Count);

        Assert.Collection(result.OutstandingRequests,
                          prototype.OutstandingRequests.Select(
                              expected =>
                                (Action<ExternalRequest>)(actual => ValidateExternalRequest(actual, expected))).ToArray());
    }

    [Fact]
    public void Test_RunnerStateData_JsonRoundtrip()
    {
        RunnerStateData prototype = TestRunnerStateData;
        RunnerStateData result = RunJsonRoundtrip(prototype);

        ValidateRunnerStateData(result, prototype);
    }

    private static FanInEdgeState TestFanInEdgeState => new(TestFanInEdgeData);
    private static PortableValue CreateEdgeState<TMessage>(TMessage message) where TMessage : notnull
    {
        FanInEdgeState state = TestFanInEdgeState;
        _ = state.ProcessMessage("SourceExecutor1", new MessageEnvelope(message, "SourceExecutor1", typeof(TMessage)));

        return new(state);
    }

    private static TestJsonSerializable TestCustomSerializable => new() { Id = 42, Name = nameof(TestCustomSerializable) };

    private static Dictionary<EdgeId, PortableValue> TestEdgeState
    {
        get
        {
            return new()
            {
                [TakeEdgeId()] = CreateEdgeState("Hello, world!"),
                [TakeEdgeId()] = CreateEdgeState(TestExternalResponse),
                [TakeEdgeId()] = CreateEdgeState(TestCustomSerializable)
            };
        }
    }

    private static void ValidateEdgeStateData(Dictionary<EdgeId, PortableValue> result, Dictionary<EdgeId, PortableValue> prototype)
    {
        result.Should().HaveCount(prototype.Count);
        foreach (EdgeId id in prototype.Keys)
        {
            result.Should().ContainKey(id)
                       .And.Subject[id].Should().Be(prototype[id])
                       .And.Subject.As<PortableValue>()
                                   .As<FanInEdgeState>().Should().NotBeNull()
                                                             .And.Match(CreateValidator(prototype[id].As<FanInEdgeState>()!));
        }
        Expression<Func<FanInEdgeState, bool>> CreateValidator(FanInEdgeState prototype)
        {
            return actual => actual.Unseen.SetEquals(prototype.Unseen) &&
                             actual.SourceIds.SequenceEqual(prototype.SourceIds) &&
                             actual.PendingMessages.Zip(prototype.PendingMessages,
                                (actualMessage, expectedMessage) => actualMessage.MessageType == expectedMessage.MessageType &&
                                                                    actualMessage.TargetId == expectedMessage.TargetId &&
                                                                    actualMessage.Message.Equals(expectedMessage.Message)).All(v => v);
        }
    }

    [Fact]
    public void Test_EdgeStateData_JsonRoundtrip()
    {
        Dictionary<EdgeId, PortableValue> value = TestEdgeState;
        Dictionary<EdgeId, PortableValue> result = RunJsonRoundtrip(value, TestCustomSerializedJsonOptions);

        ValidateEdgeStateData(result, value);
    }

    private static ScopeKey TestScopeKey1 => new(StringToIntId, null, "Key1");
    private static ScopeKey TestScopeKey2 => new(StringToIntId, "Shared", "Key2");
    private static ScopeKey TestScopeKey3 => new(IntToStringId, "Shared", "Key3");

    private static ChatMessage TestUserMessage => new(ChatRole.User, "Hello");

    private static Dictionary<ScopeKey, PortableValue> TestStateData
    {
        get
        {
            return new()
            {
                [TestScopeKey1] = new("Lorem Ipsum"),
                [TestScopeKey2] = new(TestUserMessage),
                [TestScopeKey3] = new(TestCustomSerializable)
            };
        }
    }

    private static void ValidateStateData(Dictionary<ScopeKey, PortableValue> result, Dictionary<ScopeKey, PortableValue> prototype)
    {
        result.Should().HaveCount(prototype.Count);

        foreach (ScopeKey key in prototype.Keys)
        {
            PortableValue state =
                result.Should().ContainKey(key)
                           .And.Subject[key].Should().Be(prototype[key])
                           .And.Subject.As<PortableValue>();
            switch (key.Key)
            {
                case "Key1":
                    state.As<string>().Should().Be("Lorem Ipsum");
                    break;
                case "Key2":
                    ChatMessage? maybeMessage = state.As<ChatMessage>();
                    maybeMessage.Should().NotBeNull()
                                     .And.Match(TestUserMessage.CreateValidatorCheckingText());
                    break;
                case "Key3":
                    state.As<TestJsonSerializable>().Should().Be(TestCustomSerializable);
                    break;
                default:
                    throw new NotImplementedException($"Missing validation for key '{key.Key}'");
            }
        }
    }

    [Fact]
    public void Test_ExecutorStateData_JsonRoundTrip()
    {
        Dictionary<ScopeKey, PortableValue> value = TestStateData;
        Dictionary<ScopeKey, PortableValue> result = RunJsonRoundtrip(value, TestCustomSerializedJsonOptions);

        ValidateStateData(result, value);
    }

    private static readonly string s_runId = Guid.NewGuid().ToString("N");
    private static readonly string s_parentCheckpointId = Guid.NewGuid().ToString("N");

    private static CheckpointInfo TestParentCheckpointInfo => new(s_runId, s_parentCheckpointId);

    [Fact]
    public async Task Test_Checkpoint_JsonRoundTripAsync()
    {
        WorkflowInfo testWorkflowInfo = await CreateTestWorkflowInfoAsync();
        Checkpoint prototype = new(12, testWorkflowInfo, TestRunnerStateData, TestStateData, TestEdgeState, TestParentCheckpointInfo);
        Checkpoint result = RunJsonRoundtrip(prototype, TestCustomSerializedJsonOptions);

        result.Should().Match((Checkpoint checkpoint) => checkpoint.StepNumber == prototype.StepNumber);

        result.Parent.Should().Be(prototype.Parent);

        ValidateWorkflowInfo(result.Workflow, prototype.Workflow);
        ValidateRunnerStateData(result.RunnerData, prototype.RunnerData);
        ValidateStateData(result.StateData, prototype.StateData);
        ValidateEdgeStateData(result.EdgeStateData, prototype.EdgeStateData);
    }
}
