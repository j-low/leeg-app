"""
Unit tests for Stage 2: Hybrid RAG (embeddings, ingestion, retrieval, reranking, stage).

All external dependencies are mocked:
  - sentence-transformers (SentenceTransformer, CrossEncoder)
  - Redis (redis.asyncio)
  - Qdrant (qdrant_client.AsyncQdrantClient)
  - LLMLingua (PromptCompressor)
  - SQLAlchemy async session

Tests run without any running infrastructure.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.schemas.pipeline import EntityMap, Intent, StructuredInput


# ── Fixtures ──────────────────────────────────────────────────────────────────

CTX = {"team_id": 42, "channel": "sms", "from_phone": "+16135550101"}

SAMPLE_STRUCTURED_INPUT = StructuredInput(
    raw_text="What position does Bob play?",
    channel="sms",
    from_phone="+16135550101",
    entities=EntityMap(persons=["Bob"]),
    intent=Intent.query,
    is_safe=True,
    confidence=0.5,
    metadata=CTX,
)

ATTENDANCE_INPUT = StructuredInput(
    raw_text="yes I'll be there",
    channel="sms",
    from_phone="+16135550101",
    entities=EntityMap(actions=["yes"]),
    intent=Intent.attendance_update,
    is_safe=True,
    confidence=0.85,
    metadata=CTX,
)


# ── Embedding tests ───────────────────────────────────────────────────────────

class TestEmbeddings:
    def test_embed_texts_calls_model_on_cache_miss(self):
        """On cache miss, the SentenceTransformer model is called."""
        import numpy as np

        fake_vector = [0.1] * 384
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([fake_vector])

        async def mock_redis_mget(*args):
            return [None]  # cache miss

        async def run():
            with (
                patch("app.rag.embeddings._get_model", return_value=mock_model),
                patch("app.rag.embeddings._get_redis") as mock_get_redis,
            ):
                mock_redis = AsyncMock()
                mock_redis.mget = AsyncMock(return_value=[None])
                mock_redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
                pipe = AsyncMock()
                pipe.set = AsyncMock()
                pipe.execute = AsyncMock(return_value=[True])
                mock_redis.pipeline.return_value = pipe
                mock_redis.aclose = AsyncMock()
                mock_get_redis.return_value = mock_redis

                from app.rag.embeddings import embed_texts
                result = await embed_texts(["hello world"])

            assert len(result) == 1
            assert len(result[0]) == 384
            mock_model.encode.assert_called_once()

        asyncio.run(run())

    def test_embed_texts_uses_cache_on_hit(self):
        """On cache hit, the model is NOT called."""
        import numpy as np

        fake_vector = [0.5] * 384
        cached_json = json.dumps(fake_vector)
        mock_model = MagicMock()

        async def run():
            with (
                patch("app.rag.embeddings._get_model", return_value=mock_model),
                patch("app.rag.embeddings._get_redis") as mock_get_redis,
            ):
                mock_redis = AsyncMock()
                mock_redis.mget = AsyncMock(return_value=[cached_json])
                mock_redis.aclose = AsyncMock()
                mock_get_redis.return_value = mock_redis

                from app.rag.embeddings import embed_texts
                result = await embed_texts(["hello world"])

            assert result[0] == fake_vector
            mock_model.encode.assert_not_called()

        asyncio.run(run())

    def test_embed_texts_empty_input(self):
        async def run():
            from app.rag.embeddings import embed_texts
            result = await embed_texts([])
            assert result == []

        asyncio.run(run())


# ── Ingestion tests ───────────────────────────────────────────────────────────

class TestIngestion:
    def _make_db_mock(self, players=None, games=None, prefs=None, surveys=None):
        """Build a mock AsyncSession that returns the given records."""
        db = AsyncMock()

        def make_result(rows):
            result = MagicMock()
            result.scalars.return_value.all.return_value = rows or []
            return result

        # execute() returns different results based on call order
        db.execute.side_effect = [
            make_result(players or []),
            make_result(games or []),
            make_result(prefs or []),
            make_result(surveys or []),
        ]
        return db

    def _mock_splitter(self):
        """Return a mock splitter that passes text through unchanged."""
        mock = MagicMock()
        mock.split_text.side_effect = lambda text: [text]
        return mock

    def test_ingestion_creates_player_points(self):
        """Player records are converted to Qdrant PointStructs."""
        player = MagicMock()
        player.id = 1
        player.name = "Alice"
        player.team_id = 42
        player.position_prefs = ["wing", "center"]
        player.skill_notes = "Fast skater"
        player.sub_flag = False

        async def run():
            with (
                patch("app.rag.ingestion._get_qdrant") as mock_get_qdrant,
                patch("app.rag.ingestion._get_splitter", return_value=self._mock_splitter()),
                patch("app.rag.ingestion.embed_texts", return_value=[[0.1] * 384]),
            ):
                mock_client = AsyncMock()
                mock_client.get_collections.return_value = MagicMock(collections=[])
                mock_client.create_collection = AsyncMock()
                mock_client.upsert = AsyncMock()
                mock_client.close = AsyncMock()
                mock_get_qdrant.return_value = mock_client

                db = self._make_db_mock(players=[player])

                from app.rag.ingestion import ingest_team_data
                summary = await ingest_team_data(42, db)

            assert summary.get("player") == 1
            mock_client.upsert.assert_called()
            call_args = mock_client.upsert.call_args
            points = call_args.kwargs.get("points") or call_args.args[1]
            assert len(points) >= 1
            assert points[0].payload["team_id"] == 42
            assert points[0].payload["doc_type"] == "player"

        asyncio.run(run())

    def test_ingestion_collection_created_if_missing(self):
        """Qdrant collection is created when it does not exist."""
        async def run():
            with (
                patch("app.rag.ingestion._get_qdrant") as mock_get_qdrant,
                patch("app.rag.ingestion._get_splitter", return_value=self._mock_splitter()),
                patch("app.rag.ingestion.embed_texts", return_value=[[0.1] * 384]),
            ):
                mock_client = AsyncMock()
                mock_client.get_collections.return_value = MagicMock(collections=[])
                mock_client.create_collection = AsyncMock()
                mock_client.upsert = AsyncMock()
                mock_client.close = AsyncMock()
                mock_get_qdrant.return_value = mock_client

                db = self._make_db_mock()

                from app.rag.ingestion import ingest_team_data
                await ingest_team_data(42, db)

            mock_client.create_collection.assert_called_once()

        asyncio.run(run())

    def test_ingestion_skips_collection_creation_if_exists(self):
        """Qdrant collection is NOT re-created if it already exists."""
        async def run():
            existing = MagicMock()
            existing.name = "leeg_docs"
            with (
                patch("app.rag.ingestion._get_qdrant") as mock_get_qdrant,
                patch("app.rag.ingestion._get_splitter", return_value=self._mock_splitter()),
                patch("app.rag.ingestion.embed_texts", return_value=[[0.1] * 384]),
            ):
                mock_client = AsyncMock()
                mock_client.get_collections.return_value = MagicMock(collections=[existing])
                mock_client.create_collection = AsyncMock()
                mock_client.upsert = AsyncMock()
                mock_client.close = AsyncMock()
                mock_get_qdrant.return_value = mock_client

                db = self._make_db_mock()

                from app.rag.ingestion import ingest_team_data
                await ingest_team_data(42, db)

            mock_client.create_collection.assert_not_called()

        asyncio.run(run())


# ── Retrieval tests ───────────────────────────────────────────────────────────

class TestRetriever:
    def test_retrieve_filters_by_team_id(self):
        """Qdrant search filter always includes team_id from context."""
        fake_vector = [0.1] * 384

        async def run():
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)  # cache miss
            mock_redis.set = AsyncMock()
            mock_redis.aclose = AsyncMock()

            async def mock_from_url(*args, **kwargs):
                return mock_redis

            with (
                patch("app.rag.retriever._get_qdrant") as mock_get_qdrant,
                patch("app.rag.retriever.embed_query", return_value=fake_vector),
                patch("app.rag.retriever.aioredis.from_url", side_effect=mock_from_url),
            ):
                mock_hit = MagicMock()
                mock_hit.score = 0.92
                mock_hit.payload = {
                    "text": "Player: Alice. Position preferences: wing.",
                    "team_id": 42,
                    "doc_type": "player",
                    "entity_id": 1,
                    "chunk_idx": 0,
                }

                mock_client = AsyncMock()
                mock_client.search = AsyncMock(return_value=[mock_hit])
                mock_client.close = AsyncMock()
                mock_get_qdrant.return_value = mock_client

                from app.rag.retriever import retrieve
                results = await retrieve("What position does Alice play?", {"team_id": 42})

            assert len(results) == 1
            assert results[0]["score"] == 0.92
            assert results[0]["doc_type"] == "player"

            # Confirm the filter passed to Qdrant included team_id=42
            search_call = mock_client.search.call_args
            qdrant_filter = search_call.kwargs.get("query_filter")
            must = qdrant_filter.must
            team_condition = next(c for c in must if c.key == "team_id")
            assert team_condition.match.value == 42

        asyncio.run(run())

    def test_retrieve_returns_cached_result(self):
        """When Redis has a cached result, Qdrant is not queried."""
        cached = [{"text": "cached chunk", "score": 0.9, "doc_type": "player",
                   "entity_id": 1, "team_id": 42, "chunk_idx": 0}]

        async def run():
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=json.dumps(cached))
            mock_redis.aclose = AsyncMock()

            # aioredis.from_url is sync but returns an awaitable Redis object.
            # Use side_effect with an async function so `await from_url(...)` works.
            async def mock_from_url(*args, **kwargs):
                return mock_redis

            with (
                patch("app.rag.retriever._get_qdrant") as mock_get_qdrant,
                patch("app.rag.retriever.embed_query", return_value=[0.1] * 384),
                patch("app.rag.retriever.aioredis.from_url", side_effect=mock_from_url),
            ):
                mock_get_qdrant.return_value = AsyncMock()

                from app.rag.retriever import retrieve
                results = await retrieve("query", {"team_id": 42})

            assert results == cached
            mock_get_qdrant.return_value.search.assert_not_called()

        asyncio.run(run())


# ── Reranker tests ────────────────────────────────────────────────────────────

class TestReranker:
    def test_rerank_orders_by_score_descending(self):
        """Reranker returns chunks sorted by cross-encoder score."""
        import numpy as np

        chunks = [
            {"text": "low relevance chunk", "score": 0.5},
            {"text": "high relevance chunk", "score": 0.8},
            {"text": "medium relevance chunk", "score": 0.6},
        ]
        # Cross-encoder scores in same order as input
        mock_scores = np.array([0.2, 0.9, 0.5])

        async def run():
            with patch("app.rag.reranker._get_reranker") as mock_get_reranker:
                mock_ce = MagicMock()
                mock_ce.predict.return_value = mock_scores
                mock_get_reranker.return_value = mock_ce

                from app.rag.reranker import rerank
                result = await rerank("query", chunks, top_k=2)

            assert len(result) == 2
            assert result[0]["text"] == "high relevance chunk"
            assert result[0]["rerank_score"] == pytest.approx(0.9)
            assert result[1]["text"] == "medium relevance chunk"

        asyncio.run(run())

    def test_rerank_empty_input(self):
        async def run():
            from app.rag.reranker import rerank
            result = await rerank("query", [], top_k=5)
            assert result == []

        asyncio.run(run())


# ── RAG stage tests ───────────────────────────────────────────────────────────

class TestRagStage:
    def test_attendance_intent_skips_rag(self):
        """attendance_update intent returns empty context without touching Qdrant."""
        async def run():
            with patch("app.stages.retrieval.rag.retrieve") as mock_retrieve:
                from app.stages.retrieval import retrieve_context
                result = await retrieve_context(ATTENDANCE_INPUT, CTX)

            assert result == []
            mock_retrieve.assert_not_called()

        asyncio.run(run())

    def test_query_intent_triggers_retrieval(self):
        """Non-attendance intents call retrieve() and rerank()."""
        mock_chunks = [
            {"text": "Player: Bob. Position preferences: defense.", "score": 0.88,
             "doc_type": "player", "entity_id": 2, "team_id": 42, "chunk_idx": 0}
        ]

        async def run():
            with (
                patch("app.stages.retrieval.rag.retrieve", return_value=mock_chunks),
                patch("app.stages.retrieval.rag.rerank", return_value=mock_chunks),
                patch("app.stages.retrieval.rag._try_import_llmlingua", return_value=None),
            ):
                from app.stages.retrieval import retrieve_context
                result = await retrieve_context(SAMPLE_STRUCTURED_INPUT, CTX)

            assert len(result) == 1
            assert result[0]["doc_type"] == "player"

        asyncio.run(run())

    def test_no_results_returns_empty(self):
        """Empty retrieval result propagates as empty list."""
        async def run():
            with (
                patch("app.stages.retrieval.rag.retrieve", return_value=[]),
                patch("app.stages.retrieval.rag.rerank", return_value=[]),
            ):
                from app.stages.retrieval import retrieve_context
                result = await retrieve_context(SAMPLE_STRUCTURED_INPUT, CTX)

            assert result == []

        asyncio.run(run())
