# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import warnings
from collections.abc import AsyncIterable, Callable, Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError, dataclass, field
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal, cast
from unittest.mock import patch

import msgspec
import pytest
from pydantic import BaseModel
from pydantic import Field as PydanticField
from typing_extensions import TypeVar

from agent_framework import (
    DISTANCE_FUNCTION_DIRECTION_HELPER,
    BaseEmbeddingClient,
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    Content,
    DistanceFunction,
    Embedding,
    EmbeddingGenerationOptions,
    ExperimentalFeature,
    FieldTypes,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    IndexKind,
    Param,
    SearchResponse,
    SearchResults,
    SearchType,
    SupportsVectorSearch,
    SupportsVectorUpsert,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    register_vectorstoremodel,
    vectorstoremodel,
)
from agent_framework._feature_stage import ExperimentalWarning
from agent_framework._telemetry import FeatureIndex
from agent_framework._vector_filters import filter_values_equal
from agent_framework._vectors import _VectorStoreRecordHandler as VectorStoreRecordHandler
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException

pytestmark = pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")

with warnings.catch_warnings():
    warnings.simplefilter("ignore", ExperimentalWarning)
    RecordVector = Annotated[
        str | list[float] | None,
        VectorStoreField(
            "vector",
            dimensions=2,
            index_kind="hnsw",
            distance_function="cosine_similarity",
            provider_annotations={"index": {"ef_construction": 200}},
        ),
    ]

    @vectorstoremodel(collection_name="records")
    @dataclass
    class Record:
        id: Annotated[str, VectorStoreField("key", storage_name="record_id")]
        text: Annotated[str, VectorStoreField("data", storage_name="body", is_full_text_indexed=True)]
        vector: RecordVector = None
        category: str = "general"


class MockEmbeddingClient(BaseEmbeddingClient):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[Any] = []
        self.options: EmbeddingGenerationOptions | None = None

    async def get_embeddings(
        self,
        values: Sequence[Any],
        *,
        options: EmbeddingGenerationOptions | None = None,
    ) -> GeneratedEmbeddings[list[float]]:
        self.values = list(values)
        self.options = options
        return GeneratedEmbeddings([Embedding(vector=[float(len(str(value))), 0.5]) for value in values])


