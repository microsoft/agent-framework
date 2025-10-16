// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common;

/// <summary>
/// Represents a disposable that aggregates multiple disposable objects.
/// </summary>
internal sealed class CompositeDisposable : IDisposable
{
    private readonly IDisposable[] _disposables;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompositeDisposable"/> class.
    /// </summary>
    /// <param name="disposables">The disposable objects to aggregate.</param>
    public CompositeDisposable(params IDisposable?[] disposables)
    {
        this._disposables = disposables.Where(d => d != null).ToArray()!;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        foreach (var disposable in this._disposables)
        {
            disposable.Dispose();
        }
    }
}
