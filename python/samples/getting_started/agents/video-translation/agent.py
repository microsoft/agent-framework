# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.identity import AzureCliCredential, get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from azure.storage.blob.aio import BlobServiceClient
from pydantic import Field

# Import video translation utilities
from video_translation_client import VideoTranslationClient
from video_translation_enum import VoiceKind, WebvttFileKind

"""
Azure AI Video Translation Agent Sample

This sample demonstrates how to create an AI agent that helps users translate videos
from one language to another using Azure AI Video Translation service. The agent handles
long-running translation operations asynchronously, allowing users to start translations
and check their status without blocking.
"""


async def upload_video_file(
    local_file_path: Annotated[str, Field(description="Absolute path to the local video file to upload")],
    blob_name: Annotated[str, Field(description="Name for the blob in storage (e.g., 'my-video.mp4')")]
) -> str:
    """
    Upload a local video file to Azure Blob Storage.
    
    This tool uploads a video file from the user's local system to Azure Blob Storage
    and returns a URL with SAS token that can be used for video translation.
    
    Args:
        local_file_path: Path to the local video file
        blob_name: Name to give the file in blob storage
        
    Returns:
        Success message with secure access URL (valid for 24 hours)
        
    Example:
        User: "Upload my video at C:\\Videos\\demo.mp4"
        Result: "File uploaded successfully! Use this URL: https://..."
    """
    try:
        # 1. Validate file exists
        if not os.path.exists(local_file_path):
            return f"Error: File not found at path '{local_file_path}'. Please check the path and try again."
        
        # 2. Get storage account configuration
        storage_account_name = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
        if not storage_account_name:
            return ("Error: AZURE_STORAGE_ACCOUNT_NAME environment variable is not set. "
                   "Please configure your Azure Storage account name in the .env file.")
        
        container_name = "video-translation"  # Default container for video translations
        account_url = f"https://{storage_account_name}.blob.core.windows.net"
        blob_url = f"{account_url}/{container_name}/{blob_name}"
        
        # 3. Upload file to blob storage
        async with AsyncDefaultAzureCredential() as credential:
            async with BlobServiceClient(account_url, credential=credential) as blob_service_client:
                # Ensure container exists
                container_client = blob_service_client.get_container_client(container_name)
                try:
                    await container_client.create_container()
                except Exception:
                    pass  # Container already exists
                
                # Upload the file
                blob_client = container_client.get_blob_client(blob_name)
                with open(local_file_path, "rb") as data:
                    await blob_client.upload_blob(data, overwrite=True)
                
                # 4. Generate SAS URL (valid for 24 hours)
                start_time = datetime.now()
                expiry_time = start_time + timedelta(hours=24)
                
                try:
                    user_delegation_key = await blob_service_client.get_user_delegation_key(
                        key_start_time=start_time,
                        key_expiry_time=expiry_time
                    )
                    
                    sas_token = generate_blob_sas(
                        account_name=storage_account_name,
                        container_name=container_name,
                        blob_name=blob_name,
                        user_delegation_key=user_delegation_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=expiry_time
                    )
                    
                    sas_url = f"{blob_url}?{sas_token}"
                    return (f"File uploaded successfully!\n\n"
                           f"Blob URL: {blob_url}\n"
                           f"Secure URL (valid for 24 hours): {sas_url}\n\n"
                           f"Use the secure URL for video translation.")
                except Exception as e:
                    return (f"File uploaded successfully to {blob_url}\n\n"
                           f"Note: Could not generate SAS URL: {str(e)}\n"
                           f"You may need to manually generate a SAS token with read permissions.")
                    
    except Exception as e:
        return f"Error uploading file: {str(e)}\nPlease check your file path and Azure credentials."