class MockCollection(BaseVectorCollection[str, Record], BaseVectorSearch[str, Record]):
    supported_key_types: ClassVar[set[str] | None] = {"str"}
    supported_vector_types: ClassVar[set[str] | None] = {"float"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector", "keyword_hybrid"}

    def __init__(self, *, embedding_generator: MockEmbeddingClient | None = None) -> None:
        super().__init__(Record, embedding_generator=embedding_generator)
        self.created = False
        self.records: dict[str, dict[str, Any]] = {}
        self.last_search_type: str | None = None
        self.last_search_values: Any | None = None
        self.last_search_vector: Sequence[float | int] | None = None
        self.last_search_filter: Filter | FilterGroup | None = None
        self.last_get_filter: Filter | FilterGroup | None = None
        self.last_search_top = 0
        self.last_search_skip = 0
        self.last_search_score_threshold: float | None = None
        self.fail_upsert = False
        self.upsert_error: Exception | None = None
        self.get_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.search_error: Exception | None = None
        self.mutate_search_filter = False
        self.upsert_keys: Sequence[str] | None = None
        self.raw_search_results: AsyncIterable[Any] | Sequence[Any] | None = None

    async def ensure_collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        self.created = True

    async def collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.created

    async def ensure_collection_deleted(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        self.created = False
        self.records.clear()

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        if self.upsert_error is not None:
            raise self.upsert_error
        if self.fail_upsert:
            raise RuntimeError("store unavailable")
        keys: list[str] = []
        for record in records:
            mapping = cast(Mapping[str, Any], record)
            key = cast(str, mapping["record_id"])
            self.records[key] = dict(mapping)
            keys.append(key)
        return self.upsert_keys if self.upsert_keys is not None else keys

    async def _inner_get(
        self,
        *,
        keys: Sequence[str] | None = None,
        filter: Filter | FilterGroup | None = None,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[Any] | None:
        if self.get_error is not None:
            raise self.get_error
        self.last_get_filter = filter
        if keys is not None:
            return [self.records[key] for key in keys if key in self.records]
        return list(self.records.values())[skip : skip + top]

    async def _inner_delete(
        self,
        keys: Sequence[str],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        for key in keys:
            self.records.pop(key, None)

    async def _inner_search(
        self,
        *,
        search_type: SearchType,
        filter: Filter | FilterGroup | None = None,
        values: Any | None = None,
        vector: Sequence[float | int] | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[Any]:
        if self.search_error is not None:
            raise self.search_error
        self.last_search_type = search_type
        self.last_search_values = values
        self.last_search_vector = vector
        self.last_search_filter = filter
        self.last_search_top = top
        self.last_search_skip = skip
        self.last_search_score_threshold = score_threshold
        if self.mutate_search_filter and isinstance(filter, Filter) and isinstance(filter.value, list):
            filter.value.append("connector mutation")
        raw_results = self.raw_search_results or [
            {"record": record, "score": score} for record, score in zip(self.records.values(), (0.9, 0.4), strict=False)
        ]
        return SearchResults(raw_results, metadata={"mock_count": len(self.records)})

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return cast(float | None, result["score"])


StoreModelT = TypeVar("StoreModelT")


class MockStore(BaseVectorStore):
    def __init__(self, collection: MockCollection) -> None:
        super().__init__()
        self.collection = collection

    def get_collection(
        self,
        record_type: type[StoreModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: Any | None = None,
    ) -> BaseVectorCollection[Any, StoreModelT]:
        return cast(BaseVectorCollection[Any, StoreModelT], self.collection)

    async def list_collection_names(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        return [self.collection.collection_name] if self.collection.created else []

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        assert collection_name == self.collection.collection_name
        await self.collection.ensure_collection_deleted(operation_options=operation_options)


def test_vector_literal_types_and_distance_directions() -> None:
    field_type: FieldTypes = "vector"
    index_kind: IndexKind = "hnsw"
    distance_function: DistanceFunction = "cosine_similarity"

    assert field_type == "vector"
    assert index_kind == "hnsw"
    assert distance_function == "cosine_similarity"
    assert DISTANCE_FUNCTION_DIRECTION_HELPER["cosine_similarity"](0.5, 0.5)
    assert DISTANCE_FUNCTION_DIRECTION_HELPER["cosine_distance"](0.5, 0.5)
    assert not DISTANCE_FUNCTION_DIRECTION_HELPER["cosine_distance"](0.6, 0.5)


def test_vector_apis_are_marked_experimental() -> None:
    staged_apis = (
        VectorStoreField,
        VectorStoreCollectionDefinition,
        vectorstoremodel,
        SearchResponse,
        SearchResults,
        BaseVectorCollection,
        BaseVectorStore,
        BaseVectorSearch,
        register_vectorstoremodel,
    )
    for api in staged_apis:
        assert getattr(api, "__feature_stage__", None) == "experimental"
        assert getattr(api, "__feature_id__", None) == ExperimentalFeature.VECTOR_STORES.value
        assert ".. warning:: Experimental" in (api.__doc__ or "")

    staged_protocols = (
        SupportsVectorUpsert,
        SupportsVectorSearch,
    )
    for protocol in staged_protocols:
        assert ".. warning:: Experimental" in (protocol.__doc__ or "")


def test_vector_field_validates_vector_options() -> None:
    with pytest.raises(ValueError, match="positive"):
        cast(Any, VectorStoreField)("vector")
    with pytest.raises(ValueError, match="Vector-only"):
        cast(Any, VectorStoreField)("data", dimensions=3)
    with pytest.raises(ValueError, match="Only key fields"):
        cast(Any, VectorStoreField)("data", is_auto_generated=True)
    with pytest.raises(TypeError, match="index_kind must be a string"):
        cast(Any, VectorStoreField)("vector", dimensions=3, index_kind=1)
    with pytest.raises(TypeError, match="distance_function must be a string"):
        cast(Any, VectorStoreField)("vector", dimensions=3, distance_function=object())

    annotations = {"index": {"ef_construction": 200}}
    provider_field = VectorStoreField(
        "vector",
        dimensions=3,
        index_kind="provider.custom_index",
        distance_function="provider.custom_distance",
        provider_annotations=annotations,
    )
    annotations["index"]["ef_construction"] = 100
    assert provider_field.index_kind == "provider.custom_index"
    assert provider_field.distance_function == "provider.custom_distance"
    assert provider_field.provider_annotations["index"]["ef_construction"] == 200
    provider_field.provider_annotations["index"]["ef_construction"] = 100
    assert provider_field.provider_annotations["index"]["ef_construction"] == 100
    assert hash(provider_field)
    with pytest.raises(TypeError, match="keys must be strings"):
        VectorStoreField("data", provider_annotations=cast(Any, {1: "value"}))


def test_collection_definition_exposes_fields() -> None:
    definition = cast(VectorStoreCollectionDefinition, vars(Record)["__vectorstoremodel_definition__"])

    assert definition.collection_name == "records"
    assert definition.key_name == "id"
    assert definition.key_field_storage_name == "record_id"
    assert definition.names == ["id", "text", "vector"]
    assert definition.storage_names == ["record_id", "body", "vector"]
    assert definition.data_field_names == ["text"]
    assert definition.vector_field_names == ["vector"]
    assert definition.get_names(include_vector_fields=False) == ["id", "text"]
    assert definition.get_storage_names(include_key_field=False) == ["body", "vector"]
    assert isinstance(definition.fields, tuple)
    assert definition.vector_fields[0].dimensions == 2
    assert definition.vector_fields[0].type_ == "float"
    assert definition.vector_fields[0].index_kind == "hnsw"
    assert definition.vector_fields[0].distance_function == "cosine_similarity"
    assert definition.vector_fields[0].provider_annotations["index"]["ef_construction"] == 200
    assert not definition.key_field.is_auto_generated

    frozen_field = cast(Any, definition.fields[0])
    with pytest.raises(FrozenInstanceError):
        frozen_field.name = "changed"
    frozen_definition = cast(Any, definition)
    with pytest.raises(FrozenInstanceError):
        frozen_definition.fields = ()


@pytest.mark.parametrize("value", [0, 1, "false", None])
@pytest.mark.parametrize("field_type", ["key", "data", "vector"])
def test_auto_generated_flag_requires_a_boolean(value: Any, field_type: FieldTypes) -> None:
    with pytest.raises(TypeError, match="is_auto_generated must be a boolean"):
        cast(Any, VectorStoreField)(
            field_type, is_auto_generated=value, dimensions=2 if field_type == "vector" else None
        )


async def test_bytearray_annotation_uses_normalized_binary_metadata() -> None:
    @vectorstoremodel
    @dataclass
    class BinaryRecord:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[bytearray | None, VectorStoreField("vector", dimensions=24)] = None

    class BinaryHandler(VectorStoreRecordHandler[str, BinaryRecord]):
        supported_vector_types: ClassVar[set[str] | None] = {"bytes"}

    handler = BinaryHandler(BinaryRecord)
    assert handler.definition.vector_fields[0].type_ == "bytes"
    assert await handler.serialize(BinaryRecord("one", bytearray((1, 2, 3))), generate_vectors=False) == {
        "id": "one",
        "vector": b"\x01\x02\x03",
    }


@pytest.mark.parametrize(
    "fields, message",
    [
        ([], "at least one"),
        ([VectorStoreField("data", name="text")], "exactly one key"),
        (
            [
                VectorStoreField("key", name="id"),
                VectorStoreField("key", name="other_id"),
            ],
            "exactly one key",
        ),
        (
            [
                VectorStoreField("key", name="id"),
                VectorStoreField("data", name="id"),
            ],
            "must be unique",
        ),
        (
            [
                VectorStoreField("key", name="id", storage_name="record_id"),
                VectorStoreField("data", name="record_id", storage_name="body"),
            ],
            "storage name cannot match another field's model name",
        ),
    ],
)
def test_collection_definition_rejects_invalid_fields(
    fields: list[VectorStoreField],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        VectorStoreCollectionDefinition(fields)


def test_vectorstoremodel_supports_pydantic_models() -> None:
    @vectorstoremodel
    class PydanticRecord(BaseModel):
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None

    definition = cast(
        VectorStoreCollectionDefinition,
        vars(PydanticRecord)["__vectorstoremodel_definition__"],
    )
    assert vars(PydanticRecord)["__vectorstoremodel__"]
    assert definition.key_field.type_ == "str"
    assert definition.vector_fields[0].type_ == "float"
    handler = VectorStoreRecordHandler(PydanticRecord)
    record = handler.deserialize({"id": "one", "vector": [1.0, 0.0]}, include_vectors=False)
    assert isinstance(record, PydanticRecord)
    assert record.vector is None


def test_vectorstoremodel_supports_plain_classes() -> None:
    @vectorstoremodel
    class PlainRecord:
        def __init__(
            self,
            id: Annotated[str, VectorStoreField("key")],
            text: Annotated[str, VectorStoreField("data")],
        ) -> None:
            self.id = id
            self.text = text

    definition = cast(
        VectorStoreCollectionDefinition,
        vars(PlainRecord)["__vectorstoremodel_definition__"],
    )
    assert definition.names == ["id", "text"]


def test_vectorstoremodel_ignores_fields_with_defaults() -> None:
    assert (
        "category"
        not in cast(
            VectorStoreCollectionDefinition,
            vars(Record)["__vectorstoremodel_definition__"],
        ).names
    )


def test_vectorstoremodel_detects_factory_and_required_slotted_defaults() -> None:
    @vectorstoremodel
    @dataclass(slots=True)
    class FactoryRecord:
        id: Annotated[str, VectorStoreField("key")]
        ignored: list[str] = field(default_factory=list)

    assert (
        "ignored"
        not in cast(
            VectorStoreCollectionDefinition,
            vars(FactoryRecord)["__vectorstoremodel_definition__"],
        ).names
    )

    class InvalidStruct(msgspec.Struct):
        id: Annotated[str, VectorStoreField("key")]
        required_but_unmapped: str

    with pytest.raises(ValueError, match="required_but_unmapped"):
        vectorstoremodel(InvalidStruct)

    class RequiredVector(msgspec.Struct):
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[list[float], VectorStoreField("vector", dimensions=2)]

    with pytest.raises(ValueError, match="must declare defaults"):
        vectorstoremodel(RequiredVector)


def test_vectorstoremodel_rejects_required_unmapped_fields() -> None:
    class InvalidRecord:
        id: Annotated[str, VectorStoreField("key")]
        required_but_unmapped: str

    with pytest.raises(ValueError, match="required_but_unmapped"):
        vectorstoremodel(InvalidRecord)
    assert not hasattr(InvalidRecord, "__vectorstoremodel__")


async def test_collection_and_search_validate_paging() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        await MockCollection().get(top=0)
    with pytest.raises(ValueError, match="negative"):
        await MockCollection().search("query", skip=-1)


def test_record_handler_validates_connector_field_types() -> None:
    class IntKeyHandler(VectorStoreRecordHandler[str, Record]):
        supported_key_types: ClassVar[set[str] | None] = {"int"}

    with pytest.raises(ValueError, match="Key field type"):
        IntKeyHandler(Record)


async def test_record_handler_serializes_dict_records_with_explicit_definition() -> None:
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", storage_name="record_id"),
        VectorStoreField("data", name="text", storage_name="body"),
    ])
    handler = VectorStoreRecordHandler(dict, definition=definition)

    serialized = await handler.serialize({"id": "one", "text": "hello"})
    assert serialized == {"record_id": "one", "body": "hello"}
    assert handler.deserialize(serialized) == {"id": "one", "text": "hello"}
    assert handler.deserialize([]) == []

    with pytest.raises(IntegrationInvalidResponseException, match="missing required field 'body'"):
        handler.deserialize({"record_id": "one"})
    assert handler.deserialize({"record_id": "one", "body": None}) == {"id": "one", "text": None}

    with pytest.raises(ValueError, match="missing.*text"):
        await handler.serialize({"id": "missing-text"})


async def test_batch_serializer_preserves_cardinality() -> None:
    class DroppingHandler(VectorStoreRecordHandler[Any, Record]):
        def _serialize_dicts_to_store_models(
            self,
            records: Sequence[dict[str, Any]],
            *,
            context: Mapping[str, Any] | None = None,
        ) -> Sequence[Any]:
            return records[:-1]

    with pytest.raises(IntegrationInvalidResponseException, match="Expected 2 serialized records"):
        await DroppingHandler(Record).serialize(
            [
                Record("one", "first"),
                Record("two", "second"),
            ],
            generate_vectors=False,
        )


async def test_record_handler_supports_msgspec_structs() -> None:
    @vectorstoremodel
    class MsgspecRecord(msgspec.Struct):
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None

    handler = VectorStoreRecordHandler(MsgspecRecord)
    serialized = await handler.serialize(MsgspecRecord("one", [1.0, 0.0]), generate_vectors=False)
    deserialized = handler.deserialize(serialized)

    assert serialized == {"id": "one", "vector": [1.0, 0.0]}
    assert deserialized == MsgspecRecord("one", [1.0, 0.0])


async def test_record_handler_uses_registered_codecs() -> None:
    @dataclass
    class CustomRecord:
        id: str
        text: str

    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", storage_name="record_id"),
            VectorStoreField("data", name="text", storage_name="body"),
        ],
    )
    register_vectorstoremodel(
        CustomRecord,
        definition=definition,
        encoder=lambda record: {"id": record.id, "text": record.text.upper()},
        decoder=lambda record: CustomRecord(**record),
    )
    handler = VectorStoreRecordHandler(CustomRecord)

    serialized = await handler.serialize(CustomRecord("one", "hello"))
    assert serialized == {"record_id": "one", "body": "HELLO"}
    assert handler.deserialize(serialized) == CustomRecord("one", "HELLO")


async def test_register_vectorstoremodel_supports_independent_encoder_override() -> None:
    @dataclass
    class RegisteredRecord:
        id: str = ""

    definition = VectorStoreCollectionDefinition([VectorStoreField("key", name="id")])

    def encoder(record: RegisteredRecord) -> Mapping[str, Any]:
        return {"id": record.id}

    register_vectorstoremodel(RegisteredRecord, definition=definition, encoder=encoder)
    handler = VectorStoreRecordHandler(RegisteredRecord)
    assert await handler.serialize(RegisteredRecord("one")) == {"id": "one"}
    assert handler.deserialize({"id": "one"}) == RegisteredRecord("one")

    with pytest.raises(ValueError, match="another definition"):
        register_vectorstoremodel(
            RegisteredRecord,
            definition=VectorStoreCollectionDefinition([VectorStoreField("key", name="other_id")]),
        )


async def test_array_like_vectors_round_trip_without_array_dependency() -> None:
    class ArrayLike:
        __slots__ = ("values",)

        def __init__(self, values: list[float]) -> None:
            self.values = values

        def tolist(self) -> list[float]:
            return self.values

    def decode_array_record(record: Mapping[str, Any]) -> ArrayRecord:
        return ArrayRecord(
            id=cast(str, record["id"]),
            vector=ArrayLike(cast(list[float], record["vector"])),
        )

    @vectorstoremodel(decoder=decode_array_record)
    @dataclass
    class ArrayRecord:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[Any, VectorStoreField("vector", dimensions=3)]

    handler = VectorStoreRecordHandler(ArrayRecord)
    serialized = await handler.serialize(
        ArrayRecord("one", ArrayLike([0.1, 0.2, 0.3])),
        generate_vectors=False,
    )
    restored = handler.deserialize(serialized)

    assert serialized == {"id": "one", "vector": [0.1, 0.2, 0.3]}
    assert isinstance(restored, ArrayRecord)
    assert restored.vector.values == [0.1, 0.2, 0.3]

    with pytest.raises(ValueError, match="vector field 'vector' expects 3 dimensions; got 1"):
        await handler.serialize(ArrayRecord("bad", ArrayLike([0.1])), generate_vectors=False)


async def test_custom_encoder_normalizes_array_like_vectors() -> None:
    class ArrayLike:
        def tolist(self) -> list[float]:
            return [0.1, 0.2, 0.3]

    @dataclass
    class CustomArrayRecord:
        id: str
        vector: ArrayLike

    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField("vector", name="vector", dimensions=3),
    ])
    register_vectorstoremodel(
        CustomArrayRecord,
        definition=definition,
        encoder=lambda record: {"id": record.id, "vector": record.vector},
        decoder=lambda record: CustomArrayRecord(
            id=cast(str, record["id"]),
            vector=ArrayLike(),
        ),
    )

    serialized = await VectorStoreRecordHandler(CustomArrayRecord).serialize(
        CustomArrayRecord("one", ArrayLike()),
        generate_vectors=False,
    )
    assert serialized == {"id": "one", "vector": [0.1, 0.2, 0.3]}


async def test_pydantic_aliases_round_trip_by_field_name() -> None:
    @vectorstoremodel
    class AliasedRecord(BaseModel):
        id: Annotated[str, PydanticField(alias="record_id"), VectorStoreField("key")]

    handler = VectorStoreRecordHandler(AliasedRecord)
    serialized = await handler.serialize(AliasedRecord.model_validate({"record_id": "one"}))
    restored = handler.deserialize(serialized)

    assert serialized == {"id": "one"}
    assert isinstance(restored, AliasedRecord)
    assert restored.id == "one"


async def test_collection_serializes_records_and_generates_vectors() -> None:
    embedding_client = MockEmbeddingClient()
    collection = MockCollection(embedding_generator=embedding_client)

    serialized = await collection.serialize(Record("one", "hello", "embed this"))

    assert serialized == {
        "record_id": "one",
        "body": "hello",
        "vector": [10.0, 0.5],
    }
    assert embedding_client.values == ["embed this"]
    assert embedding_client.options == {"dimensions": 2}


async def test_collection_empty_upsert_skips_embedding_generation() -> None:
    embedding_client = MockEmbeddingClient()
    collection = MockCollection(embedding_generator=embedding_client)

    assert await collection.upsert([]) == []
    assert embedding_client.values == []
    assert await MockCollection().upsert([]) == []


async def test_upsert_controls_embedding_generation() -> None:
    embedding_client = MockEmbeddingClient()
    collection = MockCollection(embedding_generator=embedding_client)

    await collection.upsert([Record("generated", "text", [1.0, 0.0])])

    assert embedding_client.values == [[1.0, 0.0]]
    assert collection.records["generated"]["vector"] == [10.0, 0.5]

    embedding_client.values.clear()
    await collection.upsert(
        [Record("preserved", "text", [1.0, 0.0])],
        generate_vectors=False,
    )

    assert embedding_client.values == []
    assert collection.records["preserved"]["vector"] == [1.0, 0.0]

    with pytest.raises(ValueError, match="has no embedding generator.*generate_vectors=False"):
        await MockCollection().upsert([Record("missing-generator", "text", [1.0, 0.0])])


@pytest.mark.parametrize("vector", [[], [1.0], [1.0, 0.0, 0.0]])
async def test_upsert_rejects_dimension_mismatches_before_connector_conversion(vector: list[float]) -> None:
    collection = MockCollection()
    records = [Record("valid", "text", [1.0, 0.0]), Record("invalid", "text", vector)]

    with patch.object(
        collection, "_serialize_dicts_to_store_models", wraps=collection._serialize_dicts_to_store_models
    ) as convert:
        with pytest.raises(
            ValueError, match=f"Record at index 1, vector field 'vector' expects 2 dimensions; got {len(vector)}"
        ):
            await collection.upsert(records, generate_vectors=False)
        convert.assert_not_called()

    assert collection.records == {}


async def test_upsert_checks_generated_dimensions_instead_of_replaced_input() -> None:
    collection = MockCollection(embedding_generator=MockEmbeddingClient())
    record = Record("replaced", "text", [1.0])

    await collection.upsert([record])

    assert len(collection.records["replaced"]["vector"]) == 2
    assert record.vector == [1.0]


async def test_upsert_rejects_generated_dimension_mismatch_before_writing() -> None:
    class WrongDimensionEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            return GeneratedEmbeddings([
                Embedding(vector=[1.0, 0.0] if index == 0 else [1.0], dimensions=2) for index, _ in enumerate(values)
            ])

    collection = MockCollection(embedding_generator=WrongDimensionEmbeddingClient())

    with pytest.raises(ValueError, match="Record at index 1, vector field 'vector' expects 2 dimensions; got 1"):
        await collection.upsert([Record("valid", "text", "source"), Record("invalid", "text", "source")])

    assert collection.records == {}


@pytest.mark.parametrize(("field_name", "dimensions"), [("primary", 2), ("secondary", 3)])
async def test_serialization_validates_all_vector_fields_and_storage_aliases(field_name: str, dimensions: int) -> None:
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField("vector", name="primary", storage_name="primary_vector", dimensions=2),
        VectorStoreField("vector", name="secondary", storage_name="secondary_vector", dimensions=3),
    ])
    handler = VectorStoreRecordHandler(dict, definition=definition)
    records = [
        {"id": "one", "primary": [1.0, 0.0], "secondary": [1.0, 0.0, 0.0]},
        {"id": "two", "primary_vector": [1.0, 0.0], "secondary_vector": [1.0, 0.0, 0.0]},
    ]
    records[1][f"{field_name}_vector"] = [1.0]

    with pytest.raises(
        ValueError, match=f"Record at index 1, vector field '{field_name}' expects {dimensions} dimensions; got 1"
    ):
        await handler.serialize(records, generate_vectors=False)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, None),
        ("provider-side source", "provider-side source"),
        (b"\x01\x02", b"\x01\x02"),
        (bytearray((1, 2)), b"\x01\x02"),
        ({"indices": [4], "values": [0.5]}, {"indices": [4], "values": [0.5]}),
    ],
)
async def test_serialization_leaves_non_dense_dimensions_to_connector(payload: Any, expected: Any) -> None:
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField("vector", name="vector", dimensions=1536),
    ])
    handler = VectorStoreRecordHandler(dict, definition=definition)

    assert await handler.serialize({"id": "one", "vector": payload}, generate_vectors=False) == {
        "id": "one",
        "vector": expected,
    }


