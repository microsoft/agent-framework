---
applyTo: '**.py'
---
## General Instructions for Converting .NET Library to Python Library
 - You are an agent whose primary job to convert the dotnet library into a python package.
 - dotnet library is under dotnet folder.
 - Utilize design docs which are available under docs folder.
 - python library should be created in python folder.
 - Add copyright notice to all files in python folder.example:
# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
  - Does not add more than one class to a file, always create a file for each class.
  - Add docstrings to classes, methods and properties, based on the dotnet classes.
  - implement protected methods as private methods in python.
  - implement interfaces as abstract classes in python.
  - 
## Bootstrap
 - Add setup.py to the root of the python folder.
 - Add requirements.txt to the root of the python folder.
 - python package will be named `azure-ai-multi-agent`.
 - Add requirements.txt file to the root of the python folder.
    - pytest
 - It will dependencies
    - openai
    - azure-identity
 - Here is sample setup.py file:
  ```
  from setuptools import setup, find_packages
    import os
    from io import open
    import re

    # azure openai testing package

    PACKAGE_NAME = "azure-openai"
    PACKAGE_PPRINT_NAME = "Azure OpenAI"

    # a-b-c => a/b/c
    package_folder_path = PACKAGE_NAME.replace("-", "/")
    # a-b-c => a.b.c
    namespace_name = PACKAGE_NAME.replace("-", ".")

    # Version extraction inspired from 'requests'
    with open(os.path.join(package_folder_path, "_version.py"), "r") as fd:
        version = re.search(r'^VERSION\s*=\s*[\'"]([^\'"]*)[\'"]', fd.read(), re.MULTILINE).group(1)
    if not version:
        raise RuntimeError("Cannot find version information")

    with open("README.md", encoding="utf-8") as f:
        long_description = f.read()

    setup(
        name=PACKAGE_NAME,
        version=version,
        description="Microsoft Azure {} Client Library for Python".format(PACKAGE_PPRINT_NAME),
        # ensure that these are updated to reflect the package owners' information
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/Azure/azure-sdk-for-python",
        keywords="azure, azure sdk",  # update with search keywords relevant to the azure service / product
        author="Microsoft Corporation",
        author_email="azuresdkengsysadmins@microsoft.com",
        license="MIT License",
        # ensure that the development status reflects the status of your package
        classifiers=[
            "Development Status :: 4 - Beta",
            "Programming Language :: Python",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "License :: OSI Approved :: MIT License",
        ],
        packages=find_packages(
            exclude=[
                "tests",
                # Exclude packages that will be covered by PEP420 or nspkg
                # This means any folder structure that only consists of a __init__.py.
                # For example, for storage, this would mean adding 'azure.storage'
                # in addition to the default 'azure' that is seen here.
                "azure",
            ]
        ),
        include_package_data=True,
        package_data={
            'azure.openai': ['py.typed'],
        },
        install_requires=[
            "azure-identity<2.0.0,>=1.15.0"
        ],
        python_requires=">=3.7",
        project_urls={
            "Bug Reports": "https://github.com/Azure/azure-sdk-for-python/issues",
            "Source": "https://github.com/Azure/azure-sdk-for-python",
        },
    )```

## ✅ Folder structure
 - python
    - azure-ai-multi-agent
        - ai
            - agent
                - abstract_agent
                - chat_completion_agent
        - samples
        - tests
            - unit
                - ai
                    - agent
                        - abstract_agent
                        - chat_completion_agent        
          
 
 - abstract_agent will map to Microsoft.Agents.Abstractions
 - chat_completion_agent will map to Microsoft.Agents.ChatCompletion

## Converting Microsoft.Agents.Abstractions
 - Convert Microsoft.Agents.Abstractions namespace to abstract_agent module.
 - Convert Microsoft.Agents.Abstractions.Agent class to Abstract
 - Convert all the classes and interfaces in Microsoft.Agents.Abstractions namespace to python classes.
 - Add unit test cases also to provide coverage for the classes.
 - Add __init__.py files to export the modules.

## Converting Microsoft.Agents.ChatCompletion
 - Convert Microsoft.Agents.ChatCompletion namespace to chat_completion_agent module.
 - Convert Microsoft.Agents.ChatCompletion.ChatCompletion class to ChatCompletion
 - Convert all the classes and interfaces in Microsoft.Agents.ChatCompletion namespace to python classes.
 - Add unit test cases also to provide coverage for the classes.
 - Add __init__.py files to export the modules.
 - Map IChatClient to open chat Client. sampleCode
    ``
        from openai import AzureOpenAI
        client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_ad_token_provider=token_provider,
        api_version=os.environ["API_VERSION_GA"],
    )
    ``
 - Logger should be created using `logging.getLogger(__name__)` in each module.

## Sample generation
 - Write sample code in folder python/azure-ai-multi-agent/samples.
 - Sample code to demonstrate how to use the library.
 - Add docstring to sample code which explain how to use the sample.
 - Provide public documentation link in docstring how to set up Azure OpenAI resources.