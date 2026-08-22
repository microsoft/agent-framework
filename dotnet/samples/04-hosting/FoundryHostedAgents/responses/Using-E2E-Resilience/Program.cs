// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using Azure.AI.Projects;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

const string AgentName = "hosted-workflow-resilient-long-running";
VerificationOptions options = VerificationOptions.Parse(args);
string repositoryRoot = FindRepositoryRoot();
string serverProject = Path.Combine(
    repositoryRoot,
    "dotnet",
    "samples",
    "04-hosting",
    "FoundryHostedAgents",
    "responses",
    "Hosted-Workflow-Resilient-Long-Running",
    "HostedWorkflowResilientLongRunning.csproj");
string workingRoot = Path.Combine(
    Path.GetTempPath(),
    $"maf-resilient-workflow-{Guid.NewGuid():N}");
string serverOutput = Path.Combine(workingRoot, "server");
string serverAssembly = Path.Combine(
    serverOutput,
    "HostedWorkflowResilientLongRunning.dll");
string stateRoot = Path.Combine(workingRoot, "state");
string logPath = Path.Combine(
    Path.GetTempPath(),
    $"maf-resilient-workflow-{Guid.NewGuid():N}.log");
int port = GetAvailablePort();
var baseAddress = new Uri($"http://127.0.0.1:{port}");
bool succeeded = false;

Directory.CreateDirectory(workingRoot);

