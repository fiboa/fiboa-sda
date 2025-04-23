import functools
import json
import multiprocessing
import tempfile
from urllib.parse import urlsplit

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import requests
from google.cloud import bigquery
from obstore.fsspec import FsspecStore
from tenacity import retry, stop_after_attempt

from fiboa_sda.logger import get_logger
from fiboa_sda.metrics import calculate_geometry_metrics
from fiboa_sda.settings import get_settings

settings = get_settings()
logger = get_logger(__name__)
FSSPEC_STORE = FsspecStore("s3", endpoint_url=settings.SOURCE_COOP_URL)

# pyarrow schema used when writing out parquet
# files to BQ
SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("collection", pa.string()),
        pa.field("category", pa.string()),
        # Save geometry to a string, cast to geography type in BQ.
        pa.field("geometry", pa.string()),
        pa.field("bbox", pa.list_(pa.int64())),
        pa.field("determination_method", pa.string()),
        pa.field("determination_datetime", pa.date64()),
        # Write external fields to a string, cast to JSON type in BQ.
        # The `pa.json_` field is added in pyarrow v19.0 but that
        # version has a bug that prevents passing a custom schema to
        # `pd.DataFrame.to_parquet`
        pa.field("external_fields", pa.string()),
        pa.field("repository_id", pa.string()),
        pa.field("url", pa.string()),
        # Geometry-metrics extension.
        pa.field("area", pa.float64()),
        pa.field("perimeter", pa.float64()),
        pa.field("width", pa.float64()),
        pa.field("height", pa.float64()),
        pa.field("circularity", pa.float64()),
        pa.field("vertex_count", pa.int64()),
        pa.field("rbf", pa.float64()),
        pa.field("azimuth", pa.float64()),
        pa.field("compactness", pa.float64()),
    ]
)


@retry(stop=stop_after_attempt(3))
def _send_request_with_retry(*args, **kwargs):
    """Send a HTTP request, retrying up to 3 times."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()


def list_parquet_files():
    """Generate a list of available fiboa geoparquet files by crawling the STAC catalog."""
    resp_json = _send_request_with_retry(settings.FIBOA_STAC_URL)
    for link in resp_json["links"]:
        # Skip non-children and relative links
        if link["rel"] != "child":
            continue
        if not link["href"].startswith("https"):
            continue
        logger.debug(f"Opening collection - {link['href']}")

        # Parse out parquet filepath from each collection
        collection = _send_request_with_retry(link["href"])
        asset = collection["assets"]["data"]["href"]

        # Skip relative links
        if not asset.startswith("https"):
            logger.warning(f"Skipping relative link for collection - {link['href']}")
            continue

        yield asset


def get_parquet_url_for_dataset(fiboa_id: str) -> str:
    """Get the geoparquet file for the given fiboa dataset by querying the STAC catalog"""
    url = f"{settings.SOURCE_COOP_URL}/fiboa/{fiboa_id}/stac/collection.json"
    resp_json = _send_request_with_retry(url)
    return resp_json["assets"]["data"]["href"]


def write_to_bq(
    df: pd.DataFrame, project_name: str, dataset_name: str, table_name: str
) -> None:
    client = bigquery.Client(project=project_name)
    job_config = bigquery.LoadJobConfig(source_format="PARQUET")

    with tempfile.NamedTemporaryFile() as tmp:
        # Geopandas does not let us pass a custom schema to `.to_parquet`, pandas
        # does though!
        df['geometry'] = df['geometry'].to_wkt()
        pd.DataFrame(df).to_parquet(tmp.name, index=False, schema=SCHEMA)
        client.load_table_from_file(
            tmp,
            f"{dataset_name}.{table_name}",
            job_config=job_config,
        )


def http_to_s3(url: str) -> str:
    """Convert a source.coop HTTP URL to a S3 path."""
    path = urlsplit(url).path
    splits = path.split("/")
    bucket = splits[1]
    key = "/".join(splits[2:])
    return f"s3://{bucket}/{key}"


def normalize_dataset(url: str) -> gpd.GeoDataFrame:
    """Open a parquet file and normalize the schema."""
    # Decompose the URL into S3 bucket/key, hitting S3 directly
    # seems more reliable than going through the source.coop data proxy.
    s3_path = http_to_s3(url)

    with FSSPEC_STORE.open(s3_path) as f:
        df = gpd.read_parquet(f)

    # Any missing fiboa fields are nan-filled.
    missing_fiboa_fields = set(settings.FIBOA_FIELDS) - set(df.columns)
    for field in missing_fiboa_fields:
        df[field] = None

    # Dump any fields that aren't part of fiboa into a JSON column.
    available_external_fields = set(df.columns) - set(settings.FIBOA_FIELDS)
    df["external_fields"] = df.apply(
        lambda row: json.dumps(
            {field: row[field] for field in available_external_fields}
        ),
        axis=1,
    )
    df = df[list(settings.FIBOA_FIELDS) + ["external_fields"]]

    # Drop the geometry-metrics fields, we'll recalculate these.
    # This also cleans up the field ordering.
    df.drop(["area", "perimeter"], axis=1, inplace=True)

    # Append some metadata linking the rows in BQ back
    # to the data in source.coop.
    df["repository_id"] = url.split("/")[-2]
    df["url"] = url

    # Handle the geometry column.  Note BQ only supports EPSG:4326.
    # We convert to WKT string because BQ has slightly different
    # validation logic than geopandas.  We'll convert this from string
    # to geography type after the data is first inserted to BQ.
    if df.crs.to_epsg() != 4326:
        df = df.to_crs(crs=4326)
    df["geometry"] = df["geometry"]
    return df


def ingest_parquet(
    url: str, project_name: str, dataset_name: str, table_name: str
) -> None:
    df = normalize_dataset(url)
    calculate_geometry_metrics(df)
    write_to_bq(df, project_name, dataset_name, table_name)


def ingest_all_parquets(project_name: str, dataset_name: str, table_name: str) -> None:
    urls = list(list_parquet_files())

    # Run across all available cores
    m = multiprocessing.Pool()
    m.map(
        functools.partial(
            ingest_parquet,
            project_name=project_name,
            dataset_name=dataset_name,
            table_name=table_name,
        ),
        urls,
    )
