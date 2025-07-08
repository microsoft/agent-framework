// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class PublishMessageTests
{
    [Fact]
    public async Task Test_PublishMessage_SuccessAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterReceiverAgentAsync(topicTypes: "TestTopic");
        await fixture.RegisterReceiverAgentAsync("2", topicTypes: "TestTopic");

        await fixture.RunPublishTestAsync(new TopicId("TestTopic"), new BasicMessage { Content = "1" });

        var values = fixture.GetAgentInstances<ReceiverAgent>().Values;
        Assert.Equal(2, values.Count);
        Assert.All(values, receiverAgent =>
        {
            Assert.NotNull(receiverAgent.Messages);
            Assert.Single(receiverAgent.Messages);
            Assert.Contains(receiverAgent.Messages, m => m.Content == "1");
        });
    }

    [Fact]
    public async Task Test_PublishMessage_SingleFailureAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterErrorAgentAsync(topicTypes: "TestTopic");

        // Test that we wrap single errors appropriately
        var e = await Assert.ThrowsAsync<AggregateException>(async () => await fixture.RunPublishTestAsync(new TopicId("TestTopic"), new BasicMessage { Content = "1" }));
        Assert.IsType<TestException>(Assert.Single(e.InnerExceptions));

        var values = fixture.GetAgentInstances<ReceiverAgent>().Values;
    }

    [Fact]
    public async Task Test_PublishMessage_MultipleFailuresAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterErrorAgentAsync(topicTypes: "TestTopic");
        await fixture.RegisterErrorAgentAsync("2", topicTypes: "TestTopic");

        // What we are really testing here is that a single exception does not prevent sending to the remaining agents
        var e = await Assert.ThrowsAsync<AggregateException>(async () => await fixture.RunPublishTestAsync(new TopicId("TestTopic"), new BasicMessage { Content = "1" }));
        Assert.Equal(2, e.InnerExceptions.Count);
        Assert.All(e.InnerExceptions, innerException => Assert.IsType<TestException>(innerException));

        var values = fixture.GetAgentInstances<ErrorAgent>().Values;
        Assert.Equal(2, values.Count);
    }

    [Fact]
    public async Task Test_PublishMessage_MixedSuccessFailureAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterReceiverAgentAsync(topicTypes: "TestTopic");
        await fixture.RegisterReceiverAgentAsync("2", topicTypes: "TestTopic");

        await fixture.RegisterErrorAgentAsync(topicTypes: "TestTopic");
        await fixture.RegisterErrorAgentAsync("2", topicTypes: "TestTopic");

        // What we are really testing here is that raising exceptions does not prevent sending to the remaining agents
        var e = await Assert.ThrowsAsync<AggregateException>(async () => await fixture.RunPublishTestAsync(new TopicId("TestTopic"), new BasicMessage { Content = "1" }));
        Assert.Equal(2, e.InnerExceptions.Count);
        Assert.All(e.InnerExceptions, innerException => Assert.IsType<TestException>(innerException));

        var agents = fixture.GetAgentInstances<ReceiverAgent>().Values;
        Assert.Equal(2, agents.Count);
        Assert.All(agents, receiverAgent =>
        {
            Assert.NotNull(receiverAgent.Messages);
            Assert.Single(receiverAgent.Messages);
            Assert.Contains(receiverAgent.Messages, m => m.Content == "1");
        });

        var errors = fixture.GetAgentInstances<ErrorAgent>().Values;
        Assert.Equal(2, errors.Count);
    }

    [Fact]
    public async Task Test_PublishMessage_RecurrentPublishSucceedsAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterFactoryMapInstances(
            nameof(PublisherAgent),
            (id, runtime) => new ValueTask<PublisherAgent>(new PublisherAgent(id, runtime, string.Empty, [new TopicId("TestTopic")])));

        await fixture.Runtime.AddSubscriptionAsync(new TestSubscription("RunTest", nameof(PublisherAgent)));

        await fixture.RegisterReceiverAgentAsync(topicTypes: "TestTopic");
        await fixture.RegisterReceiverAgentAsync("2", topicTypes: "TestTopic");

        await fixture.RunPublishTestAsync(new TopicId("RunTest"), new BasicMessage { Content = "1" });

        TopicId testTopicId = new("TestTopic");
        var values = fixture.GetAgentInstances<ReceiverAgent>().Values;
        Assert.Equal(2, values.Count);
        Assert.All(values, receiver =>
        {
            Assert.NotNull(receiver.Messages);
            Assert.Single(receiver.Messages);
            Assert.Contains(receiver.Messages, m => m.Content == $"@{testTopicId}: 1");
        });
    }
}
