"""
Build the presentation layer of the Lalka Knowledge Graph.

This script transforms the full PBL graph into a simplified,
user-oriented graph intended for visualization.

The source graph remains unchanged.

Source:
    data/lalka_graph.json

Output:
    data/lalka_presentation_graph.json

Presentation model
------------------

Node types:

    Work
    Person
    Adaptation
    Edition
    Publication
    Event
    Publisher
    Source

Presentation relationships:

    CREATED_BY
    ADAPTED_AS
    HAS_EDITION
    HAS_RECORD
    REVIEWS
    RELATED_TO
    AUTHORED_BY
    PUBLISHED_BY
    FROM_SOURCE

Important modelling decision
----------------------------

PBL uses CHILD_OF to represent the internal hierarchy of records.

For the presentation layer, CHILD_OF is not exposed directly.

Instead:

    Lalka
        |
        | ADAPTED_AS
        v
    Adaptation
        |
        | HAS_RECORD
        v
    Publication

All bibliographic record types are represented in the presentation
layer as Publication:

    BookRecord
    PublicationRecord
    OtherRecord

The original PBL type is preserved in the `original_type` field.

Records attached to those records (second PBL hierarchy level)
are also included:

    review       -- REVIEWS    --> reviewed record
    other record <-- HAS_RECORD -- parent record

The same article filed by PBL under several headings is represented
by a single Publication node (see deduplication_key).

This distinction allows the presentation layer to use a simple,
user-oriented model while preserving the technical information
from the source PBL graph.

The original PBL identifiers and metadata are preserved.

Some presentation relationships are manually verified when
they cannot be reconstructed reliably from the PBL hierarchy.
"""


from __future__ import annotations

import json
import re
from pathlib import Path
from collections import defaultdict


# =============================================================================
# CONFIGURATION
# =============================================================================

LALKA_ID = "record:109715"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

INPUT_FILE = PROJECT_DIR / "data" / "lalka_graph.json"
EDITIONS_FILE = PROJECT_DIR / "data" / "lalka_editions_verified.json"
OUTPUT_FILE = PROJECT_DIR / "data" / "lalka_presentation_graph.json"


# =============================================================================
# MANUALLY VERIFIED RELATIONSHIPS
# =============================================================================

"""
These records have been manually verified as adaptations of Lalka.

PBL files adaptations under the creator's heading, not under the
work record, so they cannot be reconstructed from CHILD_OF.

Screen adaptations:
    304249  film (dir. W. J. Has)
    136679  TV series (dir. R. Ber)

Radio and theatre (record type AU/SZ, title "Lalka", author
Bolesław Prus, PBL author 1082):
    242186, 364636, 413000, 413972, 1051082  radio broadcasts
    1513883  "Lalka. Prem. 2012", adapt. and dir. Bogdan Kokotek

The relationships are added only to the presentation layer.

The source PBL graph is not modified.
"""

MANUAL_LALKA_ADAPTATIONS = {
    "record:304249": "film",
    "record:136679": "tv_series",
    "record:242186": "radio",
    "record:364636": "radio",
    "record:413000": "radio",
    "record:413972": "radio",
    "record:1051082": "radio",
    "record:1513883": "theatre",
}


# =============================================================================
# MANUALLY VERIFIED EDITION GROUPS
# =============================================================================

"""
Verified edition records that describe volumes of one edition.

1348677, 1348678, 1348680: Świat Książki - Bertelsmann Media 2007,
three volumes ("Tekst wg: Pisma. T. 11-13, Warszawa 1935").
"""

EDITION_GROUPS = {
    "swiat-ksiazki-2007": [
        1348677,
        1348678,
        1348680,
    ],
}


# =============================================================================
# PUBLISHER ALIASES
# =============================================================================

"""
PBL publisher identifiers describing the same publisher.

alias PBL ID -> canonical PBL ID

The original identifiers and names are preserved in the
`pbl_ids` and `name_variants` properties of the canonical node.
"""

PUBLISHER_ALIASES = {
    # Zakład Narodowy im. Ossolińskich
    3722: 87,

    # Eksmo (EKSMO-Press was its earlier name)
    125157: 25550,
    35903: 25550,

    # Zielona Sowa
    67034: 26180,

    # Świat Książki
    25733: 20551,
}


# PBL record kind of reviews.
REVIEW_RECORD_KIND = "recenzja"


# =============================================================================
# PRESENTATION TYPE MAPPING
# =============================================================================