async def download_and_upload_video(
    public_video_url: Annotated[str, Field(description="Public URL of the video to download and upload (e.g., https://example.com/video.mp4)")],
    desired_blob_name: Annotated[str, Field(description="Optional name for the blob in storage (e.g., 'my-video.mp4'). If not provided, extracts from URL.")] = None
) -> str:
    """
    Download a video from a public URL and upload it to Azure Blob Storage.
    
    This tool is useful when the Video Translation API rejects a public URL and requires
    an Azure Blob Storage URL instead. It automatically:
    1. Downloads the video from the public URL to a temporary location
    2. Uploads it to Azure Blob Storage
    3. Generates a SAS URL for the translation service
    
    Args:
        public_video_url: The public URL of the video to download
        desired_blob_name: Optional custom name for the blob. If not provided, uses the filename from the URL.
        
    Returns:
        Success message with the Azure Blob Storage SAS URL, or error message if download/upload fails
        
    Example:
        User: "Download and upload https://example.com/videos/sample.mp4"
        Result: " Video downloaded and uploaded! Use this URL: https://..."
    """
    import tempfile
    import urllib.request
    from urllib.parse import urlparse
    from pathlib import Path
    
    try:
        # 1. Extract filename from URL if blob name not provided
        if not desired_blob_name:
            parsed_url = urlparse(public_video_url)
            desired_blob_name = Path(parsed_url.path).name
            if not desired_blob_name:
                desired_blob_name = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        
        # 2. Download video to temporary file
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, desired_blob_name)
        
        try:
            # Download with progress indication (simplified for agent context)
            urllib.request.urlretrieve(public_video_url, temp_file_path)
            file_size_mb = os.path.getsize(temp_file_path) / (1024 * 1024)
        except Exception as download_error:
            return (f"ERROR: Failed to download video from {public_video_url}\n"
                   f"Error: {str(download_error)}\n\n"
                   f"Please verify:\n"
                   f"- The URL is accessible\n"
                   f"- The URL points to a video file\n"
                   f"- You have internet connectivity")
        
        # 3. Get storage account configuration
        storage_account_name = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
        if not storage_account_name:
            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass
            return ("ERROR: Error: AZURE_STORAGE_ACCOUNT_NAME environment variable is not set. "
                   "Please configure your Azure Storage account name in the .env file.")
        
        container_name = "video-translation"
        account_url = f"https://{storage_account_name}.blob.core.windows.net"
        blob_url = f"{account_url}/{container_name}/{desired_blob_name}"
        
        # 4. Upload to Azure Blob Storage
        try:
            async with AsyncDefaultAzureCredential() as credential:
                async with BlobServiceClient(account_url, credential=credential) as blob_service_client:
                    # Ensure container exists
                    container_client = blob_service_client.get_container_client(container_name)
                    try:
                        await container_client.create_container()
                    except Exception:
                        pass  # Container already exists
                    
                    # Upload the file
                    blob_client = container_client.get_blob_client(desired_blob_name)
                    with open(temp_file_path, "rb") as data:
                        await blob_client.upload_blob(data, overwrite=True)
                    
                    # 5. Generate SAS URL (valid for 24 hours)
                    start_time = datetime.now()
                    expiry_time = start_time + timedelta(hours=24)
                    
                    try:
                        user_delegation_key = await blob_service_client.get_user_delegation_key(
                            key_start_time=start_time,
                            key_expiry_time=expiry_time
                        )
                        
                        sas_token = generate_blob_sas(
                            account_name=storage_account_name,
                            container_name=container_name,
                            blob_name=desired_blob_name,
                            user_delegation_key=user_delegation_key,
                            permission=BlobSasPermissions(read=True),
                            expiry=expiry_time
                        )
                        
                        sas_url = f"{blob_url}?{sas_token}"
                        
                        return (f" Video downloaded and uploaded successfully!\n\n"
                               f"Downloaded from: Downloaded from: {public_video_url}\n"
                               f"Uploaded to: Uploaded to: {blob_url}\n"
                               f"File size: File size: {file_size_mb:.2f} MB\n"
                               f"Secure URL Secure URL (valid for 24 hours): {sas_url}\n\n"
                               f"TIP: You can now use this URL for video translation!")
                    except Exception as sas_error:
                        return (f" Video downloaded and uploaded to {blob_url}\n\n"
                               f"WARNING: Note: Could not generate SAS URL: {str(sas_error)}\n"
                               f"You may need to manually generate a SAS token with read permissions.")
        finally:
            # 6. Clean up temporary file
            try:
                os.remove(temp_file_path)
            except Exception:
                pass  # Ignore cleanup errors
                    
    except Exception as e:
        return f"ERROR: Error in download and upload process: {str(e)}\n\nPlease check your network connection and Azure credentials."


