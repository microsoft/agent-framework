# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import warnings
from ast import AST, unparse
from collections.abc import AsyncIterable, Mapping, Sequence
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Annotated, Any, ClassVar, cast
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
    GeneratedEmbeddings,
    IndexKind,
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
        self.last_search_vector: Sequence[float | int] | None = None
        self.last_search_filter: Any | list[Any] | None = None
        self.last_search_top = 0
        self.last_search_skip = 0
        self.fail_upsert = False
        self.upsert_error: Exception | None = None
        self.get_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.search_error: Exception | None = None
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
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[Any] | None:
        if self.get_error is not None:
            raise self.get_error
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
        filter: Any | list[Any] | None = None,
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
        self.last_search_vector = vector
        self.last_search_filter = filter
        self.last_search_top = top
        self.last_search_skip = skip
        raw_results = self.raw_search_results or [
            {"record": record, "score": score} for record, score in zip(self.records.values(), (0.9, 0.4), strict=False)
        ]
        return SearchResults(raw_results, metadata={"mock_count": len(self.records)})

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return cast(float | None, result["score"])

    def _lambda_parser(self, node: AST) -> str:
        return unparse(node)


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
    with pytest.raises(ValueError, match="index kind"):
        cast(Any, VectorStoreField)("vector", dimensions=3, index_kind="unknown")
    with pytest.raises(ValueError, match="distance function"):
        cast(Any, VectorStoreField)("vector", dimensions=3, distance_function="unknown")


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
    assert definition.vector_fields[0].index_kind == "hnsw"
    assert definition.vector_fields[0].distance_function == "cosine_similarity"

    frozen_field = cast(Any, definition.fields[0])
    with pytest.raises(FrozenInstanceError):
        frozen_field.name = "changed"
    frozen_definition = cast(Any, definition)
    with pytest.raises(FrozenInstanceError):
        frozen_definition.fields = ()


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


async def test_collection_crud_rejects_singular_ordinary_inputs() -> None:
    collection = MockCollection()

    with pytest.raises(TypeError, match="records must be a sequence"):
        await cast(Any, collection.upsert)(Record("one", "hello"))
    with pytest.raises(TypeError, match="keys must be a sequence"):
        await collection.get("one")
    with pytest.raises(TypeError, match="keys must be a sequence"):
        await collection.delete("one")


async def test_vector_search_generates_query_vector_and_filters_threshold() -> None:
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
    assert responses[0]["record"].id == "one"
    assert responses[0]["score"] == 0.9
    assert len(responses) == 1


async def test_keyword_hybrid_search_uses_single_search_method() -> None:
    collection = MockCollection()

    await collection.search("words", search_type="keyword_hybrid")

    assert collection.last_search_type == "keyword_hybrid"


async def test_vector_search_validates_inputs_and_supported_type() -> None:
    collection = MockCollection()

    with pytest.raises(ValueError, match="requires values"):
        await cast(Any, collection.search)()

    class VectorOnlyCollection(MockCollection):
        supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    with pytest.raises(NotImplementedError, match="not supported"):
        await VectorOnlyCollection().search("words", search_type="keyword_hybrid")


async def test_vector_search_requires_explicit_distance_for_score_threshold() -> None:
    collection = MockCollection()
    collection.definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("vector", name="vector", type_="float", dimensions=2),
        ],
        collection_name="records",
    )

    with pytest.raises(ValueError, match="explicit distance"):
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


def test_vector_search_builds_connector_filter() -> None:
    collection = MockCollection()

    assert collection._build_filter("lambda record: record.category == 'travel'") == "record.category == 'travel'"
    assert collection._build_filter([
        "lambda record: record.category == 'travel'",
        "lambda record: record.id != 'ignored'",
    ]) == ["record.category == 'travel'", "record.id != 'ignored'"]


async def test_vector_search_passes_translated_filter_to_connector() -> None:
    collection = MockCollection()

    await collection.search(
        "query",
        filter="lambda record: record.category == 'travel'",
    )

    assert collection.last_search_filter == "record.category == 'travel'"


def test_vector_search_rejects_filter_without_lambda() -> None:
    with pytest.raises(ValueError, match="No lambda"):
        MockCollection()._build_filter("record.category == 'travel'")


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
    tool = create_vector_search_tool(
        collection,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "category": {"type": "string", "description": "The category to match."},
                "top": {
                    "type": "integer",
                    "description": "The maximum number of results.",
                    "maximum": 5,
                },
                "skip": {
                    "type": "integer",
                    "description": "The number of results to skip.",
                    "maximum": 10,
                },
            },
            "required": ["query", "category"],
            "additionalProperties": False,
        },
    )

    await tool(query="first", category="travel", top=1, skip=2)

    assert set(tool.parameters()["properties"]) == {"query", "category", "top", "skip"}
    assert collection.last_search_filter == "record.category == 'travel'"
    assert collection.last_search_top == 1
    assert collection.last_search_skip == 2


def test_create_search_tool_validates_custom_schema() -> None:
    collection = MockCollection()

    with pytest.raises(ValueError, match="required string"):
        create_vector_search_tool(collection, parameters={"type": "object", "properties": {}})
    with pytest.raises(ValueError, match="required string"):
        create_vector_search_tool(
            collection,
            parameters={
                "type": "object",
                "properties": {"query": {"type": "integer"}},
                "required": ["query"],
            },
        )
    with pytest.raises(ValueError, match="declare an integer maximum"):
        create_vector_search_tool(
            collection,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top": {"type": "integer"},
                },
                "required": ["query"],
            },
        )


async def test_create_search_tool_enforces_paging_limits_and_result_cap() -> None:
    collection = MockCollection()
    collection.raw_search_results = [
        {"record": {"record_id": str(index), "body": f"record {index}"}, "score": 0.9} for index in range(3)
    ]
    tool = create_vector_search_tool(
        collection,
        top=2,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top": {"type": "integer", "maximum": 2},
                "skip": {"type": "integer", "maximum": 4},
            },
            "required": ["query"],
        },
    )

    results = await tool(query="records", top=2, skip=4)
    assert len(results) == 2

    with pytest.raises(ValueError, match="top must not exceed"):
        await tool(query="records", top=3)
    with pytest.raises(ValueError, match="skip must not exceed"):
        await tool(query="records", skip=5)


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


def test_filter_parser_and_default_mapper_edge_paths() -> None:
    collection = MockCollection()
    assert collection._build_filter(lambda record: record.id == "one") == "record.id == 'one'"
    with pytest.raises(ValueError, match="Unable to parse"):
        collection._build_filter("lambda record:")


async def test_search_tool_filter_mapper_edge_paths() -> None:
    collection = MockCollection()
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string"},
        },
        "required": ["query", "category"],
    }
    tool = create_vector_search_tool(
        collection,
        parameters=parameters,
        filter=["lambda record: record.id != 'ignored'"],
    )
    await tool(query="query", category="travel")
    assert collection.last_search_filter == ["record.id != 'ignored'", "record.category == 'travel'"]

    invalid_tool = create_vector_search_tool(
        collection,
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}, "bad-name": {"type": "string"}},
            "required": ["query"],
        },
    )
    with pytest.raises(ValueError, match="cannot be mapped"):
        await invalid_tool(query="query", **{"bad-name": "value"})
    with pytest.raises(TypeError, match="'query'.*string"):
        await cast(Any, create_vector_search_tool(collection))(query=1)


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
