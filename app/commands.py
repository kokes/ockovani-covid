import time
from datetime import date

import click

from app import app
from app.etl import Etl
from app.opendata_fetcher import OpenDataFetcher


@app.cli.command('fetch-opendata')
def fetch_opendata_command():
    """Fetch opendata from UZIS."""
    start = time.time()
    app.logger.info("Fetching opendata started.")
    fetcher = OpenDataFetcher()
    result = fetcher.fetch_all()
    if result:
        end = time.time()
        app.logger.info("Fetching opendata finished successfully in {:.1f} s.".format(end - start))
        exit(0)
    else:
        app.logger.error("Fetching opendata failed.")
        exit(1)


@app.cli.command('compute-metrics')
@click.argument("datum", nargs=-1)
def compute_metrics_command(datum):
    """Fetch opendata from UZIS."""
    start = time.time()
    app.logger.info("Computing metrics started.")
    etl = Etl(date.fromisoformat(datum[0]) if len(datum) == 1 else date.today())
    result = etl.compute_all()
    if result:
        end = time.time()
        app.logger.info("Computing metrics finished successfully in {:.1f} s.".format(end - start))
        exit(0)
    else:
        app.logger.error("Computing metrics failed.")
        exit(1)