async def test_serialization_selects_vector_fields_for_generation() -> None:
    embedding_client = MockEmbeddingClient()

    @dataclass
    class MixedVectorRecord:
        id: str
        local_vector: str | list[float] | None = None
        provider_vector: str | list[float] | None = None

    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField(
            "vector",
            name="local_vector",
            dimensions=2,
            embedding_generator=embedding_client,
        ),
        VectorStoreField("vector", name="provider_vector", dimensions=2),
    ])
    register_vectorstoremodel(MixedVectorRecord, definition=definition)
    handler = VectorStoreRecordHandler(MixedVectorRecord)
    serialized = await handler.serialize(
        MixedVectorRecord("one", "embed locally", "send to provider"),
        generate_vectors=["local_vector"],
    )

    assert serialized == {
        "id": "one",
        "local_vector": [13.0, 0.5],
        "provider_vector": "send to provider",
    }
    assert embedding_client.values == ["embed locally"]

    with pytest.raises(ValueError, match="vector field 'provider_vector' expects 2 dimensions; got 1"):
        await handler.serialize(
            MixedVectorRecord("bad", "embed locally", [1.0]),
            generate_vectors=["local_vector"],
        )

    with pytest.raises(ValueError, match="Unknown vector field"):
        await handler.serialize(
            MixedVectorRecord("one", "local", "provider"),
            generate_vectors=["missing"],
        )
    with pytest.raises(ValueError, match="must be unique"):
        await handler.serialize(
            MixedVectorRecord("one", "local", "provider"),
            generate_vectors=["local_vector", "local_vector"],
        )
    with pytest.raises(TypeError, match="boolean or a sequence"):
        await handler.serialize(
            MixedVectorRecord("one", "local", "provider"),
            generate_vectors=cast(Any, "local_vector"),
        )


async def test_generated_binary_vectors_are_preserved() -> None:
    class ByteArrayEmbeddingClient(BaseEmbeddingClient[Any, bytearray, EmbeddingGenerationOptions]):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[bytearray]:
            return GeneratedEmbeddings([Embedding(vector=bytearray((1, 2, 3))) for _ in values])

    @vectorstoremodel
    class BinaryRecord(BaseModel):
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[
            str | bytes | None,
            VectorStoreField("vector", dimensions=24),
        ] = None

    handler = VectorStoreRecordHandler(
        BinaryRecord,
        embedding_generator=ByteArrayEmbeddingClient(),
    )
    serialized = await handler.serialize(BinaryRecord(id="one", vector="source"))

    assert serialized == {"id": "one", "vector": b"\x01\x02\x03"}
    assert handler.definition.vector_fields[0].type_ == "bytes"
    assert await handler.serialize(
        BinaryRecord(id="two", vector=b"\x04\x05\x06"),
        generate_vectors=False,
    ) == {"id": "two", "vector": b"\x04\x05\x06"}

    @dataclass
    class UnsupportedBinaryRecord:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[str | bytes | None, VectorStoreField("vector", dimensions=24)] = None

    with pytest.raises(ValueError, match="default msgspec decoder.*custom decoder"):
        vectorstoremodel(UnsupportedBinaryRecord)

    @vectorstoremodel
    class BytesOnlyRecord(BaseModel):
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[bytes | None, VectorStoreField("vector", dimensions=24)] = None

    pydantic_handler = VectorStoreRecordHandler(BytesOnlyRecord)
    supplied = BytesOnlyRecord(id="three", vector=b"\x07\x08\x09")
    serialized_supplied = await pydantic_handler.serialize(supplied, generate_vectors=False)
    restored = pydantic_handler.deserialize(serialized_supplied)

    assert serialized_supplied == {"id": "three", "vector": b"\x07\x08\x09"}
    assert isinstance(restored, BytesOnlyRecord)
    assert restored.vector == b"\x07\x08\x09"


async def test_collection_crud_preserves_single_and_batch_shapes() -> None:
    collection = MockCollection(embedding_generator=MockEmbeddingClient())
    await collection.ensure_collection_exists()

    first_keys = await collection.upsert([Record("one", "first", "first")])
    keys = await collection.upsert([
        Record("two", "second", "second"),
        Record("three", "third", "third"),
    ])
    one = await collection.get(["one"])
    many = await collection.get(["one", "two"], include_vectors=True)
    filtered = await collection.get(top=1)

    assert first_keys == ["one"]
    assert keys == ["two", "three"]
    assert one == [Record("one", "first")]
    assert many == [
        Record("one", "first", [5.0, 0.5]),
        Record("two", "second", [6.0, 0.5]),
    ]
    assert filtered == [Record("one", "first")]

    await collection.delete(["one", "two"])
    assert await collection.get(["one", "two"]) == []


async def test_collection_wraps_connector_errors() -> None:
    collection = MockCollection()
    collection.fail_upsert = True

    with pytest.raises(IntegrationException, match="store unavailable"):
        await collection.upsert([Record("one", "hello")], generate_vectors=False)


async def test_collection_get_without_keys_lists_records() -> None:
    assert await MockCollection().get() == []


async def test_collection_get_accepts_filter_as_alternate_retrieval_mode() -> None:
    collection = MockCollection()
    filter_ = Filter("text", "eq", "hello")

    await collection.get(filter=filter_)

    assert collection.last_get_filter == filter_
    assert collection.last_get_filter is not filter_
    with pytest.raises(ValueError, match="alternate retrieval modes"):
        await collection.get(["one"], filter=filter_)


