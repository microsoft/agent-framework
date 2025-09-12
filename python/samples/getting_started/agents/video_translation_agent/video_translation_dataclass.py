# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

import locale
from datetime import datetime
from dataclasses import dataclass
from urllib3.util import Url
from typing import Optional

from video_translation_enum import OperationStatus, WebvttFileKind, VoiceKind, OneApiState


@dataclass(kw_only=True)
class OperationDefinition():
    id: str
    status: OperationStatus


@dataclass(kw_only=True)
class TranslationInputBaseDefinition():
    speakerCount: Optional[int] = None
    exportSubtitleInVideo: Optional[bool] = None
    subtitleMaxCharCountPerSegment: Optional[int] = None


@dataclass(kw_only=True)
class WebvttFileDefinition():
    url: Url
    kind: WebvttFileKind


@dataclass(kw_only=True)
class TranslationInputDefinition(TranslationInputBaseDefinition):
    # This is optional because the moment after translation created, API has not downloaded video file to server side yet.
    videoFileUrl: Optional[str] = None
    sourceLocale: locale
    targetLocale: locale
    voiceKind: VoiceKind


@dataclass(kw_only=True)
class StatelessResourceBaseDefinition():
    id: Optional[str] = None
    displayName: Optional[str] = None
    description: Optional[str] = None
    createdDateTime: Optional[datetime] = None


@dataclass(kw_only=True)
class StatefulResourceBaseDefinition(StatelessResourceBaseDefinition):
    status: Optional[OneApiState] = None
    lastActionDateTime: Optional[datetime] = None


@dataclass(kw_only=True)
class IterationInputDefinition(TranslationInputBaseDefinition):
    webvttFile: Optional[WebvttFileDefinition] = None


@dataclass(kw_only=True)
class IterationResultDefinition():
    translatedVideoFileUrl: Optional[Url] = None
    sourceLocaleSubtitleWebvttFileUrl: Optional[Url] = None
    targetLocaleSubtitleWebvttFileUrl: Optional[Url] = None
    metadataJsonWebvttFileUrl: Optional[Url] = None


@dataclass(kw_only=True)
class IterationDefinition(StatefulResourceBaseDefinition):
    input: IterationInputDefinition
    result: Optional[IterationResultDefinition] = None
    iterationFailureReason: Optional[str] = None


@dataclass(kw_only=True)
class TranslationDefinition(StatefulResourceBaseDefinition):
    input: TranslationInputDefinition
    latestIteration: Optional[IterationDefinition] = None
    latestSucceededIteration: Optional[IterationDefinition] = None
    translationFailureReason: Optional[str] = None


@dataclass(kw_only=True)
class PagedTranslationDefinition():
    value: list[TranslationDefinition]
    nextLink: Optional[Url] = None


@dataclass(kw_only=True)
class PagedIterationDefinition():
    value: list[IterationDefinition]
    nextLink: Optional[Url] = None