var cancellationSource = new CancellationTokenSource(TimeSpan.FromMinutes(3));
var client = new HttpClient
{
    BaseAddress = baseAddress,
    Timeout = Timeout.InfiniteTimeSpan,
};
await using var logWriter = new StreamWriter(logPath, append: false, new UTF8Encoding(false))
{
    AutoFlush = true,
};
ServerProcess? server = null;
Task? createStream = null;
AgentStreamObserver? streamObserver = null;
LocalAgentClient? localAgentClient = null;
CancellationTokenSource? initialStreamCancellation = null;
try
{
    PrintHeader(options, stateRoot, logPath);

    Console.WriteLine("Preparing isolated Debug server binaries...");
    await BuildServerAsync(
        serverProject,
        serverOutput,
        logWriter,
        cancellationSource.Token);
    Console.WriteLine("      server build complete");
    Console.WriteLine();

    Console.WriteLine("[1/7] Starting the first server process...");
    Console.WriteLine($"      endpoint: {baseAddress}");
    server = StartServer(
        serverAssembly,
        stateRoot,
        port,
        options.DelaySeconds,
        logWriter);
    Console.WriteLine($"      process tree root: {server.Id}");
    await WaitForReadinessAsync(client, cancellationSource.Token);
    Console.WriteLine("      server ready");
    Console.WriteLine();

    localAgentClient = CreateClientAgent(baseAddress, AgentName);
    AIAgent agent = localAgentClient.Agent;
    AgentSession session = await agent.CreateSessionAsync(cancellationSource.Token);
    AgentRunOptions runOptions = new() { AllowBackgroundResponses = true };

    Console.WriteLine("[2/7] Starting the background countdown...");
    streamObserver = new AgentStreamObserver(options.CrashAfterCount);
    initialStreamCancellation =
        CancellationTokenSource.CreateLinkedTokenSource(cancellationSource.Token);
#pragma warning disable CA2025 // The stream must run concurrently until the server is killed; finally awaits it before disposing resources.
    createStream = WatchInitialAgentStreamAsync(
        agent,
        session,
        runOptions,
        options.Target,
        streamObserver,
        initialStreamCancellation.Token);
#pragma warning restore CA2025

    string responseId = await WaitForResponseIdAsync(
        streamObserver,
        createStream,
        cancellationSource.Token);
    Console.WriteLine($"      response id: {responseId}");
    Console.WriteLine();

    Console.WriteLine(
        $"[3/7] Waiting for {options.CrashAfterCount} countdown items and their response checkpoint...");
    await streamObserver.CrashPointReached.Task.WaitAsync(cancellationSource.Token);
    await WaitForPersistedResponseCheckpointAsync(
        stateRoot,
        responseId,
        streamObserver.CompletedTexts,
        cancellationSource.Token);
    Console.WriteLine("      checkpoint persisted");
    Console.WriteLine();

    Console.WriteLine("[4/7] Force-killing the first server process...");
    initialStreamCancellation.Cancel();
    await IgnoreExpectedDisconnectAsync(createStream);
    createStream = null;
    initialStreamCancellation.Dispose();
    initialStreamCancellation = null;
    await server.KillAsync();
    server = null;
    DeleteStaleStreamLocks(stateRoot);
    Console.WriteLine("      process terminated");
    Console.WriteLine();

    Console.WriteLine("[5/7] Starting a replacement server over the same durable state...");
    server = StartServer(
        serverAssembly,
        stateRoot,
        port,
        options.DelaySeconds,
        logWriter);
    Console.WriteLine($"      process tree root: {server.Id}");
    await WaitForReadinessAsync(client, cancellationSource.Token);
    Console.WriteLine("      recovery scan completed");
    Console.WriteLine();
    Console.WriteLine("[6/7] Reconnecting with the sequence-aware continuation token...");
    streamObserver.BeginRecovery();
    runOptions.ContinuationToken = streamObserver.ContinuationToken
        ?? throw new InvalidOperationException(
            "The initial stream did not provide a continuation token.");
    await WatchRecoveredAgentStreamAsync(
        agent,
        session,
        runOptions,
        streamObserver,
        cancellationSource.Token);

    List<string> actual = streamObserver.CompletedTexts;
    List<string> expected =
    [
        .. Enumerable.Range(1, options.Target)
            .Reverse()
            .Select(value => value.ToString(CultureInfo.InvariantCulture)),
        "Countdown complete.",
    ];

    if (!streamObserver.ResponseCompleted)
    {
        throw new InvalidOperationException(
            "The recovered stream ended without response.completed.");
    }

    if (!actual.SequenceEqual(expected))
    {
        throw new InvalidOperationException(
            "Recovered output did not match the expected countdown." +
            $"{Environment.NewLine}Expected: {string.Join(", ", expected)}" +
            $"{Environment.NewLine}Actual:   {string.Join(", ", actual)}");
    }

    Console.WriteLine();
    Console.WriteLine("[7/7] Replaying from the start without a sequence cursor...");
    AgentRunOptions replayOptions = new()
    {
        AllowBackgroundResponses = true,
        ContinuationToken = CreateReplayFromStartToken(responseId),
    };
    var replayObserver = new AgentStreamObserver(int.MaxValue);
    await WatchReplayedAgentStreamAsync(
        agent,
        session,
        replayOptions,
        replayObserver,
        cancellationSource.Token);
    if (!replayObserver.ResponseCompleted
        || !replayObserver.CompletedTexts.SequenceEqual(expected))
    {
        throw new InvalidOperationException(
            "The cursor-free replay did not return the complete countdown.");
    }
    int retainedCountdownUpdates =
        actual.Count(text => text != "Countdown complete.");
    int replayedCountdownUpdates =
        replayObserver.CompletedTexts.Count(
            text => text != "Countdown complete.");
    Console.WriteLine();
    Console.WriteLine(
        $"Client retained countdown updates: {retainedCountdownUpdates}");
    Console.WriteLine(
        $"Replay countdown updates:          {replayedCountdownUpdates}");

    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine(
        "PASS: crash recovery completed with ordered output and no missing or duplicated items.");
    Console.ResetColor();
    succeeded = true;
}
catch (Exception exception)
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine($"FAIL: {exception.Message}");
    Console.ResetColor();
    Console.Error.WriteLine($"Server log: {logPath}");
    System.Environment.ExitCode = 1;
}
finally
{
    if (server is not null)
    {
        await server.KillAsync();
    }

    if (createStream is not null)
    {
        initialStreamCancellation?.Cancel();
        await IgnoreExpectedDisconnectAsync(createStream);
    }

    initialStreamCancellation?.Dispose();
    client.Dispose();
    localAgentClient?.Dispose();
    cancellationSource.Dispose();

    if (succeeded)
    {
        TryDeleteDirectory(workingRoot);
    }
    else
    {
        Console.Error.WriteLine($"E2E working directory retained at: {workingRoot}");
    }
}

