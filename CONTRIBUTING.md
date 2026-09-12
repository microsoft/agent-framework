# Contributing to Agent Framework

You can contribute to Agent Framework with issues and pull requests (PRs). Simply
filing issues for problems you encounter is a great way to contribute. Contributing
code is greatly appreciated.

## Reporting Issues

We always welcome bug reports, API proposals and overall feedback. Here are a few
tips on how you can make reporting your issue as effective as possible.

### Where to Report

New issues can be reported in our [list of issues](https://github.com/microsoft/agent-framework/issues).

Before filing a new issue, please search the list of issues to make sure it does
not already exist.

If you do find an existing issue for what you wanted to report, please include
your own feedback in the discussion. Do consider upvoting (👍 reaction) the original
post, as this helps us prioritize popular issues in our backlog.

### Writing a Good Bug Report

Good bug reports make it easier for maintainers to verify and root cause the
underlying problem.
The better a bug report, the faster the problem will be resolved. Ideally, a bug
report should contain the following information:

- A high-level description of the problem.
- A _minimal reproduction_, i.e. the smallest size of code/configuration required
  to reproduce the wrong behavior.
- A description of the _expected behavior_, contrasted with the _actual behavior_ observed.
- Information on the environment: OS/distribution, CPU architecture, SDK version, etc.
- Additional information, e.g. Is it a regression from previous versions? Are there
  any known workarounds?

## Contributing Changes

Project maintainers will merge accepted code changes from contributors.

### DOs and DON'Ts

DO's:

- **DO** follow the standard coding conventions

  - [.NET](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
  - [Python](https://pypi.org/project/black/)

- **DO** give priority to the current style of the project or file you're changing
  if it diverges from the general guidelines.
- **DO** use the pre-commit hooks for python to ensure proper formatting.
- **DO** include tests when adding new features. When fixing bugs, start with
  adding a test that highlights how the current behavior is broken.
- **DO** keep the discussions focused. When a new or related topic comes up
  it's often better to create new issue than to side track the discussion.
- **DO** clearly state on an issue that you are going to take on implementing it.
- **DO** blog and tweet (or whatever) about your contributions, frequently!

DON'Ts:

- **DON'T** surprise us with big pull requests. Instead, file an issue and start
  a discussion so we can agree on a direction before you invest a large amount of time.
- **DON'T** commit code that you didn't write. If you find code that you think is a good
  fit to add to Agent Framework, file an issue and start a discussion before proceeding.
- **DON'T** submit PRs that alter licensing related files or headers. If you believe
  there's a problem with them, file an issue and we'll be happy to discuss it.
- **DON'T** make new APIs without filing an issue and discussing with us first.

### Breaking Changes

Contributions must maintain API signature and behavioral compatibility. Contributions
that include breaking changes will be rejected. Please file an issue to discuss
your idea or change if you believe that a breaking change is warranted.

#### Automated API Compatibility Validation

The .NET projects use [Package Validation](https://learn.microsoft.com/dotnet/fundamentals/package-validation/overview)
to automatically detect API breaking changes. This validation runs during `dotnet build`
(Release configuration) and `dotnet pack`, comparing the current API surface against the
latest published NuGet baseline version.

**What gets validated:** By default, packable RC packages (`IsReleaseCandidate=true`) and
GA packages (`IsGenerallyAvailable=true`) that have a published NuGet baseline and do not
override validation settings are automatically validated. The shared baseline version and
default validation settings are defined in `dotnet/nuget/nuget-package.props`, but
individual projects may opt out (for example by setting `EnablePackageValidation=false`).

**If the build fails with CP errors (e.g., CP0001, CP0002):**

1. **Unintentional breaking change** — Refactor your code to maintain backward compatibility.
2. **Intentional breaking change** (approved by maintainers) — Generate a suppression file:
   ```bash
   dotnet build <project>.csproj -c Release /p:ApiCompatGenerateSuppressionFile=true
   ```
   This creates or updates a `CompatibilitySuppressions.xml` in the project directory.
   Include this file in your PR with justification for the breaking change.

**After each release:**

1. Delete all `CompatibilitySuppressions.xml` files from validated projects.
2. Update `PackageValidationBaselineVersion` in `dotnet/nuget/nuget-package.props` to the
   newly published version.

For more details, see the [Package Validation diagnostic IDs](https://learn.microsoft.com/dotnet/fundamentals/package-validation/diagnostic-ids).

#### Public API Baselines

Released .NET packages also use `Microsoft.CodeAnalysis.PublicApiAnalyzers` to make source-level public API changes visible during builds. The `PublicAPI.*.txt` files use `#nullable enable` so nullability annotations are tracked as part of the public API surface. When adding, changing, or removing public APIs in a released package, update the package's `PublicAPI.Unshipped.txt` file with the analyzer-provided entries and include that change in your PR. The build will fail if public API changes are not reflected in the baseline files.

If local or CI builds report Public API Analyzer warnings or errors, handle each diagnostic separately:

- `RS0016` reports a newly exposed public API that is missing from the baseline. The preferred fix is to use the analyzer code fix on the affected code symbol to add the missing API entry automatically. Alternatively, run `dotnet format` for `RS0016` from the repository root:

  ```powershell
  dotnet format .\dotnet\agent-framework-dotnet.slnx analyzers --diagnostics RS0016
  ```

- `RS0017` reports that a declared public API was deleted. Restore the API if the deletion was accidental; otherwise, record the removed signature in the package's `PublicAPI.Unshipped.txt` file with the `*REMOVED*` prefix by using the corresponding code fix, or the following dotnet format script:

  ```powershell
  dotnet format .\dotnet\agent-framework-dotnet.slnx analyzers --diagnostics RS0017
  ```

After a release, the `Promote Shipped APIs` workflow moves entries from `PublicAPI.Unshipped.txt` to `PublicAPI.Shipped.txt` and opens or updates a promotion PR. Publish builds fail if released packages still contain unshipped public API entries.

### Suggested Workflow

We use and recommend the following workflow:

1. Create an issue for your work.
   - You can skip this step for trivial changes.
   - Reuse an existing issue on the topic, if there is one.
   - Get agreement from the team and the community that your proposed change is
     a good one.
   - Clearly state that you are going to take on implementing it, if that's the case.
     You can request that the issue be assigned to you. Note: The issue filer and
     the implementer don't have to be the same person.
2. Create a personal fork of the repository on GitHub (if you don't already have one).
3. In your fork, create a branch off of main (`git checkout -b mybranch`).
   - Name the branch so that it clearly communicates your intentions, such as
     "issue-123" or "githubhandle-issue".
4. Make and commit your changes to your branch.
5. Add new tests corresponding to your change, if applicable.
6. Run the relevant scripts in [the section below](#development-setup) to ensure that your build is clean and all tests are passing.
7. Create a PR against the repository's **main** branch.
   - State in the description what issue or improvement your change is addressing.
   - Verify that all the Continuous Integration checks are passing.
8. Address feedback from the code maintainers. Reply to every review comment with
   the outcome and resolve each completed review conversation yourself before
   requesting another review.
9. When area owners have signed off, and all checks are green, your PR will be merged.

### Resolving PR Review Comments

PR authors are responsible for closing out all review conversations on their pull
requests, including conversations opened by reviewers. Do not wait for the reviewer
or a maintainer to resolve completed conversations for you.

For every review comment:

- If the feedback was addressed, reply with a brief explanation and, preferably,
  the commit containing the change.
- If the feedback was not addressed, reply with the reason why.

After replying and completing any necessary discussion, **resolve the conversation
yourself**. Leave a conversation open only while it has an unanswered question or
active discussion. Reviewers may reopen a conversation if further changes or
discussion are needed.

### Development Setup

Each language has its own dev setup guide, coding standards, and build scripts:

- **Python**: [Dev Setup](./python/DEV_SETUP.md) · [Coding Standard](./python/CODING_STANDARD.md) · [README](./python/README.md)
  - From the `./python` directory:
    - Build: `uv run poe build`
    - Unit tests: `uv run poe test -A -m "not integration"`
    - Integration tests: `uv run poe test -A -m integration` (requires API keys/endpoints)
    - Format + lint: `uv run poe syntax`
    - All checks: `uv run poe check`
- **.NET**: [README](./dotnet/README.md) · [Agent Instructions](./dotnet/AGENTS.md)
  - From the `./dotnet` directory:
    - Build: `dotnet build`
    - Unit tests: `dotnet test --filter-query "/*UnitTests*/*/*/*"`
    - Integration tests: `dotnet test --filter-query "/*IntegrationTests*/*/*/*"` (requires API keys/endpoints)
    - Linting (auto-fix): `dotnet format`

#### Microsoft Internal Feed Proxy for GitHub Copilot SDK (.NET)

Microsoft contributors can route GitHub Copilot SDK npm downloads through the internal proxy without passing extra `dotnet` arguments:

1. Create `dotnet/Directory.Build.rsp` with:

   ```text
   -p:CopilotNpmRegistryUrl=https://packagefeedproxy.microsoft.io/npm/
   ```

When running `dotnet build` (or other `dotnet` commands) from the `./dotnet` directory, this property is applied automatically.

### PR - CI Process

The continuous integration (CI) system will automatically perform the required
builds and run tests (including the ones you are expected to run) for PRs. Builds
and test runs must be clean.

If the CI build fails for any reason, the PR issue will be updated with a link
that can be used to determine the cause of the failure.
