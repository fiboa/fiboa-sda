import functools
import json
import multiprocessing
import tempfile

import boto3
import geopandas as gpd
import pandas as pd
import pyarrow as pa
from google.cloud import bigquery

from fiboa_sda.logger import get_logger, timer_func
from fiboa_sda.metrics import calculate_geometry_metrics
from fiboa_sda.settings import get_settings

settings = get_settings()
logger = get_logger(__name__)
BUCKET_NAME = "us-west-2.opendata.source.coop"
S3_CLIENT = boto3.client('s3', region_name="us-west-2")

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

def list_parquet_files(prefix: str = "fiboa"):
    all_keys = []
    for obj in S3_CLIENT.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)['Contents']:
        if obj['Key'].endswith(".parquet"):
            all_keys.append(obj['Key'])

    return all_keys


def get_s3_key_for_dataset(fiboa_id: str) -> list[str]:
    return list_parquet_files(prefix=f"fiboa/{fiboa_id}")


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

@timer_func
def normalize_dataset(df: gpd.GeoDataFrame, repository_id: str, s3_path: str) -> gpd.GeoDataFrame:
    """Open a parquet file and normalize the schema."""
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
    df["repository_id"] = repository_id
    df["url"] = s3_path

    # Handle the geometry column.  Note BQ only supports EPSG:4326.
    # We convert to WKT string because BQ has slightly different
    # validation logic than geopandas.  We'll convert this from string
    # to geography type after the data is first inserted to BQ.
    if df.crs.to_epsg() != 4326:
        df = df.to_crs(crs=4326)
    df["geometry"] = df["geometry"]
    return df


@timer_func
def download_parquet(key: str) -> gpd.GeoDataFrame:
    with tempfile.NamedTemporaryFile(mode="w+b") as f:
        S3_CLIENT.download_fileobj(BUCKET_NAME, key, f)
        df = gpd.read_parquet(f.name)
        return df


@timer_func
def ingest_parquet(
    key: str, project_name: str, dataset_name: str, table_name: str
) -> None:
    logger.info(f"Ingesting s3://{BUCKET_NAME}/{key} to {project_name}:{dataset_name}.{table_name}")

    df = download_parquet(key)
    normalized_df = normalize_dataset(df, repository_id=key.split("/")[1], s3_path=f"s3://{BUCKET_NAME}/{key}")
    calculate_geometry_metrics(normalized_df)
    write_to_bq(normalized_df, project_name, dataset_name, table_name)


def ingest_all_parquets(project_name: str, dataset_name: str, table_name: str, n_processes: int | None) -> None:
    urls = list_parquet_files()

    # Run across all available cores
    m = multiprocessing.Pool(n_processes)
    m.map(
        functools.partial(
            ingest_parquet,
            project_name=project_name,
            dataset_name=dataset_name,
            table_name=table_name,
        ),
        urls,
    )
