// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration.Transforms;

/// <summary>
/// Delegate for transforming an input of type <typeparamref name="TInput"/> into a collection of <see cref="ChatMessage"/>.
/// This is typically used to convert user or system input into a format suitable for chat orchestration.
/// </summary>
/// <param name="input">The input object to transform.</param>
/// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
/// <returns>A <see cref="ValueTask{TResult}"/> containing an enumerable of <see cref="ChatMessage"/> representing the transformed input.</returns>
public delegate ValueTask<IEnumerable<ChatMessage>> OrchestrationInputTransform<TInput>(TInput input, CancellationToken cancellationToken = default);

/// <summary>
/// Delegate for transforming a <see cref="ChatMessage"/> into an output of type <typeparamref name="TOutput"/>.
/// This is typically used to convert a chat response into a desired output format.
/// </summary>
/// <param name="result">The result messages to transform.</param>
/// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
/// <returns>A <see cref="ValueTask{TResult}"/> containing the transformed output of type <typeparamref name="TOutput"/>.</returns>
public delegate ValueTask<TOutput> OrchestrationOutputTransform<TOutput>(IList<ChatMessage> result, CancellationToken cancellationToken = default);

/// <summary>
/// Delegate for transforming the internal result message for an orchestration into a <see cref="ChatMessage"/>.
/// </summary>
/// <typeparam name="TResult">The result message type</typeparam>
/// <param name="result">The result messages</param>
/// <returns>The orchestration result as a <see cref="ChatMessage"/>.</returns>
public delegate IList<ChatMessage> OrchestrationResultTransform<TResult>(TResult result);
