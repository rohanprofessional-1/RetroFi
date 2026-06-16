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
STATE_CODES = {"ca", "fl", "ga", "il", "nc", "ny", "oh", "pa", "tx"}


def rebuild_index(sources_dir: Path, collection_name: str = "retrofi_incentive_sources", reset: bool = True) -> dict:
    parsed_sources = parse_sources(sources_dir)
    chunks = chunk_sources(parsed_sources)
    records = extract_records(chunks)

    store = ChromaVectorStore(collection_name=collection_name)
    if reset:
        store.reset()
    indexed_count = store.upsert_records(records)

    manifest = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "sources_dir": str(sources_dir),
        "collection_name": collection_name,
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
    return manifest, parsed_sources


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
    parser.add_argument(
        "--states-only",
        action="store_true",
        help="Only index state-specific folders, skip the main sources directory.",
    )
    args = parser.parse_args()

    sources_dir = Path(args.sources_dir)
    reset = not args.no_reset

    if not args.states_only:
        # Index main sources directory (excludes state-specific subdirectories)
        print("Indexing main sources directory...")
        manifest, _ = rebuild_index(sources_dir, collection_name="retrofi_incentive_sources", reset=reset)
        counts = manifest["counts"]
        print(
            f"Main index: {counts['files_parsed']} files, {counts['chunks_created']} chunks, "
            f"{counts['records_indexed']} records"
        )
        for file_entry in manifest["files"]:
            for warning in file_entry["warnings"]:
                print(f"WARNING {file_entry['path']}: {warning}")
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Main manifest written to {MANIFEST_PATH}")

    # Index state-specific directories
    for state_code in STATE_CODES:
        state_dir = sources_dir / state_code
        if not state_dir.exists():
            continue
        print(f"\nIndexing state: {state_code.upper()}")
        collection_name = f"retrofi_incentive_sources_{state_code}"
        manifest, _ = rebuild_index(state_dir, collection_name=collection_name, reset=reset)
        counts = manifest["counts"]
        if counts["files_parsed"] == 0:
            print(f"  No sources found in {state_code}")
            continue
        print(
            f"  {counts['files_parsed']} files, {counts['chunks_created']} chunks, "
            f"{counts['records_indexed']} records"
        )
        for file_entry in manifest["files"]:
            for warning in file_entry["warnings"]:
                print(f"  WARNING {file_entry['path']}: {warning}")

        state_manifest_path = BACKEND_ROOT / "data" / f"source_index_manifest_{state_code}.json"
        state_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"  Manifest written to {state_manifest_path}")


if __name__ == "__main__":
    main()
