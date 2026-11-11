// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.IO;
#if !NET
using System.Runtime.InteropServices;
#endif

namespace Microsoft.Shared.Diagnostics;

/// <summary>
/// Validates caller-supplied file paths that must name one fixed file, such as an executable to start.
/// </summary>
/// <remarks>
/// A fully qualified path never depends on the current directory or on a search such as <c>PATH</c>.
/// This matters for executables, where starting a bare name such as <c>docker</c> can search
/// the current directory of the host process before <c>PATH</c>.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static class PathValidation
{
    /// <summary>
    /// Ensures that <paramref name="path"/> is a fully qualified path to an existing executable file.
    /// </summary>
    /// <param name="path">The path to validate.</param>
    /// <param name="paramName">The name of the parameter that supplied <paramref name="path"/>.</param>
    /// <param name="fileDescription">A short description of the file used in error messages, such as <c>Python executable</c>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="path"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">
    /// <paramref name="path"/> is empty, whitespace, or not fully qualified, or on Windows has no file extension.
    /// </exception>
    /// <exception cref="FileNotFoundException">No file exists at <paramref name="path"/>.</exception>
    public static void ValidateFullyQualifiedPathToExistingExecutable([NotNull] string? path, string paramName, string fileDescription)
    {
        ValidateFullyQualifiedExecutablePath(path, paramName, fileDescription);

        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"The {fileDescription} file was not found.", path);
        }
    }

    /// <summary>
    /// Ensures that <paramref name="path"/> is a fully qualified path that names exactly one executable file.
    /// Does not check whether anything exists at the path.
    /// </summary>
    /// <remarks>
    /// On Windows, starting a path with no file extension, such as <c>C:\tools\docker</c>, can run a
    /// different file, such as <c>C:\tools\docker.exe</c>. Requiring an extension on Windows ensures the
    /// file that is checked is the file that is started.
    /// </remarks>
    /// <param name="path">The path to validate.</param>
    /// <param name="paramName">The name of the parameter that supplied <paramref name="path"/>.</param>
    /// <param name="fileDescription">A short description of the file used in error messages, such as <c>Python executable</c>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="path"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">
    /// <paramref name="path"/> is empty, whitespace, or not fully qualified, or on Windows has no file extension.
    /// </exception>
    public static void ValidateFullyQualifiedExecutablePath([NotNull] string? path, string paramName, string fileDescription)
    {
        ValidateFullyQualifiedPath(path, paramName, fileDescription);

        if (IsWindows && !Path.HasExtension(path))
        {
            throw new ArgumentException($"The {fileDescription} path must include a file extension, such as .exe, on Windows.", paramName);
        }
    }

    /// <summary>
    /// Ensures that <paramref name="path"/> is fully qualified. Does not check whether anything exists at the path.
    /// </summary>
    /// <param name="path">The path to validate.</param>
    /// <param name="paramName">The name of the parameter that supplied <paramref name="path"/>.</param>
    /// <param name="fileDescription">A short description of the file used in error messages, such as <c>Python executable</c>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="path"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="path"/> is empty, whitespace, or not fully qualified.</exception>
    public static void ValidateFullyQualifiedPath([NotNull] string? path, string paramName, string fileDescription)
    {
        _ = Throw.IfNullOrWhitespace(path, paramName);

        if (!IsFullyQualifiedPath(path))
        {
            throw new ArgumentException($"The {fileDescription} path must be fully qualified.", paramName);
        }
    }

    /// <summary>
    /// Determines whether <paramref name="path"/> is fully qualified.
    /// </summary>
    /// <param name="path">The path to check.</param>
    /// <returns>
    /// <see langword="true"/> if <paramref name="path"/> is fully qualified; <see langword="false"/> if it is
    /// <see langword="null"/>, empty, whitespace, or depends on the current directory or drive.
    /// </returns>
    public static bool IsFullyQualifiedPath([NotNullWhen(true)] string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return false;
        }

#if NET
        return Path.IsPathFullyQualified(path);
#else
        // Path.IsPathFullyQualified is not available on .NET Framework or .NET Standard 2.0,
        // so mirror its rules here.
        if (Path.DirectorySeparatorChar != '\\')
        {
            return path![0] == '/';
        }

        if (path!.Length < 2)
        {
            return false;
        }

        // UNC (\\server\share) and device (\\?\, \\.\) paths.
        if (IsWindowsDirectorySeparator(path[0]))
        {
            return path[1] == '?' || IsWindowsDirectorySeparator(path[1]);
        }

        // Drive-absolute paths (C:\ or C:/). Drive-relative (C:x) and root-relative (\x) paths are not fully qualified.
        return path.Length >= 3
            && path[1] == ':'
            && IsWindowsDirectorySeparator(path[2])
            && ((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z'));
#endif
    }

#if NET
    private static bool IsWindows => OperatingSystem.IsWindows();
#else
    private static bool IsWindows => RuntimeInformation.IsOSPlatform(OSPlatform.Windows);

    private static bool IsWindowsDirectorySeparator(char c) => c is '\\' or '/';
#endif
}