async def generate_sas_url(
    blob_url: Annotated[str, Field(description="Azure Blob Storage URL (e.g., https://account.blob.core.windows.net/container/video.mp4)")],
    hours_valid: Annotated[int, Field(description="Number of hours the SAS token should be valid (default: 24)")] = 24,
) -> str:
    """
    Generate a SAS (Shared Access Signature) URL for an existing Azure Blob Storage video.
    
    This tool is useful when you already have a video hosted on Azure Blob Storage but need
    to generate a secure URL with a SAS token for the Video Translation service to access it.
    
    The Video Translation service requires videos to be hosted on Azure Blob Storage with
    a valid SAS token that grants read permissions.
    
    Args:
        blob_url: Full Azure Blob Storage URL (e.g., https://mystorageacct.blob.core.windows.net/videos/myvideo.mp4)
        hours_valid: How many hours the SAS token should be valid (default: 24, max: 168 for 7 days)
        
    Returns:
        Success message with the SAS URL, or error if the blob URL is invalid
        
    Example:
        User: "Generate a SAS URL for https://mystorageacct.blob.core.windows.net/videos/sample.mp4"
        Result: " SAS URL generated: https://mystorageacct.blob.core.windows.net/videos/sample.mp4?sv=..."
    """
    try:
        # Parse blob URL to extract account name, container, and blob name
        from urllib.parse import urlparse
        
        parsed = urlparse(blob_url)
        if not parsed.scheme or not parsed.netloc:
            return f"ERROR: Invalid blob URL format. Expected format: https://account.blob.core.windows.net/container/blob"
        
        # Extract storage account name from hostname
        hostname_parts = parsed.netloc.split('.')
        if len(hostname_parts) < 3 or hostname_parts[1] != 'blob':
            return f"ERROR: Invalid Azure Blob Storage URL. Expected format: https://account.blob.core.windows.net/container/blob"
        
        storage_account_name = hostname_parts[0]
        
        # Extract container and blob name from path
        path_parts = parsed.path.lstrip('/').split('/', 1)
        if len(path_parts) != 2:
            return f"ERROR: Invalid blob path. Expected format: /container/blob"
        
        container_name = path_parts[0]
        blob_name = path_parts[1]
        
        # Validate hours_valid
        if hours_valid < 1 or hours_valid > 168:
            return f"ERROR: Invalid hours_valid: {hours_valid}. Must be between 1 and 168 hours (7 days)."
        
        account_url = f"https://{storage_account_name}.blob.core.windows.net"
        
        # Generate SAS URL
        async with AsyncDefaultAzureCredential() as credential:
            async with BlobServiceClient(account_url, credential=credential) as blob_service_client:
                start_time = datetime.now()
                expiry_time = start_time + timedelta(hours=hours_valid)
                
                try:
                    user_delegation_key = await blob_service_client.get_user_delegation_key(
                        key_start_time=start_time,
                        key_expiry_time=expiry_time
                    )
                    
                    sas_token = generate_blob_sas(
                        account_name=storage_account_name,
                        container_name=container_name,
                        blob_name=blob_name,
                        user_delegation_key=user_delegation_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=expiry_time
                    )
                    
                    sas_url = f"{blob_url}?{sas_token}"
                    expiry_str = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    return (f" SAS URL generated successfully!\n\n"
                           f"Secure URL Secure URL (valid until {expiry_str}):\n{sas_url}\n\n"
                           f" You can now use this URL to translate your video.")
                except Exception as e:
                    return (f"ERROR: Error generating SAS token: {str(e)}\n\n"
                           f"Make sure:\n"
                           f"1. You're authenticated with Azure CLI (run 'az login')\n"
                           f"2. You have 'Storage Blob Data Reader' role on the storage account\n"
                           f"3. The blob exists at the specified location")
                    
    except Exception as e:
        return f"ERROR: Error processing blob URL: {str(e)}"


