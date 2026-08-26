"""Discover address/location tables without printing provider data.

Run:

    python tools\discover_addresses.py > address-discovery.txt

The output contains table and column metadata only:
- no practitioner names
- no NPIs
- no addresses
- no dates of birth
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def heading(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    from libraries.CaqhDatabase import CaqhDatabase

    database = CaqhDatabase()

    heading("CAQH QA - ADDRESS / LOCATION SCHEMA DISCOVERY")
    print("Schema metadata only. No practitioner records are queried.\n")

    try:
        database.run_sql("SELECT 1")
    except Exception as exc:
        print(f"Cannot connect to the database: {str(exc).splitlines()[0]}")
        return 1

    # ------------------------------------------------------------------ tables

    heading("1. TABLES WITH ADDRESS OR LOCATION IN THEIR NAME")

    name_rows = database.run_sql(
        """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND (
              TABLE_NAME LIKE '%Address%'
              OR TABLE_NAME LIKE '%Location%'
              OR TABLE_NAME LIKE '%Practice%'
              OR TABLE_NAME LIKE '%Facility%'
          )
        ORDER BY TABLE_NAME
        """
    )

    if not name_rows:
        print("No candidate tables found by table name.")
    else:
        for row in name_rows:
            print(f"  {row['TABLE_NAME']}")

    # --------------------------------------------------------------- columns

    heading("2. TABLES WITH ADDRESS-LIKE COLUMNS")

    column_rows = database.run_sql(
        """
        SELECT
            TABLE_NAME,
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE
            COLUMN_NAME LIKE '%Address%'
            OR COLUMN_NAME LIKE '%Location%'
            OR COLUMN_NAME LIKE '%City%'
            OR COLUMN_NAME LIKE '%State%'
            OR COLUMN_NAME LIKE '%Zip%'
            OR COLUMN_NAME LIKE '%Postal%'
            OR COLUMN_NAME LIKE '%County%'
            OR COLUMN_NAME LIKE '%Latitude%'
            OR COLUMN_NAME LIKE '%Longitude%'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
    )

    by_table: dict[str, list[dict]] = defaultdict(list)
    for row in column_rows:
        by_table[row["TABLE_NAME"]].append(row)

    if not by_table:
        print("No candidate tables found by column names.")
    else:
        for table, columns in by_table.items():
            print(f"\n{table}")
            print("-" * len(table))
            for column in columns:
                kind = column["DATA_TYPE"]
                length = column["CHARACTER_MAXIMUM_LENGTH"]
                if length:
                    kind += f"({length})"
                print(f"  {column['COLUMN_NAME']:<38} {kind}")

    # ------------------------------------------------ practitioner linkage

    heading("3. TABLES LINKED TO PRACTITIONERS")

    practitioner_rows = database.run_sql(
        """
        SELECT
            TABLE_NAME,
            COLUMN_NAME,
            DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE COLUMN_NAME IN (
            'PractitionerID',
            'ProviderID',
            'ParentRecID',
            'LocationID',
            'AddressID',
            'AddressTypeID'
        )
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
    )

    linked: dict[str, list[dict]] = defaultdict(list)
    for row in practitioner_rows:
        linked[row["TABLE_NAME"]].append(row)

    for table, columns in linked.items():
        print(f"\n{table}")
        print("-" * len(table))
        for column in columns:
            print(f"  {column['COLUMN_NAME']:<38} {column['DATA_TYPE']}")

    # -------------------------------------------------------- foreign keys

    heading("4. FOREIGN KEYS REFERENCING ADDRESS TYPES")

    try:
        fk_rows = database.run_sql(
            """
            SELECT
                OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS schema_name,
                OBJECT_NAME(fkc.parent_object_id) AS table_name,
                COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS column_name,
                OBJECT_NAME(fkc.referenced_object_id) AS referenced_table,
                COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id)
                    AS referenced_column
            FROM sys.foreign_key_columns AS fkc
            WHERE OBJECT_NAME(fkc.referenced_object_id) = 'AddressTypes'
            ORDER BY table_name, column_name
            """
        )
    except Exception as exc:
        print(f"Could not inspect foreign keys: {str(exc).splitlines()[0]}")
        fk_rows = []

    if not fk_rows:
        print("No declared foreign keys reference AddressTypes.")
        print("This does not mean address data is absent; the database may not use FKs.")
    else:
        for row in fk_rows:
            print(
                f"  {row['schema_name']}.{row['table_name']}.{row['column_name']}"
                f" -> {row['referenced_table']}.{row['referenced_column']}"
            )

    # -------------------------------------------------------- all columns

    heading("5. FULL COLUMNS FOR CANDIDATE TABLES")

    candidate_names = {row["TABLE_NAME"] for row in name_rows}
    candidate_names.update(by_table.keys())

    if not candidate_names:
        print("No candidate table names identified.")
    else:
        for table in sorted(candidate_names):
            rows = database.run_sql(
                """
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
                """,
                table_name=table,
            )

            print(f"\n{table}")
            print("-" * len(table))
            for row in rows:
                kind = row["DATA_TYPE"]
                if row["CHARACTER_MAXIMUM_LENGTH"]:
                    kind += f"({row['CHARACTER_MAXIMUM_LENGTH']})"
                print(
                    f"  {row['COLUMN_NAME']:<38} "
                    f"{kind:<20} "
                    f"{row['IS_NULLABLE']}"
                )

    heading("NEXT STEP")
    print(
        "Send sections 1, 2, 3, and 5 of this output. "
        "Then address validation SQL can be added safely to queries.yaml."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
