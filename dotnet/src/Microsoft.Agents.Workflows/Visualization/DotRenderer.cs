// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides methods for rendering Graphviz DOT source code into various output formats.
/// </summary>
/// <remarks>This class serves as a wrapper for the Graphviz "dot" executable, enabling the conversion of DOT
/// source code into formats such as SVG, PNG, and PDF. The "dot" executable must be installed and accessible via the
/// system PATH. For more information about Graphviz, visit <see href="https://graphviz.org"/>.</remarks>
public static class DotRenderer
{
    /// <summary>
    /// Specifies the output format for generated files.
    /// </summary>
    /// <remarks>This enumeration is used to indicate the desired format for output, such as vector graphics
    /// or raster images.</remarks>
    public enum OutputFormat
    {
        /// <summary>
        /// Represents an SVG (Scalable Vector Graphics) element or document.
        /// </summary>
        /// <remarks>SVG is a widely used XML-based format for vector graphics that supports interactivity
        /// and animation. This class provides functionality to work with SVG elements, enabling manipulation,
        /// rendering, or exporting of SVG content.</remarks>
        Svg,

        /// <summary>
        /// Represents a Portable Network Graphics (PNG) image format.
        /// </summary>
        /// <remarks>This class or member is used to handle operations or data related to PNG images. PNG
        /// is a lossless image format commonly used for web graphics and image storage.</remarks>
        Png,

        /// <summary>
        /// Represents a PDF document and provides functionality for working with its content.
        /// </summary>
        /// <remarks>This class can be used to load, manipulate, and save PDF documents. It provides
        /// methods for  accessing pages, extracting text, and performing other common PDF operations.</remarks>
        Pdf
    }

    /// <summary>
    /// Renders a DOT graph source into a specified output format using the Graphviz "dot" tool.
    /// </summary>
    /// <remarks>This method requires the Graphviz "dot" executable to be installed and accessible via the
    /// system PATH. If the "dot" executable is not found, an <see cref="InvalidOperationException"/> is thrown with
    /// details on how to resolve the issue. The method writes the DOT source to the "dot" process and reads the
    /// rendered output as a byte array.</remarks>
    /// <param name="dotSource">The DOT graph source to render. Cannot be null, empty, or whitespace.</param>
    /// <param name="format">The desired output format for the rendered graph (e.g., SVG, PNG, PDF).</param>
    /// <param name="timeoutMs">The maximum time, in milliseconds, to wait for the rendering process to complete. Defaults to 30,000 ms.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests. The operation will be canceled if the token is triggered.</param>
    /// <returns>A byte array containing the rendered graph in the specified format.</returns>
    /// <exception cref="ArgumentException">Thrown if <paramref name="dotSource"/> is null, empty, or consists only of whitespace.</exception>
    /// <exception cref="ArgumentOutOfRangeException">Thrown if <paramref name="format"/> is not a valid <see cref="OutputFormat"/> value.</exception>
    /// <exception cref="InvalidOperationException">Thrown if the "dot" process fails to start, the "dot" executable is not found on the system PATH, or the process
    /// exits with a non-zero exit code.</exception>
    /// <exception cref="TimeoutException">Thrown if the rendering process does not complete within the specified <paramref name="timeoutMs"/>.</exception>
    public static async Task<byte[]> RenderAsync(
        string dotSource,
        OutputFormat format,
        int timeoutMs = 30000,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(dotSource))
        {
            throw new ArgumentException("DOT source is empty.", nameof(dotSource));
        }

        var typeArg = format switch
        {
            OutputFormat.Svg => "-Tsvg",
            OutputFormat.Png => "-Tpng",
            OutputFormat.Pdf => "-Tpdf",
            _ => throw new ArgumentOutOfRangeException(nameof(format))
        };

        var psi = new ProcessStartInfo
        {
            FileName = "dot", // must be on PATH
            Arguments = typeArg,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        using var proc = new Process { StartInfo = psi };

        try
        {
            if (!proc.Start())
            {
                throw new InvalidOperationException("Failed to start Graphviz 'dot' process.");
            }
        }
        catch (System.ComponentModel.Win32Exception ex) when (ex.NativeErrorCode == 2) // file not found
        {
            throw new InvalidOperationException(
                "Graphviz 'dot' was not found on the system PATH.\n\n" +
                "Please install Graphviz and ensure the 'dot' executable is accessible from the command line.\n" +
                "Download: https://graphviz.org/download/",
                ex);
        }

        // Write input and close stdin to signal EOF
        using (var stdin = proc.StandardInput)
        {
            await stdin.WriteAsync(dotSource).ConfigureAwait(false);
        }

        // read output bytes
        using var ms = new MemoryStream();
        var copyTask = proc.StandardOutput.BaseStream.CopyToAsync(ms, 81920, cancellationToken); // 80KB buffer
#if NET472 || NETSTANDARD2_0
        var errTask = proc.StandardError.ReadToEndAsync();
#else
        var errTask = proc.StandardError.ReadToEndAsync(cancellationToken);
#endif

        if (!proc.WaitForExit(timeoutMs))
        {
            try { proc.Kill(); } catch { /* ignore */ }
            throw new TimeoutException($"Graphviz 'dot' timed out after {timeoutMs} ms");
        }

        await Task.WhenAll(copyTask, errTask).ConfigureAwait(false);

        if (proc.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"Graphviz 'dot' exited with code {proc.ExitCode}.\n" +
                $"Error output:\n{await errTask.ConfigureAwait(false)}");
        }

        return ms.ToArray();
    }

    /// <summary>
    /// Renders a DOT source string to a specified file in the given output format.
    /// </summary>
    /// <remarks>This method combines rendering the DOT source into the specified format and writing the
    /// result to a file. Ensure that the <paramref name="outputPath"/> is valid and accessible, and that the <paramref
    /// name="dotSource"/> is well-formed.</remarks>
    /// <param name="dotSource">The DOT source string to be rendered. This cannot be <see langword="null"/> or empty.</param>
    /// <param name="format">The output format for the rendered file, such as PNG, SVG, or PDF.</param>
    /// <param name="outputPath">The file path where the rendered output will be saved. This cannot be <see langword="null"/> or empty.</param>
    /// <param name="timeoutMs">The maximum time, in milliseconds, to wait for the rendering operation to complete. The default is 30,000
    /// milliseconds (30 seconds).</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests. The default value is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task completes when the file has been successfully
    /// written to the specified path.</returns>
    public static async Task RenderToFileAsync(
        string dotSource,
        OutputFormat format,
        string outputPath,
        int timeoutMs = 30000,
        CancellationToken cancellationToken = default)
    {
        var bytes = await RenderAsync(dotSource, format, timeoutMs, cancellationToken).ConfigureAwait(false);
#if NET472 || NETSTANDARD2_0
        File.WriteAllBytes(outputPath, bytes);
#else
        await File.WriteAllBytesAsync(outputPath, bytes, cancellationToken).ConfigureAwait(false);
#endif
    }
}
