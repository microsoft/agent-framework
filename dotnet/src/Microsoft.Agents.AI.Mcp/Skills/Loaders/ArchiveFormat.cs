// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// The archive container formats supported by <see cref="AgentMcpSkillArchiveExtractor"/>.
/// </summary>
internal enum ArchiveFormat
{
    /// <summary>The format could not be determined.</summary>
    Unknown,

    /// <summary>A ZIP archive.</summary>
    Zip,

    /// <summary>An uncompressed TAR archive.</summary>
    Tar,

    /// <summary>A gzip-compressed TAR archive (<c>.tar.gz</c>/<c>.tgz</c>).</summary>
    TarGz,
}
