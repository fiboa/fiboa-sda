import click

from fiboa_sda.ingest import (get_s3_key_for_dataset, ingest_all_parquets,
                              ingest_parquet)


@click.group
def app():
    pass


@app.command(help="Ingest all fiboa datasets to BQ")
@click.argument("dataset_name")
@click.argument("table_name")
@click.option("--project-name", required=True)
@click.option("--n-processes", required=False, default=None, type=int)
def ingest_all(dataset_name: str, table_name: str, project_name: str, n_processes: int | None = None):
    ingest_all_parquets(project_name, dataset_name, table_name, n_processes)


@app.command(help="Ingest a single fiboa dataset to BQ")
@click.argument("fiboa_id")
@click.argument("dataset_name")
@click.argument("table_name")
@click.option("--project-name", required=True)
def ingest_one(fiboa_id: str, dataset_name: str, table_name: str, project_name: str):
    keys = get_s3_key_for_dataset(fiboa_id)
    for key in keys:
        ingest_parquet(key, project_name, dataset_name, table_name)
    click.echo(
        f"Finished ingesting {fiboa_id} to {project_name}:{dataset_name}.{table_name}"
    )
