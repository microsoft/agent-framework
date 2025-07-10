// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public sealed class BasicMessage
{
    public string Content { get; set; } = string.Empty;
}

#pragma warning disable RCS1194 // Implement exception constructors
public sealed class TestException : Exception;
#pragma warning restore RCS1194 // Implement exception constructors

public sealed class PublisherAgent : TestAgent
{
    public PublisherAgent(ActorId id, IAgentRuntime runtime, string description, IList<TopicId> targetTopics) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage>(async (item, messageContext, cancellationToken) =>
        {
            this.ReceivedMessages.Add(item);
            foreach (TopicId targetTopic in targetTopics)
            {
                await this.PublishMessageAsync(
                    new BasicMessage { Content = $"@{targetTopic}: {item.Content}" },
                    targetTopic,
                    cancellationToken: cancellationToken);
            }
        });
    }
}

public sealed class SendOnAgent : TestAgent
{
    public SendOnAgent(ActorId id, IAgentRuntime runtime, string description, IList<Guid> targetKeys) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage>(async (item, messageContext, cancellationToken) =>
        {
            foreach (Guid targetKey in targetKeys)
            {
                ActorId targetId = new(nameof(ReceiverAgent), targetKey.ToString());
                BasicMessage response = new() { Content = $"@{targetKey}: {item.Content}" };
                await this.SendMessageAsync(response, targetId, cancellationToken: cancellationToken);
            }
        });
    }
}

public sealed class ReceiverAgent : TestAgent
{
    public List<BasicMessage> Messages { get; } = [];

    public ReceiverAgent(ActorId id, IAgentRuntime runtime, string description) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage>(async (item, messageContext, cancellationToken) =>
        {
            this.Messages.Add(item);
        });
    }
}

public sealed class ProcessorAgent : TestAgent
{
    public ProcessorAgent(ActorId id, IAgentRuntime runtime, Func<string, string> processFunc, string description) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage, BasicMessage>(async (item, messageContext, cancellationtoken) =>
        {
            return new BasicMessage() { Content = processFunc.Invoke(((BasicMessage)item).Content) };
        });
    }
}

public sealed class CancelAgent : TestAgent
{
    public CancelAgent(ActorId id, IAgentRuntime runtime, string description) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage>(async (item, messageContext, cancellationToken) =>
        {
            CancellationToken cancelledToken = new(canceled: true);
            cancelledToken.ThrowIfCancellationRequested();
        });
    }
}

public sealed class ErrorAgent : TestAgent
{
    public ErrorAgent(ActorId id, IAgentRuntime runtime, string description) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<BasicMessage>(async (item, messageContext, cancellationToken) =>
        {
            this.DidThrow = true;
            throw new TestException();
        });
    }
    public bool DidThrow { get; private set; }
}

public sealed class MessagingTestFixture
{
    private Dictionary<Type, object> AgentsTypeMap { get; } = [];
    public InProcessRuntime Runtime { get; } = new();

    public ValueTask<ActorType> RegisterFactoryMapInstances<TAgent>(ActorType type, Func<ActorId, IAgentRuntime, ValueTask<TAgent>> factory)
        where TAgent : IRuntimeActor
    {
        async ValueTask<TAgent> WrappedFactory(ActorId id, IAgentRuntime runtime)
        {
            TAgent agent = await factory(id, runtime);
            this.GetAgentInstances<TAgent>()[id] = agent;
            return agent;
        }

        return this.Runtime.RegisterActorFactoryAsync(type, WrappedFactory);
    }

    public Dictionary<ActorId, TAgent> GetAgentInstances<TAgent>() where TAgent : IRuntimeActor
    {
        if (!this.AgentsTypeMap.TryGetValue(typeof(TAgent), out object? maybeAgentMap) ||
            maybeAgentMap is not Dictionary<ActorId, TAgent> result)
        {
            this.AgentsTypeMap[typeof(TAgent)] = result = [];
        }

        return result;
    }
    public async ValueTask RegisterReceiverAgentAsync(string? agentNameSuffix = null, params string[] topicTypes)
    {
        await this.RegisterFactoryMapInstances(
            new($"{nameof(ReceiverAgent)}{agentNameSuffix ?? string.Empty}"),
            (id, runtime) => new ValueTask<ReceiverAgent>(new ReceiverAgent(id, runtime, string.Empty)));

        foreach (string topicType in topicTypes)
        {
            await this.Runtime.AddSubscriptionAsync(new TestSubscription(topicType, new($"{nameof(ReceiverAgent)}{agentNameSuffix ?? string.Empty}")));
        }
    }

    public async ValueTask RegisterErrorAgentAsync(string? agentNameSuffix = null, params string[] topicTypes)
    {
        await this.RegisterFactoryMapInstances(
            new($"{nameof(ErrorAgent)}{agentNameSuffix ?? string.Empty}"),
            (id, runtime) => new ValueTask<ErrorAgent>(new ErrorAgent(id, runtime, string.Empty)));

        foreach (string topicType in topicTypes)
        {
            await this.Runtime.AddSubscriptionAsync(new TestSubscription(topicType, new($"{nameof(ErrorAgent)}{agentNameSuffix ?? string.Empty}")));
        }
    }

    public async ValueTask RunPublishTestAsync(TopicId sendTarget, object message, string? messageId = null)
    {
        messageId ??= Guid.NewGuid().ToString();

        await this.Runtime.StartAsync();
        await this.Runtime.PublishMessageAsync(message, sendTarget, messageId: messageId);
        await this.Runtime.RunUntilIdleAsync();
    }

    public async ValueTask<object?> RunSendTestAsync(ActorId sendTarget, object message, string? messageId = null)
    {
        messageId ??= Guid.NewGuid().ToString();

        await this.Runtime.StartAsync();

        object? result = await this.Runtime.SendMessageAsync(message, sendTarget, messageId: messageId);

        await this.Runtime.RunUntilIdleAsync();

        return result;
    }
}
