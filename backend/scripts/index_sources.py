import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"
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
    parser.add_argument(
        "--extract-programs",
        action="store_true",
        help="Run LLM extraction to update incentive_programs_{state}.json from source documents.",
    )
    parser.add_argument(
        "--extract-model",
        default="qwen2.5:7b",
        help="Ollama model to use for LLM extraction (default: qwen2.5:7b).",
    )
    parser.add_argument(
        "--extract-base-url",
        default="http://127.0.0.1:11434",
        help="Ollama base URL for LLM extraction (default: http://127.0.0.1:11434).",
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

    # LLM extraction for structured incentive programs
    if args.extract_programs:
        _run_extraction(sources_dir, args.extract_model, args.extract_base_url)


def _run_extraction(sources_dir: Path, model: str, base_url: str):
    """Run LLM extraction pipeline for each state directory."""
    from services.llm_extractor import extract_programs_from_chunks

    print("\n" + "=" * 60)
    print("LLM EXTRACTION: Generating incentive_programs_{state}.json")
    print(f"Model: {model}  Base URL: {base_url}")
    print("=" * 60)

    for state_code in sorted(STATE_CODES):
        state_dir = sources_dir / state_code
        if not state_dir.exists():
            continue

        print(f"\nExtracting programs for: {state_code.upper()}")

        # Parse and chunk the source documents
        parsed_sources = parse_sources(state_dir)
        if not parsed_sources:
            print(f"  No source documents found")
            continue

        chunks = chunk_sources(parsed_sources)
        print(f"  {len(parsed_sources)} files, {len(chunks)} chunks")

        # Run LLM extraction
        programs, review_items = extract_programs_from_chunks(
            chunks=chunks,
            state=state_code,
            model=model,
            base_url=base_url,
        )

        # Write per-state programs file
        output_path = DATA_DIR / f"incentive_programs_{state_code}.json"
        programs_data = [p.model_dump(mode="json") for p in programs]
        output_path.write_text(json.dumps(programs_data, indent=2), encoding="utf-8")
        print(f"  Wrote {len(programs)} programs to {output_path.name}")

        # Write review queue if any
        if review_items:
            review_path = DATA_DIR / f"review_queue_{state_code}.json"
            review_data = [r.model_dump(mode="json") for r in review_items]
            review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")
            print(f"  Wrote {len(review_items)} items to {review_path.name} (needs human review)")

    print("\nExtraction complete.")
    print(f"Note: incentive_programs_federal.json is hand-curated and was NOT modified.")


if __name__ == "__main__":
    main()
