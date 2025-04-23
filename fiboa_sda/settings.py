import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings

# Skip geopandas warning when operating on geodataframes without
# a geometry column.
warnings.filterwarnings(
    action="ignore",
    category=UserWarning,
    message="Geometry column does not contain geometry.",
)


class Settings(BaseSettings):
    FIBOA_STAC_URL: str = "https://fiboa.org/stac/catalog.json"
    SOURCE_COOP_URL: str = "https://data.source.coop"
    FIBOA_FIELDS: list[str] = [
        "id",
        "collection",
        "category",
        "geometry",
        "bbox",
        "area",
        "perimeter",
        "determination_method",
        "determination_datetime",
        "determination_details",
    ]  # TODO: Discover these programatically (parse the JSON schemas?)
    DEBUG: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
