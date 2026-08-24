"""Robot keywords for database access. Pooled connections, bound parameters."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from robot.api import logger
from robot.api.deco import keyword, library
from sqlalchemy import URL, Engine, bindparam, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from libraries.config import get_settings

QUERIES = Path(__file__).resolve().parent.parent / "resources" / "queries.yaml"


@library(scope="GLOBAL", version="1.0", auto_keywords=False)
class CaqhDatabase:
    """Read-only access to the credentialing database."""

    # ------------------------------------------------------------ internals

    def _url(self) -> URL:
        settings = get_settings()
        query = {
            "driver": settings.db_driver,
            "Encrypt": "yes",
            "TrustServerCertificate": "yes" if settings.db_trust_cert else "no",
            "APP": "caqh-qa",
        }
        if settings.db_trusted:
            query["Trusted_Connection"] = "yes"
            return URL.create(
                "mssql+pyodbc", host=settings.db_host, port=settings.db_port,
                database=settings.db_name, query=query,
            )
        return URL.create(
            "mssql+pyodbc",
            username=settings.db_user,
            password=settings.db_password.get_secret_value(),
            host=settings.db_host, port=settings.db_port,
            database=settings.db_name, query=query,
        )

    @lru_cache(maxsize=1)  # noqa: B019
    def _engine(self) -> Engine:
        settings = get_settings()
        logger.info(f"connecting to {settings.db_host} / {settings.db_name}")
        return create_engine(
            self._url(), pool_size=5, max_overflow=2, pool_pre_ping=True,
            pool_recycle=1800, connect_args={"timeout": settings.db_timeout},
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def _queries() -> dict[str, str]:
        return yaml.safe_load(QUERIES.read_text("utf-8")) or {}

    @staticmethod
    def _defaults() -> dict[str, Any]:
        settings = get_settings()
        return {
            "client": settings.client_entity,
            "status": settings.trigger_status,
            "actions": settings.cred_actions,
            "service": settings.service_address_type,
            "caqh_type": settings.caqh_id_type,
        }

    # -------------------------------------------------------------- keywords

    @keyword("Database Should Be Reachable")
    def database_should_be_reachable(self) -> None:
        """Fails with a readable message if the database cannot be reached."""
        settings = get_settings()
        if not settings.db_configured:
            missing = settings.missing("db_host", "db_name") or ["DB_USER or DB_TRUSTED"]
            raise AssertionError(
                f"Database not configured. Missing: {', '.join(missing)}.\n"
                f"Set them in .env locally, or as GitHub Variables/Secrets in CI."
            )
        try:
            with self._engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise AssertionError(
                f"Cannot reach {settings.db_host} / {settings.db_name}\n"
                f"{str(exc).splitlines()[0][:200]}"
            ) from None
        logger.info(f"connected to {settings.db_name}")

    @keyword("Database Is Available")
    def database_is_available(self) -> bool:
        """Returns True or False. Use with Skip If, never raises."""
        try:
            self.database_should_be_reachable()
            return True
        except Exception:
            return False

    @keyword("Run Reference Query")
    @retry(
        retry=retry_if_exception_type(SQLAlchemyError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def run_reference_query(self, name: str, **overrides: Any) -> list[dict[str, Any]]:
        """Runs a named query from resources/queries.yaml and returns a list of rows.

        Example:
        | ${rows}= | Run Reference Query | fan_out |
        """
        sql = self._queries().get(name)
        if sql is None:
            available = ", ".join(sorted(self._queries()))
            raise AssertionError(
                f"No query named '{name}' in resources/queries.yaml.\nAvailable: {available}"
            )
        return self._execute(sql, {**self._defaults(), **overrides}, label=name)

    @keyword("Run SQL")
    def run_sql(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        """Runs raw read-only SQL. Use bound parameters, never string joining.

        | ${rows}= | Run SQL | SELECT * FROM Practitioners WHERE NPI = :npi | npi=1234567890 |
        """
        lowered = sql.strip().lower()
        if not lowered.startswith(("select", "with", "declare")):
            raise AssertionError("Run SQL is read-only. Only SELECT / WITH / DECLARE allowed.")
        return self._execute(sql, params, label="ad-hoc")

    def _execute(self, sql: str, params: dict[str, Any], label: str) -> list[dict[str, Any]]:
        statement = text(sql)
        expanding = [
            bindparam(key, expanding=True)
            for key, value in params.items()
            if isinstance(value, (list, tuple, set)) and f":{key}" in sql
        ]
        if expanding:
            statement = statement.bindparams(*expanding)
        used = {k: v for k, v in params.items() if f":{k}" in sql}

        try:
            with self._engine().connect() as conn:
                result = conn.execute(statement, used)
                rows = [dict(r._mapping) for r in result] if result.returns_rows else []
        except SQLAlchemyError as exc:
            raise AssertionError(
                f"Query '{label}' does not fit this schema.\n"
                f"{str(exc).splitlines()[0][:220]}\n"
                f"Fix resources/queries.yaml, or run: python tools/discover.py"
            ) from None

        logger.info(f"{label}: {len(rows)} row(s)")
        return rows

    @keyword("Row Count")
    def row_count(self, rows: list[dict[str, Any]]) -> int:
        return len(rows)

    @keyword("Column Values")
    def column_values(self, rows: list[dict[str, Any]], column: str) -> list[Any]:
        """Pulls one column out of a result set as a plain list."""
        return [row[column] for row in rows if column in row]

    @keyword("Format Rows")
    def format_rows(self, rows: list[dict[str, Any]], limit: int = 8) -> str:
        """Turns rows into an indented block for a failure message."""
        if not rows:
            return "      (none)"
        lines = [
            "      " + "  ".join(f"{k}={v}" for k, v in row.items())
            for row in rows[:limit]
        ]
        if len(rows) > limit:
            lines.append(f"      ... and {len(rows) - limit} more")
        return "\n".join(lines)

    @keyword("Table Should Exist")
    def table_should_exist(self, name: str) -> None:
        rows = self.run_sql(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = :t", t=name
        )
        if not rows:
            raise AssertionError(
                f"Table '{name}' not found.\n"
                f"Run 'python tools/discover.py' to see the real name, "
                f"then fix resources/queries.yaml."
            )

    @keyword("Column Should Exist")
    def column_should_exist(self, table: str, column: str) -> None:
        rows = self.run_sql(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = :t AND COLUMN_NAME = :c", t=table, c=column
        )
        if not rows:
            present = self.run_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = :t ORDER BY ORDINAL_POSITION", t=table
            )
            names = ", ".join(r["COLUMN_NAME"] for r in present) or "(table not found)"
            raise AssertionError(f"{table}.{column} not found.\nColumns present: {names}")

    @keyword("Reference Value Should Exist")
    def reference_value_should_exist(
        self, table: str, column: str, value: str, setting_name: str
    ) -> None:
        """Checks a configured business value really exists in the data."""
        rows = self.run_sql(
            f"SELECT 1 FROM {table} WHERE {column} = :v", v=value  # noqa: S608
        )
        if not rows:
            available = self.run_sql(f"SELECT DISTINCT {column} AS v FROM {table}")  # noqa: S608
            options = ", ".join(str(r["v"]) for r in available[:25]) or "(none)"
            raise AssertionError(
                f"No {table}.{column} equal to '{value}'.\n"
                f"Available: {options}\n"
                f"Fix {setting_name} in .env (or the GitHub Variable of that name)."
            )