"""FIREWATCH ontology objects (Palantir-style nouns).

The ontology is the single source of truth (CLAUDE.md / docs/ONTOLOGY.md). Every module reads and
writes these objects; modules never exchange raw feed payloads. Objects are time-stamped and
carry provenance where relevant, so state is reconstructable at any past instant and projectable
to future instants.

Geometry is stored as GeoJSON-style mappings in EPSG:4326 (see firewatch.geo). Timestamps are
timezone-aware UTC.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator
from shapely.geometry.base import BaseGeometry

from firewatch.geo import from_geojson, to_geojson


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _as_geojson(v: Any) -> dict | None:
    """Coerce a shapely geometry / GeoJSON mapping / None into a GeoJSON mapping."""
    if v is None:
        return None
    if isinstance(v, BaseGeometry):
        return to_geojson(v)
    return v


# ── enums ─────────────────────────────────────────────────────────────────────


class FireStatus(StrEnum):
    active = "active"
    contained = "contained"
    controlled = "controlled"
    out = "out"
    unknown = "unknown"


class ObservationKind(StrEnum):
    goes = "goes"
    viirs = "viirs"
    modis = "modis"
    camera_front = "camera_front"
    official_perimeter = "official_perimeter"


class PerimeterSource(StrEnum):
    official = "official"
    forecast = "forecast"
    observed = "observed"


class RecommendationKind(StrEnum):
    evacuate = "evacuate"
    close_road = "close_road"
    stage = "stage"


class ResourceKind(StrEnum):
    crew = "crew"
    engine = "engine"
    air = "air"


# ── base ──────────────────────────────────────────────────────────────────────


class OntologyObject(BaseModel):
    """Base for every ontology object. `kind` is the table name in the store."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    #: valid-time of this object version (the instant it describes / becomes true)
    t: datetime = Field(default_factory=utcnow)

    @property
    def type_name(self) -> str:
        """Ontology object type (the store's table name). Not a pydantic field."""
        return type(self).__name__

    def geometry_fields(self) -> list[str]:
        """Names of GeoJSON-valued fields (overridden where geometry exists)."""
        return []

    def geom(self, field: str = "geometry") -> BaseGeometry | None:
        return from_geojson(getattr(self, field, None))


class Provenance(BaseModel):
    """Mandatory on every Observation. Needed for assimilation weighting and audit (FR-ING-3)."""

    source: str  # e.g. "NASA FIRMS", "GOES-18 ABI", "ALERTCalifornia", "NIFC WFIGS"
    product: str  # e.g. "VNP14IMG", "ABI-L2-FDCC", "camera_georef", "IR perimeter"
    retrieved_at: datetime = Field(default_factory=utcnow)
    native_resolution_m: float | None = None
    reported_uncertainty_m: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


# ── objects ───────────────────────────────────────────────────────────────────