async def test_collection_crud_rejects_singular_ordinary_inputs() -> None:
    collection = MockCollection()

    with pytest.raises(TypeError, match="records must be a sequence"):
        await cast(Any, collection.upsert)(Record("one", "hello"))
    with pytest.raises(TypeError, match="keys must be a sequence"):
        await collection.get("one")
    with pytest.raises(TypeError, match="keys must be a sequence"):
        await collection.delete("one")


async def test_vector_search_generates_query_vector_and_forwards_threshold() -> None:
    embedding_client = MockEmbeddingClient()
    collection = MockCollection(embedding_generator=embedding_client)
    await collection.upsert([
        Record("one", "first", "first"),
        Record("two", "second", "second"),
    ])

    results = await collection.search(
        "find this",
        score_threshold=0.5,
    )
    responses = [response async for response in results]

    assert results.metadata == {"mock_count": 2}
    assert embedding_client.values == ["find this"]
    assert collection.last_search_vector == [9.0, 0.5]
    assert collection.last_search_score_threshold == 0.5
    assert responses[0]["record"].id == "one"
    assert responses[0]["score"] == 0.9
    assert [response["record"].id for response in responses] == ["one", "two"]
    assert responses[1]["score"] == 0.4


async def test_keyword_hybrid_search_uses_single_search_method() -> None:
    collection = MockCollection()

    await collection.search("words", search_type="keyword_hybrid")

    assert collection.last_search_type == "keyword_hybrid"


@pytest.mark.parametrize("values", ["vectorize this on the provider", {"indices": [4], "values": [0.5]}, [1.0]])
async def test_search_passes_values_to_provider_when_no_generator_is_configured(values: Any) -> None:
    collection = MockCollection()

    await collection.search(values)

    assert collection.last_search_values is values
    assert collection.last_search_vector is None


@pytest.mark.parametrize("vector", [[], [1.0], (1.0,), range(1), [1.0, 0.0, 0.0]])
@pytest.mark.parametrize("search_type", ["vector", "keyword_hybrid"])
async def test_search_rejects_dense_dimension_mismatches_before_dispatch(
    vector: Sequence[float], search_type: SearchType
) -> None:
    collection = MockCollection()

    with pytest.raises(ValueError, match=f"Query vector field 'vector' expects 2 dimensions; got {len(vector)}"):
        await collection.search("query", vector=vector, search_type=search_type)

    assert collection.last_search_type is None


@pytest.mark.parametrize(
    ("selected_field", "logical_name", "dimensions"),
    [(None, "vector", 2), ("secondary", "secondary", 3), ("secondary_vector", "secondary", 3)],
)
async def test_search_checks_dimensions_of_selected_vector_field(
    selected_field: str | None, logical_name: str, dimensions: int
) -> None:
    collection = MockCollection()
    collection.definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField("vector", name="vector", dimensions=2),
        VectorStoreField("vector", name="secondary", storage_name="secondary_vector", dimensions=3),
    ])
    vector = [1.0] * dimensions

    await collection.search(vector=vector, vector_property_name=selected_field)
    assert collection.last_search_vector is vector

    with pytest.raises(
        ValueError, match=f"Query vector field '{logical_name}' expects {dimensions} dimensions; got {dimensions + 1}"
    ):
        await collection.search(vector=[1.0] * (dimensions + 1), vector_property_name=selected_field)
    assert collection.last_search_vector is vector


async def test_search_rejects_generated_dimension_mismatch() -> None:
    class WrongDimensionEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            return GeneratedEmbeddings([Embedding(vector=[1.0], dimensions=2)])

    collection = MockCollection(embedding_generator=WrongDimensionEmbeddingClient())

    with pytest.raises(ValueError, match="Query vector field 'vector' expects 2 dimensions; got 1"):
        await collection.search("source")

    assert collection.last_search_type is None


async def test_search_dimension_check_does_not_iterate_or_copy_vectors() -> None:
    class LengthOnlyVector(list[float]):
        def __iter__(self) -> Iterator[float]:
            raise AssertionError("Dimension checks must not iterate vector elements.")

    vector = LengthOnlyVector([1.0, 0.0])
    collection = MockCollection()

    await collection.search(vector=vector)

    assert collection.last_search_vector is vector


@pytest.mark.parametrize("vector", [(1.0, 0.0), range(2)])
async def test_search_accepts_matching_dense_sequence_dimensions(vector: Sequence[float | int]) -> None:
    collection = MockCollection()

    await collection.search(vector=vector)

    assert collection.last_search_vector is vector


@pytest.mark.parametrize("vector", [b"\x01", bytearray((1,))])
async def test_search_leaves_binary_dimensions_to_connector(vector: bytes | bytearray) -> None:
    collection = MockCollection()

    await collection.search(vector=vector)

    assert collection.last_search_vector is vector


async def test_vector_search_validates_inputs_and_supported_type() -> None:
    collection = MockCollection()

    with pytest.raises(ValueError, match="requires values"):
        await cast(Any, collection.search)()
    with pytest.raises(ValueError, match="Vector field 'missing' was not found"):
        await collection.search(vector=[1.0, 0.0], vector_property_name="missing")

    class VectorOnlyCollection(MockCollection):
        supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    with pytest.raises(NotImplementedError, match="not supported"):
        await VectorOnlyCollection().search("words", search_type="keyword_hybrid")


@pytest.mark.parametrize(
    "distance_function", [None, "DEFAULT", "provider.custom_distance", "cosine_similarity", "cosine_distance"]
)
@pytest.mark.parametrize("precomputed", [False, True])
@pytest.mark.parametrize("threshold", [0.0, 0.5])
async def test_core_preserves_connector_scores_without_interpreting_thresholds(
    distance_function: DistanceFunction | None, precomputed: bool, threshold: float
) -> None:
    collection = MockCollection()
    fields = [
        VectorStoreField("key", name="id", storage_name="record_id"),
        VectorStoreField("data", name="text", storage_name="body"),
    ]
    if distance_function is not None:
        fields.append(
            VectorStoreField("vector", name="vector", type_="float", dimensions=2, distance_function=distance_function)
        )
    collection.definition = VectorStoreCollectionDefinition(
        fields,
        collection_name="records",
    )
    collection.raw_search_results = [
        {"record": {"record_id": "low", "body": "low"}, "score": -0.2},
        {"record": {"record_id": "equal", "body": "equal"}, "score": threshold},
        {"record": {"record_id": "high", "body": "high"}, "score": 0.9},
        {"record": {"record_id": "scoreless", "body": "scoreless"}, "score": None},
    ]
    filter_ = Filter("text", "eq", "provider interprets this")

    results = await collection.search(
        "query",
        vector=[1.0, 0.0] if precomputed else None,
        filter=filter_,
        score_threshold=threshold,
        top=4,
        skip=2,
    )
    responses = [response async for response in results]

    assert collection.last_search_score_threshold == threshold
    assert collection.last_search_filter == filter_
    assert collection.last_search_top == 4
    assert collection.last_search_skip == 2
    assert [response["record"].id for response in responses] == ["low", "equal", "high", "scoreless"]
    assert [response["score"] for response in responses] == [-0.2, threshold, 0.9, None]


async def test_connector_can_enforce_provider_threshold_before_core_deserialization() -> None:
    class ProviderThresholdCollection(MockCollection):
        async def _inner_search(
            self,
            *,
            search_type: SearchType,
            filter: Filter | FilterGroup | None = None,
            values: Any | None = None,
            vector: Sequence[float | int] | bytes | bytearray | None = None,
            top: int = 3,
            skip: int = 0,
            include_vectors: bool = False,
            vector_property_name: str | None = None,
            additional_property_name: str | None = None,
            score_threshold: float | None = None,
            operation_options: Mapping[str, Any] | None = None,
        ) -> SearchResults[Any]:
            self.last_search_score_threshold = score_threshold
            assert self.raw_search_results is not None
            results = SearchResults(self.raw_search_results)
            return SearchResults([
                result async for result in results if score_threshold is None or result["score"] <= score_threshold
            ])

    collection = ProviderThresholdCollection()
    collection.definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", storage_name="record_id"),
            VectorStoreField("data", name="text", storage_name="body"),
            VectorStoreField(
                "vector",
                name="vector",
                dimensions=2,
                distance_function="provider.custom_distance",
            ),
        ],
        collection_name="records",
    )
    collection.raw_search_results = [
        {"record": {"record_id": "rejected", "body": "far"}, "score": 0.9},
        {"record": {"record_id": "accepted", "body": "near"}, "score": 0.2},
    ]

    results = await collection.search(vector=[1.0, 0.0], score_threshold=0.5)

    assert collection.last_search_score_threshold == 0.5
    assert [(result["record"].id, result["score"]) async for result in results] == [("accepted", 0.2)]


async def test_connector_can_reject_unsupported_threshold_execution() -> None:
    collection = MockCollection()
    collection.search_error = NotImplementedError("Connector does not support score thresholds.")

    with pytest.raises(NotImplementedError, match="Connector does not support score thresholds"):
        await collection.search(vector=[1.0, 0.0], score_threshold=0.5)


async def test_vector_search_wraps_embedding_failures() -> None:
    class FailingEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            raise RuntimeError("embedding unavailable")

    collection = MockCollection(embedding_generator=FailingEmbeddingClient())

    with pytest.raises(IntegrationException, match="embedding unavailable"):
        await collection.search("query")


async def test_vector_search_passes_filter_to_connector() -> None:
    collection = MockCollection()
    search_filter = FilterGroup("and", (Filter("text", "eq", "travel"), Filter("id", "ne", "ignored")))

    await collection.search(
        "query",
        filter=search_filter,
    )

    assert collection.last_search_filter == search_filter
    assert collection.last_search_filter is not search_filter


async def test_vector_search_rejects_invalid_or_unresolved_filters() -> None:
    collection = MockCollection()
    with pytest.raises(ValueError, match="not part of the vector store definition"):
        await collection.search("query", filter=Filter("missing", "eq", "value"))
    with pytest.raises(ValueError, match="must be resolved"):
        await collection.search("query", filter=Filter("text", "eq", Param("text", str)))


async def test_create_search_tool_returns_mapped_results() -> None:
    collection = MockCollection()
    collection.records["one"] = {"record_id": "one", "body": "first", "vector": [1.0, 0.0]}
    tool = create_vector_search_tool(
        collection,
        name="search_records",
        approval_mode="always_require",
        top=1,
        result_mapper=lambda response: f"{response['record'].id}:{response['score']}",
    )

    result = await tool(query="first")

    assert tool.name == "search_records"
    assert tool.approval_mode == "always_require"
    assert len(result) == 1
    assert result[0].text == "one:0.9"


