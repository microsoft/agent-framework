// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using AgentConversation.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Abstractions.IntegrationTests;

/// <summary>
/// Example integration tests that exercise the <see cref="ConversationHarness"/> using an
/// in-memory <see cref="InMemoryConversationTestSystem"/> that does not require live AI credentials.
/// </summary>
/// <remarks>
/// <para>
/// This class derives from <see cref="ConversationHarnessTests{TSystem}"/> and provides the system
/// and test cases. The <see cref="ConversationHarnessTests{TSystem}.RunAllTestCasesAsync"/> test
/// method is inherited automatically and will run all cases returned by <see cref="GetTestCases"/>.
/// </para>
/// <para>
/// To adapt these tests to a real AI backend, replace <see cref="InMemoryConversationTestSystem"/>
/// with an implementation that constructs agents backed by your AI service.
/// </para>
/// </remarks>
public class AgentConversationHarnessTests(ITestOutputHelper output)
    : ConversationHarnessTests<InMemoryConversationTestSystem>(output)
{
    /// <inheritdoc />
    protected override InMemoryConversationTestSystem CreateTestSystem() =>
        new InMemoryConversationTestSystem();

    /// <inheritdoc />
    protected override IEnumerable<IConversationTestCase> GetTestCases() =>
    [
        new MenuConversationTestCase(),
    ];
}
