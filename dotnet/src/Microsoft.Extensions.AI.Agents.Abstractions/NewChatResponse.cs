// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Contains new properties that will be added to <see cref="ChatResponse"/> in the future.
/// </summary>
/// <remarks>
/// This class contains temporary properties that are not part of the <see cref="ChatOptions"/> class yet.
/// Later, these properties will be moved to the official <see cref="ChatResponse"/> class, and
/// this class will be removed. Therefore, please expect a breaking change if you are using
/// this class directly in your code.
/// </remarks>
public class NewChatResponse : ChatResponse
{
    /// <summary>
    /// Continuation token to continue the operation that generated this response.
    /// </summary>
    public string? ContinuationToken { get; set; }
}