async def test_create_search_tool_supports_declared_filter_parameters() -> None:
    collection = MockCollection()
    collection.records["one"] = {"record_id": "one", "body": "first", "vector": [1.0, 0.0]}
    category = Param(
        "category",
        Literal["travel", "work"],
        required=True,
        description="The category to match.",
    )
    tool = create_vector_search_tool(
        collection,
        filter=Filter("text", "eq", category),
        top=Param("top", int, default=1, minimum=1, maximum=5),
        skip=Param("skip", int, default=0, minimum=0, maximum=10),
    )

    await tool(query="first", category="travel", top=1, skip=2)

    assert set(tool.parameters()["properties"]) == {"query", "category", "top", "skip"}
    assert tool.parameters()["additionalProperties"] is False
    assert tool.parameters()["properties"]["category"]["enum"] == ["travel", "work"]
    assert tool.parameters()["properties"]["top"]["minimum"] == 1
    assert tool.parameters()["properties"]["top"]["maximum"] == 5
    assert collection.last_search_filter == Filter("text", "eq", "travel")
    assert collection.last_search_top == 1
    assert collection.last_search_skip == 2


def test_create_search_tool_validates_params() -> None:
    collection = MockCollection()

    with pytest.raises(ValueError, match="minimum"):
        create_vector_search_tool(
            collection,
            top=Param("top", int, default=1, maximum=5),
        )
    with pytest.raises(ValueError, match="finite integer maximum"):
        create_vector_search_tool(
            collection,
            top=Param("top", int, default=1, minimum=1),
        )
    with pytest.raises(ValueError, match="conflicting declarations"):
        create_vector_search_tool(
            collection,
            filter=FilterGroup(
                "and",
                (
                    Filter("id", "eq", Param("record_id", str)),
                    Filter("text", "eq", Param("record_id", int)),
                ),
            ),
        )


async def test_create_search_tool_enforces_paging_limits_and_result_cap() -> None:
    collection = MockCollection()
    collection.raw_search_results = [
        {"record": {"record_id": str(index), "body": f"record {index}"}, "score": 0.9} for index in range(3)
    ]
    tool = create_vector_search_tool(
        collection,
        top=Param("top", int, default=2, minimum=1, maximum=2),
        skip=Param("skip", int, default=0, minimum=0, maximum=4),
    )

    results = await tool(query="records", top=2, skip=4)
    assert len(results) == 2

    with pytest.raises(ValueError, match="must be at most 2"):
        await tool(query="records", top=3)
    with pytest.raises(ValueError, match="must be at most 4"):
        await tool(query="records", skip=5)
    with pytest.raises(TypeError, match="does not match"):
        await create_vector_search_tool(
            collection,
            filter=Filter("text", "eq", Param("category", Literal["travel", "work"], required=True)),
        )(query="records", category="other")


async def test_create_search_tool_supports_multimodal_results() -> None:
    collection = MockCollection()
    collection.records["one"] = {"record_id": "one", "body": "first", "vector": [1.0, 0.0]}
    tool = create_vector_search_tool(
        collection,
        top=1,
        result_mapper=lambda response: [
            Content.from_text(response["record"].text),
            Content.from_uri("https://example.com/result.png", media_type="image/png"),
        ],
    )

    result = await tool.invoke(arguments={"query": "first"})

    assert [content.type for content in result] == ["text", "uri"]


async def test_create_search_tool_uses_msgspec_for_default_result_mapping() -> None:
    collection = MockCollection()
    collection.records["one"] = {"record_id": "one", "body": "first", "vector": [1.0, 0.0]}

    result = await create_vector_search_tool(collection, top=1)(query="first")

    assert result[0].text is not None
    decoded = msgspec.json.decode(result[0].text)
    assert set(create_vector_search_tool(collection).parameters()["properties"]) == {"query"}
    assert decoded["record"]["id"] == "one"
    assert decoded["score"] == 0.9


async def test_create_search_tool_defers_unsupported_type_to_search() -> None:
    class VectorOnlyCollection(MockCollection):
        supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    tool = create_vector_search_tool(VectorOnlyCollection(), search_type="keyword_hybrid")
    with pytest.raises(NotImplementedError, match="not supported"):
        await tool(query="query")


def test_search_protocol_and_tool_factory_only_require_search() -> None:
    class SearchOnly:
        async def search(
            self,
            values: Any,
            *,
            search_type: SearchType = "vector",
            vector: Sequence[float | int] | None = None,
            filter: Any = None,
            top: int = 3,
            skip: int = 0,
            include_vectors: bool = False,
            vector_property_name: str | None = None,
            additional_property_name: str | None = None,
            score_threshold: float | None = None,
            operation_options: Mapping[str, Any] | None = None,
        ) -> SearchResults[SearchResponse[Record]]:
            return SearchResults([])

    search = SearchOnly()
    assert isinstance(cast(Any, search), SupportsVectorSearch)
    assert create_vector_search_tool(cast(SupportsVectorSearch[Record], search)).name == "search"


def test_collection_satisfies_vector_protocols() -> None:
    collection = MockCollection()

    assert isinstance(collection, SupportsVectorUpsert)
    assert isinstance(collection, SupportsVectorSearch)


async def test_vector_store_collection_lifecycle_helpers() -> None:
    collection = MockCollection()
    store = MockStore(collection)

    assert not await store.collection_exists("records")
    await collection.ensure_collection_exists()
    assert await store.collection_exists("records")
    await store.ensure_collection_deleted("records")
    assert not await store.collection_exists("records")


def test_search_response_holds_record_and_score() -> None:
    record = Record("one", "hello")
    response = SearchResponse(record=record, score=0.75)

    assert response["record"] is record
    assert response["score"] == 0.75


def test_deserialization_rejects_non_mapping_store_records() -> None:
    handler = VectorStoreRecordHandler(Record)

    with pytest.raises(TypeError, match="must be mappings"):
        handler.deserialize(object())


def test_additional_field_and_definition_validation_paths() -> None:
    with pytest.raises(ValueError, match="Unknown vector store field type"):
        cast(Any, VectorStoreField)("unknown")
    with pytest.raises(ValueError, match="must not be empty"):
        VectorStoreCollectionDefinition([VectorStoreField("key")])
    with pytest.raises(ValueError, match="storage names must be unique"):
        VectorStoreCollectionDefinition([
            VectorStoreField("key", name="id", storage_name="same"),
            VectorStoreField("data", name="text", storage_name="same"),
        ])

    definition = cast(VectorStoreCollectionDefinition, vars(Record)["__vectorstoremodel_definition__"])
    assert definition.try_get_vector_field("vector") is definition.vector_fields[0]
    assert definition.try_get_vector_field("missing") is None


async def test_default_codecs_cover_pydantic_plain_and_unsupported_models() -> None:
    @vectorstoremodel
    class PydanticRecord(BaseModel):
        id: Annotated[str, VectorStoreField("key")]

    @vectorstoremodel
    class PlainRecord:
        id: Annotated[str, VectorStoreField("key")]

        def __init__(self, id: str) -> None:
            self.id = id

    @vectorstoremodel
    class SlottedRecord:
        __slots__ = ("id",)
        id: Annotated[str, VectorStoreField("key")]

        def __init__(self, id: str) -> None:
            self.id = id

    assert await VectorStoreRecordHandler(PydanticRecord).serialize(PydanticRecord(id="one")) == {"id": "one"}
    assert await VectorStoreRecordHandler(PlainRecord).serialize(PlainRecord("one")) == {"id": "one"}
    with pytest.raises(NotImplementedError, match="SlottedRecord"):
        await VectorStoreRecordHandler(SlottedRecord).serialize(SlottedRecord("one"))


def test_vectorstoremodel_rejects_unresolvable_or_missing_annotations() -> None:
    class UnresolvableRecord:
        __annotations__ = {"id": "MissingRecordType"}

    class EmptyRecord:
        pass

    with pytest.raises(ValueError, match="Unable to resolve"):
        vectorstoremodel(UnresolvableRecord)
    with pytest.raises(ValueError, match="at least one annotated field"):
        vectorstoremodel(EmptyRecord)


def test_registration_is_idempotent_and_rejects_changed_codecs() -> None:
    @dataclass
    class RegisteredRecord:
        id: str

    definition = VectorStoreCollectionDefinition([VectorStoreField("key", name="id")])

    def encoder(record: RegisteredRecord) -> Mapping[str, Any]:
        return {"id": record.id}

    def decoder(record: Mapping[str, Any]) -> RegisteredRecord:
        return RegisteredRecord(cast(str, record["id"]))

    register_vectorstoremodel(RegisteredRecord, definition=definition, encoder=encoder, decoder=decoder)
    register_vectorstoremodel(RegisteredRecord, definition=definition, encoder=encoder, decoder=decoder)

    with pytest.raises(ValueError, match="another encoder"):
        register_vectorstoremodel(
            RegisteredRecord,
            definition=definition,
            encoder=lambda record: {"id": record.id},
            decoder=decoder,
        )
    with pytest.raises(ValueError, match="another decoder"):
        register_vectorstoremodel(
            RegisteredRecord,
            definition=definition,
            encoder=encoder,
            decoder=lambda record: RegisteredRecord(cast(str, record["id"])),
        )


def test_record_handler_requires_registered_models_or_explicit_dict_definitions() -> None:
    class UnregisteredRecord:
        pass

    with pytest.raises(ValueError, match="explicit"):
        VectorStoreRecordHandler(dict)
    with pytest.raises(ValueError, match="must be registered"):
        VectorStoreRecordHandler(UnregisteredRecord)

    other_definition = VectorStoreCollectionDefinition([VectorStoreField("key", name="other_id")])
    with pytest.raises(ValueError, match="another definition"):
        VectorStoreRecordHandler(Record, definition=other_definition)


async def test_serialization_shape_and_embedding_failures() -> None:
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", storage_name="record_id"),
        VectorStoreField("data", name="text", storage_name="body"),
    ])
    dict_handler = VectorStoreRecordHandler(dict, definition=definition)
    assert await dict_handler.serialize({"record_id": "one", "body": "hello"}) == {
        "record_id": "one",
        "body": "hello",
    }
    with pytest.raises(TypeError, match="must serialize to mappings"):
        await dict_handler.serialize(cast(Any, 1))

    collection = MockCollection(embedding_generator=MockEmbeddingClient())
    with pytest.raises(ValueError, match="value is missing"):
        await collection.serialize(Record("one", "hello"))

    class EmptyEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            return GeneratedEmbeddings()

    with pytest.raises(IntegrationInvalidResponseException, match="returned 0 vectors"):
        await MockCollection(embedding_generator=EmptyEmbeddingClient()).serialize(Record("one", "hello", "embed"))

    assert dict_handler.deserialize(None) is None


