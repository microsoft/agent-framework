# Path Validation

Checks that caller-supplied paths are fully qualified and name an existing file, so they never depend on the current directory or a `PATH` search. On Windows, executable paths must also include a file extension (such as `.exe`).

It also provides a `PATH` search (`TryFindOnPath`) that only looks in fully qualified directories, skipping empty and relative entries, and a helper (`RemoveRelativePathEntries`) that removes those entries from a `PATH` value.

To use this in your project, add the following to your `.csproj` file:

```xml
<PropertyGroup>
  <InjectSharedPathValidation>true</InjectSharedPathValidation>
</PropertyGroup>
```

This also depends on the shared Throw class, so InjectSharedThrow must also be enabled:

```xml
<PropertyGroup>
  <InjectSharedThrow>true</InjectSharedThrow>
</PropertyGroup>
```
