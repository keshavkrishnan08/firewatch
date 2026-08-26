"""Satellite fire-object tracking (forecast/tracking.py)."""
from datetime import timedelta

from shapely.geometry import MultiPoint

from firewatch.forecast.tracking import _cluster, track_from_observations
from firewatch.geo import destination_point
from firewatch.ontology.objects import Observation, ObservationKind, Provenance, new_id


def _goes(t0, minutes, points):
    return Observation(id=new_id("obs"), t=t0 + timedelta(minutes=minutes), fire_id="f",
                       kind=ObservationKind.goes, geometry=MultiPoint(points),
                       provenance=Provenance(source="GOES-18 ABI", product="ABI-L2-FDCC"))


def test_cluster_separates_two_fires():
    a = [(-121.6, 39.8), (-121.61, 39.81)]
    b = [(-121.2, 39.4), (-121.21, 39.41)]  # ~40 km away
    clusters = _cluster(a + b, eps_km=4.0)
    assert len(clusters) == 2


def test_track_grows_and_moves(ign_time):
    lon0, lat0 = -121.6, 39.8
    obs = []
    # a fire that grows (more detections, wider extent) and marches north over 3 frames
    for k, mm in enumerate((0, 30, 60)):
        c = destination_point(lon0, lat0, 0.0, k * 2000)  # move north 2 km/frame
        radius = 1200 + k * 1600
        dirs = list(range(0, 360, 45 - 10 * k))  # more detections each frame
        pts = [c] + [destination_point(*c, b, radius) for b in dirs]
        obs.append(_goes(ign_time, mm, pts))
    track = track_from_observations(obs, ign_time)
    assert track.n_frames == 3
    areas = [p.area_km2 for p in track.points]
    assert areas[-1] > areas[0]  # the tracked object grows
    assert track.total_detections == sum(len(o.geometry["coordinates"]) for o in obs)
    assert 300 < track.net_heading_deg() < 360 or track.net_heading_deg() < 30  # ~north
    assert track.mean_ros_kmh() > 0
