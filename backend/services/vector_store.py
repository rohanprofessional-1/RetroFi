import hashlib
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from services.incentive_schema_extractor import IncentiveIndexRecord


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_PATH = BACKEND_ROOT / "data" / "chroma"
COLLECTION_NAME = "retrofi_incentive_sources"


class DeterministicEmbeddingFunction:
    """Small local embedding adapter for development Chroma indexes."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def name(self) -> str:
        return f"retrofi-hash-embedding-{self.dimensions}"

    def __call__(self, input):  # Chroma passes a list of strings.
        return [self.embed(text) for text in input]

    def embed_query(self, input):
        return self(input)

    def embed_documents(self, input):
        return self(input)

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class ChromaVectorStore:
    def __init__(
        self,
        persist_path: Path = DEFAULT_CHROMA_PATH,
        collection_name: str = COLLECTION_NAME,
        embedding_function: Optional[DeterministicEmbeddingFunction] = None,
    ):
        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "chromadb is not installed. Run `pip install -r backend/requirements.txt` "
                "before rebuilding or querying the source vector index."
            ) from exc

        self.persist_path = persist_path
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.embedding_function = embedding_function or DeterministicEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"description": "RetroFi ATL source-backed incentive records"},
        )

    def reset(self):
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            embedding_function=self.embedding_function,
            metadata={"description": "RetroFi ATL source-backed incentive records"},
        )

    def upsert_records(self, records: Iterable[IncentiveIndexRecord]) -> int:
        records = list(records)
        if not records:
            return 0

        self.collection.upsert(
            ids=[record.id for record in records],
            documents=[record.raw_text_chunk for record in records],
            metadatas=[
                _sanitize_metadata({
                    **record.to_metadata(),
                    "linked_program_id": record.program_id,
                })
                for record in records
            ],
        )
        return len(records)

    def query(
        self,
        query_text: str,
        limit: int = 12,
        measures: Optional[List[str]] = None,
        jurisdiction: Optional[str] = None,
        utility: Optional[str] = None,
    ) -> List[Dict]:
        query_result = self.collection.query(
            query_texts=[query_text],
            n_results=max(limit * 4, limit),
            include=["documents", "metadatas", "distances"],
        )

        documents = query_result.get("documents", [[]])[0]
        metadatas = query_result.get("metadatas", [[]])[0]
        distances = query_result.get("distances", [[]])[0]
        ids = query_result.get("ids", [[]])[0]

        matches: List[Dict] = []
        for record_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            if measures and metadata.get("measure") not in measures:
                continue
            if jurisdiction and not _jurisdiction_matches(metadata.get("jurisdiction", ""), jurisdiction):
                continue
            utility_territory = metadata.get("utility_territory", "")
            if utility and utility_territory and utility_territory.lower() != utility.lower():
                continue
            matches.append(
                {
                    **metadata,
                    "id": record_id,
                    "raw_text_chunk": document,
                    "distance": distance,
                    "score": 1 / (1 + distance) if distance is not None else 0,
                }
            )
            if len(matches) >= limit:
                break
        return matches

    def count(self) -> int:
        return self.collection.count()


def _sanitize_metadata(metadata: Dict) -> Dict:
    sanitized = {}
    for key, value in metadata.items():
        if value is None:
            sanitized[key] = ""
        elif isinstance(value, bool):
            sanitized[key] = value
        elif isinstance(value, (int, float, str)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


def _jurisdiction_matches(record_jurisdiction: str, query_jurisdiction: str) -> bool:
    record = record_jurisdiction.lower()
    query = query_jurisdiction.lower()
    return record in {"us", "federal"} or record == query or query in record
