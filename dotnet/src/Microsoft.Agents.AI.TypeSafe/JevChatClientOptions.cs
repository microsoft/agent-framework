// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Configures a <see cref="JevChatClient"/> and the client pipeline that sends its requests to the TypeSafe System
/// One API.
/// </summary>
/// <remarks>
/// <para>
/// This type follows the <see cref="ClientPipelineOptions"/> pattern of the OpenAI and Azure AI client libraries:
/// <see cref="ClientPipelineOptions.Transport"/> selects the HTTP stack, <see cref="ClientPipelineOptions.RetryPolicy"/>
/// controls retries, and <see cref="ClientPipelineOptions.AddPolicy(PipelinePolicy, PipelinePosition)"/> adds custom
/// policies. Unset pipeline settings get the defaults of the official TypeSafe SDK, as described for
/// <see cref="JevAIToolOptions"/>. <see cref="ClientPipelineOptions.ClientLoggingOptions"/> also supplies the logger
/// that reports tools left out of a request.
/// </para>
/// <para>
/// Like other client options, an instance becomes read-only once a client has been created with it.
/// </para>
/// </remarks>
public sealed class JevChatClientOptions : ClientPipelineOptions
{
    /// <inheritdoc />
    public override void Freeze()
    {
        JevPipelineDefaults.Apply(this);
        base.Freeze();
    }

    /// <summary>
    /// Gets or sets the System One endpoint. When <see langword="null"/>, <c>https://api.typesafe.ai/v1/systemone</c> is used.
    /// </summary>
    public Uri? Endpoint
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    }

    /// <summary>
    /// Gets or sets the Jev model that answers the questions, unless <see cref="Extensions.AI.ChatOptions.ModelId"/>
    /// selects another for a request. Defaults to <c>jev-latest</c>.
    /// </summary>
    public string ModelId
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    } = JevPipelineDefaults.DefaultModelId;

    /// <summary>
    /// Gets or sets the questions to answer when a request does not pass its own with
    /// <see cref="JevChatOptionsExtensions.WithJevQuestions"/>.
    /// </summary>
    /// <remarks>
    /// Default questions let code that knows nothing about Jev, such as a framework component with a fixed task,
    /// use the client as any other <see cref="Extensions.AI.IChatClient"/>. The client copies the dictionary when it
    /// is created.
    /// </remarks>
    public IReadOnlyDictionary<string, JevQuestion>? DefaultQuestions
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    }

    /// <summary>
    /// Gets or sets how many tool calls Jev may request in one turn, that is, while answering one user request.
    /// Defaults to 1.
    /// </summary>
    /// <remarks>
    /// The turn starts after the last user message, except that text sent together with a tool approval response
    /// continues the turn of the call it approves. Once the turn has this many function calls, the client stops
    /// offering tools and answers the questions, with the tool results in the state. The route question tells Jev
    /// which calls the turn already made, but a closed-set choice can still repeat one, so the limit is what
    /// guarantees that the tool loop ends. Raise it when one user request needs several distinct calls, such as the
    /// weather in two cities; set it to 0 to never call tools.
    /// </remarks>
    /// <exception cref="ArgumentOutOfRangeException">The value is negative.</exception>
    public int MaximumToolCallsPerTurn
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = Throw.IfLessThan(value, 0);
        }
    } = 1;
}
