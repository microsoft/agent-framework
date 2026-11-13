// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Configures the <see cref="Extensions.AI.AIFunction"/> built by <see cref="JevAIToolBuilder"/> and the
/// client pipeline that sends its requests to the TypeSafe System One API.
/// </summary>
/// <remarks>
/// <para>
/// This type follows the <see cref="ClientPipelineOptions"/> pattern of the OpenAI and Azure AI client libraries:
/// <see cref="ClientPipelineOptions.Transport"/> selects the HTTP stack (for example an
/// <see cref="HttpClientPipelineTransport"/> over an <c>HttpClient</c> from <c>IHttpClientFactory</c>),
/// <see cref="ClientPipelineOptions.RetryPolicy"/> controls retries, and
/// <see cref="ClientPipelineOptions.AddPolicy(PipelinePolicy, PipelinePosition)"/> adds custom policies. The pipeline settings,
/// <see cref="Endpoint"/>, and <see cref="ModelId"/> apply only when the builder uses the TypeSafe API, that is, when
/// it receives an <see cref="ApiKeyCredential"/>; <see cref="Name"/> and <see cref="Description"/> apply to every
/// mapping.
/// </para>
/// <para>
/// Unset pipeline settings get the defaults of the official TypeSafe SDK. When
/// <see cref="ClientPipelineOptions.RetryPolicy"/> is <see langword="null"/>, up to two retries follow 408, 429, and
/// 5xx responses and network failures, waiting for the server's <c>retry-after-ms</c> or <c>Retry-After</c> delay up
/// to one minute, or else for an exponential backoff from half a second to five seconds; the policy follows
/// <see cref="ClientPipelineOptions.ClientLoggingOptions"/>. When <see cref="ClientPipelineOptions.NetworkTimeout"/>
/// is <see langword="null"/>, each attempt times out after 10 seconds.
/// </para>
/// <para>
/// Like other client options, an instance becomes read-only once a tool has been built with it.
/// </para>
/// </remarks>
public sealed class JevAIToolOptions : ClientPipelineOptions
{
    private const string DefaultDescription =
        "Answers named questions about text or structured state with Jev, a classification model. Jev does not write " +
        "text: it returns calibrated probabilities. Use it to classify, route, score, or check facts, and ask all related " +
        "questions in one call. A 'choice' question selects one of the named alternatives in its criteria. A 'score' " +
        "question assigns a score using an ordered rubric of 2 to 10 entries, and the score can fall between entries. A " +
        "'noul' question returns the probability that the answer to a yes or no question is yes. Choice and score " +
        "answers include a confidence from 0 to 1; treat a low confidence as uncertain.";

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
    /// Gets or sets the Jev model that answers the questions. Defaults to <c>jev-latest</c>.
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
    /// Gets or sets the name of the function that the model sees. Defaults to <c>ask_system_one</c>, after the SDK's
    /// <c>systemOne</c> operation.
    /// </summary>
    public string Name
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    } = "ask_system_one";

    /// <summary>
    /// Gets or sets the description of the function that the model sees.
    /// </summary>
    /// <remarks>
    /// The default description explains the Choice, Score, and Noul question kinds. A replacement should explain them
    /// too, together with when the agent should call the function.
    /// </remarks>
    public string Description
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    } = DefaultDescription;
}
