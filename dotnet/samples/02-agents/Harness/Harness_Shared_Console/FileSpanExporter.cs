// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Globalization;
using OpenTelemetry;

namespace Harness.Shared.Console;

/// <summary>
/// A simple OpenTelemetry span exporter that writes completed activities (spans) to a text file.
/// Each span is formatted as a human-readable block with timestamps, operation name, duration,
/// status, and any tags/events.
/// </summary>
public sealed class FileSpanExporter : BaseExporter<Activity>
{
    private readonly string _filePath;
    private readonly object _lock = new();

    public FileSpanExporter(string filePath)
    {
        this._filePath = filePath;
        Directory.CreateDirectory(Path.GetDirectoryName(filePath)!);
    }

    public override ExportResult Export(in Batch<Activity> batch)
    {
        lock (this._lock)
        {
            using var writer = new StreamWriter(this._filePath, append: true);
            foreach (var activity in batch)
            {
                WriteActivity(writer, activity);
            }
        }

        return ExportResult.Success;
    }

    private static void WriteActivity(StreamWriter writer, Activity activity)
    {
        var start = activity.StartTimeUtc.ToString("yyyy-MM-dd HH:mm:ss.fff", CultureInfo.InvariantCulture);
        var duration = activity.Duration.TotalMilliseconds.ToString("F1", CultureInfo.InvariantCulture);

        writer.WriteLine($"[{start}] {activity.OperationName} ({duration}ms) [{activity.Status}]");

        if (!string.IsNullOrEmpty(activity.DisplayName) && activity.DisplayName != activity.OperationName)
        {
            writer.WriteLine($"  DisplayName: {activity.DisplayName}");
        }

        foreach (var tag in activity.Tags)
        {
            writer.WriteLine($"  {tag.Key}: {tag.Value}");
        }

        foreach (var ev in activity.Events)
        {
            writer.WriteLine($"  Event: {ev.Name} @ {ev.Timestamp:HH:mm:ss.fff}");
            foreach (var tag in ev.Tags)
            {
                writer.WriteLine($"    {tag.Key}: {tag.Value}");
            }
        }

        writer.WriteLine();
    }
}
