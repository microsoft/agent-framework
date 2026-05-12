// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for <see cref="ShellResolver.ResolveArgv"/>: bash-only flags like
/// <c>--noprofile</c> / <c>--norc</c> must only be passed to bash; other
/// POSIX shells (sh, zsh, dash, ash, ksh, busybox) reject or mishandle them.
/// </summary>
public class ShellResolverTests
{
    private static readonly string[] s_shCommandArgv = new[] { "-c", "echo hi" };
    private static readonly string[] s_bashCommandArgv = new[] { "--noprofile", "--norc", "-c", "echo hi" };
    private static readonly string[] s_bashPersistentArgv = new[] { "--noprofile", "--norc" };

    private static ResolvedShell ResolveSingle(string binary) => ShellResolver.ResolveArgv(new[] { binary });

    [Theory]
    [InlineData("/bin/sh")]
    [InlineData("/bin/dash")]
    [InlineData("/bin/ash")]
    [InlineData("/usr/bin/busybox")]
    [InlineData("/usr/bin/zsh")]
    [InlineData("/bin/ksh")]
    public void ShVariants_StatelessArgv_OmitBashOnlyFlags(string binary)
    {
        var argv = ResolveSingle(binary).StatelessArgvForCommand("echo hi");

        Assert.Equal(s_shCommandArgv, argv);
        Assert.DoesNotContain("--noprofile", argv);
        Assert.DoesNotContain("--norc", argv);
    }

    [Theory]
    [InlineData("/bin/sh")]
    [InlineData("/bin/dash")]
    [InlineData("/bin/ash")]
    [InlineData("/usr/bin/busybox")]
    [InlineData("/usr/bin/zsh")]
    [InlineData("/bin/ksh")]
    public void ShVariants_PersistentArgv_OmitBashOnlyFlags(string binary)
    {
        var argv = ResolveSingle(binary).PersistentArgv();

        Assert.Empty(argv);
    }

    [Theory]
    [InlineData("/bin/bash")]
    [InlineData("/usr/local/bin/bash")]
    public void BashVariants_StatelessArgv_IncludeBashFlags(string binary)
    {
        var argv = ResolveSingle(binary).StatelessArgvForCommand("echo hi");

        Assert.Equal(s_bashCommandArgv, argv);
    }

    [Theory]
    [InlineData("/bin/bash")]
    [InlineData("/usr/local/bin/bash")]
    public void BashVariants_PersistentArgv_IncludeBashFlags(string binary)
    {
        var argv = ResolveSingle(binary).PersistentArgv();

        Assert.Equal(s_bashPersistentArgv, argv);
    }
}