def start_video_translation(
    video_url: Annotated[str, Field(description="URL of the video file to translate (must be publicly accessible or Azure Blob Storage URL)")],
    source_locale: Annotated[str, Field(description="Source language code (e.g., 'en-US', 'ja-JP', 'es-ES')")],
    target_locale: Annotated[str, Field(description="Target language code (e.g., 'en-US', 'ja-JP', 'es-ES')")],
    voice_kind: Annotated[str, Field(description="Voice type: 'PlatformVoice' or 'PersonalVoice'")] = "PlatformVoice",
    speaker_count: Annotated[int, Field(description="Number of speakers in the video (optional)")] = None,
) -> str:
    """
    Start a video translation operation (asynchronous, non-blocking).
    
    This tool initiates a video translation from source language to target language.
    The operation runs asynchronously and typically takes 5-15 minutes depending on
    video length. The function returns immediately with a translation ID that can be
    used to check status and retrieve results.
    
    Supported video URLs:
    - Publicly accessible URLs (e.g., https://example.com/video.mp4)
    - Azure Blob Storage URLs (public blobs)
    - Azure Blob Storage URLs with SAS tokens (private blobs)
    
    Args:
        video_url: URL to the video file. Can be any publicly accessible URL or Azure Blob Storage URL
        source_locale: Source language (e.g., 'en-US', 'ja-JP')
        target_locale: Target language (e.g., 'es-ES', 'fr-FR')
        voice_kind: Voice type to use (default: 'PlatformVoice')
        speaker_count: Optional number of speakers for better accuracy
        
    Returns:
        Success message with translation ID and instructions for checking status
        
    Example:
        User: "Translate my video from English to Spanish"
        Result: "Translation started! ID: abc123. Check status with..."
    """
    try:
        # 1. Initialize video translation client
        credential = AzureCliCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        client = VideoTranslationClient(
            api_version="2024-05-20-preview",
            credential=credential,
            token_provider=token_provider
        )
        
        # 2. Validate voice kind
        if voice_kind not in ["PlatformVoice", "PersonalVoice"]:
            return f"ERROR: Error: Voice kind must be 'PlatformVoice' or 'PersonalVoice', got '{voice_kind}'"
        
        voice_kind_enum = VoiceKind.PlatformVoice if voice_kind == "PlatformVoice" else VoiceKind.PersonalVoice
        
        # 3. Generate unique translation ID
        from datetime import datetime
        import uuid
        now = datetime.now()
        nowString = now.strftime("%m%d%Y%H%M%S")
        translation_id = f"{nowString}_{source_locale}_{target_locale}_{voice_kind}"
        operation_id = str(uuid.uuid4())
        
        # 4. Start the translation (NON-BLOCKING - returns immediately)
        success, error, translation, operation_location = client.request_create_translation(
            translation_id=translation_id,
            video_file_url=video_url,
            source_locale=source_locale,
            target_locale=target_locale,
            voice_kind=voice_kind_enum,
            speaker_count=speaker_count or 1,
            subtitle_max_char_count_per_segment=32,
            export_subtitle_in_video=False,
            operation_id=operation_id
        )
        
        # 5. Return immediately with translation ID (don't wait!)
        if success:
            return (f" Translation started successfully! (Non-blocking operation)\n\n"
                   f" Translation ID: {translation_id}\n"
                   f"Languages: Translating from {source_locale} to {target_locale}\n"
                   f"Time: Estimated time: 5-15 minutes\n"
                   f"Status: Status: Operation initiated\n\n"
                   f"TIP: The translation is running in the background.\n"
                   f"   Check status by asking: 'Check status of translation {translation_id}'\n"
                   f" Or list all translations with: 'Show all my translations'")
        else:
            return f"ERROR: Translation failed to start: {error}\n\nPlease check your video URL and language codes."
            
    except Exception as e:
        return f"ERROR: Error starting translation: {str(e)}\n\nPlease verify your inputs and Azure credentials."