static void PrintHeader(
    VerificationOptions options,
    string stateRoot,
    string logPath)
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine("============================================================");
    Console.WriteLine("Resilient long-running workflow E2E demonstration");
    Console.WriteLine("============================================================");
    Console.ResetColor();
    Console.WriteLine($"Countdown target: {options.Target}");
    Console.WriteLine($"Crash after:      {options.CrashAfterCount} message items");
    Console.WriteLine($"Step delay:       {options.DelaySeconds} second(s)");
    Console.WriteLine($"Durable state:    {stateRoot}");
    Console.WriteLine($"Server log:       {logPath}");
    Console.WriteLine();
}

static ServerProcess StartServer(
    string serverAssembly,
    string stateRoot,
    int port,
    int delaySeconds,
    TextWriter logWriter)
{
    var startInfo = new ProcessStartInfo
    {
        FileName = "dotnet",
        WorkingDirectory = Path.GetDirectoryName(serverAssembly)!,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
        CreateNoWindow = true,
    };
    startInfo.ArgumentList.Add("exec");
    startInfo.ArgumentList.Add(serverAssembly);
    startInfo.Environment["AGENTSERVER_STATE_ROOT"] = stateRoot;
    startInfo.Environment["FOUNDRY_AGENT_SESSION_ID"] = "using-e2e-resilience";
    startInfo.Environment["AGENT_NAME"] = AgentName;
    startInfo.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
    startInfo.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
    startInfo.Environment["COUNTDOWN_DELAY_SECONDS"] =
        delaySeconds.ToString(CultureInfo.InvariantCulture);
    startInfo.Environment["DOTNET_NOLOGO"] = "true";
    startInfo.Environment.Remove("FOUNDRY_HOSTING_ENVIRONMENT");

    return ServerProcess.Start(startInfo, logWriter);
}

static LocalAgentClient CreateClientAgent(Uri baseAddress, string agentName)
{
    Uri httpsProjectEndpoint = new UriBuilder(baseAddress)
    {
        Scheme = Uri.UriSchemeHttps,
        Port = baseAddress.Port,
    }.Uri;

    var transportClient = new HttpClient(
        new LocalHttpSchemeRewriteHandler(baseAddress));
    var clientOptions = new AIProjectClientOptions
    {
        Transport = new HttpClientPipelineTransport(transportClient),
    };

    AIAgent agent = new AIProjectClient(
        httpsProjectEndpoint,
        new LocalDevelopmentTokenCredential(),
        clientOptions)
        .AsAIAgent(
            model: agentName,
            instructions: "Invoke the local hosted countdown workflow.");
    return new LocalAgentClient(agent, transportClient);
}

static ResponseContinuationToken CreateReplayFromStartToken(
    string responseId)
{
    ResponseContinuationToken innerToken =
        ResponseContinuationToken.FromBytes(
            JsonSerializer.SerializeToUtf8Bytes(
                new { responseId }));
    string serializedInnerToken = JsonSerializer.Serialize(
        innerToken,
        AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(
            typeof(ResponseContinuationToken)));
    byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(
        new
        {
            type = "chatClientAgentContinuationToken",
            innerToken = serializedInnerToken,
        });
    return ResponseContinuationToken.FromBytes(bytes);
}

