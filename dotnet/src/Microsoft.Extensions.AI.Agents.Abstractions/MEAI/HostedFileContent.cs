// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a file that is hosted by the AI service.
/// </summary>
/// <remarks>
/// Unlike <see cref="DataContent"/> which contains the data for a file or blob, this class represents a file that is hosted
/// by the AI service and referenced by an identifier. Such identifiers are specific to the provider.
/// </remarks>
[DebuggerDisplay("FileId = {FileId}")]
[ExcludeFromCodeCoverage]
public sealed class HostedFileContent : AIContent
{
    private string _fileId;

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedFileContent"/> class.
    /// </summary>
    /// <param name="fileId">The ID of the hosted file.</param>
    /// <exception cref="ArgumentNullException"><paramref name="fileId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="fileId"/> is empty or composed entirely of whitespace.</exception>
    public HostedFileContent(string fileId)
    {
        _fileId = Throw.IfNullOrWhitespace(fileId);
    }

    /// <summary>
    /// Gets or sets the ID of the hosted file.
    /// </summary>
    /// <exception cref="ArgumentNullException"><paramref name="value"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="value"/> is empty or composed entirely of whitespace.</exception>
    public string FileId
    {
        get => _fileId;
        set => _fileId = Throw.IfNullOrWhitespace(value);
    }
}