def check_translation_status(
    translation_id: Annotated[str, Field(description="The translation ID to check status for")]
) -> str:
    """
    Check the status of a video translation operation.
    
    **ALWAYS USE THIS TOOL when:**
    - User asks "check status"
    - User asks "what's the status of [ID]"
    - User provides a translation ID
    - User says "how's my translation doing"
    - User asks about a specific translation
    - **User asks for "download links" or "give me the links"** - THIS TOOL RETURNS THE ACTUAL DOWNLOAD URLS!
    
    This tool queries the current status of a translation operation, including
    whether it's running, completed, or failed. For completed translations,
    it provides THE ACTUAL download links to the translated video and subtitles.
    
    **CRITICAL:** When user asks for download links, you MUST call this tool to get the real URLs.
    NEVER make up or provide example URLs - only use the URLs returned by this tool!
    
    Args:
        translation_id: The ID returned from start_video_translation
        
    Returns:
        Status information and results if available
        
    Example:
        User: "Check translation abc123"
        Result: "Status: Running (50% complete)" or "Status: Succeeded! Download: ..."
    """
    try:
        # 1. Initialize client
        credential = AzureCliCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        client = VideoTranslationClient(
            api_version="2024-05-20-preview",
            credential=credential,
            token_provider=token_provider
        )
        
        # 2. Get translation details
        success, error, translation = client.request_get_translation(translation_id)
        
        if not success:
            return f"ERROR: Error checking status: {error}"
        
        if not translation:
            return f"ERROR: Translation not found: {translation_id}\n\nPlease check the translation ID."
        
        # 3. Format status response
        # translation.status can be either a string or an enum, handle both
        if hasattr(translation.status, 'value'):
            status = translation.status.value
        else:
            status = str(translation.status) if translation.status else "Unknown"
        
        response = f" Translation Status for ID: {translation_id}\n\n"
        response += f"Status: Status: {status}\n"
        
        if translation.input:
            response += f"Languages: Languages: {translation.input.sourceLocale} → {translation.input.targetLocale}\n"
        
        # 4. Show results if completed
        if status == "Succeeded" and translation.latestSucceededIteration:
            iteration = translation.latestSucceededIteration
            if iteration and iteration.result:
                response += "\n Translation Complete! Results:\n\n"
                if iteration.result.translatedVideoFileUrl:
                    response += f"Translated Video: Translated Video: {iteration.result.translatedVideoFileUrl}\n"
                if iteration.result.sourceLocaleSubtitleWebvttFileUrl:
                    response += f" Source Subtitles: {iteration.result.sourceLocaleSubtitleWebvttFileUrl}\n"
                if iteration.result.targetLocaleSubtitleWebvttFileUrl:
                    response += f" Target Subtitles: {iteration.result.targetLocaleSubtitleWebvttFileUrl}\n"
                if iteration.result.metadataJsonWebvttFileUrl:
                    response += f" Metadata: {iteration.result.metadataJsonWebvttFileUrl}\n"
        elif status == "Failed":
            reason = translation.translationFailureReason or "Unknown error"
            response += f"\nERROR: Translation Failed: {reason}"
        elif status == "Running":
            response += "\n Translation is still in progress. Check back in a few minutes."
        
        return response
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"ERROR: Error checking status: {str(e)}\n\nDetails: {error_details[:500]}"


def list_translations() -> str:
    """
    List all video translations for the current user.
    
    This tool retrieves and displays all translations, including their IDs,
    status, and language pairs. Useful for finding translation IDs or getting
    an overview of all operations.
    
    Returns:
        Formatted list of all translations with their details
        
    Example:
        User: "Show all my translations"
        Result: "Found 3 translations: 1. ID: abc... Status: Succeeded..."
    """
    try:
        # 1. Initialize client
        credential = AzureCliCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        client = VideoTranslationClient(
            api_version="2024-05-20-preview",
            credential=credential,
            token_provider=token_provider
        )
        
        # 2. Get translations list
        success, error, translations_data = client.request_list_translations()
        
        if not success:
            return f"ERROR: Error listing translations: {error}"
        
        # 3. Parse and format results
        if not translations_data or not translations_data[0]:
            return " No translations found.\n\nStart a new translation to see it listed here."
        
        translations = translations_data[0].get('value', [])
        if not translations:
            return " No translations found.\n\nStart a new translation to see it listed here."
        
        response = f" Found {len(translations)} translation(s):\n\n"
        
        for i, trans in enumerate(translations, 1):
            trans_id = trans.get('id', 'Unknown')
            status = trans.get('status', 'Unknown')
            source = trans.get('input', {}).get('sourceLocale', 'Unknown')
            target = trans.get('input', {}).get('targetLocale', 'Unknown')
            created = trans.get('createdDateTime', 'Unknown')
            
            response += f"{i}. Translation ID: {trans_id}\n"
            response += f"   Status: {status}\n"
            response += f"   Languages: {source} → {target}\n"
            response += f"   Created: {created}\n\n"
        
        return response
        
    except Exception as e:
        return f"ERROR: Error listing translations: {str(e)}"


