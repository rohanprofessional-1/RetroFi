import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from services.incentive_schema_extractor import extract_records
from services.source_parsers import chunk_sources, file_hash, parse_sources
from services.vector_store import ChromaVectorStore


MANIFEST_PATH = BACKEND_ROOT / "data" / "source_index_manifest.json"


def rebuild_index(sources_dir: Path, reset: bool = True) -> dict:
    parsed_sources = parse_sources(sources_dir)
    chunks = chunk_sources(parsed_sources)
    records = extract_records(chunks)

    store = ChromaVectorStore()
    if reset:
        store.reset()
    indexed_count = store.upsert_records(records)

    manifest = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "sources_dir": str(sources_dir),
        "collection_count": store.count(),
        "files": [
            {
                "path": str(source.path.relative_to(REPO_ROOT)),
                "sha256": file_hash(source.path),
                "parser": source.parser,
                "source_type": source.source_type,
                "title": source.title,
                "document_date": source.document_date,
                "warnings": source.warnings,
            }
            for source in parsed_sources
        ],
        "counts": {
            "files_parsed": len(parsed_sources),
            "chunks_created": len(chunks),
            "records_indexed": indexed_count,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Rebuild the RetroFi source vector index.")
    parser.add_argument(
        "--sources-dir",
        default=str(REPO_ROOT / "sources"),
        help="Directory containing source HTML/PDF files.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Upsert records without deleting the existing Chroma collection first.",
    )
    args = parser.parse_args()

    manifest = rebuild_index(Path(args.sources_dir), reset=not args.no_reset)
    counts = manifest["counts"]
    print(
        "Indexed sources: "
        f"{counts['files_parsed']} files, "
        f"{counts['chunks_created']} chunks, "
        f"{counts['records_indexed']} records."
    )
    for file_entry in manifest["files"]:
        for warning in file_entry["warnings"]:
            print(f"WARNING {file_entry['path']}: {warning}")
    print(f"Manifest written to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
