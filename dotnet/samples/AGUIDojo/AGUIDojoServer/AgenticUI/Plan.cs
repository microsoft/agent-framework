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

internal sealed class Plan
{
    [JsonPropertyName("steps")]
    public List<Step> Steps { get; set; } = [];
}
