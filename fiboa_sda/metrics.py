import functools
import math

import pandas as pd
import geopandas as gpd
import numpy as np
import pyproj
import utm
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


def _geometry_flatten(geom: BaseGeometry):
    """unpack (multi)geometry"""
    if hasattr(geom, "geoms"):  # Multi<Type> / GeometryCollection
        for g in geom.geoms:
            yield from _geometry_flatten(g)
    elif hasattr(geom, "interiors"):  # Polygon
        yield geom.exterior
        yield from geom.interiors
    else:  # Point / LineString
        yield geom


def _vertex_count(geom):
    """count vertices"""
    return sum(len(g.coords) for g in _geometry_flatten(geom))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """distance between points"""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _azimuth(point1: tuple[float, float], point2: tuple[float, float]) -> float:
    """azimuth between 2 points (interval 0 - 180)"""
    angle = np.arctan2(point2[0] - point1[0], point2[1] - point1[1])
    return np.degrees(angle) if angle > 0 else np.degrees(angle) + 180


def _azimuth_mrr(geom: BaseGeometry) -> float:
    """azimuth of minimum_rotated_rectangle"""
    bbox = list(geom.exterior.coords)
    axis1 = _dist(bbox[0], bbox[3])
    axis2 = _dist(bbox[0], bbox[1])

    if axis1 <= axis2:
        az = _azimuth(bbox[0], bbox[1])
    else:
        az = _azimuth(bbox[0], bbox[3])

    return az


@functools.lru_cache()
def _get_transformer(src_epsg: int, dst_epsg: int) -> pyproj.Transformer:
    source_crs = pyproj.CRS(f"epsg:{src_epsg}")
    dst_crs = pyproj.CRS(f"epsg:{dst_epsg}")
    return pyproj.Transformer.from_proj(source_crs, dst_crs, always_xy=True)


def _reproject_to_utm(geom: BaseGeometry, in_epsg: int):
    centroid = geom.centroid
    _, _, zone, _ = utm.from_latlon(centroid.y, centroid.x)
    if centroid.y >= 0:
        utm_zone = int(f"326{zone}")
    else:
        utm_zone = int(f"327{zone}")

    transformer = _get_transformer(in_epsg, utm_zone)
    geom_proj = transform(transformer.transform, geom)
    return geom_proj


def _calculate_geometry_metrics_for_row(row: pd.Series):
    geometry_utm = _reproject_to_utm(row.geometry, 4326)
    mrr = geometry_utm.minimum_rotated_rectangle
    utm_bounds = geometry_utm.bounds
    area = geometry_utm.area
    perimeter = geometry_utm.length
    row['area'] = area
    row['perimeter'] = perimeter
    row['width'] = utm_bounds[2] - utm_bounds[0]
    row['height'] = utm_bounds[3] - utm_bounds[1]
    row['circularity'] = (4 * math.pi * area) / (perimeter**2)
    row["vertex_count"] = _vertex_count(geometry_utm)
    row["rbf"] = 1 - (area / mrr.area)
    row["azimuth"] = _azimuth_mrr(mrr)
    row["compactness"] = area / perimeter
    return row


def calculate_geometry_metrics(gdf: gpd.GeoDataFrame):
    """Calculate fields for the geometry-metrics extension.

    https://github.com/vecorel/geometry-metrics
    """
    gdf = gdf.apply(_calculate_geometry_metrics_for_row, axis=1)
    return gdf