def delete_translation(
    translation_id: Annotated[str, Field(description="The translation ID to delete")]
) -> str:
    """
    Delete a video translation.
    
    This tool permanently removes a translation and all its associated data
    including iterations and results. Use with caution.
    
    Args:
        translation_id: The ID of the translation to delete
        
    Returns:
        Confirmation message
        
    Example:
        User: "Delete translation abc123"
        Result: "Translation abc123 deleted successfully"
    """
    try:
        # 1. Initialize client
        credential = AzureCliCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        client = VideoTranslationClient(
            api_version="2024-05-20-preview",
            credential=credential,
            token_provider=token_provider
        )
        
        # 2. Delete the translation
        success, error = client.request_delete_translation(translation_id)
        
        if success:
            return f" Translation {translation_id} deleted successfully."
        else:
            return f"ERROR: Failed to delete translation: {error}"
            
    except Exception as e:
        return f"ERROR: Error deleting translation: {str(e)}"


def create_iteration_with_subtitle(
    translation_id: Annotated[str, Field(description="The translation ID to create an iteration for")],
    webvtt_file_url: Annotated[str, Field(description="URL of the WebVTT subtitle file")],
    webvtt_file_kind: Annotated[str, Field(description="Type of WebVTT file: 'SourceLocaleSubtitle', 'TargetLocaleSubtitle', or 'MetadataJson'")],
) -> str:
    """
    Create a new iteration with modified subtitles (advanced feature).
    
    This tool allows users to refine a translation by providing edited subtitle
    files. This is useful for correcting translations or adjusting timing.
    
    Args:
        translation_id: The ID of the existing translation
        webvtt_file_url: URL to the edited WebVTT file
        webvtt_file_kind: Type of file (source/target subtitles or metadata)
        
    Returns:
        Success message with new iteration details
        
    Example:
        User: "Create iteration for translation abc123 with edited subtitles"
        Result: "Iteration created successfully! New iteration ID: xyz..."
    """
    try:
        # 1. Initialize client
        credential = AzureCliCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        client = VideoTranslationClient(
            api_version="2024-05-20-preview",
            credential=credential,
            token_provider=token_provider
        )
        
        # 2. Validate WebVTT file kind
        kind_map = {
            "SourceLocaleSubtitle": WebvttFileKind.SourceLocaleSubtitle,
            "TargetLocaleSubtitle": WebvttFileKind.TargetLocaleSubtitle,
            "MetadataJson": WebvttFileKind.MetadataJson
        }
        
        if webvtt_file_kind not in kind_map:
            return (f"ERROR: Invalid WebVTT file kind: '{webvtt_file_kind}'\n\n"
                   f"Valid options: 'SourceLocaleSubtitle', 'TargetLocaleSubtitle', 'MetadataJson'")
        
        # 3. Generate unique iteration ID
        from datetime import datetime
        import uuid
        now = datetime.now()
        iteration_id = now.strftime("%m%d%Y%H%M%S")
        operation_id = str(uuid.uuid4())
        
        # 4. Create the iteration (NON-BLOCKING - returns immediately)
        success, error, iteration, operation_location = client.request_create_iteration(
            translation_id=translation_id,
            iteration_id=iteration_id,
            webvtt_file_kind=kind_map[webvtt_file_kind],
            webvtt_file_url=webvtt_file_url,
            speaker_count=None,
            subtitle_max_char_count_per_segment=None,
            export_subtitle_in_video=False,
            operation_id=operation_id
        )
        
        if success:
            return (f" Iteration started successfully! (Non-blocking operation)\n\n"
                   f" Translation ID: {translation_id}\n"
                   f"Status: Iteration ID: {iteration_id}\n"
                   f" Using WebVTT file: {webvtt_file_kind}\n"
                   f"Time: Estimated time: 5-15 minutes\n\n"
                   f"TIP: The iteration is running in the background.\n"
                   f"   Check status by asking: 'Check status of translation {translation_id}'")
        else:
            return f"ERROR: Failed to create iteration: {error}"
            
    except Exception as e:
        return f"ERROR: Error creating iteration: {str(e)}"