"""
Mapping from technical PBL/source graph types to the simplified
presentation model.

The presentation layer deliberately groups all bibliographic
record types under the single Publication type.

The original technical type remains available in `original_type`.
"""

PRESENTATION_TYPE_MAP = {
    "LiteraryWork": "Work",

    "ScreenAdaptation": "Adaptation",
    "TheatreRecord": "Adaptation",
    "BroadcastRecord": "Adaptation",

    "BookRecord": "Publication",
    "PublicationRecord": "Publication",
    "OtherRecord": "Publication",

    "EventRecord": "Event",
}


# =============================================================================
# UTILITIES
# =============================================================================

def load_json(path: Path):
    """Load UTF-8 JSON."""

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def save_json(data, path: Path):
    """Save UTF-8 JSON."""

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def node_id(node):
    """Return node ID."""

    return node.get("id")


def node_type(node):
    """Return source graph node type."""

    return node.get(
        "type",
        "Unknown",
    )


def node_label(node):
    """Return human-readable node label."""

    return (
        node.get("label")
        or node.get("name")
        or node.get("title")
        or node_id(node)
    )


def edge_relationship(edge):
    """Return source graph relationship type."""

    return (
        edge.get("relationship")
        or edge.get("type")
        or edge.get("label")
        or "UNKNOWN"
    )