async def test_array_like_generated_embeddings_are_normalized() -> None:
    class ArrayLike:
        def tolist(self) -> list[float]:
            return [0.1, 0.2]

    class ArrayEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[Any]:
            return GeneratedEmbeddings([Embedding(vector=ArrayLike()) for _ in values])

    collection = MockCollection(embedding_generator=ArrayEmbeddingClient())
    serialized = await collection.serialize(Record("one", "hello", "embed"))
    assert serialized["vector"] == [0.1, 0.2]

    results = await collection.search("query")
    assert collection.last_search_vector == [0.1, 0.2]
    assert [result async for result in results] == []


async def test_collection_operation_error_boundaries_and_context_manager() -> None:
    collection = MockCollection()
    async with collection as entered:
        assert entered is collection

    collection.upsert_error = IntegrationException("known upsert failure")
    with pytest.raises(IntegrationException, match="known upsert failure"):
        await collection.upsert([Record("one", "hello")], generate_vectors=False)
    collection.upsert_error = None
    collection.upsert_keys = []
    with pytest.raises(IntegrationInvalidResponseException, match="Expected 1 upserted keys"):
        await collection.upsert([Record("one", "hello")], generate_vectors=False)

    collection.get_error = RuntimeError("get failure")
    with pytest.raises(IntegrationException, match="get failure"):
        await collection.get(["one"])
    collection.get_error = None
    collection.delete_error = IntegrationException("known delete failure")
    with pytest.raises(IntegrationException, match="known delete failure"):
        await collection.delete(["one"])
    collection.delete_error = RuntimeError("delete failure")
    with pytest.raises(IntegrationException, match="delete failure"):
        await collection.delete(["one"])

    class FailingEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            raise RuntimeError("embedding down")

    with pytest.raises(IntegrationException, match="embedding down"):
        await MockCollection(embedding_generator=FailingEmbeddingClient()).upsert([Record("one", "hello", "embed")])


async def test_vector_store_context_and_missing_collection_delete() -> None:
    collection = MockCollection()
    store = MockStore(collection)

    async with store as entered:
        assert entered is store
    await store.ensure_collection_deleted("missing")
    assert not collection.created


async def test_additional_search_validation_and_error_boundaries() -> None:
    collection = MockCollection()
    with pytest.raises(ValueError, match="Unknown search type"):
        await collection.search("query", search_type=cast(Any, "unknown"))
    with pytest.raises(ValueError, match="Keyword-hybrid"):
        await cast(Any, collection.search)(search_type="keyword_hybrid", vector=[1.0, 0.0])
    with pytest.raises(ValueError, match="was not found"):
        await collection.search("query", vector_property_name="missing")

    collection.search_error = IntegrationException("known search failure")
    with pytest.raises(IntegrationException, match="known search failure"):
        await collection.search("query")
    collection.search_error = RuntimeError("search failure")
    with pytest.raises(IntegrationException, match="search failure"):
        await collection.search("query")


async def test_search_embedding_and_result_conversion_failures() -> None:
    class EmptyEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[list[float]]:
            return GeneratedEmbeddings()

    class StringEmbeddingClient(MockEmbeddingClient):
        async def get_embeddings(
            self,
            values: Sequence[Any],
            *,
            options: EmbeddingGenerationOptions | None = None,
        ) -> GeneratedEmbeddings[Any]:
            return GeneratedEmbeddings([Embedding(vector="invalid")])

    with pytest.raises(IntegrationInvalidResponseException, match="returned 0 vectors"):
        await MockCollection(embedding_generator=EmptyEmbeddingClient()).search("query")
    with pytest.raises(TypeError, match="unsupported vector type"):
        await MockCollection(embedding_generator=StringEmbeddingClient()).search("query")

    collection = MockCollection()
    collection.raw_search_results = [{"record": None, "score": 0.9}]
    results = await collection.search(vector=[1.0, 0.0])
    assert [result async for result in results] == []

    collection.raw_search_results = [{"record": [{"record_id": "one", "body": "hello"}], "score": 0.9}]
    results = await collection.search(vector=[1.0, 0.0])
    with pytest.raises(IntegrationInvalidResponseException, match="exactly one record"):
        _ = [result async for result in results]

    collection.raw_search_results = [object()]
    results = await collection.search(vector=[1.0, 0.0])
    with pytest.raises(IntegrationInvalidResponseException, match="result conversion failed"):
        _ = [result async for result in results]

    async def failing_results() -> AsyncIterable[Any]:
        yield {"record": {"record_id": "one", "body": "hello"}, "score": 0.9}
        raise RuntimeError("stream disconnected")

    collection.raw_search_results = failing_results()
    results = await collection.search(vector=[1.0, 0.0])
    with pytest.raises(IntegrationException, match="iteration failed.*stream disconnected"):
        _ = [result async for result in results]


async def test_scoreless_results_remain_when_threshold_cannot_be_applied() -> None:
    collection = MockCollection()
    collection.raw_search_results = [{"record": {"record_id": "one", "body": "hello"}, "score": None}]

    results = await collection.search(vector=[1.0, 0.0], score_threshold=0.5)

    responses = [result async for result in results]
    assert len(responses) == 1
    assert responses[0]["score"] is None


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (True, 1, False),
        (False, 0, False),
        (True, True, True),
        (False, False, True),
        (1, 1.0, True),
        ([1], [True], False),
        ([0], [False], False),
        ((1,), (True,), False),
        ([[1]], [[True]], False),
        ([(1, [0])], [(True, [False])], False),
        ([True, [False]], [True, [False]], True),
        ([1, [0]], [1.0, [0.0]], True),
        ((1, (0,)), (1.0, (0.0,)), True),
        ([1], (1,), False),
        ([], (), False),
        ([1, 2], [2, 1], False),
        ([1], [1, 2], False),
        ([], [], True),
        ({"value": [1]}, {"value": [True]}, False),
        ([{"value": (0,)}], [{"value": (False,)}], False),
        ({"value": [1]}, {"value": [1.0]}, True),
        ({"one": True, "two": False}, {"two": False, "one": True}, True),
        ({"one": True}, {"two": True}, False),
        ({"value": True}, {}, False),
        ("1", 1, False),
        ("text", "text", True),
        (b"\x01", b"\x01", True),
        (None, None, True),
    ],
)
def test_filter_values_equal_preserves_nested_types(left: Any, right: Any, expected: bool) -> None:
    assert filter_values_equal(left, right) is expected
    assert filter_values_equal(right, left) is expected


def test_filter_model_accepts_namespaced_provider_operators() -> None:
    assert Filter("text", "azure_ai_search.full_text", "query").operator == "azure_ai_search.full_text"
    with pytest.raises(ValueError, match="namespaced"):
        Filter("text", "full_text", "query")


def test_filter_model_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="requires a value"):
        Filter("text", "eq")
    with pytest.raises(TypeError, match="sequence value"):
        Filter("text", "in", "value")
    with pytest.raises(ValueError, match="two boundary"):
        Filter("text", "between", (1,))
    with pytest.raises(ValueError, match="exactly one"):
        FilterGroup("not", (Filter("text", "eq", "one"), Filter("text", "eq", "two")))
    with pytest.raises(ValueError, match="Invalid filter field name"):
        Filter("__class__", "eq", "unsafe")

    cyclic: list[Any] = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError, match="cycles"):
        Filter("text", "in", cyclic)
    with pytest.raises(ValueError, match="entire Filter value"):
        Filter("text", "in", ("fixed", Param("dynamic", str)))


def test_param_generates_native_schema_and_validates_constraints() -> None:
    param = Param(
        "category",
        Literal["travel", "work"],
        description="The category.",
        required=True,
    )
    tool = create_vector_search_tool(MockCollection(), filter=Filter("text", "eq", param))

    assert tool.parameters() == {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The query to search for."},
            "category": {
                "enum": ["travel", "work"],
                "type": "string",
                "description": "The category.",
            },
        },
        "required": ["query", "category"],
        "additionalProperties": False,
    }

    with pytest.raises(TypeError, match="cannot be represented"):
        Param("unsupported", object)
    with pytest.raises(ValueError, match="minimum cannot exceed"):
        Param("invalid_range", float, minimum=2, maximum=1)

    optional_code = Param("code", str | None, max_length=8)
    schema = create_vector_search_tool(MockCollection(), filter=Filter("text", "eq", optional_code)).parameters()
    assert {"type": "string", "maxLength": 8} in schema["properties"]["code"]["anyOf"]
    with pytest.raises(TypeError, match="homogeneous"):
        Param("pair", tuple[int, str])
    with pytest.raises(TypeError, match="JSON-compatible"):
        Param("binary_literal", Literal[b"value"])
    non_finite_literal = cast(Any, Literal)[float("inf")]
    with pytest.raises(ValueError, match="Literal numbers must be finite"):
        Param("non_finite_literal", non_finite_literal)
    with pytest.raises(TypeError, match="mapping keys must use the str type"):
        Param("integer_keys", dict[int, str])
    with pytest.raises(ValueError, match="numeric constraints require numeric"):
        Param("category_with_minimum", str, minimum=1)
    with pytest.raises(ValueError, match="numeric constraints require numeric"):
        Param("mixed_with_minimum", int | str, minimum=1)

    tuple_param = Param("numbers", tuple[int, ...])
    tuple_schema = create_vector_search_tool(
        MockCollection(),
        filter=Filter("text", "provider.numbers", tuple_param),
    ).parameters()
    assert tuple_schema["properties"]["numbers"] == {"type": "array", "items": {"type": "integer"}}

    nullable_number = Param("score", float | None, minimum=0, maximum=1)
    nullable_number_schema = create_vector_search_tool(
        MockCollection(),
        filter=Filter("text", "provider.score", nullable_number),
    ).parameters()
    assert nullable_number_schema["properties"]["score"] == {
        "anyOf": [{"type": "number"}, {"type": "null"}],
        "minimum": 0,
        "maximum": 1,
    }
    assert Param("level", Literal[1, None], minimum=1).minimum == 1

    source_default = ["travel"]
    frozen_default = Param("categories", list[str], default=source_default)
    source_default.append("work")
    returned_default = frozen_default.default
    returned_default.append("personal")
    assert frozen_default.default == ["travel"]