static async Task BuildServerAsync(
    string serverProject,
    string serverOutput,
    TextWriter logWriter,
    CancellationToken cancellationToken)
{
    var startInfo = new ProcessStartInfo
    {
        FileName = "dotnet",
        WorkingDirectory = Path.GetDirectoryName(serverProject)!,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
        CreateNoWindow = true,
    };
    startInfo.ArgumentList.Add("build");
    startInfo.ArgumentList.Add(serverProject);
    startInfo.ArgumentList.Add("--configuration");
    startInfo.ArgumentList.Add("Debug");
    startInfo.ArgumentList.Add("--output");
    startInfo.ArgumentList.Add(serverOutput);
    startInfo.ArgumentList.Add("--tl:off");
    startInfo.Environment["DOTNET_NOLOGO"] = "true";

    using Process process = Process.Start(startInfo)
        ?? throw new InvalidOperationException("Could not start the server build.");
    TextWriter synchronizedLogWriter = TextWriter.Synchronized(logWriter);
    process.OutputDataReceived += (_, eventArgs) =>
    {
        if (eventArgs.Data is not null)
        {
            synchronizedLogWriter.WriteLine($"[build stdout] {eventArgs.Data}");
        }
    };
    process.ErrorDataReceived += (_, eventArgs) =>
    {
        if (eventArgs.Data is not null)
        {
            synchronizedLogWriter.WriteLine($"[build stderr] {eventArgs.Data}");
        }
    };
    process.BeginOutputReadLine();
    process.BeginErrorReadLine();

    await process.WaitForExitAsync(cancellationToken);
    process.WaitForExit();
    if (process.ExitCode != 0)
    {
        throw new InvalidOperationException(
            $"Server build failed with exit code {process.ExitCode}.");
    }
}

static async Task WaitForReadinessAsync(
    HttpClient client,
    CancellationToken cancellationToken)
{
    var deadline = DateTimeOffset.UtcNow + TimeSpan.FromSeconds(30);
    while (DateTimeOffset.UtcNow < deadline)
    {
        try
        {
            using var requestCancellation =
                CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            requestCancellation.CancelAfter(TimeSpan.FromSeconds(2));
            using HttpResponseMessage response = await client.GetAsync(
                new Uri("readiness", UriKind.Relative),
                requestCancellation.Token);
            if (response.StatusCode == HttpStatusCode.OK)
            {
                return;
            }
        }
        catch (Exception exception)
            when (exception is HttpRequestException or TaskCanceledException)
        {
        }

        await Task.Delay(TimeSpan.FromMilliseconds(250), cancellationToken);
    }

    throw new TimeoutException("Server did not become ready within 30 seconds.");
}

static async Task WatchInitialAgentStreamAsync(
    AIAgent agent,
    AgentSession session,
    AgentRunOptions options,
    int target,
    AgentStreamObserver observer,
    CancellationToken cancellationToken)
{
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
        $"Count down from {target}",
        session,
        options,
        cancellationToken))
    {
        observer.ObserveInitial(update);
    }
}

static async Task WatchRecoveredAgentStreamAsync(
    AIAgent agent,
    AgentSession session,
    AgentRunOptions options,
    AgentStreamObserver observer,
    CancellationToken cancellationToken)
{
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
        session,
        options,
        cancellationToken))
    {
        observer.ObserveRecovered(update);
    }
}

static async Task WatchReplayedAgentStreamAsync(
    AIAgent agent,
    AgentSession session,
    AgentRunOptions options,
    AgentStreamObserver observer,
    CancellationToken cancellationToken)
{
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
        session,
        options,
        cancellationToken))
    {
        observer.ObserveReplayed(update);
    }
}

static async Task<string> WaitForResponseIdAsync(
    AgentStreamObserver observer,
    Task createStream,
    CancellationToken cancellationToken)
{
    Task completed = await Task.WhenAny(
        observer.ResponseId.Task,
        createStream,
        Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken));
    if (completed == createStream)
    {
        await createStream;
        throw new InvalidOperationException(
            "The initial stream ended before returning a response ID.");
    }

    cancellationToken.ThrowIfCancellationRequested();
    return await observer.ResponseId.Task;
}