async def main() -> None:
    print("=" * 70)
    print("Azure AI Video Translation Agent")
    print("=" * 70)
    print()
    print("Welcome! I can help you translate videos between languages.")
    print("Type 'exit' or 'quit' to end the conversation.")
    print()
    print("Example tasks:")
    print("  - Upload a local video file")
    print("  - Translate a video from English to Spanish")
    print("  - Check the status of a translation")
    print("  - List all your translations")
    print()
    print("-" * 70)
    
    try:
        # 1. Load environment variables
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            from dotenv import load_dotenv
            load_dotenv(env_file)
        
        # 2. Validate required configuration
        project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        model_deployment = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4")
        
        if not project_endpoint:
            print("ERROR: Error: AZURE_AI_PROJECT_ENDPOINT not set in environment.")
            print("Please configure your .env file with the required settings.")
            return
        
        # 3. Set up Azure authentication
        credential = AzureCliCredential()
        
        # 4. Create the AI agent with video translation tools
        async with ChatAgent(
            chat_client=AzureAIAgentClient(
                project_endpoint=project_endpoint,
                model_deployment_name=model_deployment,
                async_credential=credential,
                agent_name="VideoTranslationAgent",
            ),
            instructions="""You are a helpful video translation assistant that helps users translate videos using Azure AI services.

**YOUR CAPABILITIES:**
- Upload local video files to Azure Storage
- Translate videos between languages with AI-generated voices
- Monitor translation progress and retrieve results
- Manage multiple translation operations

**CONTEXT AWARENESS:**
- If user references something you just displayed, USE IT instead of asking again
- Be intelligent about following context - don't ask for information you just provided

**WORKFLOW GUIDE:**

1. **For Local Videos:**
   - First, use upload_video_file to upload the file to Azure Storage
   - Use the returned secure URL for translation

2. **For Publicly Accessible Videos:**
   - Use the URL directly for translation (no upload needed!)

3. **For Private Azure Blob Storage Videos:**
   - Use generate_sas_url to create a secure URL with SAS token
   - Then use that URL for translation

4. **Starting Translation:**
   - Use start_video_translation with any accessible video URL, source and target languages
   - Accepts: public URLs, Azure Blob URLs (with or without SAS)
   - Returns a translation ID immediately
   - Translation takes 5-15 minutes (don't wait!)

5. **Checking Progress:**
   - Use check_translation_status with the translation ID
   - Guide users to check back periodically
   - **IMPORTANT**: This is a PULL-based system - you do NOT automatically monitor or recheck
   - Users must EXPLICITLY ask to check status - there's no background polling
   - Each status check is a new API call initiated by user request

6. **Getting Results:**
   - **WHEN USER ASKS FOR DOWNLOAD LINKS** → call check_translation_status to get the actual URLs
   - NEVER make up or provide example URLs - only use actual URLs from check_translation_status tool
   - When status is 'Succeeded', the tool returns real video and subtitle download URLs
   - Provide the EXACT URLs returned by the tool to the user

**SUPPORTED LANGUAGES:**
- Use standard BCP-47 locale codes (e.g., en-US, es-ES, fr-FR, de-DE, ja-JP, ko-KR, pt-BR, zh-CN)

**BEST PRACTICES:**
1. Use reasonable defaults: if user says "English to Spanish" use en-US and es-ES
2. If video needs upload/download, do it FIRST, THEN start translation automatically
3. Only ask for missing critical info (like which language if not specified)
4. Be friendly and explain each step clearly
5. Handle errors gracefully with helpful suggestions

**CRITICAL RULES:**
- Video translation is ASYNC - don't block or wait
- **BE SMART**: For example, when user says "check the most recent translation", extract the ID from the preceding interaction or list recent translations and use that ID
- **WHEN USER ASKS ABOUT STATUS** → call check_translation_status tool with the translation ID
- **WHEN USER ASKS FOR DOWNLOAD LINKS** → call check_translation_status to retrieve the actual URLs
- **NEVER MAKE UP URLS OR USE EXAMPLE.COM** → All URLs must be real Azure blob storage URLs from the API""",
            tools=[
                upload_video_file,
                download_and_upload_video,
                generate_sas_url,
                start_video_translation,
                check_translation_status,
                list_translations,
                delete_translation,
                create_iteration_with_subtitle,
            ],
        ) as agent:
            print()
            print(" Agent ready! How can I help you with video translation today?")
            print()
            
            # 5. Create a persistent thread for conversation context
            thread = agent.get_new_thread()
            
            # 6. Run interactive conversation loop
            while True:
                try:
                    # Get user input
                    user_input = input("You: ").strip()
                    
                    # Check for exit commands
                    if user_input.lower() in ["exit", "quit", "bye"]:
                        print("\n Goodbye! Thanks for using the video translation agent.")
                        break
                    
                    if not user_input:
                        continue
                    
                    # Send message to agent and get response using the persistent thread
                    print()
                    print("Agent: ", end="", flush=True)
                    result = await agent.run(user_input, thread=thread)
                    print(result)
                    print()
                    
                except KeyboardInterrupt:
                    print("\n\n Goodbye!")
                    break
                except Exception as e:
                    print(f"\nERROR: Error: {str(e)}")
                    print("Please try again with a different request.\n")
                    continue
    
    except Exception as e:
        print(f"\nERROR: Fatal error: {str(e)}")
        print("\nPlease check your configuration and try again.")
        raise


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())