class Fire(OntologyObject):
    """The incident. Anchors everything."""

    name: str
    discovered_at: datetime
    status: FireStatus = FireStatus.active
    centroid: dict | None = None  # GeoJSON Point
    ignition_estimate: dict | None = None  # GeoJSON Point

    _coerce = field_validator("centroid", "ignition_estimate", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["centroid", "ignition_estimate"]


class FirePerimeter(OntologyObject):
    """Observed or forecast perimeter at time `t`."""

    fire_id: str
    geometry: dict  # GeoJSON Polygon/MultiPolygon
    source: PerimeterSource = PerimeterSource.observed
    confidence: float = 1.0
    prob_field_ref: str | None = None  # Forecast.id when source == forecast

    _coerce = field_validator("geometry", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["geometry"]


class Observation(OntologyObject):
    """The atoms the filter assimilates. Provenance is mandatory (FR-ING-3)."""

    fire_id: str
    kind: ObservationKind
    geometry: dict | None = None  # GeoJSON of the detection footprint / front / point cluster
    value: dict[str, Any] = Field(default_factory=dict)  # FRP, brightness, pixel count, etc.
    provenance: Provenance
    reported_uncertainty_m: float | None = None

    _coerce = field_validator("geometry", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["geometry"]


class Forecast(OntologyObject):
    """Output of the assimilation loop, per horizon (FR-FC-4)."""

    fire_id: str
    issued_at: datetime
    horizon_min: int
    #: burn-probability field metadata; the raster itself is cached under outputs/ / data/
    prob_field: dict[str, Any] = Field(default_factory=dict)
    expected_perimeter: dict | None = None  # GeoJSON
    region_90: dict | None = None  # GeoJSON of the 90% credible burn region
    assimilation: bool = True  # ON vs OFF arm (the ablation)
    calibration_ref: str | None = None

    _coerce = field_validator("expected_perimeter", "region_90", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["expected_perimeter", "region_90"]


class Camera(OntologyObject):
    """Tower/ground camera. Pose feeds georeferencing; tilt often approximate → self-calibrated."""

    name: str
    lat: float
    lon: float
    elev_m: float
    pan_deg: float = 0.0  # azimuth of optical axis, 0 = North, clockwise
    tilt_deg: float = 0.0  # + up from horizontal
    fov_deg: float = 60.0  # horizontal field of view
    image_width: int = 1920
    image_height: int = 1080
    network: str = "unknown"
    pan_uncertainty_deg: float = 3.0
    tilt_uncertainty_deg: float = 3.0
    pose_uncertainty_m: float = 25.0
    last_frame: str | None = None


class WeatherCell(OntologyObject):
    """HRRR grid cell / RAWS station reading. Drives ROS + ensemble perturbation."""

    bbox: list[float]  # [minlon, minlat, maxlon, maxlat]
    wind_u: float  # m/s eastward at 10 m
    wind_v: float  # m/s northward at 10 m
    rh: float | None = None  # %
    temp_c: float | None = None
    source: str = "HRRR"

    @property
    def wind_speed(self) -> float:
        return float((self.wind_u**2 + self.wind_v**2) ** 0.5)

    @property
    def wind_dir_to_deg(self) -> float:
        """Compass direction the wind is blowing *toward* (0=N, clockwise)."""
        import math

        return (math.degrees(math.atan2(self.wind_u, self.wind_v)) + 360.0) % 360.0


class TerrainCell(OntologyObject):
    """From DEM. Static. Drives ROS slope term + the ray-cast surface."""

    bbox: list[float]
    elev_m: float
    slope_deg: float
    aspect_deg: float


class FuelCell(OntologyObject):
    """LANDFIRE. Drives ROS; moisture is an ensemble-perturbed unknown."""

    bbox: list[float]
    fuel_model: int  # Scott & Burgan / Anderson 13 code
    canopy_pct: float = 0.0
    moisture_est: float = 0.08  # dead fuel moisture fraction


class Structure(OntologyObject):
    """Building footprint × census. Exposure target."""

    footprint: dict  # GeoJSON Polygon
    type: str = "residential"
    population_est: float = 2.5

    _coerce = field_validator("footprint", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["footprint"]


class PopulationZone(OntologyObject):
    """County evac zone where available, else census block."""

    name: str
    geometry: dict  # GeoJSON Polygon
    population: int = 0
    evac_status: str = "normal"  # normal | warning | order

    _coerce = field_validator("geometry", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["geometry"]


class RoadSegment(OntologyObject):
    """OSM edge. Egress routing + threat timing."""

    geometry: dict  # GeoJSON LineString
    name: str = ""
    graph_edge: list[str] = Field(default_factory=list)  # [u, v] node ids
    highway: str = "road"
    capacity: int = 600  # vehicles/hour (planning figure)

    _coerce = field_validator("geometry", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["geometry"]


class Resource(OntologyObject):
    """Crew/engine/air asset, for staging suggestions (where public)."""

    kind: ResourceKind
    location: dict  # GeoJSON Point
    status: str = "available"
    label: str = ""

    _coerce = field_validator("location", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["location"]


class Recommendation(OntologyObject):
    """The decision-layer output. Human-in-the-loop; evidence[] links the justifying objects.

    Nothing here is an autonomous order — it informs a human decision (FR-DEC-5, NFR guardrail).
    """

    kind: RecommendationKind
    target: str  # object id (zone / road / point label)
    target_name: str = ""
    lead_time_min: float | None = None
    lead_time_low_min: float | None = None  # confidence band
    lead_time_high_min: float | None = None
    confidence: float = 0.0
    urgency: float = 0.0  # ranking score, higher = more urgent
    geometry: dict | None = None
    evidence: list[str] = Field(default_factory=list)  # object ids that justify this
    rationale: str = ""
    issued_at: datetime = Field(default_factory=utcnow)
    acknowledged_by: str | None = None  # human decision, never automated

    _coerce = field_validator("geometry", mode="before")(_as_geojson)

    def geometry_fields(self) -> list[str]:
        return ["geometry"]


#: registry used by the store to resolve a kind string back to its class
OBJECT_TYPES: dict[str, type[OntologyObject]] = {
    cls.__name__: cls
    for cls in [
        Fire,
        FirePerimeter,
        Observation,
        Forecast,
        Camera,
        WeatherCell,
        TerrainCell,
        FuelCell,
        Structure,
        PopulationZone,
        RoadSegment,
        Resource,
        Recommendation,
    ]
}