def test_filter_and_param_constructor_boundaries() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        Param("", str)
    with pytest.raises(ValueError, match="reserved"):
        Param("query", str)
    with pytest.raises(ValueError, match="required parameter cannot declare a default"):
        Param("required", str, required=True, default="value")
    with pytest.raises(ValueError, match="finite number"):
        Param("minimum", float, minimum=float("inf"))
    with pytest.raises(ValueError, match="non-negative integer"):
        Param("length", str, min_length=-1)
    with pytest.raises(ValueError, match="cannot exceed max_length"):
        Param("length", str, min_length=2, max_length=1)
    with pytest.raises(TypeError, match="field_name must be a string"):
        Filter(cast(Any, 1), "eq", "value")
    with pytest.raises(TypeError, match="operator must be a string"):
        Filter("text", cast(Any, 1), "value")
    with pytest.raises(ValueError, match="does not accept a value"):
        Filter("text", "is_null", "value")
    with pytest.raises(TypeError, match="operator must be a string"):
        FilterGroup(cast(Any, 1), (Filter("text", "eq", "value"),))
    with pytest.raises(ValueError, match="Unknown filter group"):
        FilterGroup(cast(Any, "xor"), (Filter("text", "eq", "value"),))
    with pytest.raises(TypeError, match="must be a sequence"):
        FilterGroup("and", cast(Any, "not-a-sequence"))
    with pytest.raises(ValueError, match="at least one"):
        FilterGroup("and", ())
    with pytest.raises(TypeError, match="Filter or FilterGroup"):
        FilterGroup("and", cast(Any, (object(),)))


async def test_param_native_schema_and_runtime_validation_for_container_types() -> None:
    items = Param("items", list[str], min_length=1, max_length=3)
    flags = Param("flags", dict[str, int], max_length=2)
    enabled = Param("enabled", bool, required=True)
    collection = MockCollection()
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            (
                Filter("text", "eq", items),
                Filter("text", "eq", flags),
                Filter("text", "eq", enabled),
            ),
        ),
    )

    schema = tool.parameters()
    assert schema["properties"]["items"] == {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "maxItems": 3,
    }
    assert schema["properties"]["flags"] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
        "maxProperties": 2,
    }
    assert schema["required"] == ["query", "enabled"]

    await tool(query="query", items=["a"], flags={"one": 1}, enabled=True)
    with pytest.raises(TypeError, match="does not match"):
        await tool(query="query", items=[1], enabled=True)
    with pytest.raises(ValueError, match="longer than 3"):
        await tool(query="query", items=["a", "b", "c", "d"], enabled=True)
    with pytest.raises(TypeError, match="Missing required"):
        await tool(query="query")


async def test_filter_resource_validation_boundaries() -> None:
    collection = MockCollection()
    invalid_mapping = Filter("text", "provider.native", cast(Any, {1: "value"}))
    with pytest.raises(TypeError, match="mapping keys must be strings"):
        await collection.search("query", filter=invalid_mapping)

    mutable_value: list[Any] = ["fixed"]
    mutated_filter = Filter("text", "in", mutable_value)
    mutable_value.append(Param("dynamic", str))
    with pytest.raises(ValueError, match="entire Filter value"):
        await collection.search("query", filter=mutated_filter)

    too_many = FilterGroup("and", (Filter("text", "eq", "value"),))
    too_many.filters = tuple(Filter("text", "eq", str(index)) for index in range(65))
    with pytest.raises(ValueError, match="more than 64 nodes"):
        await collection.search("query", filter=too_many)

    cyclic_group = FilterGroup("and", (Filter("text", "eq", "value"),))
    cyclic_group.filters = (cyclic_group,)
    with pytest.raises(ValueError, match="cannot contain cycles"):
        await collection.search("query", filter=cyclic_group)

    cyclic_expression_value = Filter("text", "provider.nested", "value")
    cyclic_expression_value.value = cyclic_expression_value
    with pytest.raises(ValueError, match="cannot contain cycles"):
        await collection.search("query", filter=cyclic_expression_value)

    nested: Filter | FilterGroup = Filter("relative_name", "eq", "value")
    assert Filter("text", "provider.nested", nested).value is nested


@pytest.mark.parametrize("operation", ["get", "search", "tool"])
async def test_filter_limits_are_checked_before_snapshot_copy(operation: str) -> None:
    collection = MockCollection()
    expression: Filter | FilterGroup = Filter("text", "eq", "value")
    for _ in range(1100):
        expression = FilterGroup("and", (expression,))

    with patch("agent_framework._vector_filters.deepcopy") as copy:
        with pytest.raises(ValueError, match="depth of 8"):
            if operation == "get":
                await collection.get(filter=expression)
            elif operation == "search":
                await collection.search("query", filter=expression)
            else:
                create_vector_search_tool(collection, filter=expression)
        copy.assert_not_called()


def test_filter_group_constructor_bounds_child_copying() -> None:
    child = Filter("text", "eq", "value")

    class LargeFilterSequence(Sequence[Filter]):
        def __init__(self) -> None:
            self.visited = 0

        def __len__(self) -> int:
            return 1_000_000

        def __getitem__(self, index: Any) -> Any:
            self.visited += 1
            assert self.visited <= 64
            return child

    filters = LargeFilterSequence()
    with pytest.raises(ValueError, match="more than 64 nodes"):
        FilterGroup("and", filters)
    assert filters.visited == 64
    assert len(FilterGroup("and", [child] * 63).filters) == 63


async def test_filter_value_traversal_stops_at_node_budget_before_copy() -> None:
    class LargeSequence(Sequence[int]):
        def __init__(self) -> None:
            self.visited = 0

        def __len__(self) -> int:
            return 1_000_000

        def __getitem__(self, index: Any) -> Any:
            self.visited += 1
            assert self.visited <= 64
            return index

        def __deepcopy__(self, memo: dict[int, Any]) -> Any:
            raise AssertionError("Oversized values must not be copied.")

    values = LargeSequence()
    expression = Filter("text", "provider.values", [])
    expression.value = values
    with pytest.raises(ValueError, match="more than 64 nodes"):
        await MockCollection().search("query", filter=expression)
    assert values.visited == 64


async def test_filter_collection_values_keep_existing_node_budget_and_snapshot_semantics() -> None:
    values = set(range(63))
    expression = Filter("text", "provider.native", values)
    collection = MockCollection()
    tool = create_vector_search_tool(collection, filter=expression)
    values.add(63)

    await tool(query="query")
    assert collection.last_search_filter == Filter("text", "provider.native", set(range(63)))
    with pytest.raises(ValueError, match="more than 64 nodes"):
        await collection.search("query", filter=expression)


@pytest.mark.parametrize(
    "wrap",
    [
        lambda param: {param},
        lambda param: frozenset((param,)),
        lambda param: {"key": param}.values(),
        lambda param: {param: "value"},
        lambda param: {(param,): "value"},
        lambda param: {"nested": {param}},
    ],
)
def test_filters_reject_params_in_collection_values_and_mapping_keys(wrap: Callable[[Param], Any]) -> None:
    with pytest.raises(ValueError, match="entire Filter value"):
        Filter("text", "provider.native", wrap(Param("hidden", str)))


def test_filter_constructor_bounds_nested_value_inspection() -> None:
    value: Any = "value"
    for _ in range(1100):
        value = [value]
    with pytest.raises(ValueError, match="depth of 8"):
        Filter("text", "provider.nested", value)


def test_param_default_is_bounded_before_copying() -> None:
    with patch("agent_framework._vector_filters.deepcopy") as copy:
        with pytest.raises(ValueError, match="more than 256 nodes"):
            Param("values", list[int], default=list(range(300)))
        copy.assert_not_called()


@pytest.mark.parametrize("operator", ["starts_with", "ends_with", "contains_text"])
@pytest.mark.parametrize("value", [1, False, []])
def test_string_filter_operators_require_string_operands(operator: str, value: Any) -> None:
    with pytest.raises(TypeError, match="must be a string"):
        Filter("text", operator, value)


@pytest.mark.parametrize("case", ["nested_param", "string_operand", "combined_budget"])
async def test_definitionless_search_still_validates_portable_filter_structure(case: str) -> None:
    class SearchOnly:
        async def search(self, values: Any, **kwargs: Any) -> SearchResults[SearchResponse[Record]]:
            raise AssertionError("Invalid filter reached the connector.")

    search = cast(SupportsVectorSearch[Record], SearchOnly())
    if case == "nested_param":
        expression = Filter("text", "provider.native", set())
        expression.value.add(Param("hidden", str))
        with pytest.raises(ValueError, match="entire Filter value"):
            create_vector_search_tool(search, filter=expression)
    elif case == "string_operand":
        tool = create_vector_search_tool(search, filter=Filter("text", "contains_text", Param("text", int)))
        with pytest.raises(TypeError, match="must be a string"):
            await tool(query="query", text=1)
    else:
        tool = create_vector_search_tool(
            search,
            filter=FilterGroup(
                "and",
                (
                    Filter("first", "in", Param("first", list[str])),
                    Filter("second", "in", Param("second", list[str])),
                ),
            ),
        )
        with pytest.raises(ValueError, match="more than 64 nodes"):
            await tool(query="query", first=["one"] * 40, second=["two"] * 40)


async def test_search_tool_param_edge_paths() -> None:
    collection = MockCollection()
    category = Param("category", str)
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            (
                Filter("id", "ne", "ignored"),
                Filter("text", "eq", category),
            ),
        ),
    )
    await tool(query="query", category="travel")
    assert collection.last_search_filter == FilterGroup(
        "and",
        (
            Filter("id", "ne", "ignored"),
            Filter("text", "eq", "travel"),
        ),
    )

    await tool(query="query")
    assert collection.last_search_filter == FilterGroup("and", (Filter("id", "ne", "ignored"),))

    with pytest.raises(ValueError, match="Invalid parameter name"):
        Param("bad-name", str)
    with pytest.raises(TypeError, match="'query'.*string"):
        await cast(Any, create_vector_search_tool(collection))(query=1)
    with pytest.raises(TypeError, match="Unexpected argument"):
        await tool(query="query", undeclared="value")
    with pytest.raises(ValueError, match="must be finite"):
        await create_vector_search_tool(
            collection,
            filter=Filter("text", "eq", Param("score", float)),
        )(query="query", score=float("nan"))
    with pytest.raises(TypeError, match="does not match"):
        await create_vector_search_tool(
            collection,
            filter=Filter("text", "eq", Param("level", Literal[1, 2], required=True)),
        )(query="query", level=True)

    nullable_tool = create_vector_search_tool(
        collection,
        filter=Filter("text", "provider.nullable", Param("nullable", str | None)),
    )
    await nullable_tool(query="query", nullable=None)
    assert collection.last_search_filter == Filter("text", "provider.nullable", None)

    nested_values_tool = create_vector_search_tool(
        collection,
        filter=Filter("text", "provider.values", Param("values", list[list[int]])),
    )
    with pytest.raises(ValueError, match="more than 256 nodes"):
        await nested_values_tool(query="query", values=[[index for index in range(20)] for _ in range(20)])

    with pytest.raises(ValueError, match="must be finite"):
        await collection.search("query", filter=Filter("text", "provider.number", Decimal("NaN")))


