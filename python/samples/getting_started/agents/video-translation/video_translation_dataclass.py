# Copyright (c) Microsoft. All rights reserved.

import locale
from dataclasses import dataclass
from datetime import datetime

from urllib3.util import Url
from video_translation_enum import OneApiState, OperationStatus, VoiceKind, WebvttFileKind


@dataclass(kw_only=True)
class OperationDefinition:
    id: str
    status: OperationStatus


@dataclass(kw_only=True)
class TranslationInputBaseDefinition:
    speakerCount: int | None = None
    exportSubtitleInVideo: bool | None = None
    subtitleMaxCharCountPerSegment: int | None = None


@dataclass(kw_only=True)
class WebvttFileDefinition:
    url: Url
    kind: WebvttFileKind


@dataclass(kw_only=True)
class TranslationInputDefinition(TranslationInputBaseDefinition):
    # This is optional because the moment after translation created, API has not downloaded video file to server side yet.
    videoFileUrl: str | None = None
    sourceLocale: locale
    targetLocale: locale
    voiceKind: VoiceKind


@dataclass(kw_only=True)
class StatelessResourceBaseDefinition:
    id: str | None = None
    displayName: str | None = None
    description: str | None = None
    createdDateTime: datetime | None = None


@dataclass(kw_only=True)
class StatefulResourceBaseDefinition(StatelessResourceBaseDefinition):
    status: OneApiState | None = None
    lastActionDateTime: datetime | None = None


@dataclass(kw_only=True)
class IterationInputDefinition(TranslationInputBaseDefinition):
    webvttFile: WebvttFileDefinition | None = None


@dataclass(kw_only=True)
class IterationResultDefinition:
    translatedVideoFileUrl: Url | None = None
    sourceLocaleSubtitleWebvttFileUrl: Url | None = None
    targetLocaleSubtitleWebvttFileUrl: Url | None = None
    metadataJsonWebvttFileUrl: Url | None = None


@dataclass(kw_only=True)
class IterationDefinition(StatefulResourceBaseDefinition):
    input: IterationInputDefinition
    result: IterationResultDefinition | None = None
    iterationFailureReason: str | None = None


@dataclass(kw_only=True)
class TranslationDefinition(StatefulResourceBaseDefinition):
    input: TranslationInputDefinition
    latestIteration: IterationDefinition | None = None
    latestSucceededIteration: IterationDefinition | None = None
    translationFailureReason: str | None = None


@dataclass(kw_only=True)
class PagedTranslationDefinition:
    value: list[TranslationDefinition]
    nextLink: Url | None = None


@dataclass(kw_only=True)
class PagedIterationDefinition:
    value: list[IterationDefinition]
    nextLink: Url | None = None
