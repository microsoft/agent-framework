# Copyright (c) Microsoft. All rights reserved.

import dataclasses
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import orjson
import urllib3
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from termcolor import colored
from urllib3.util import Url, parse_url
from video_translation_dataclass import (
    IterationDefinition,
    IterationInputDefinition,
    OperationDefinition,
    PagedIterationDefinition,
    PagedTranslationDefinition,
    TranslationDefinition,
    WebvttFileDefinition,
)
from video_translation_enum import OperationStatus, VoiceKind, WebvttFileKind
from video_translation_util import append_url_args, dict_to_dataclass

logger = logging.getLogger(__name__)

HTTP_HEADERS_OPERATION_LOCATION = "Operation-Location"


class VideoTranslationClient:
    URL_SEGMENT_NAME_TRANSLATIONS = "translations"
    URL_SEGMENT_NAME_ITERATIONS = "iterations"
    URL_PATH_ROOT = "videotranslation"

    VIDEO_TRANSLATION_SCOPE = "https://cognitiveservices.azure.com/.default"

    def __init__(
        self,
        api_version: str,
        credential: TokenCredential | None = None,
        token_provider: Callable[[], str] | None = None,
    ):
        """
        Initialize the Video Translation client.

        Args:
            api_version: API version to use (e.g. "2024-05-20-preview")
            credential: Azure credential for token-based authentication
            token_provider: Optional token provider function from get_bearer_token_provider
        """
        if credential and not token_provider:
            token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

        if not credential and not token_provider:
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

        self.api_version = api_version
        self.credential: TokenCredential | None = credential
        self.token_provider: Callable[[], str] | None = token_provider
        self.token: str | None = None
        self.token_expiry: datetime | None = None

        from urllib3.util import Timeout
        status_forcelist = tuple(
            {x for x in range(200, 600)} - {200, 201, 204, 400, 401, 403, 404, 409}
        )
        retries = urllib3.Retry(total=5, status_forcelist=status_forcelist)
        timeout = Timeout(10)
        self.http = urllib3.PoolManager(timeout=timeout, retries=retries)

    def get_auth_token(self) -> str | None:
        """Get an authentication token using the provided credential or token provider"""
        current_time = datetime.now()
        if self.token and self.token_expiry and current_time < self.token_expiry:
            return self.token

        try:
            if self.token_provider:
                token_response = self.token_provider()

                if token_response:
                    if isinstance(token_response, str):
                        self.token = token_response
                        # Set a default expiry time (1 hour) for string tokens
                        self.token_expiry = current_time + timedelta(hours=1)
                    else:
                        self.token = token_response.token
                        # Set token expiry (subtract 5 minutes for safety margin)
                        self.token_expiry = current_time + timedelta(minutes=55)

                    return self.token

            elif self.credential:
                scope = "https://cognitiveservices.azure.com/.default"
                access_token = self.credential.get_token(scope)

                if access_token and access_token.token:
                    self.token = access_token.token
                    self.token_expiry = current_time + timedelta(minutes=55)
                    return self.token
        except Exception as e:
            logger.exception(f"Failed to get authentication token: {str(e)}")

        return None

    def build_request_header(self) -> tuple[bool, dict[str, str] | str]:
        """Build the request headers with appropriate authentication"""
        headers = {"Content-Type": "application/json"}

        token = self.get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            return True, headers
        return False, "Authentication failed: Unable to obtain a valid token"

    def create_translate_and_run_first_iteration_until_terminated(
        self,
        video_file_url: Url,
        source_locale: str,
        target_locale: str,
        voice_kind: VoiceKind,
        speaker_count: int = 1,
        subtitle_max_char_count_per_segment: int = 32,
        export_subtitle_in_video: bool = False,
    ) -> tuple[bool, str | None, TranslationDefinition | None, IterationDefinition | None, str | None, str | None]:
        if video_file_url is None or source_locale is None or target_locale is None or voice_kind is None:
            raise ValueError

        now = datetime.now()
        nowString = now.strftime("%m%d%Y%H%M%S")
        translation_id = f"{nowString}_{source_locale}_{target_locale}_{voice_kind}"
        success, error, translation = self.create_translation_until_terminated(
            translation_id=translation_id,
            video_file_url=video_file_url,
            source_locale=source_locale,
            target_locale=target_locale,
            voice_kind=voice_kind,
        )
        if not success or translation is None:
            return False, error or "Translation creation failed", None, None, None, None

        translation_json_formatted_str = json.dumps(dataclasses.asdict(translation), indent=2)

        iteration_id = f"{nowString}_default"
        success, error, iteration = self.create_iteration_until_terminated(
            translation_id=translation_id,
            iteration_id=iteration_id,
            speaker_count=speaker_count,
            subtitle_max_char_count_per_segment=subtitle_max_char_count_per_segment,
            export_subtitle_in_video=export_subtitle_in_video,
        )
        if not success or iteration is None:
            return False, error or "Iteration creation failed", None, None, None, None

        iteration_json_formatted_str = json.dumps(dataclasses.asdict(iteration), indent=2)

        return True, None, translation, iteration, translation_json_formatted_str, iteration_json_formatted_str

    # For iteration from secondary, webvtt file is required.
    def run_iteration_with_webvtt_until_terminated(
        self,
        translation_id: str,
        webvtt_file_kind: WebvttFileKind,
        webvtt_file_url: Url,
        speaker_count: int = 1,
        subtitle_max_char_count_per_segment: int = 32,
        export_subtitle_in_video: bool = False,
    ) -> tuple[bool, str | None, TranslationDefinition | None, IterationDefinition | None]:
        if webvtt_file_kind is None or webvtt_file_url is None:
            raise ValueError

        success, error, translation = self.request_get_translation(
            translation_id=translation_id,
        )
        if not success:
            return False, error, None, None
        if translation is None:
            return False, f"Not found translation ID: {translation_id}", None, None

        now = datetime.now()
        iteration_id = now.strftime("%m%d%Y%H%M%S")

        success, error, iteration = self.create_iteration_until_terminated(
            translation_id=translation_id,
            iteration_id=iteration_id,
            webvtt_file_kind=webvtt_file_kind,
            webvtt_file_url=webvtt_file_url,
            speaker_count=speaker_count,
            subtitle_max_char_count_per_segment=subtitle_max_char_count_per_segment,
            export_subtitle_in_video=export_subtitle_in_video,
        )
        if not success:
            return False, error, None, None

        return True, None, translation, iteration

    def create_translation_until_terminated(
        self,
        translation_id: str,
        video_file_url: Url,
        source_locale: str,
        target_locale: str,
        voice_kind: VoiceKind,
    ) -> tuple[bool, str | None, TranslationDefinition | None]:
        operation_id = str(uuid.uuid4())
        success, error, response_translation, operation_location = self.request_create_translation(
            translation_id=translation_id,
            video_file_url=video_file_url.url if isinstance(video_file_url, Url) else video_file_url,
            source_locale=source_locale,
            target_locale=target_locale,
            voice_kind=voice_kind,
            speaker_count=1,
            subtitle_max_char_count_per_segment=32,
            export_subtitle_in_video=False,
            # translation_display_name = None,
            # translation_description = None,
            operation_id=operation_id,
        )
        if not success or operation_location is None:
            logger.error(colored(f"Failed to create translation with ID {translation_id} with error: {error}", "red"))
            return False, error, None

        self.request_operation_until_terminated(operation_location)

        success, error, response_translation = self.request_get_translation(translation_id)
        if not success or response_translation is None:
            logger.error(colored(f"Failed to query translation {translation_id} with error: {error}", "red"))
            return False, error, None
        if response_translation.status != OperationStatus.Succeeded:
            logger.error(colored(f"Translation creation failed with error: {error}", "red"))
            logger.debug(json.dumps(dataclasses.asdict(response_translation), indent=2))
            return False, response_translation.translationFailureReason, None

        return True, None, response_translation

    def request_operation_until_terminated(self, operation_location: Url):
        success, error, response_operation = self.request_get_operation(
            operation_location=operation_location, printUrl=True
        )
        if not success or response_operation is None:
            logger.error(
                colored(
                    f"Failed to query operation for translation creation operation "
                    f"from location {operation_location} with error: {error}",
                    "red",
                )
            )
            return error

        lastStatus = None
        while response_operation.status in [OperationStatus.Running, OperationStatus.NotStarted]:
            success, error, response_operation = self.request_get_operation(
                operation_location=operation_location, printUrl=False
            )
            if not success or response_operation is None:
                logger.error(
                    colored(
                        f"Failed to query operation for translation creation operation "
                        f"from location {operation_location} with error: {error}",
                        "red",
                    )
                )
                return error
            if lastStatus != response_operation.status:
                logger.debug(response_operation.status)
                lastStatus = response_operation.status
            logger.debug("Waiting...")
            time.sleep(5)

        return response_operation.status

    def create_iteration_until_terminated(
        self,
        translation_id: str,
        iteration_id: str,
        webvtt_file_kind: WebvttFileKind | None = None,
        webvtt_file_url: Url | None = None,
        speaker_count: int | None = None,
        subtitle_max_char_count_per_segment: int | None = None,
        export_subtitle_in_video: bool | None = None,
    ) -> tuple[bool, str | None, IterationDefinition | None]:
        if translation_id is None or iteration_id is None:
            raise ValueError
        success, error, response_iteration, operation_location = self.request_create_iteration(
            translation_id=translation_id,
            iteration_id=iteration_id,
            webvtt_file_kind=webvtt_file_kind,
            webvtt_file_url=webvtt_file_url,
            speaker_count=speaker_count,
            subtitle_max_char_count_per_segment=subtitle_max_char_count_per_segment,
            export_subtitle_in_video=export_subtitle_in_video,
            iteration_description=None,
            operation_id=None,
        )
        if not success:
            logger.error(
                colored(
                    f"Failed to create iteration with ID {iteration_id} for translation "
                    f"{translation_id} with error: {error}",
                    "red",
                )
            )
            return False, error, None

        if operation_location is None:
            return False, "Operation location was not returned", None
        
        self.request_operation_until_terminated(operation_location)

        success, error, response_iteration = self.request_get_iteration(translation_id, iteration_id)
        if not success or response_iteration is None:
            logger.error(
                colored(
                    f"Failed to query iteration {iteration_id} for translation {translation_id} with error: {error}",
                    "red",
                )
            )
            return False, error, None
        if response_iteration.status != OperationStatus.Succeeded:
            logger.error(colored(f"Iteration creation failed with error: {error}", "red"))
            logger.debug(json.dumps(dataclasses.asdict(response_iteration), indent=2))
            return False, response_iteration.iterationFailureReason, None

        return True, None, response_iteration

    def build_translations_path(self) -> str:
        return f"{self.URL_PATH_ROOT}/{self.URL_SEGMENT_NAME_TRANSLATIONS}"

    def build_translation_path(self, translation_id: str) -> str:
        if translation_id is None:
            raise ValueError
        translations_path = self.build_translations_path()
        return f"{translations_path}/{translation_id}"

    def build_iterations_path(self, translation_id: str) -> str:
        if translation_id is None:
            raise ValueError
        translation_path = self.build_translation_path(translation_id)
        return f"{translation_path}/{self.URL_SEGMENT_NAME_ITERATIONS}"

    def build_iteration_path(self, translation_id: str, iteration_id: str) -> str:
        if translation_id is None or iteration_id is None:
            raise ValueError
        iterations_path = self.build_iterations_path(translation_id)
        return f"{iterations_path}/{iteration_id}"

    def build_endpoint(self) -> str:
        endpoint = os.getenv("COGNITIVE_SERVICES_ENDPOINT")
        if not endpoint:
            raise ValueError("Video Translation endpoint environment variable was not provided")
        # Remove any protocol prefix if present
        if endpoint.startswith("https://"):
            endpoint = endpoint[8:]
        elif endpoint.startswith("http://"):
            endpoint = endpoint[7:]
        return endpoint

    def build_url(self, segments: str) -> str:
        if segments is None:
            raise ValueError
        endpoint = self.build_endpoint()
        if segments.startswith("/"):
            segments = segments[1:]
        return f"https://{endpoint}/{segments}?api-version={self.api_version}"

    def build_translations_url(self) -> str:
        path = self.build_translations_path()
        return self.build_url(path)

    def build_translation_url(self, translation_id: str) -> str:
        if translation_id is None:
            raise ValueError
        path = self.build_translation_path(translation_id)
        return self.build_url(path)

    def build_iterations_url(self, translation_id: str) -> str:
        if translation_id is None:
            raise ValueError
        path = self.build_iterations_path(translation_id)
        return self.build_url(path)

    def build_iteration_url(self, translation_id: str, iteration_id: str) -> str:
        if translation_id is None or iteration_id is None:
            raise ValueError
        path = self.build_iteration_path(translation_id, iteration_id)
        return self.build_url(path)

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/operation-operations/get-operation?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_get_operation(self, operation_location: Url, printUrl: bool) -> tuple[bool, str | None, OperationDefinition | None]:
        if operation_location is None:
            raise ValueError

        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None

        assert isinstance(headers_or_error, dict)
        response = self.http.request("GET", operation_location.url, headers=headers_or_error)

        #   OK = 200,
        #   NotFound = 404,
        if response.status == 200:
            response_json = response.json()
            response = dict_to_dataclass(data=response_json, dataclass_type=OperationDefinition)
            return True, None, response
        if response.status == 404:
            return True, None, None

        return False, response.reason, None

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/translation-operations/get-translation?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_get_translation(self, translation_id: str) -> tuple[bool, str | None, TranslationDefinition | None]:
        if translation_id is None:
            raise ValueError

        url = self.build_translation_url(translation_id)
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None

        assert isinstance(headers_or_error, dict)
        response = self.http.request("GET", url, headers=headers_or_error)

        #   OK = 200,
        #   NotFound = 404,
        if response.status == 200:
            response_translation_json = response.json()
            response_translation = dict_to_dataclass(
                data=response_translation_json, dataclass_type=TranslationDefinition
            )
            return True, None, response_translation
        if response.status == 404:
            return True, None, None

        return False, response.reason, None

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/iteration-operations/get-iteration?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_get_iteration(self, translation_id: str, iteration_id: str) -> tuple[bool, str | None, IterationDefinition | None]:
        if translation_id is None or iteration_id is None:
            raise ValueError

        url = self.build_iteration_url(translation_id, iteration_id)
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None

        assert isinstance(headers_or_error, dict)
        response = self.http.request("GET", url, headers=headers_or_error)

        #   OK = 200,
        #   NotFound = 404,
        if response.status == 200:
            response_iteration_json = response.json()
            response_iteration = dict_to_dataclass(data=response_iteration_json, dataclass_type=IterationDefinition)
            return True, None, response_iteration
        if response.status == 404:
            return True, None, None

        return False, response.reason, None

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/translation-operations/list-translation?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_list_translations(
        self, top: int | None = None, skip: int | None = None, maxPageSize: int | None = None
    ) -> tuple[bool, str | None, PagedTranslationDefinition | None]:
        url = self.build_translations_url()
        args = {}
        if top is not None:
            args["top"] = top
        if skip is not None:
            args["skip"] = skip
        if maxPageSize is not None:
            args["maxPageSize"] = maxPageSize

        url = append_url_args(url, args)

        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None

        assert isinstance(headers_or_error, dict)
        response = self.http.request("GET", url.url, headers=headers_or_error)

        #   OK = 200,
        if response.status not in [200]:
            error = response.data.decode("utf-8")
            return False, error, None
        response_translations_json = response.json()

        return True, None, response_translations_json

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/iteration-operations/list-iteration?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_list_iterations(self, translation_id: str) -> tuple[bool, str | None, PagedIterationDefinition | None]:
        url = self.build_iterations_url(translation_id)
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None

        assert isinstance(headers_or_error, dict)
        response = self.http.request("GET", url, headers=headers_or_error)

        #   OK = 200,
        if response.status not in [200]:
            error = response.data.decode("utf-8")
            return False, error, None
        response_iterations_json = response.json()
        return True, None, response_iterations_json

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/translation-operations/delete-translation?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_delete_translation(self, translation_id: str) -> tuple[bool, str | None]:
        url = self.build_translation_url(translation_id)
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error

        assert isinstance(headers_or_error, dict)
        response = self.http.request("DELETE", url, headers=headers_or_error)

        #   NoContent = 204,
        if response.status not in [204]:
            error = response.data.decode("utf-8")
            return False, error
        return True, None

    def generate_operation_id(self) -> str:
        """
        Generates a valid operation ID that meets API requirements:
        - Between 3-64 characters
        - Starts and ends with alphanumeric character
        - Contains only alphanumeric characters, period, underscore, or hyphen

        Returns:
            A valid operation ID string
        """
        # Create a clean UUID-based operation ID without dashes
        uuid_str = str(uuid.uuid4()).replace("-", "")
        # Prefix with "op" to ensure it starts with a letter
        return f"op{uuid_str}"[:64]  # Trim to max 64 chars if needed

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/translation-operations/create-translation?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_create_translation(
        self,
        translation_id: str,
        video_file_url: str,
        source_locale: str,
        target_locale: str,
        voice_kind: VoiceKind,
        speaker_count: int = 1,
        subtitle_max_char_count_per_segment: int = 32,
        export_subtitle_in_video: bool = False,
        translation_display_name: str | None = None,
        translation_description: str | None = None,
        operation_id: str | None = None,
    ) -> tuple[bool, str | None, TranslationDefinition | None, Url | None]:
        if (
            translation_id is None
            or video_file_url is None
            or source_locale is None
            or target_locale is None
            or voice_kind is None
        ):
            raise ValueError

        if not operation_id:
            operation_id = self.generate_operation_id()

        input_body: dict[str, Any] = {
            "sourceLocale": source_locale,
            "targetLocale": target_locale,
            "voiceKind": voice_kind.value,
            "videoFileUrl": video_file_url,
        }

        if speaker_count is not None:
            input_body["speakerCount"] = speaker_count

        if subtitle_max_char_count_per_segment is not None:
            input_body["subtitleMaxCharCountPerSegment"] = subtitle_max_char_count_per_segment

        if export_subtitle_in_video is not None:
            input_body["exportSubtitleInVideo"] = export_subtitle_in_video

        translation_create_body: dict[str, Any] = {"input": input_body}

        # Add optional fields only if they are provided
        if translation_display_name:
            translation_create_body["displayName"] = translation_display_name

        if translation_description:
            translation_create_body["description"] = translation_description

        encoded_translation_create_body = orjson.dumps(translation_create_body)

        url = self.build_translation_url(translation_id)
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None, None

        assert isinstance(headers_or_error, dict)
        headers_or_error["Operation-Id"] = operation_id

        response = self.http.request("PUT", url, headers=headers_or_error, body=encoded_translation_create_body)

        # Handle authentication errors specifically
        if response.status == 401:
            error_message = response.data.decode("utf-8")
            return False, f"Authentication failed: {error_message}", None, None

        #   OK = 200,
        #   Created = 201,
        if response.status not in [200, 201]:
            error = response.data.decode("utf-8")
            return False, error, None, None
        response_translation_json = response.json()
        response_translation = dict_to_dataclass(data=response_translation_json, dataclass_type=TranslationDefinition)
        operation_location = response.headers[HTTP_HEADERS_OPERATION_LOCATION]
        operation_location_url = parse_url(operation_location)
        return True, None, response_translation, operation_location_url

    # https://learn.microsoft.com/rest/api/aiservices/videotranslation/iteration-operations/create-iteration?view=rest-aiservices-videotranslation-2024-05-20-preview&tabs=HTTP
    def request_create_iteration(
        self,
        translation_id: str,
        iteration_id: str,
        webvtt_file_kind: WebvttFileKind | None = None,
        webvtt_file_url: Url | None = None,
        speaker_count: int | None = None,
        subtitle_max_char_count_per_segment: int | None = None,
        export_subtitle_in_video: bool | None = None,
        iteration_description: str | None = None,
        operation_id: str | None = None,
    ) -> tuple[bool, str | None, IterationDefinition | None, Url | None]:
        if translation_id is None or iteration_id is None:
            raise ValueError

        if not operation_id:
            operation_id = self.generate_operation_id()

        translation_create_input_body = IterationInputDefinition(
            speakerCount=speaker_count,
            exportSubtitleInVideo=export_subtitle_in_video,
            subtitleMaxCharCountPerSegment=subtitle_max_char_count_per_segment,
        )

        if webvtt_file_kind is not None and webvtt_file_url is not None:
            translation_create_input_body.webvttFile = WebvttFileDefinition(
                kind=webvtt_file_kind,
                url=webvtt_file_url,
            )

        iteration_create_body = IterationDefinition(
            input=translation_create_input_body,
            description=iteration_description,
        )

        encoded_iteration_create_body = orjson.dumps(dataclasses.asdict(iteration_create_body))
        url = self.build_iteration_url(translation_id, iteration_id)
        if operation_id is None:
            operation_id = str(uuid.uuid4())
        success, headers_or_error = self.build_request_header()
        if not success:
            assert isinstance(headers_or_error, str)
            return False, headers_or_error, None, None

        assert isinstance(headers_or_error, dict)
        headers_or_error["Operation-Id"] = operation_id

        response = self.http.request("PUT", url, headers=headers_or_error, body=encoded_iteration_create_body)

        if response.status == 401:
            error_message = response.data.decode("utf-8")
            return False, f"Authentication failed: {error_message}", None, None

        #   OK = 200,
        #   Created = 201,
        if response.status not in [200, 201]:
            error = response.data.decode("utf-8")
            return False, error, None, None
        response_iteration_json = response.json()
        response_iteration = dict_to_dataclass(data=response_iteration_json, dataclass_type=IterationDefinition)
        operation_location = response.headers[HTTP_HEADERS_OPERATION_LOCATION]
        operation_location_url = parse_url(operation_location)
        return True, None, response_iteration, operation_location_url
