"""SQLite access layer. All SQL lives here so the app and the tests share one definition."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from data_gen import build_database

DB_PATH = Path(__file__).resolve().parent / "data" / "sales_simulated.db"


def ensure_database(path: str | Path = DB_PATH) -> Path:
    """Build the simulated database on first use."""
    path = Path(path)
    if not path.exists():
        build_database(path)
    return path


def query(sql: str, params: tuple = (), path: str | Path = DB_PATH) -> pd.DataFrame:
    path = ensure_database(path)
    with closing(sqlite3.connect(path)) as con:
        return pd.read_sql_query(sql, con, params=params)


def load_sales(path: str | Path = DB_PATH) -> pd.DataFrame:
    return query(
        "SELECT month, customer_id, customer_name, country, iso3, region, segment, "
        "service, category, shipments, revenue FROM fact_sales ORDER BY month, customer_id, service",
        path=path,
    )


def load_targets(path: str | Path = DB_PATH) -> pd.DataFrame:
    return query("SELECT month, region, target_revenue FROM targets ORDER BY month, region", path=path)


def load_customers(path: str | Path = DB_PATH) -> pd.DataFrame:
    return query("SELECT * FROM customers", path=path)


def load_services(path: str | Path = DB_PATH) -> pd.DataFrame:
    return query("SELECT * FROM services", path=path)


def load_info(path: str | Path = DB_PATH) -> pd.DataFrame:
    return query("SELECT key, value FROM dataset_info", path=path)
