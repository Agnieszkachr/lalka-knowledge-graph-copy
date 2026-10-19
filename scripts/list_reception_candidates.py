"""
List candidate records about "Lalka" that are not in the presentation graph.

PBL files many publications, events and adaptations concerning "Lalka"
under the personal heading of Bolesław Prus instead of under the work
record 109715. They cannot be connected with the work automatically.

This script lists such records for editorial review. It does NOT modify
the graphs; accepted records should be added through a curated list
(as MANUAL_LALKA_ADAPTATIONS in build_presentation_graph.py).

Input:
    data/lalka_graph.json
    data/lalka_presentation_graph.json

Output:
    data/lalka_reception_candidates.json
"""


from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent

GRAPH_FILE = PROJECT_DIR / "data" / "lalka_graph.json"
PRESENTATION_FILE = PROJECT_DIR / "data" / "lalka_presentation_graph.json"
OUTPUT_FILE = PROJECT_DIR / "data" / "lalka_reception_candidates.json"

# Title or annotation mentioning the work, its main characters
# or its translated titles.
CANDIDATE_PATTERN = re.compile(
    r"lalk|lalc|wokulsk|rzeck|łęck|kukla|\bdoll\b",
    flags=re.IGNORECASE,
)

RECORD_TYPES = {
    "BookRecord",
    "PublicationRecord",
    "OtherRecord",
    "EventRecord",
    "TheatreRecord",
    "BroadcastRecord",
    "ScreenAdaptation",
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def presentation_record_ids(presentation_graph) -> set[str]:
    """Return source record IDs represented in the presentation graph."""

    ids = set()

    for node in presentation_graph["nodes"]:

        ids.add(node["id"])

        for pbl_id in node.get("properties", {}).get("merged_pbl_ids", []):
            ids.add(f"record:{pbl_id}")

    return ids


def main():

    graph = load_json(GRAPH_FILE)
    presented = presentation_record_ids(load_json(PRESENTATION_FILE))

    candidates = []

    for node in graph["nodes"]:

        if node["type"] not in RECORD_TYPES or node["id"] in presented:
            continue

        properties = node.get("properties", {})

        matched_fields = [
            field
            for field, value in (
                ("title", node.get("label")),
                ("annotation", properties.get("annotation")),
            )
            if value and CANDIDATE_PATTERN.search(str(value))
        ]

        if not matched_fields:
            continue

        candidates.append({
            "pbl_id": properties.get("pbl_id"),
            "title": node.get("label"),
            "graph_type": node["type"],
            "record_kind": properties.get("record_kind"),
            "section": properties.get("section_name"),
            "parent_pbl_id": properties.get("parent_id"),
            "year": (
                properties.get("publication_year")
                or properties.get("source_year")
            ),
            "source": properties.get("source"),
            "annotation": properties.get("annotation"),
            "matched_fields": matched_fields,
            "decision": None,
            "user_notes": None,
        })

    candidates.sort(key=lambda item: (item["graph_type"], item["pbl_id"]))

    result = {
        "metadata": {
            "title": "Kandydaci do recepcji Lalki spoza hasła utworu",
            "source_graph": GRAPH_FILE.name,
            "presentation_graph": PRESENTATION_FILE.name,
            "pattern": CANDIDATE_PATTERN.pattern,
            "note": (
                "Records matched by title or annotation. Not verified: "
                "each candidate requires an editorial decision."
            ),
            "record_count": len(candidates),
            "by_type": dict(
                sorted(Counter(item["graph_type"] for item in candidates).items())
            ),
        },
        "candidates": candidates,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"Candidates: {len(candidates)}")

    for graph_type, count in result["metadata"]["by_type"].items():
        print(f"  {graph_type}: {count}")

    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