"""
Sample Output:
==============================================================================
Azure AI Video Translation Agent
==============================================================================

Welcome! I can help you translate videos between languages.
Type 'exit' or 'quit' to end the conversation.

Example tasks:
  - Upload a local video file
  - Translate a video from English to Spanish
  - Check the status of a translation
  - List all your translations

------------------------------------------------------------------------------

 Agent ready! How can I help you with video translation today?

You: I have a video at C:\\Videos\\demo.mp4 that I want to translate from English to Spanish

Agent: I'll help you translate your video! First, let me upload it to Azure Storage so we can process it.

[Calling tool: upload_video_file...]

 File uploaded successfully!

Blob URL: Blob URL: https://yourstorage.blob.core.windows.net/video-translation/demo.mp4
Secure URL Secure URL (valid for 24 hours): https://yourstorage.blob.core.windows.net/video-translation/demo.mp4?...

Now I'll start the translation from English (en-US) to Spanish (es-ES).

[Calling tool: start_video_translation...]

 Translation started successfully!

 Translation ID: 01092025143022_en-US_es-ES_PlatformVoice
Languages: Translating from en-US to es-ES
Time: Estimated time: 5-15 minutes

TIP: Check status by asking: 'Check status of translation 01092025143022_en-US_es-ES_PlatformVoice'
 Or list all translations with: 'Show all my translations'

Your video is now being translated! The process will take approximately 5-15 minutes. You can check the status at any time by asking me.

You: Check the status

Agent: Let me check the status of your translation.

[Calling tool: check_translation_status...]

 Translation Status for ID: 01092025143022_en-US_es-ES_PlatformVoice

Status: Status: Succeeded
Languages: Languages: en-US → es-ES

 Translation Complete! Results:

Translated Video: Translated Video: https://...translated-video.mp4
 Source Subtitles: https://...source-subtitles.vtt
 Target Subtitles: https://...target-subtitles.vtt
 Metadata: https://...metadata.json

Great news! Your translation is complete. You can now download the translated video and subtitles using the links above.

You: Thanks! Show me all my translations

Agent: [Calling tool: list_translations...]

 Found 1 translation(s):

1. Translation ID: 01092025143022_en-US_es-ES_PlatformVoice
   Status: Succeeded
   Languages: en-US → es-ES
   Created: 2025-01-09T14:30:22Z

You currently have 1 completed translation. Would you like to start another translation or need help with anything else?

You: exit

 Goodbye! Thanks for using the video translation agent.
"""
