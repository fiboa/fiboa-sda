import warnings
from functools import lru_cache

from pandas.errors import SettingWithCopyWarning
from pydantic_settings import BaseSettings

# Skip noisy geopandas warnings
warnings.filterwarnings(
    action="ignore",
    category=UserWarning,
    message=r".*"
)
warnings.filterwarnings(
    action="ignore",
    category=SettingWithCopyWarning,
    message=r".*",
)
warnings.filterwarnings(
    action="ignore",
    category=FutureWarning,
    message=r".*",
    module="geopandas"
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
