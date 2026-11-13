// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.InteropServices;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for <see cref="ShellResolver"/>: bash-only flags like
/// <c>--noprofile</c> / <c>--norc</c> must only be passed to bash; other
/// POSIX shells (sh, zsh, dash, ash, ksh, busybox) reject or mishandle them.
/// Explicit shells must be fully qualified paths.
/// </summary>
public class ShellResolverTests
{
    private static readonly string[] s_shCommandArgv = new[] { "-c", "echo hi" };
    private static readonly string[] s_bashCommandArgv = new[] { "--noprofile", "--norc", "-c", "echo hi" };
    private static readonly string[] s_bashPersistentArgv = new[] { "--noprofile", "--norc" };

    private static readonly bool s_isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);

    // The test data uses POSIX paths; on Windows, map them to a fully qualified path with an extension
    // so they pass validation while keeping the same file name.
    private static ResolvedShell ResolveSingle(string binary) =>
        ShellResolver.ResolveArgv(new[] { s_isWindows ? "C:" + binary.Replace('/', '\\') + ".exe" : binary });

    [Theory]
    [InlineData("pwsh")]
    [InlineData("pwsh.exe")]
    [InlineData("bash")]
    [InlineData("./bash")]
    [InlineData(@".\pwsh.exe")]
    public void Resolve_PartialPath_ThrowsArgumentException(string shell)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => ShellResolver.Resolve(shell, "options.Shell"));
        Assert.Equal("options.Shell", exception.ParamName);
    }

    [Theory]
    [InlineData("pwsh")]
    [InlineData("pwsh.exe")]
    [InlineData("bash")]
    [InlineData("./bash")]
    [InlineData(@".\pwsh.exe")]
    public void ResolveArgv_PartialPath_ThrowsArgumentException(string shell)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => ShellResolver.ResolveArgv(new[] { shell, "-x" }, "options.ShellArgv"));
        Assert.Equal("options.ShellArgv", exception.ParamName);
    }

    [Fact]
    public void Resolve_NoExtension_ThrowsOnWindows()
    {
        Assert.SkipUnless(s_isWindows, "File extensions are only required on Windows.");

        // Act & Assert
        const string Shell = @"C:\tools\pwsh";
        _ = Assert.Throws<ArgumentException>(() => ShellResolver.Resolve(Shell));
        _ = Assert.Throws<ArgumentException>(() => ShellResolver.ResolveArgv([Shell]));
    }

    [Fact]
    public void Resolve_FullPath_IsUsedAsIs()
    {
        // Arrange
        var shell = s_isWindows ? @"C:\tools\pwsh.exe" : "/usr/local/bin/pwsh";

        // Act
        var resolved = ShellResolver.Resolve(shell);

        // Assert
        Assert.Equal(shell, resolved.Binary);
        Assert.Equal(ShellKind.PowerShell, resolved.Kind);
    }

    [Fact]
    public void Resolve_Default_ReturnsFullPath()
    {
        // Act
        var resolved = ShellResolver.Resolve();

        // Assert
        Assert.True(System.IO.Path.IsPathFullyQualified(resolved.Binary), resolved.Binary);
    }

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
