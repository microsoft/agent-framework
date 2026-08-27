#!/usr/bin/env bash
#
# Rewires an already-scaffolded hosted-agent folder to build against the local Agent Framework
# source, so `azd deploy` ships your framework changes instead of the published packages.
#
# Source (ZIP) deploy uploads the agent folder and Foundry runs `dotnet restore` + `dotnet publish`
# on it in the cloud. That restore pulls the Agent Framework from nuget.org, so a contributor's
# local framework changes are never exercised.
#
# Run this after `azd ai agent init` and before `azd provision`. It changes three things in the
# folder that `init` scaffolded:
#
#   local-feed/    New. The Agent Framework packed from the local source tree, stamped with a
#                  version derived from the repo's current VersionPrefix plus a `-preview-local`
#                  suffix. The whole closure is packed: packing only the leaf packages lets NuGet
#                  fill the rest from nuget.org, mixing a published core with a locally built host.
#   nuget.config   New. Maps Microsoft.Agents.AI* to that folder feed and everything else to
#                  nuget.org.
#   the .csproj    Edited. Its AgentFrameworkVersion property is repointed at the version just
#                  packed.
#
# Neither generated file is excluded by `.agentignore`, so they travel inside the ZIP and the
# server-side restore uses them.
#
# Everything else stays identical to the end-user flow: you create the working directory, run
# `azd ai agent init`, and finish with `azd provision`, `azd deploy`, and `azd ai agent invoke`.
# The scaffolded folder is a throwaway copy, so editing its project file leaves the repository
# untouched.
#
# Usage:
#   add-local-framework-feed.sh [path-to-scaffolded-folder]
#
# The path defaults to the current directory.
#
# This is the bash counterpart of Add-LocalFrameworkFeed.ps1. For contributors validating framework
# changes end to end. End users skip this script entirely and get the published packages.

set -euo pipefail

# The Agent Framework closure the hosted samples resolve. Packing only the leaf packages makes
# NuGet satisfy the rest from nuget.org, producing assembly-reference errors at build time.
framework_projects=(
    Microsoft.Agents.AI.Abstractions
    Microsoft.Agents.AI
    Microsoft.Agents.AI.Workflows
    Microsoft.Agents.AI.Hosting
    Microsoft.Agents.AI.LocalCodeAct
    Microsoft.Agents.AI.Mcp
    Microsoft.Agents.AI.Foundry
    Microsoft.Agents.AI.Foundry.Hosting
)

target_input="${1:-.}"

if [[ ! -d "$target_input" ]]; then
    echo "Error: '$target_input' is not a directory." >&2
    exit 1
fi

target="$(cd "$target_input" && pwd)"

if [[ ! -f "$target/azure.yaml" ]]; then
    echo "Error: no azure.yaml in '$target'. Point the path at the folder 'azd ai agent init' scaffolded." >&2
    exit 1
fi

project_file="$(find "$target" -maxdepth 1 -name '*.csproj' | head -n 1)"

if [[ -z "$project_file" ]]; then
    echo "Error: no .csproj in '$target'. This script targets .NET hosted agents." >&2
    exit 1
fi

if ! grep -q '<AgentFrameworkVersion>' "$project_file"; then
    echo "Error: $(basename "$project_file") has no <AgentFrameworkVersion> property to repoint at a local build." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosted_root="$(dirname "$script_dir")"
dotnet_root="$(cd "$hosted_root/../../.." && pwd)"
src_root="$dotnet_root/src"

# Derive the package version from the repo so the packages track the current release line.
# The timestamp keeps every run unique: NuGet caches by id and version, so reusing a version would
# silently restore the previously packed bits instead of the build you just made. It also changes
# the ZIP contents on every run, which matters because Foundry mints a new agent version only when
# the uploaded ZIP changes.
package_props="$dotnet_root/nuget/nuget-package.props"
version_prefix="$(sed -n 's/.*<VersionPrefix>\([^<]*\)<\/VersionPrefix>.*/\1/p' "$package_props" | head -n 1)"

if [[ -z "$version_prefix" ]]; then
    echo "Error: could not read VersionPrefix from $package_props." >&2
    exit 1
fi

version="$version_prefix-preview-local.$(date +%Y%m%d%H%M%S)"

feed_path="$target/local-feed"
rm -rf "$feed_path"
mkdir -p "$feed_path"

echo "Wiring $(basename "$target") to the local Agent Framework"
echo "  version: $version"
echo

for project in "${framework_projects[@]}"; do
    project_path="$src_root/$project/$project.csproj"
    echo "Packing $project..."

    # Debug, not Release: the Release configuration runs the repo's formatting and analyzer passes,
    # which rewrite source files and fail the build on style violations. Packing only needs runnable
    # binaries, so Debug keeps the working tree untouched.
    #
    # PackageVersion (not Version) is the property the repo's packaging props use to stamp both the
    # package version and its dependency ranges, so the packed packages reference each other at this
    # version instead of the bare VersionPrefix.
    dotnet build "$project_path" -c Debug "-p:PackageVersion=$version" --tl:off >/dev/null
    dotnet pack "$project_path" -c Debug --no-build -o "$feed_path" "-p:PackageVersion=$version" --tl:off >/dev/null
done

cat > "$target/nuget.config" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by add-local-framework-feed.sh: resolves the Agent Framework from this upload. -->
<configuration>
  <packageSources>
    <clear />
    <add key="local-feed" value="./local-feed" />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
  <packageSourceMapping>
    <packageSource key="local-feed">
      <package pattern="Microsoft.Agents.AI*" />
    </packageSource>
    <packageSource key="nuget.org">
      <package pattern="*" />
    </packageSource>
  </packageSourceMapping>
</configuration>
EOF

# The scaffolded copy is disposable, so repointing its project file at the local build is safe and
# keeps the checked-in sample free of contributor-only scaffolding. Reruns are safe: the pattern
# matches whatever version is currently there. sed rewrites the line in place, leaving the file's
# leading byte order mark untouched.
sed -i.bak "s|<AgentFrameworkVersion>[^<]*</AgentFrameworkVersion>|<AgentFrameworkVersion>$version</AgentFrameworkVersion>|" "$project_file"
rm -f "$project_file.bak"
sed -E -i.bak "s|(PackageReference Include=\"Microsoft\\.Agents\\.AI[^\"]*\" Version=\")[^\"]*(\" />)|\\1$version\\2|g" "$project_file"
rm -f "$project_file.bak"

echo
echo "Done. Continue with the standard flow:"
echo
echo "  cd \"$target\""
echo "  azd provision"
echo "  azd deploy"
echo "  azd ai agent invoke \"Hello!\""
