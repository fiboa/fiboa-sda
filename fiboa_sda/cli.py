import click

from fiboa_sda.ingest import (get_parquet_url_for_dataset, ingest_all_parquets,
                              ingest_parquet)


@click.group
def app():
    pass


@app.command(help="Ingest all fiboa datasets to BQ")
@click.argument("dataset_name")
@click.argument("table_name")
@click.option("--project-name", required=True)
def ingest_all(dataset_name: str, table_name: str, project_name: str):
    ingest_all_parquets(project_name, dataset_name, table_name)


@app.command(help="Ingest a single fiboa dataset to BQ")
@click.argument("fiboa_id")
@click.argument("dataset_name")
@click.argument("table_name")
@click.option("--project-name", required=True)
def ingest_one(fiboa_id: str, dataset_name: str, table_name: str, project_name: str):
    urls = get_parquet_url_for_dataset(fiboa_id)
    for url in urls:
        ingest_parquet(url, project_name, dataset_name, table_name)
    click.echo(
        f"Finished ingesting {fiboa_id} to {project_name}:{dataset_name}.{table_name}"
    )
