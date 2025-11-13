<<<<<<< HEAD
<<<<<<< HEAD
﻿// Copyright (c) Microsoft. All rights reserved.
=======
// Copyright (c) Microsoft. All rights reserved.
>>>>>>> beabff3e (Update the dojo samples)
=======
﻿// Copyright (c) Microsoft. All rights reserved.
>>>>>>> 660dee85 (cleanups)

using System.Text.Json.Serialization;

namespace AGUIDojoServer.AgenticUI;

internal sealed class JsonPatchOperation
{
    [JsonPropertyName("op")]
    public required string Op { get; set; }

    [JsonPropertyName("path")]
    public required string Path { get; set; }

    [JsonPropertyName("value")]
    public object? Value { get; set; }

    [JsonPropertyName("from")]
    public string? From { get; set; }
}
