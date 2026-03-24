from __future__ import annotations

import os
from typing import Any

import psycopg2
import psycopg2.extras

class Database:
    """Manages the connection and queries to the PostgreSQL database."""

    def __init__(self, conn_params: dict[str, str] | None = None):
        self.conn_params = conn_params if conn_params is not None else self._load_conn_params()
        self.conn: psycopg2.extensions.connection | None = None
        self.connect()

    def _load_conn_params(self) -> dict[str, str] | None:
        user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
        password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")
        dbname = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB")

        if not user or not password or not dbname:
            return None

        return {
            "host": os.getenv("PGHOST", "localhost"),
            "port": os.getenv("PGPORT", "5432"),
            "user": user,
            "password": password,
            "dbname": dbname,
        }

    def connect(self) -> None:
        """Establishes the connection to the database."""
        if not self.conn_params:
            self.conn = None
            return

        try:
            self.conn = psycopg2.connect(**self.conn_params)
        except Exception as exc:
            print(f"Error al conectar a la base de datos: {exc}")
            self.conn = None

    def execute_query(self, query: str, params: tuple[Any, ...] | None = None) -> bool:
        """Executes a query (INSERT, UPDATE, DELETE) and commits."""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
            self.conn.commit()
            return True
        except psycopg2.Error as e:
            print(f"Fallo la consulta: {e}")
            self.conn.rollback()
            return False

    def fetch_all(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Executes a SELECT query and returns all results as dicts."""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Fallo la obtención de datos: {e}")
            return []

    def close(self) -> None:
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