def edition_display_title(title):
    """Return an edition title without technical PBL title qualifiers."""

    value = (title or "Lalka").strip()
    value = re.sub(
        r"^\[Lalka\]\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\.\s*\[Powieść\]\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip() or "Lalka"


def normalize_title(title):
    """Return a title normalized for deduplication."""

    value = (title or "").lower()
    value = re.sub(r"[^\w]+", " ", value)

    return value.strip()


def canonical_publisher_id(pbl_id):
    """Return the canonical PBL ID of a publisher."""

    return PUBLISHER_ALIASES.get(
        int(pbl_id),
        int(pbl_id),
    )


def edition_group_id(pbl_id):
    """Return the edition group of a verified edition record."""

    for group_id, record_ids in EDITION_GROUPS.items():

        if pbl_id in record_ids:
            return group_id

    return None


def is_translation(edition):
    """Return whether a verified edition record is a translation."""

    flags = edition.get("review_flags") or ""

    return "przekład" in flags


# =============================================================================
# PRESENTATION TYPE
# =============================================================================

def get_presentation_type(original_type):
    """
    Convert a source graph node type into a presentation type.

    All bibliographic record types are represented as Publication.
    """

    if original_type in {
        "Creator",
        "Author",
    }:
        return "Person"

    if original_type == "Publisher":
        return "Publisher"

    if original_type == "PBLSource":
        return "Source"

    return PRESENTATION_TYPE_MAP.get(
        original_type,
        "Publication",
    )


# =============================================================================
# PRESENTATION GRAPH BUILDER
# =============================================================================

class PresentationGraphBuilder:
    """Build a simplified presentation graph."""

    def __init__(
        self,
        source_graph,
    ):

        self.source_graph = source_graph

        self.nodes = {}
        self.edges = []

        # Prevent duplicate presentation relationships.
        self.edge_keys = set()

        # Duplicate PBL records: record ID -> presentation node ID.
        self.record_aliases = {}
        self.deduplication_index = {}

        # Canonical publisher ID -> {pbl_id: (name, city)}
        self.publisher_variants = defaultdict(dict)

        self.snapshot_consistency = None

        # ---------------------------------------------------------------------
        # Source graph indexes
        # ---------------------------------------------------------------------

        self.source_nodes = {
            node_id(node): node
            for node in source_graph.get(
                "nodes",
                [],
            )
        }

        self.source_edges = (
            source_graph.get(
                "edges",
                [],
            )
        )

        self.incoming = defaultdict(list)
        self.outgoing = defaultdict(list)

        self._build_edge_indexes()

    # =========================================================================
    # INDEXES
    # =========================================================================

    def _build_edge_indexes(self):
        """Build incoming and outgoing source graph indexes."""

        for edge in self.source_edges:

            source = edge.get("source")
            target = edge.get("target")

            if not source or not target:
                continue

            self.outgoing[source].append(edge)
            self.incoming[target].append(edge)

    # =========================================================================
    # NODES
    # =========================================================================

    def add_node(
        self,
        node_id_value,
        presentation_type_value,
        label,
        original_node=None,
        **properties,
    ):
        """
        Add a presentation node.

        Original PBL properties are preserved.
        """

        if node_id_value in self.nodes:
            return

        original_type = None

        if original_node:
            original_type = original_node.get("type")

        node_properties = {}

        if original_node:

            original_properties = (
                original_node.get("properties")
                or {}
            )

            node_properties.update(
                original_properties
            )

        node_properties.update(
            {
                key: value
                for key, value in properties.items()
                if value is not None
            }
        )

        self.nodes[node_id_value] = {
            "id": node_id_value,
            "type": presentation_type_value,
            "label": label,
            "properties": node_properties,
            "presentation_type": presentation_type_value,
            "original_type": original_type,
        }

    # =========================================================================
    # EDGES
    # =========================================================================

    def add_edge(
        self,
        source,
        target,
        relationship,
        **properties,
    ):
        """Add a presentation relationship."""

        edge_key = (
            source,
            target,
            relationship,
        )

        if edge_key in self.edge_keys:
            return

        self.edge_keys.add(
            edge_key
        )

        edge = {
            "source": source,
            "target": target,
            "relationship": relationship,
        }

        for key, value in properties.items():

            if value is not None:
                edge[key] = value

        self.edges.append(edge)

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    def deduplication_key(self, record):
        """
        Return the key identifying the same publication.

        PBL may describe one article in several records, e.g. once
        under each of the two screen adaptations.

        Only records with a title and a bibliographic source are
        deduplicated.
        """

        properties = record.get("properties") or {}

        title = normalize_title(
            record.get("label")
        )

        if not title or properties.get("source_id") is None:
            return None

        authors = sorted(
            edge.get("source")
            for edge in self.incoming.get(node_id(record), [])
            if edge_relationship(edge) == "AUTHOR_OF"
        )

        return (
            tuple(authors),
            title,
            properties.get("source_id"),
            properties.get("source_year"),
            properties.get("source_number"),
            properties.get("source_pages"),
        )

    def presentation_record_id(self, record):
        """
        Return the presentation node ID for a source record.

        Duplicates are mapped to the first record with the same key.
        """

        record_id = node_id(record)

        if record_id in self.record_aliases:
            return self.record_aliases[record_id]

        key = self.deduplication_key(record)

        if key is None:
            self.record_aliases[record_id] = record_id
            return record_id

        canonical_id = self.deduplication_index.setdefault(
            key,
            record_id,
        )

        self.record_aliases[record_id] = canonical_id

        if canonical_id != record_id and canonical_id in self.nodes:

            merged = self.nodes[canonical_id]["properties"].setdefault(
                "merged_pbl_ids",
                [],
            )

            merged.append(
                (record.get("properties") or {}).get("pbl_id")
            )

        return canonical_id

    def add_record(
        self,
        record,
        role,
        **properties,
    ):
        """Add a source record and return its presentation node ID."""

        record_id = self.presentation_record_id(
            record
        )

        self.add_node(
            node_id_value=record_id,
            presentation_type_value=get_presentation_type(
                node_type(record)
            ),
            label=node_label(record),
            original_node=record,
            role=role,
            **properties,
        )

        return record_id

    # =========================================================================
    # PUBLISHERS
    # =========================================================================

    def add_publisher(
        self,
        pbl_id,
        name,
        city,
        role,
        original_node=None,
    ):
        """Add a publisher under its canonical PBL identifier."""

        canonical_id = canonical_publisher_id(pbl_id)
        presentation_id = f"publisher:{canonical_id}"

        self.publisher_variants[canonical_id][int(pbl_id)] = (
            name,
            city,
        )

        self.add_node(
            node_id_value=presentation_id,
            presentation_type_value="Publisher",
            label=name,
            original_node=original_node,
            pbl_id=canonical_id,
            city=city,
            role=role,
        )

        return presentation_id

    def finalize_publishers(self):
        """Store all PBL identifiers and names of merged publishers."""

        for canonical_id, variants in self.publisher_variants.items():

            node = self.nodes[f"publisher:{canonical_id}"]

            if canonical_id in variants:

                name, city = variants[canonical_id]
                node["label"] = name
                node["properties"]["pbl_id"] = canonical_id

                if city:
                    node["properties"]["city"] = city

            if len(variants) > 1:

                node["properties"]["pbl_ids"] = sorted(variants)
                node["properties"]["name_variants"] = sorted(
                    {name for name, _ in variants.values()}
                )

    # =========================================================================
    # ROOT WORK
    # =========================================================================

    def add_root(self):
        """Add Lalka as the central Work node."""

        root = self.source_nodes.get(
            LALKA_ID
        )

        if not root:

            raise RuntimeError(
                "Lalka root node was not found "
                "in the source graph."
            )

        self.add_node(
            node_id_value=LALKA_ID,
            presentation_type_value="Work",
            label="Lalka",
            original_node=root,
            role="central_work",
        )

    # =========================================================================
    # WORK CREATORS
    # =========================================================================

    def add_root_creators(self):
        """
        Add creators directly connected to Lalka.

        Only actual CREATED_BY relationships of Lalka
        are used.
        """

        for edge in self.outgoing.get(
            LALKA_ID,
            [],
        ):

            if edge_relationship(edge) != "CREATED_BY":
                continue

            creator_id = edge.get("target")

            creator = self.source_nodes.get(
                creator_id
            )

            if not creator:
                continue

            if node_type(creator) != "Creator":
                continue

            self.add_node(
                node_id_value=creator_id,
                presentation_type_value="Person",
                label=node_label(creator),
                original_node=creator,
                role="work_creator",
            )

            self.add_edge(
                source=LALKA_ID,
                target=creator_id,
                relationship="CREATED_BY",
                relation_source="pbl",
            )

    # =========================================================================
    # DIRECT LALKA RECORDS
    # =========================================================================

    def get_direct_lalka_records(self):
        """
        Return records directly attached to Lalka through CHILD_OF.

        Source relationship:

            child -- CHILD_OF --> Lalka
        """

        records = []

        for edge in self.incoming.get(
            LALKA_ID,
            [],
        ):

            if edge_relationship(edge) != "CHILD_OF":
                continue

            child_id = edge.get("source")

            child = self.source_nodes.get(
                child_id
            )

            if not child:
                continue

            if child_id == LALKA_ID:
                continue

            records.append(child)

        return records

    # =========================================================================
    # RECORD CLASSIFICATION
    # =========================================================================

    def record_role(
        self,
        presentation_type_value,
    ):
        """Return presentation role for a record."""

        if presentation_type_value == "Adaptation":
            return "adaptation"

        if presentation_type_value == "Publication":
            return "publication"

        if presentation_type_value == "Event":
            return "event"

        return "publication"

    # =========================================================================
    # DIRECT RECORD RELATIONSHIP
    # =========================================================================

    def record_relationship(
        self,
        presentation_type_value,
    ):
        """
        Determine the relationship between Lalka
        and a direct child record.

        Direct adaptations receive ADAPTED_AS.

        Other direct records remain RELATED_TO.
        """

        if presentation_type_value == "Adaptation":
            return "ADAPTED_AS"

        return "RELATED_TO"

    # =========================================================================
    # DIRECT RECORDS
    # =========================================================================

    def add_direct_records(self):
        """
        Add records directly connected to Lalka.

        Adaptations are promoted to the presentation layer.

        All bibliographic record types are represented as Publication.
        """

        direct_records = (
            self.get_direct_lalka_records()
        )

        for record in direct_records:

            if not node_id(record):
                continue

            presentation_type_value = (
                get_presentation_type(
                    node_type(record)
                )
            )

            role = self.record_role(
                presentation_type_value
            )

            record_id = self.add_record(
                record,
                role=role,
                root_relation="direct_child_of_lalka",
            )

            self.add_edge(
                source=LALKA_ID,
                target=record_id,
                relationship=(
                    self.record_relationship(
                        presentation_type_value
                    )
                ),
                relation_source="pbl_hierarchy",
                source_relationship="CHILD_OF",
            )

    # =========================================================================
    # MANUAL ADAPTATIONS
    # =========================================================================

    def add_manual_adaptations(self):
        """
        Add manually verified screen adaptations of Lalka.

        These relationships belong to the presentation layer only.

        The source PBL graph is not modified.
        """

        for adaptation_id, medium in (
            MANUAL_LALKA_ADAPTATIONS.items()
        ):

            adaptation = self.source_nodes.get(
                adaptation_id
            )

            if not adaptation:

                print(
                    "WARNING: Manual adaptation "
                    f"not found: {adaptation_id}"
                )

                continue

            self.add_node(
                node_id_value=adaptation_id,
                presentation_type_value="Adaptation",
                label=node_label(adaptation),
                original_node=adaptation,
                role="adaptation",
                medium=medium,
                root_relation="manually_verified",
            )

            self.add_edge(
                source=LALKA_ID,
                target=adaptation_id,
                relationship="ADAPTED_AS",
                relation_source="manual",
            )

    # =========================================================================
    # VERIFIED EDITIONS
    # =========================================================================

    def add_verified_editions(self, editions_data):
        """Add editions approved during curatorial review of a PBL snapshot."""

        for edition in editions_data.get("editions", []):
            record_id = f"record:{edition['pbl_id']}"
            publishers = edition.get("publishers", [])
            publisher_names = [item["name"] for item in publishers]
            year = edition.get("publication_year")
            label_parts = [str(year)] if year else []
            if publisher_names:
                label_parts.append(" / ".join(publisher_names))
            label_suffix = ", ".join(label_parts)
            display_title = edition_display_title(edition.get("title"))
            label = display_title + (f" ({label_suffix})" if label_suffix else "")

            properties = {
                key: value
                for key, value in edition.items()
                if key not in {"publishers", "original_language"}
                and value is not None
            }
            properties.update({
                "pbl_type": "KS",
                "role": "verified_edition",
                "publisher_names": publisher_names,
                "publisher_city": [
                    item["city"] for item in publishers if item.get("city")
                ],
                "is_translation": is_translation(edition),
                "edition_group": edition_group_id(edition["pbl_id"]),
                # Raw ZA_JEZYK_ORYGINALU; not the language of this edition.
                "za_jezyk_oryginalu_raw": edition.get("original_language"),
            })

            self.add_node(
                node_id_value=record_id,
                presentation_type_value="Edition",
                label=label,
                **properties,
            )
            self.add_edge(
                source=LALKA_ID,
                target=record_id,
                relationship="HAS_EDITION",
                relation_source="curated_pbl_snapshot",
                review_status=edition.get("review_status"),
            )

            for publisher in publishers:
                publisher_id = self.add_publisher(
                    publisher["pbl_id"],
                    publisher["name"],
                    publisher.get("city"),
                    role="edition_publisher",
                )
                self.add_edge(
                    source=record_id,
                    target=publisher_id,
                    relationship="PUBLISHED_BY",
                    relation_source="pbl_snapshot",
                )

    def check_editions_against_source(self, editions_data):
        """
        Compare curated editions (Oracle snapshot) with the source graph
        (basic extraction).

        Both inputs come from different PBL exports, so differences in
        titles, years or publishers are reported.
        """

        differences = []

        for edition in editions_data.get("editions", []):

            record_id = f"record:{edition['pbl_id']}"
            record = self.source_nodes.get(record_id)

            if not record:
                differences.append(
                    f"{record_id}: missing in the source graph"
                )
                continue

            properties = record.get("properties") or {}

            if node_label(record) != edition.get("title"):
                differences.append(
                    f"{record_id}: title differs"
                )

            source_year = properties.get("publication_year")

            if (
                source_year is not None
                and edition.get("publication_year_source") == "ZA_ROK_WYDANIA"
                and int(source_year) != edition.get("publication_year")
            ):
                differences.append(
                    f"{record_id}: publication year differs"
                )

            source_publishers = {
                edge.get("target")
                for edge in self.outgoing.get(record_id, [])
                if edge_relationship(edge) == "PUBLISHED_BY"
            }

            edition_publishers = {
                f"publisher:{item['pbl_id']}"
                for item in edition.get("publishers", [])
            }

            if source_publishers != edition_publishers:
                differences.append(
                    f"{record_id}: publishers differ"
                )

        for difference in differences:
            print(f"WARNING: {difference}")

        self.snapshot_consistency = {
            "checked_editions": len(editions_data.get("editions", [])),
            "differences": differences,
        }

        return differences

    # =========================================================================
    # ADAPTATION CHILD RECORDS
    # =========================================================================

    def get_adaptation_child_records(
        self,
        adaptation_id,
    ):
        """
        Return records directly attached to an adaptation.

        Source relationship:

            child -- CHILD_OF --> adaptation

        This is intentionally limited to direct children.
        """

        records = []

        for edge in self.incoming.get(
            adaptation_id,
            [],
        ):

            if edge_relationship(edge) != "CHILD_OF":
                continue

            child_id = edge.get("source")

            child = self.source_nodes.get(
                child_id
            )

            if not child:
                continue

            if child_id == adaptation_id:
                continue

            records.append(child)

        return records

    # =========================================================================
    # ADD ADAPTATION CHILD RECORDS
    # =========================================================================

    def add_adaptation_child_records(self):
        """
        Add bibliographic records belonging directly to
        screen adaptations.

        Example:

            record:304249
                |
                | HAS_RECORD
                v
            record:401079

            record:136679
                |
                | HAS_RECORD
                v
            record:136684

        These records are represented as Publication objects
        in the presentation layer, regardless of their original
        PBL record type.
        """

        adaptation_ids = [
            node_id_value
            for node_id_value, node in self.nodes.items()
            if node.get("presentation_type") == "Adaptation"
        ]

        for adaptation_id in adaptation_ids:

            child_records = (
                self.get_adaptation_child_records(
                    adaptation_id
                )
            )

            for child in child_records:

                if not node_id(child):
                    continue

                presentation_type_value = (
                    get_presentation_type(
                        node_type(child)
                    )
                )

                role = self.record_role(
                    presentation_type_value
                )

                child_id = self.add_record(
                    child,
                    role=role,
                    root_relation="child_of_adaptation",
                    parent_presentation_id=adaptation_id,
                )

                self.add_edge(
                    source=adaptation_id,
                    target=child_id,
                    relationship="HAS_RECORD",
                    relation_source="pbl_hierarchy",
                    source_relationship="CHILD_OF",
                )

    # =========================================================================
    # SECOND HIERARCHY LEVEL
    # =========================================================================

    def add_nested_records(self):
        """
        Add records attached to records already related to Lalka
        or to its adaptations (second PBL hierarchy level).

        Reviews receive:

            review -- REVIEWS --> reviewed record

        Other records receive:

            parent record -- HAS_RECORD --> record
        """

        parents = [
            (source_id, presentation_id)
            for source_id, presentation_id in self.record_aliases.items()
            if self.nodes[presentation_id].get("properties", {}).get(
                "root_relation"
            ) in {
                "direct_child_of_lalka",
                "child_of_adaptation",
            }
        ]

        for source_parent_id, parent_id in parents:

            for edge in self.incoming.get(source_parent_id, []):

                if edge_relationship(edge) != "CHILD_OF":
                    continue

                child = self.source_nodes.get(
                    edge.get("source")
                )

                if not child:
                    continue

                presentation_type_value = get_presentation_type(
                    node_type(child)
                )

                child_id = self.add_record(
                    child,
                    role=self.record_role(
                        presentation_type_value
                    ),
                    root_relation="nested_record",
                    parent_presentation_id=parent_id,
                )

                record_kind = (
                    child.get("properties") or {}
                ).get("record_kind")

                if record_kind == REVIEW_RECORD_KIND:

                    self.add_edge(
                        source=child_id,
                        target=parent_id,
                        relationship="REVIEWS",
                        relation_source="pbl_hierarchy",
                        source_relationship="CHILD_OF",
                    )

                else:

                    self.add_edge(
                        source=parent_id,
                        target=child_id,
                        relationship="HAS_RECORD",
                        relation_source="pbl_hierarchy",
                        source_relationship="CHILD_OF",
                    )

    # =========================================================================
    # RELATED METADATA
    # =========================================================================

    def add_related_metadata(self):
        """
        Add selected metadata for records already present
        in the presentation graph.

        This prevents uncontrolled graph expansion.
        """

        presentation_record_ids = [
            node_id_value
            for node_id_value, node in self.nodes.items()
            if node.get(
                "presentation_type"
            ) in {
                "Adaptation",
                "Publication",
                "Event",
            }
        ]

        for record_id in presentation_record_ids:

            self.add_metadata_for_record(
                record_id
            )

        # Metadata of merged duplicate records.
        for source_id, presentation_id in self.record_aliases.items():

            if source_id != presentation_id:

                self.add_metadata_for_record(
                    source_id,
                    target_id=presentation_id,
                )

    # =========================================================================
    # METADATA
    # =========================================================================

    def add_metadata_for_record(
        self,
        record_id,
        target_id=None,
    ):
        """
        Add authors, publishers and sources for a record.

        Only metadata already explicitly represented in the
        source graph is used.

        target_id is the presentation node receiving the metadata
        (differs from record_id for merged duplicates).
        """

        source_record_id = record_id
        record_id = target_id or record_id

        # ---------------------------------------------------------------------
        # AUTHORS
        # ---------------------------------------------------------------------

        for edge in self.incoming.get(
            source_record_id,
            [],
        ):

            if edge_relationship(edge) != "AUTHOR_OF":
                continue

            author_id = edge.get("source")

            author = self.source_nodes.get(
                author_id
            )

            if not author:
                continue

            if node_type(author) != "Author":
                continue

            self.add_node(
                node_id_value=author_id,
                presentation_type_value="Person",
                label=node_label(author),
                original_node=author,
                role="record_author",
            )

            self.add_edge(
                source=record_id,
                target=author_id,
                relationship="AUTHORED_BY",
                relation_source="pbl",
            )

        # ---------------------------------------------------------------------
        # PUBLISHERS
        # ---------------------------------------------------------------------

        for edge in self.outgoing.get(
            source_record_id,
            [],
        ):

            if edge_relationship(edge) != "PUBLISHED_BY":
                continue

            publisher = self.source_nodes.get(
                edge.get("target")
            )

            if not publisher:
                continue

            if node_type(publisher) != "Publisher":
                continue

            publisher_properties = publisher.get("properties") or {}

            publisher_id = self.add_publisher(
                publisher_properties.get("pbl_id"),
                node_label(publisher),
                publisher_properties.get("city"),
                role="record_publisher",
                original_node=publisher,
            )

            self.add_edge(
                source=record_id,
                target=publisher_id,
                relationship="PUBLISHED_BY",
                relation_source="pbl",
            )

        # ---------------------------------------------------------------------
        # SOURCES
        # ---------------------------------------------------------------------

        for edge in self.outgoing.get(
            source_record_id,
            [],
        ):

            if edge_relationship(edge) != "FROM_SOURCE":
                continue

            source_id = edge.get("target")

            source = self.source_nodes.get(
                source_id
            )

            if not source:
                continue

            if node_type(source) != "PBLSource":
                continue

            self.add_node(
                node_id_value=source_id,
                presentation_type_value="Source",
                label=node_label(source),
                original_node=source,
                role="bibliographic_source",
            )

            self.add_edge(
                source=record_id,
                target=source_id,
                relationship="FROM_SOURCE",
                relation_source="pbl",
            )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def build_statistics(self):
        """Return presentation graph statistics."""

        node_counts = defaultdict(int)
        edge_counts = defaultdict(int)

        for node in self.nodes.values():

            node_counts[
                node.get("presentation_type")
            ] += 1

        for edge in self.edges:

            edge_counts[
                edge.get("relationship")
            ] += 1

        editions = [
            node
            for node in self.nodes.values()
            if node.get("presentation_type") == "Edition"
        ]

        edition_units = {
            node["properties"].get("edition_group") or node["id"]
            for node in editions
        }

        adaptation_media = defaultdict(int)

        for node in self.nodes.values():

            if node.get("presentation_type") == "Adaptation":

                adaptation_media[
                    node["properties"].get("medium", "unknown")
                ] += 1

        merged_records = sorted(
            source_id
            for source_id, presentation_id in self.record_aliases.items()
            if source_id != presentation_id
        )

        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),

            "editions": {
                "records": len(editions),
                "translations": sum(
                    1
                    for node in editions
                    if node["properties"].get("is_translation")
                ),
                "edition_units": len(edition_units),
            },

            "adaptation_media": dict(
                sorted(
                    adaptation_media.items()
                )
            ),

            "merged_duplicate_records": merged_records,

            "node_types": dict(
                sorted(
                    node_counts.items()
                )
            ),

            "relationships": dict(
                sorted(
                    edge_counts.items()
                )
            ),
        }

    # =========================================================================
    # EXPORT
    # =========================================================================

    def to_dict(self):
        """Return serializable presentation graph."""

        statistics = self.build_statistics()

        return {
            "metadata": {
                "project":
                    "Lalka Knowledge Graph",

                "layer":
                    "presentation",

                "source":
                    "Polska Bibliografia Literacka",

                "source_graph":
                    "lalka_graph.json",

                "curated_editions":
                    "lalka_editions_verified.json",

                "snapshot_consistency":
                    self.snapshot_consistency,

                "root":
                    LALKA_ID,

                "description":
                    (
                        "A simplified presentation layer of the "
                        "Lalka Knowledge Graph designed for interactive "
                        "visual exploration."
                    ),

                "model": {
                    "node_types": [
                        "Work",
                        "Person",
                        "Adaptation",
                        "Edition",
                        "Publication",
                        "Event",
                        "Publisher",
                        "Source",
                    ],

                    "relationships": [
                        "CREATED_BY",
                        "ADAPTED_AS",
                        "HAS_EDITION",
                        "HAS_RECORD",
                        "REVIEWS",
                        "RELATED_TO",
                        "AUTHORED_BY",
                        "PUBLISHED_BY",
                        "FROM_SOURCE",
                    ],
                },

                "manual_relationships": {
                    "adaptations": list(
                        MANUAL_LALKA_ADAPTATIONS
                    ),
                    "adaptation_media": (
                        MANUAL_LALKA_ADAPTATIONS
                    ),
                    "edition_groups": EDITION_GROUPS,
                    "publisher_aliases": {
                        str(alias): canonical
                        for alias, canonical in PUBLISHER_ALIASES.items()
                    },
                },

                "statistics":
                    statistics,
            },

            "nodes":
                list(
                    self.nodes.values()
                ),

            "edges":
                self.edges,
        }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print(
        "Building Lalka presentation graph..."
    )

    # -------------------------------------------------------------------------
    # CHECK INPUT
    # -------------------------------------------------------------------------

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            "Source graph not found:\n"
            f"{INPUT_FILE}"
        )

    # -------------------------------------------------------------------------
    # LOAD SOURCE GRAPH
    # -------------------------------------------------------------------------

    print()
    print(
        "Loading source graph..."
    )

    source_graph = load_json(
        INPUT_FILE
    )

    source_nodes = source_graph.get(
        "nodes",
        []
    )

    source_edges = source_graph.get(
        "edges",
        []
    )

    print(
        f"  Source nodes: {len(source_nodes)}"
    )

    print(
        f"  Source edges: {len(source_edges)}"
    )

    # -------------------------------------------------------------------------
    # CREATE BUILDER
    # -------------------------------------------------------------------------

    graph = PresentationGraphBuilder(
        source_graph
    )

    # -------------------------------------------------------------------------
    # CENTRAL WORK
    # -------------------------------------------------------------------------

    print()
    print(
        "Adding central work..."
    )

    graph.add_root()

    # -------------------------------------------------------------------------
    # WORK CREATOR
    # -------------------------------------------------------------------------

    print(
        "Adding work creators..."
    )

    graph.add_root_creators()

    # -------------------------------------------------------------------------
    # DIRECT RECORDS
    # -------------------------------------------------------------------------

    print(
        "Adding records directly connected to Lalka..."
    )

    direct_records = (
        graph.get_direct_lalka_records()
    )

    print(
        f"  Direct records: "
        f"{len(direct_records)}"
    )

    graph.add_direct_records()

    # -------------------------------------------------------------------------
    # MANUAL ADAPTATIONS
    # -------------------------------------------------------------------------

    print(
        "Adding manually verified adaptations..."
    )

    graph.add_manual_adaptations()

    # -------------------------------------------------------------------------
    # VERIFIED EDITIONS
    # -------------------------------------------------------------------------

    if not EDITIONS_FILE.exists():
        raise FileNotFoundError(
            "Curated editions file not found:\n"
            f"{EDITIONS_FILE}"
        )

    editions_data = load_json(EDITIONS_FILE)

    print(
        "Checking curated editions against the source graph..."
    )

    differences = graph.check_editions_against_source(
        editions_data
    )

    print(
        f"  Differences: {len(differences)}"
    )

    print(
        "Adding verified editions..."
    )

    graph.add_verified_editions(editions_data)

    # -------------------------------------------------------------------------
    # ADAPTATION CHILD RECORDS
    # -------------------------------------------------------------------------

    print(
        "Adding records belonging to adaptations..."
    )

    graph.add_adaptation_child_records()

    # -------------------------------------------------------------------------
    # SECOND HIERARCHY LEVEL
    # -------------------------------------------------------------------------

    print(
        "Adding records attached to related records..."
    )

    graph.add_nested_records()

    # -------------------------------------------------------------------------
    # RELATED METADATA
    # -------------------------------------------------------------------------

    print(
        "Adding related metadata..."
    )

    graph.add_related_metadata()

    graph.finalize_publishers()

    # -------------------------------------------------------------------------
    # EXPORT
    # -------------------------------------------------------------------------

    presentation_graph = (
        graph.to_dict()
    )

    save_json(
        presentation_graph,
        OUTPUT_FILE,
    )

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    statistics = (
        presentation_graph[
            "metadata"
        ]["statistics"]
    )

    print()
    print(
        "=" * 80
    )

    print(
        "PRESENTATION GRAPH BUILT"
    )

    print(
        "=" * 80
    )

    print(
        f"Nodes: {statistics['nodes']}"
    )

    print(
        f"Edges: {statistics['edges']}"
    )

    print()
    print(
        "Node types:"
    )

    for node_type_value, count in (
        statistics[
            "node_types"
        ].items()
    ):

        print(
            f"  {node_type_value}: "
            f"{count}"
        )

    print()
    print(
        "Relationships:"
    )

    for relationship, count in (
        statistics[
            "relationships"
        ].items()
    ):

        print(
            f"  {relationship}: "
            f"{count}"
        )

    print()
    print(
        f"Output: {OUTPUT_FILE}"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
