// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal sealed class ExecutorAgentHarness(AIAgent agent, AIAgentUnservicedRequestsCollector collector)
{
    internal const string AgentSessionKey = nameof(AgentSession);
    private AgentSession? _session;

    private async ValueTask<AgentSession> EnsureSessionAsync(IWorkflowContext context, CancellationToken cancellationToken) =>
        this._session ??= await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

    public async ValueTask<AgentResponse> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, bool emitUpdateEvents, CancellationToken cancellationToken = default)
    {
        AgentResponse response;

        if (emitUpdateEvents)
        {
            // Run the agent in streaming mode only when agent run update events are to be emitted.
            IAsyncEnumerable<AgentResponseUpdate> agentStream = agent.RunStreamingAsync(
                messages,
                await this.EnsureSessionAsync(context, cancellationToken).ConfigureAwait(false),
                cancellationToken: cancellationToken);

            List<AgentResponseUpdate> updates = [];
            await foreach (AgentResponseUpdate update in agentStream.ConfigureAwait(false))
            {
                await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
                collector.ProcessAgentResponseUpdate(update);
                updates.Add(update);
            }

            response = updates.ToAgentResponse();
        }
        else
        {
            // Otherwise, run the agent in non-streaming mode.
            response = await agent.RunAsync(messages,
                                                  await this.EnsureSessionAsync(context, cancellationToken).ConfigureAwait(false),
                                                  cancellationToken: cancellationToken)
                                        .ConfigureAwait(false);

            collector.ProcessAgentResponse(response);
        }

        return response;
    }

    public async ValueTask<JsonElement?> SerializeSessionAsync(CancellationToken cancellationToken)
        => this._session == null
         ? null
         : await agent.SerializeSessionAsync(this._session, cancellationToken: cancellationToken).ConfigureAwait(false);

    public async ValueTask DeserializeSessionAsync(JsonElement? serializedSession, CancellationToken cancellationToken)
    {
        this._session = serializedSession == null
                      ? null
                      : await agent.DeserializeSessionAsync(serializedSession.Value, cancellationToken: cancellationToken)
                                   .ConfigureAwait(false);
    }

    public void ResetSession()
    {
        this._session = null;
    }
}
