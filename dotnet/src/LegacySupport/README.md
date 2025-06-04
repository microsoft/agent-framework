# About this Folder

This folder contains a bunch of sources copied from newer versions of .NET which we pull in to
our sources as necessary. This enables us to compile source code that depends on these newer
features from .NET even when targeting older frameworks.

Please see the `eng/MSBuild/LegacySupport.props` file for the set of project properties that control importing
these source files into your project.