static async Task WaitForPersistedResponseCheckpointAsync(
    string stateRoot,
    string responseId,
    IReadOnlyList<string> expectedPrefix,
    CancellationToken cancellationToken)
{
    string path = Path.Combine(
        stateRoot,
        "responses",
        "envelopes",
        $"{responseId}.json");
    var deadline = DateTimeOffset.UtcNow + TimeSpan.FromSeconds(15);
    while (DateTimeOffset.UtcNow < deadline)
    {
        try
        {
            using FileStream file = new(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            using JsonDocument document = await JsonDocument.ParseAsync(
                file,
                cancellationToken: cancellationToken);
            JsonElement response =
                document.RootElement.GetProperty("envelope");
            List<string> persistedTexts = GetPersistedMessageTexts(response);
            bool hasCheckpointMetadata =
                response.TryGetProperty("metadata", out JsonElement metadata)
                && metadata.TryGetProperty("_internal_metadata", out JsonElement internalMetadata)
                && !string.IsNullOrWhiteSpace(internalMetadata.GetString());
            if (hasCheckpointMetadata
                && persistedTexts.Count >= expectedPrefix.Count
                && persistedTexts
                    .Take(expectedPrefix.Count)
                    .SequenceEqual(expectedPrefix))
            {
                return;
            }
        }
        catch (Exception exception)
            when (exception is IOException
                or JsonException
                or KeyNotFoundException)
        {
        }

        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);
    }

    throw new TimeoutException(
        "The response checkpoint was not persisted within 15 seconds.");
}

static List<string> GetPersistedMessageTexts(JsonElement response)
{
    List<string> texts = [];
    foreach (JsonElement item in response.GetProperty("output").EnumerateArray())
    {
        if (item.GetProperty("type").GetString() != "message")
        {
            continue;
        }

        foreach (JsonElement content in item.GetProperty("content").EnumerateArray())
        {
            if (content.GetProperty("type").GetString() == "output_text")
            {
                texts.Add(content.GetProperty("text").GetString() ?? string.Empty);
            }
        }
    }

    return texts;
}

static async Task IgnoreExpectedDisconnectAsync(Task streamTask)
{
    try
    {
        await streamTask;
    }
    catch (Exception exception)
        when (IsExpectedDisconnect(exception))
    {
    }

    static bool IsExpectedDisconnect(Exception exception)
    {
        if (exception is AggregateException aggregate)
        {
            return aggregate
                .Flatten()
                .InnerExceptions
                .All(IsExpectedDisconnect);
        }

        return exception is ClientResultException
            or HttpRequestException
            or IOException
            or OperationCanceledException;
    }
}

static void DeleteStaleStreamLocks(string stateRoot)
{
    string streamsPath = Path.Combine(stateRoot, "streams");
    if (!Directory.Exists(streamsPath))
    {
        return;
    }

    foreach (string lockPath in Directory.EnumerateFiles(
        streamsPath,
        "*.jsonl.lock",
        SearchOption.TopDirectoryOnly))
    {
        for (int attempt = 1; attempt <= 10; attempt++)
        {
            try
            {
                File.Delete(lockPath);
                break;
            }
            catch (UnauthorizedAccessException) when (attempt < 10)
            {
                Thread.Sleep(TimeSpan.FromMilliseconds(250));
            }
            catch (IOException) when (attempt < 10)
            {
                Thread.Sleep(TimeSpan.FromMilliseconds(250));
            }
        }
    }
}

static int GetAvailablePort()
{
    var listener = new TcpListener(IPAddress.Loopback, 0);
    listener.Start();
    int port = ((IPEndPoint)listener.LocalEndpoint).Port;
    listener.Stop();
    return port;
}

