import functools
import math

import pandas as pd
import geopandas as gpd
import pyproj
import utm
from shapely.geometry import LineString
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
    row["vertex_count"] = _vertex_count(row._geometry_utm)

    # Calculate azimuth
    coords = [c for c in row._mrr.boundary.coords]
    segments = [LineString([a, b]) for a, b in zip(coords,coords[1:])]
    longest_segment = max(segments, key=lambda x: x.length)
    p1, p2 = [c for c in longest_segment.coords]
    azimuth = math.degrees(math.atan2(p2[1]-p1[1], p2[0]-p1[0]))
    row["azimuth"] = azimuth
    return row


def calculate_geometry_metrics(gdf: gpd.GeoDataFrame):
    """Calculate fields for the geometry-metrics extension.

    https://github.com/vecorel/geometry-metrics
    """
    # Calculate a few temporary fields.
    gdf["_geometry_utm"] = gdf["geometry"].apply(
        functools.partial(_reproject_to_utm, in_epsg=gdf.crs.to_epsg()), gdf["geometry"]
    )
    gdf["_mrr"] = gdf["_geometry_utm"].minimum_rotated_rectangle()

    # Vectorize as much as we can
    gdf['area'] = gdf._geometry_utm.area
    gdf['perimeter'] = gdf._geometry_utm.length
    gdf['circularity'] = (4 * math.pi * gdf.area) / (gdf.perimeter**2)
    gdf['rbf'] = 1 - (gdf.area / gdf._mrr.area)
    gdf['compactness'] = gdf.area / gdf.perimeter
    bounds = gdf._geometry_utm.bounds
    gdf['width'] = bounds.maxx - bounds.minx
    gdf['height'] = bounds.maxy - bounds.miny

    # Some operations can't be vectorized
    gdf = gdf.apply(_calculate_geometry_metrics_for_row, axis=1)

    # Drop the temporary fields
    gdf.drop(['_geometry_utm', '_mrr'], axis=1, inplace=True)

    return gdf