@pytest.mark.parametrize("value_type", [str, int, list[str | None]])
def test_param_omit_if_none_requires_nullable_type(value_type: Any) -> None:
    with pytest.raises(ValueError, match="value type that accepts None"):
        Param("value", value_type, default=None, omit_if_none=True)


def test_param_omit_if_none_requires_explicit_null_default() -> None:
    with pytest.raises(ValueError, match="explicit default=None"):
        Param("text", str | None, omit_if_none=True)
    with pytest.raises(ValueError, match="explicit default=None"):
        Param("text", str | None, default="hotel", omit_if_none=True)
    with pytest.raises(ValueError, match="required parameter cannot declare a default"):
        Param("text", str | None, required=True, default=None, omit_if_none=True)
    with pytest.raises(TypeError, match="omit_if_none must be a boolean"):
        Param("text", str | None, default=None, omit_if_none=cast(Any, "true"))


async def test_param_omit_if_none_exposes_nullable_schema_and_validates_values() -> None:
    param = Param("text", str | None, default=None, omit_if_none=True, max_length=8)
    tool = create_vector_search_tool(MockCollection(), filter=Filter("text", "contains_text", param))

    assert param.omit_if_none
    assert param.has_default
    assert param.default is None
    assert tool.parameters()["properties"]["text"] == {
        "anyOf": [{"type": "string", "maxLength": 8}, {"type": "null"}],
        "default": None,
    }
    assert tool.parameters()["required"] == ["query"]
    with pytest.raises(TypeError, match="does not match"):
        await tool(query="query", text=123)
    with pytest.raises(ValueError, match="longer than 8"):
        await tool(query="query", text="too long a value")


@pytest.mark.parametrize(
    ("operator", "value_type", "supplied"),
    [
        ("contains_text", str | None, "hotel"),
        ("contains_text", str | None, ""),
        ("contains_text", str | None, "*"),
        ("eq", Literal["hotel", None], "hotel"),
        ("gte", float | None, 0),
        ("in", list[str] | None, []),
        ("provider.enabled", bool | None, False),
    ],
)
async def test_search_tool_omits_only_null_param_values(operator: str, value_type: Any, supplied: Any) -> None:
    collection = MockCollection()
    param = Param("value", value_type, default=None, omit_if_none=True)
    search_filter = Filter("text", operator, param)
    tool = create_vector_search_tool(collection, filter=search_filter)

    await tool(query="query")
    assert collection.last_search_filter is None
    await tool(query="query", value=None)
    assert collection.last_search_filter is None
    await tool(query="query", value=supplied)
    assert collection.last_search_filter == Filter("text", operator, supplied)
    await tool(query="query", value=None)
    assert collection.last_search_filter is None
    assert search_filter.value is param


@pytest.mark.parametrize("operator", ["and", "or"])
async def test_search_tool_null_omission_keeps_remaining_group_children(operator: Literal["and", "or"]) -> None:
    collection = MockCollection()
    param = Param("text", str | None, default=None, omit_if_none=True)
    fixed = Filter("id", "eq", "one")
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(operator, (fixed, Filter("text", "contains_text", param))),
    )

    await tool(query="query")
    assert collection.last_search_filter == FilterGroup(operator, (fixed,))
    await tool(query="query", text=None)
    assert collection.last_search_filter == FilterGroup(operator, (fixed,))
    await tool(query="query", text="hotel")
    assert collection.last_search_filter == FilterGroup(operator, (fixed, Filter("text", "contains_text", "hotel")))


@pytest.mark.parametrize("operator", ["and", "or", "not"])
@pytest.mark.parametrize("nested", [False, True])
async def test_search_tool_null_omission_prunes_empty_groups(
    operator: Literal["and", "or", "not"], nested: bool
) -> None:
    collection = MockCollection()
    param = Param("text", str | None, default=None, omit_if_none=True)
    fixed = Filter("id", "eq", "one")
    group = FilterGroup(operator, (Filter("text", "contains_text", param),))
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup("and", (fixed, group)) if nested else group,
    )
    expected = FilterGroup("and", (fixed,)) if nested else None

    await tool(query="query")
    assert collection.last_search_filter == expected
    await tool(query="query", text=None)
    assert collection.last_search_filter == expected
    await tool(query="query", text="hotel")
    resolved_group = FilterGroup(operator, (Filter("text", "contains_text", "hotel"),))
    assert collection.last_search_filter == (FilterGroup("and", (fixed, resolved_group)) if nested else resolved_group)


async def test_search_tool_null_omission_is_opt_in_per_parameter() -> None:
    collection = MockCollection()
    omitted = Param("text", str | None, default=None, omit_if_none=True)
    retained = Param("native", str | None, default=None)
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            (Filter("text", "contains_text", omitted), Filter("text", "provider.nullable", retained)),
        ),
    )

    assert not retained.omit_if_none
    await tool(query="query", text=None, native=None)
    assert collection.last_search_filter == FilterGroup("and", (Filter("text", "provider.nullable", None),))
    await tool(query="query")
    assert collection.last_search_filter == FilterGroup("and", (Filter("text", "provider.nullable", None),))

    strict_tool = create_vector_search_tool(collection, filter=Filter("text", "contains_text", retained))
    with pytest.raises(ValueError, match="requires a value"):
        await strict_tool(query="query", native=None)
    with pytest.raises(ValueError, match="requires a value"):
        await strict_tool(query="query")
    with pytest.raises(ValueError, match="requires a value"):
        Filter("text", "contains_text", None)


def test_search_tool_rejects_conflicting_null_omission_policies() -> None:
    with pytest.raises(ValueError, match="conflicting declarations"):
        create_vector_search_tool(
            MockCollection(),
            filter=FilterGroup(
                "and",
                (
                    Filter("text", "contains_text", Param("text", str | None, default=None, omit_if_none=True)),
                    Filter("text", "provider.nullable", Param("text", str | None, default=None)),
                ),
            ),
        )


@pytest.mark.parametrize("option_name", ["top", "skip"])
def test_search_tool_rejects_null_omission_for_paging(option_name: Literal["top", "skip"]) -> None:
    param = Param(option_name, int | None, default=None, omit_if_none=True, minimum=1, maximum=10)
    with pytest.raises(ValueError, match=f"{option_name} Param does not support omit_if_none"):
        create_vector_search_tool(
            MockCollection(),
            top=param if option_name == "top" else 5,
            skip=param if option_name == "skip" else 0,
        )


async def test_search_operations_snapshot_mutable_filters() -> None:
    collection = MockCollection()
    collection.mutate_search_filter = True
    values = ["one"]
    search_filter = Filter("id", "in", values)

    await collection.search("query", filter=search_filter)

    assert values == ["one"]
    assert search_filter.value == ["one"]

    tool = create_vector_search_tool(collection, filter=search_filter)
    search_filter.field_name = "text"
    values.append("two")
    await tool(query="query")

    assert isinstance(collection.last_search_filter, Filter)
    assert collection.last_search_filter.field_name == "id"
    assert collection.last_search_filter.value == ["one", "connector mutation"]


@pytest.mark.parametrize("supply_argument", [False, True])
async def test_search_tool_copies_mutable_param_values_per_invocation(supply_argument: bool) -> None:
    class MutatingSearch:
        def __init__(self) -> None:
            self.seen_values: list[list[str]] = []

        async def search(
            self,
            values: Any,
            *,
            search_type: SearchType = "vector",
            filter: Filter | FilterGroup | None = None,
            top: int = 3,
            skip: int = 0,
            **kwargs: Any,
        ) -> SearchResults[SearchResponse[Record]]:
            assert isinstance(filter, Filter)
            received = cast(list[str], filter.value)
            self.seen_values.append(list(received))
            received.append("mutated")
            return SearchResults([])

    search = MutatingSearch()
    tool = create_vector_search_tool(
        cast(SupportsVectorSearch[Record], search),
        filter=Filter("tenant_id", "in", Param("tenant_ids", list[str], default=["acme"])),
    )

    supplied = ["acme"]
    arguments = {"tenant_ids": supplied} if supply_argument else {}
    await tool(query="first", **arguments)
    await tool(query="second", **arguments)

    assert search.seen_values == [["acme"], ["acme"]]
    assert supplied == ["acme"]


async def test_search_tool_deep_copies_supplied_mapping_values() -> None:
    class MutatingSearch:
        async def search(
            self, values: Any, *, filter: Filter | FilterGroup | None = None, **kwargs: Any
        ) -> SearchResults[SearchResponse[Record]]:
            assert isinstance(filter, Filter)
            filter.value["tags"].append("mutated")
            return SearchResults([])

    tool = create_vector_search_tool(
        cast(SupportsVectorSearch[Record], MutatingSearch()),
        filter=Filter("metadata", "provider.native", Param("metadata", dict[str, list[str]])),
    )
    supplied = {"tags": ["original"]}

    await tool(query="query", metadata=supplied)

    assert supplied == {"tags": ["original"]}


async def test_runtime_operations_mark_vector_store_feature_usage() -> None:
    collection = MockCollection()
    store = MockStore(collection)

    with patch("agent_framework._vectors.mark_feature_used") as mark_feature_used_mock:
        await collection.serialize(Record("one", "hello"), generate_vectors=False)
        mark_feature_used_mock.assert_called_with(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        collection.deserialize({"record_id": "one", "body": "hello", "vector": None})
        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        await collection.upsert([Record("one", "hello")], generate_vectors=False)
        mark_feature_used_mock.assert_any_call(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        await collection.get(["one"])
        mark_feature_used_mock.assert_any_call(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        await collection.delete(["one"])
        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        await store.collection_exists("records")
        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_VECTOR_STORES)

        mark_feature_used_mock.reset_mock()
        await collection.search(vector=[1.0, 0.0])
        mark_feature_used_mock.assert_called_once_with(FeatureIndex.CORE_VECTOR_STORES)
