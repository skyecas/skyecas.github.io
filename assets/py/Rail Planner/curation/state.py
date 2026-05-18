from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LegCuration:
    leg_index: int
    highlighted: bool = False
    photos: list[str] = field(default_factory=list)
    notes: str = ""
    omit_from_narrative: bool = False


@dataclass
class SectionCuration:
    """A section is a logical grouping of legs between meaningful stops."""
    section_name: str
    leg_indices: list[int]
    photos: list[str] = field(default_factory=list)
    notes: str = ""
    highlights: list[str] = field(default_factory=list)


@dataclass
class CurationState:
    snapshot_id: str
    selected_route_index: int = 0

    outbound_label: str = "Outbound"
    inbound_label: str = "Inbound"

    trip_title: str = ""
    trip_date: str = ""
    trip_description: str = ""
    trip_tags: list[str] = field(default_factory=lambda: ["train", "travel", "canonical"])
    trip_category: str = "train-travel"

    overall_notes: str = ""
    destination_notes: str = ""
    trains_notes: str = ""
    stations_notes: str = ""
    countries: list[str] = field(default_factory=list)

    leg_curations: dict[int, LegCuration] = field(default_factory=dict)

    speed_highlights: list[str] = field(default_factory=list)
    notable_transfers: list[str] = field(default_factory=list)
    station_reviews: dict[str, str] = field(default_factory=dict)

    emoji_rating: str = ""
    summary_metrics_note: str = ""

    blog_style: str = "diary"  # diary, technical, scenic, minimalist

    def leg(self, index: int) -> LegCuration:
        if index not in self.leg_curations:
            self.leg_curations[index] = LegCuration(leg_index=index)
        return self.leg_curations[index]
