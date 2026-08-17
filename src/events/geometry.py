"""Zone / line geometry helpers built on Shapely."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from src.common.types import BoundingBox


def bbox_foot(bbox: BoundingBox) -> Point:
    """Foot-of-box point (bottom-center) — the "where it stands" for a tracked object."""
    return Point((bbox.x1 + bbox.x2) / 2.0, bbox.y2)


def bbox_center(bbox: BoundingBox) -> Point:
    return Point((bbox.x1 + bbox.x2) / 2.0, (bbox.y1 + bbox.y2) / 2.0)


@dataclass
class Zone:
    id: str
    kind: str
    polygon: Polygon
    meta: dict

    def contains(self, bbox: BoundingBox) -> bool:
        return self.polygon.contains(bbox_foot(bbox))


@dataclass
class Line:
    id: str
    kind: str
    a: tuple[float, float]
    b: tuple[float, float]
    direction: str | None = None

    @property
    def geom(self) -> LineString:
        return LineString([self.a, self.b])

    def crossed_by(self, previous: BoundingBox, current: BoundingBox) -> bool:
        """True when the foot of the box crossed this line between frames."""
        prev = bbox_foot(previous)
        cur = bbox_foot(current)
        segment = LineString([(prev.x, prev.y), (cur.x, cur.y)])
        return self.geom.crosses(segment) or self.geom.intersects(segment)


def polygon_from_pairs(pairs: Iterable[list[float]]) -> Polygon:
    return Polygon([(p[0], p[1]) for p in pairs])
