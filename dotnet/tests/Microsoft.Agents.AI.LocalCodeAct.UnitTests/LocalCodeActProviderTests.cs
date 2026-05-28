// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class LocalCodeActProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static AIContextProvider.InvokingContext NewInvokingContext() =>
        new(s_mockAgent, session: null, new AIContext());

    private static LocalCodeActProviderOptions Options() =>
        new("/usr/bin/python3")
        {
            ValidationEnabled = false, // No subprocess will be launched in these tests
        };

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsExecuteCodeToolAndInstructionsAsync()
    {
        using var provider = new LocalCodeActProvider(Options());

        var context = await provider.InvokingAsync(NewInvokingContext());

        Assert.NotNull(context);
        Assert.NotNull(context!.Tools);
        var tools = context.Tools!.ToList();
        Assert.Single(tools);
        var function = Assert.IsAssignableFrom<AIFunction>(tools[0]);
        Assert.Equal("execute_code", function.Name);
        Assert.False(string.IsNullOrWhiteSpace(context.Instructions));
    }

    [Fact]
    public void AddAndRemoveTools_RoundTrips()
    {
        using var provider = new LocalCodeActProvider(Options());

        var tool = new TestTool("ping");
        provider.AddTools(tool);

        Assert.Contains(provider.GetTools(), t => t.Name == "ping");

        provider.RemoveTools("ping");
        Assert.DoesNotContain(provider.GetTools(), t => t.Name == "ping");
    }

    [Fact]
    public void AddAndRemoveFileMounts_RoundTrips()
    {
        using var provider = new LocalCodeActProvider(Options());

        var tempDir = System.IO.Directory.CreateTempSubdirectory("localcodeact-test-").FullName;
        try
        {
            var mount = new FileMount(tempDir, "/app/data");
            provider.AddFileMounts(mount);

            Assert.Contains(provider.GetFileMounts(), m => m.MountPath == "/app/data");

            provider.RemoveFileMounts("/app/data");
            Assert.DoesNotContain(provider.GetFileMounts(), m => m.MountPath == "/app/data");
        }
        finally
        {
            System.IO.Directory.Delete(tempDir, recursive: true);
        }
    }

    [Fact]
    public void ClearMethods_EmptyState()
    {
        using var provider = new LocalCodeActProvider(Options());

        var tempDir1 = System.IO.Directory.CreateTempSubdirectory("localcodeact-test-").FullName;
        var tempDir2 = System.IO.Directory.CreateTempSubdirectory("localcodeact-test-").FullName;
        try
        {
            provider.AddTools(new TestTool("a"), new TestTool("b"));
            provider.AddFileMounts(new FileMount(tempDir1, "/m/1"), new FileMount(tempDir2, "/m/2"));

            provider.ClearTools();
            provider.ClearFileMounts();

            Assert.Empty(provider.GetTools());
            Assert.Empty(provider.GetFileMounts());
        }
        finally
        {
            System.IO.Directory.Delete(tempDir1, recursive: true);
            System.IO.Directory.Delete(tempDir2, recursive: true);
        }
    }

    private sealed class TestTool : AIFunction
    {
        public TestTool(string name)
        {
            this.Name = name;
        }

        public override string Name { get; }

        public override string Description => "test tool";

        protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, System.Threading.CancellationToken cancellationToken) =>
            new((object?)null);
    }
}
