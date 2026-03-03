// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using Xunit.Abstractions;

namespace ConversationDynamics.IntegrationTests;

/// <summary>
/// Abstract xunit base class for conversation dynamics integration tests.
/// </summary>
/// <remarks>
/// <para>
/// Subclasses must implement <see cref="CreateTestSystem"/> and <see cref="GetTestCases"/> to provide
/// the AI backend and the set of test cases to run. Each subclass will automatically inherit the
/// <see cref="RunAllTestCasesAsync"/> test method, which runs every case returned by
/// <see cref="GetTestCases"/> through the <see cref="ConversationHarness"/>.
/// </para>
/// <para>
/// To generate (and serialize) the initial context for a test case, the same subclass inherits
/// <see cref="SerializeAllInitialContextsAsync"/>, which should be run once outside of normal CI.
/// </para>
/// </remarks>
/// <typeparam name="TSystem">
/// The concrete <see cref="IConversationTestSystem"/> implementation that provides agent creation
/// and compaction for the system under test.
/// </typeparam>
public abstract class ConversationHarnessTests<TSystem>
    where TSystem : IConversationTestSystem
{
    private readonly ITestOutputHelper? _output;

    /// <summary>
    /// Initializes a new instance of <see cref="ConversationHarnessTests{TSystem}"/>.
    /// </summary>
    protected ConversationHarnessTests()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="ConversationHarnessTests{TSystem}"/> with xunit test output.
    /// </summary>
    /// <param name="output">The xunit test output helper used to log metrics and step results.</param>
    protected ConversationHarnessTests(ITestOutputHelper output)
    {
        this._output = output;
    }

    /// <summary>
    /// Creates the <see cref="IConversationTestSystem"/> to use for agent creation and compaction.
    /// </summary>
    protected abstract TSystem CreateTestSystem();

    /// <summary>
    /// Returns the set of <see cref="IConversationTestCase"/> instances to exercise.
    /// </summary>
    protected abstract IEnumerable<IConversationTestCase> GetTestCases();

    /// <summary>
    /// Runs all test cases returned by <see cref="GetTestCases"/> and logs the metrics report for each.
    /// </summary>
    [Fact]
    public virtual async Task RunAllTestCasesAsync()
    {
        var system = this.CreateTestSystem();
        var harness = new ConversationHarness(system);

        foreach (var testCase in this.GetTestCases())
        {
            this.Log($"[{testCase.Name}] Running...");
            var stopwatch = Stopwatch.StartNew();

            var report = await harness.RunAsync(testCase);

            stopwatch.Stop();
            this.Log($"[{testCase.Name}] Completed in {stopwatch.ElapsedMilliseconds}ms. Metrics: {report}");
        }
    }

    /// <summary>
    /// Generates and serializes the initial context for each test case returned by <see cref="GetTestCases"/>.
    /// </summary>
    /// <remarks>
    /// This test is skipped during normal test runs because generating contexts requires live AI calls and
    /// can be expensive. Run it explicitly (e.g., with <c>dotnet test --filter "FullyQualifiedName~Serialize"</c>)
    /// to regenerate the fixture files. After running, commit the generated files alongside the test code.
    /// </remarks>
    [Fact(Skip = "Run explicitly to regenerate initial context fixture files.")]
    public virtual async Task SerializeAllInitialContextsAsync()
    {
        var system = this.CreateTestSystem();
        var harness = new ConversationHarness(system);

        foreach (var testCase in this.GetTestCases())
        {
            var outputPath = GetDefaultContextFilePath(testCase);
            this.Log($"[{testCase.Name}] Serializing initial context to '{outputPath}'...");

            await harness.SerializeInitialContextAsync(testCase, outputPath);

            this.Log($"[{testCase.Name}] Context serialized successfully.");
        }
    }

    // -------------------------------------------------------------------------
    // Protected helpers for subclasses
    // -------------------------------------------------------------------------

    /// <summary>
    /// Computes the default file path used by <see cref="SerializeAllInitialContextsAsync"/> when
    /// writing the initial context for <paramref name="testCase"/>.
    /// </summary>
    /// <remarks>
    /// Override this method to change the output location. The default path is
    /// <c>{TestCase.Name}.context.json</c> relative to the current working directory.
    /// </remarks>
    /// <param name="testCase">The test case whose default output path is required.</param>
    /// <returns>The absolute or relative file path to write the serialized context to.</returns>
    protected virtual string GetDefaultContextFilePath(IConversationTestCase testCase) =>
        $"{testCase.Name}.context.json";

    /// <summary>
    /// Writes a message to the xunit test output, if available, otherwise to the console.
    /// </summary>
    protected void Log(string message)
    {
        if (this._output is not null)
        {
            this._output.WriteLine(message);
        }
        else
        {
            Console.WriteLine(message);
        }
    }
}
