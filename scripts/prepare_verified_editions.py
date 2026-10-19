"""Prepare the curated Lalka editions file from a PBL Oracle snapshot.

The script reads candidate records reviewed by a human and enriches them with
publisher identifiers from snapshot tables exported by PBL-oracle-export.
It is intentionally separate from the Oracle extraction pipeline: a snapshot
is immutable input, while acceptance into the graph is a curatorial decision.

Each candidate may carry a "decision" field ("approved" or "rejected") and
"user_notes" explaining it. Rejected candidates are kept in the output under
"rejected", so that the selection remains auditable. Candidates without
a decision are accepted only with the explicit --approve-all confirmation.

Usage:
    python scripts/prepare_verified_editions.py \
        --snapshot-dir /path/to/snapshot \
        --candidates /path/to/lalka_candidates.json \
        --approve-all
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "lalka_editions_verified.json"


def read_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def locate_table(snapshot_dir: Path, table_name: str) -> Path:
    for suffix in ("jsonl.gz", "ndjson.gz"):
        path = snapshot_dir / f"{table_name}.{suffix}"
        if path.exists():
            return path
    raise FileNotFoundError(f"Snapshot table not found: {table_name}")


def build_publishers(snapshot_dir: Path, record_ids: set[int]):
    links = {}
    link_path = locate_table(snapshot_dir, "PBL_ZAPISY_WYDAWNICTWA")
    for record_id, publisher_id, *_ in read_jsonl_rows(link_path):
        record_id = int(record_id)
        if record_id in record_ids:
            links.setdefault(record_id, []).append(int(publisher_id))

    required_ids = {
        publisher_id
        for publisher_ids in links.values()
        for publisher_id in publisher_ids
    }
    publishers = {}
    publisher_path = locate_table(snapshot_dir, "PBL_WYDAWNICTWA")
    for row in read_jsonl_rows(publisher_path):
        publisher_id = int(row[0])
        if publisher_id in required_ids:
            publishers[publisher_id] = {
                "pbl_id": publisher_id,
                "name": row[1],
                "city": row[2],
            }

    return {
        record_id: [publishers[publisher_id] for publisher_id in publisher_ids]
        for record_id, publisher_ids in links.items()
    }


def split_decisions(candidates, approve_all: bool):
    """Split candidates into approved and rejected according to decisions."""

    approved = []
    rejected = []
    undecided = []

    for candidate in candidates:
        decision = candidate.get("decision")
        if decision == "rejected":
            rejected.append(candidate)
        elif decision == "approved" or (decision is None and approve_all):
            approved.append(candidate)
        else:
            undecided.append(candidate)

    if undecided:
        raise ValueError(
            "Candidates without a review decision: "
            + ", ".join(str(item["pbl_id"]) for item in undecided)
            + ". Add a decision or confirm with --approve-all."
        )

    return approved, rejected


def prepare(
    snapshot_dir: Path,
    candidates_path: Path,
    snapshot_name: str | None = None,
    approve_all: bool = False,
):
    candidates, rejected = split_decisions(read_json(candidates_path), approve_all)
    record_ids = {int(candidate["pbl_id"]) for candidate in candidates}
    publishers = build_publishers(snapshot_dir, record_ids)

    editions = []
    for candidate in candidates:
        record_id = int(candidate["pbl_id"])
        edition = {
            "pbl_id": record_id,
            "title": candidate.get("title"),
            "original_title": candidate.get("original_title"),
            "publication_year": candidate.get("year_for_sort"),
            "publication_year_source": (
                "ZA_ROK_WYDANIA"
                if candidate.get("year_field") is not None
                else "inferred_from_physical_description"
            ),
            "original_language": candidate.get("language"),
            "edition_statement": candidate.get("edition"),
            "volumes": candidate.get("volumes"),
            "physical_description": candidate.get("physical_description"),
            "series": candidate.get("series"),
            "bn_number": candidate.get("bn_number"),
            "bn_url": candidate.get("bn_url"),
            "parent_pbl_id": candidate.get("parent_pbl_id"),
            "publishers": publishers.get(record_id, []),
            "qualification_rule": candidate.get("qualification_rule"),
            "review_status": "approved",
            "review_notes": candidate.get("user_notes") or None,
            "review_flags": candidate.get("flags") or None,
        }
        editions.append(edition)

    editions.sort(key=lambda item: (item["publication_year"] or 9999, item["pbl_id"]))
    result = {
        "metadata": {
            "title": "Zweryfikowane wydania Lalki",
            "source": "PBL Oracle snapshot exported by PBL-oracle-export",
            "snapshot": snapshot_name or snapshot_dir.resolve().name,
            "prepared_on": date.today().isoformat(),
            "review_status": "all_records_approved",
            "record_count": len(editions),
            "selection_note": (
                "Records linked to Bolesław Prus (PBL creator 3426), selected "
                "by title rules and individually approved by the project editor."
            ),
            "language_note": (
                "original_language reproduces ZA_JEZYK_ORYGINALU and must not "
                "be interpreted as the language of this edition."
            ),
        },
        "editions": editions,
    }

    if rejected:
        result["metadata"]["rejected_count"] = len(rejected)
        result["rejected"] = [
            {
                "pbl_id": int(candidate["pbl_id"]),
                "title": candidate.get("title"),
                "qualification_rule": candidate.get("qualification_rule"),
                "review_status": "rejected",
                "review_notes": candidate.get("user_notes") or None,
            }
            for candidate in sorted(rejected, key=lambda item: int(item["pbl_id"]))
        ]

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot-name")
    parser.add_argument(
        "--approve-all",
        action="store_true",
        help="Approve candidates without an explicit decision field.",
    )
    args = parser.parse_args()

    try:
        result = prepare(
            args.snapshot_dir,
            args.candidates,
            args.snapshot_name,
            approve_all=args.approve_all,
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved {len(result['editions'])} editions to {args.output}")


if __name__ == "__main__":
    main()