static string FindRepositoryRoot()
{
    foreach (string start in new[] { Environment.CurrentDirectory, AppContext.BaseDirectory })
    {
        DirectoryInfo? directory = new(start);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(
                    directory.FullName,
                    "dotnet",
                    "agent-framework-dotnet.slnx")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }
    }

    throw new InvalidOperationException(
        "Could not find the Agent Framework repository root.");
}

static void TryDeleteDirectory(string path)
{
    try
    {
        Directory.Delete(path, recursive: true);
    }
    catch (IOException)
    {
    }
    catch (UnauthorizedAccessException)
    {
    }
}

internal sealed class AgentStreamObserver(int crashAfterCount)
{
    private readonly Dictionary<string, StringBuilder> _messageBuffers =
        new(StringComparer.Ordinal);
    private readonly HashSet<string> _completedMessageIds =
        new(StringComparer.Ordinal);
    private List<string>? _preCrashTexts;
    private bool? _recoveryIncludesSnapshot;
    private int _recoverySnapshotIndex;
    private int _messageCount;

    public TaskCompletionSource<string> ResponseId { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    public TaskCompletionSource CrashPointReached { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    public List<string> CompletedTexts { get; } = [];

    public ResponseContinuationToken? ContinuationToken { get; private set; }

    public bool ResponseCompleted { get; private set; }

    public void BeginRecovery()
    {
        this._preCrashTexts = [.. this.CompletedTexts];
        this._recoveryIncludesSnapshot = null;
        this._recoverySnapshotIndex = 0;
    }

    public void ObserveInitial(AgentResponseUpdate update) =>
        this.Observe(update, "before", trackCheckpoint: true);

    public void ObserveRecovered(AgentResponseUpdate update) =>
        this.Observe(update, "recovered", trackCheckpoint: false);

    public void ObserveReplayed(AgentResponseUpdate update) =>
        this.Observe(update, "replayed", trackCheckpoint: false);

    private void Observe(
        AgentResponseUpdate update,
        string phase,
        bool trackCheckpoint)
    {
        object? rawRepresentation =
            update.RawRepresentation is ChatResponseUpdate chatResponseUpdate
                ? chatResponseUpdate.RawRepresentation
                : update.RawRepresentation;

        if (update.ContinuationToken is { } continuationToken)
        {
            this.ContinuationToken = continuationToken;
        }

        if (!string.IsNullOrWhiteSpace(update.ResponseId))
        {
            this.ResponseId.TrySetResult(update.ResponseId);
        }

        if (!string.IsNullOrWhiteSpace(update.MessageId)
            && !string.IsNullOrEmpty(update.Text))
        {
            if (!this._messageBuffers.TryGetValue(
                    update.MessageId,
                    out StringBuilder? buffer))
            {
                buffer = new StringBuilder();
                this._messageBuffers[update.MessageId] = buffer;
            }

            buffer.Append(update.Text);
        }

        if (rawRepresentation is StreamingResponseOutputItemDoneUpdate
            {
                Item: MessageResponseItem message
            }
            && this._completedMessageIds.Add(message.Id))
        {
            string text = this._messageBuffers.TryGetValue(
                message.Id,
                out StringBuilder? buffer)
                ? buffer.ToString()
                : string.Empty;
            if (phase != "before" && text.Length == 0)
            {
                return;
            }

            if (phase == "recovered"
                && this.TryHandleRecoverySnapshot(text))
            {
                return;
            }

            this.CompletedTexts.Add(text);
            WriteOutput(phase, text);

            if (trackCheckpoint && ++this._messageCount >= crashAfterCount)
            {
                this.CrashPointReached.TrySetResult();
            }
        }

        if (rawRepresentation is StreamingResponseCompletedUpdate)
        {
            this.ResponseCompleted = true;
        }
    }

    private bool TryHandleRecoverySnapshot(string text)
    {
        if (this._preCrashTexts is not { Count: > 0 } preCrashTexts)
        {
            return false;
        }

        this._recoveryIncludesSnapshot ??=
            string.Equals(text, preCrashTexts[0], StringComparison.Ordinal);
        if (this._recoveryIncludesSnapshot is not true)
        {
            return false;
        }

        if (this._recoverySnapshotIndex >= preCrashTexts.Count)
        {
            return false;
        }

        if (!string.Equals(
                text,
                preCrashTexts[this._recoverySnapshotIndex],
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "The response snapshot returned during reconnection did not match the pre-crash output.");
        }

        this._recoverySnapshotIndex++;
        WriteOutput("restored", text);
        return true;
    }

    private static void WriteOutput(string phase, string text)
    {
        Console.ForegroundColor = phase == "recovered"
            ? ConsoleColor.Green
            : ConsoleColor.DarkGray;
        Console.WriteLine($"      {phase,-9} > {text}");
        Console.ResetColor();
    }
}

internal sealed class ServerProcess
{
    private readonly Process _process;
    private readonly Task _outputPump;
    private readonly Task _errorPump;

    private ServerProcess(Process process, TextWriter logWriter)
    {
        this._process = process;
        this._outputPump = PumpAsync(process.StandardOutput, logWriter, "stdout");
        this._errorPump = PumpAsync(process.StandardError, logWriter, "stderr");
    }

    public int Id => this._process.Id;

    public static ServerProcess Start(
        ProcessStartInfo startInfo,
        TextWriter logWriter)
    {
        Process process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Could not start the server process.");
        return new ServerProcess(process, TextWriter.Synchronized(logWriter));
    }

    public async Task KillAsync()
    {
        if (!this._process.HasExited)
        {
            this._process.Kill(entireProcessTree: true);
        }

        await this._process.WaitForExitAsync();
        await Task.WhenAll(this._outputPump, this._errorPump)
            .WaitAsync(TimeSpan.FromSeconds(5));
        this._process.Dispose();
    }

    private static async Task PumpAsync(
        StreamReader reader,
        TextWriter writer,
        string source)
    {
        while (await reader.ReadLineAsync() is { } line)
        {
            await writer.WriteLineAsync($"[{source}] {line}");
        }
    }
}

internal sealed class LocalAgentClient(
    AIAgent agent,
    HttpClient transportClient) : IDisposable
{
    public AIAgent Agent { get; } = agent;

    public void Dispose() => transportClient.Dispose();
}

internal sealed record VerificationOptions(
    int Target,
    int CrashAfterCount,
    int DelaySeconds)
{
    public static VerificationOptions Parse(string[] args)
    {
        int target = 20;
        int? crashAfterCount = null;
        int delaySeconds = 1;

        for (int index = 0; index < args.Length; index++)
        {
            string argument = args[index];
            switch (argument)
            {
                case "--target":
                    target = ReadInteger(args, ref index, argument);
                    break;
                case "--crash-after-count":
                    crashAfterCount = ReadInteger(args, ref index, argument);
                    break;
                case "--delay-seconds":
                    delaySeconds = ReadInteger(args, ref index, argument);
                    break;
                default:
                    throw new ArgumentException($"Unknown argument '{argument}'.");
            }
        }

        int resolvedCrashAfterCount = crashAfterCount ?? Math.Max(1, target / 2);
        if (target < 2)
        {
            throw new ArgumentOutOfRangeException(
                nameof(args),
                "Target must be at least 2.");
        }

        if (resolvedCrashAfterCount < 1 || resolvedCrashAfterCount >= target)
        {
            throw new ArgumentOutOfRangeException(
                nameof(args),
                "Crash count must be greater than zero and less than the target.");
        }

        if (delaySeconds < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(args),
                "Delay seconds must be zero or greater.");
        }

        return new(target, resolvedCrashAfterCount, delaySeconds);
    }

    private static int ReadInteger(
        string[] args,
        ref int index,
        string argument)
    {
        if (++index >= args.Length
            || !int.TryParse(
                args[index],
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out int value))
        {
            throw new ArgumentException(
                $"Argument '{argument}' requires an integer value.");
        }

        return value;
    }
}
