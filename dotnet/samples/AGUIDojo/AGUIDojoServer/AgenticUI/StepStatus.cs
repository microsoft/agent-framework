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

[JsonConverter(typeof(JsonStringEnumConverter<StepStatus>))]
internal enum StepStatus
{
    Pending,
    Completed
}
