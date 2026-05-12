// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Abstract base class for console observers that participate in the agent response
/// streaming lifecycle. Observers can configure run options, observe streamed content,
/// and return messages to re-invoke the agent after the stream completes.
/// All methods have default no-op implementations so subclasses only override what they need.
/// </summary>
public abstract class ConsoleObserver
{
    /// <summary>
    /// Configures <see cref="AgentRunOptions"/> before the agent is invoked.
    /// Override to set options such as <see cref="AgentRunOptions.ResponseFormat"/>.
    /// </summary>
    /// <param name="options">The run options to configure.</param>
    public virtual void ConfigureRunOptions(AgentRunOptions options)
    {
    }

    /// <summary>
    /// Called for each <see cref="AIContent"/> item in the response stream.
    /// </summary>
    /// <param name="ux">The harness UX container, used for rendering output and interacting with the user.</param>
    /// <param name="content">The content item from the stream.</param>
    public virtual Task OnContentAsync(HarnessUXContainer ux, AIContent content) => Task.CompletedTask;

    /// <summary>
    /// Called for each text update in the response stream.
    /// </summary>
    /// <param name="ux">The harness UX container, used for rendering output and interacting with the user.</param>
    /// <param name="text">The text from the update.</param>
    public virtual Task OnTextAsync(HarnessUXContainer ux, string text) => Task.CompletedTask;

    /// <summary>
    /// Called after the response stream completes. Returns messages to include in the
    /// next agent invocation, or <see langword="null"/> if no re-invocation is needed.
    /// </summary>
    /// <param name="ux">The harness UX container, used for rendering output and interacting with the user.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    /// <param name="options">The console options.</param>
    /// <returns>Messages to send to the agent, or <see langword="null"/> if no action is needed.</returns>
    public virtual Task<IList<ChatMessage>?> OnStreamCompleteAsync(
        HarnessUXContainer ux,
        AIAgent agent,
        AgentSession session,
        HarnessConsoleOptions options) => Task.FromResult<IList<ChatMessage>?>(null);
}
