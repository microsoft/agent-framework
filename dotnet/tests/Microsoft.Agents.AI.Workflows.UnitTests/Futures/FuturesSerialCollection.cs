// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Futures;

/// <summary>
/// xUnit collection marker for tests that mutate the process-global
/// <see cref="Workflows.Futures"/> switches. Membership in this collection serializes
/// the tests against each other so that <see cref="FuturesScope"/> cannot leak state
/// into a concurrently running test.
/// </summary>
[CollectionDefinition(Name, DisableParallelization = true)]
[SuppressMessage("Naming", "CA1711:Identifiers should not have incorrect suffix",
    Justification = "xUnit's [CollectionDefinition] pattern names the marker type after the collection's purpose; the 'Collection' suffix is idiomatic.")]
public sealed class FuturesSerialCollection
{
    public const string Name = "FuturesSerial";
}
