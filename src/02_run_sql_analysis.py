import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path("data/processed/bc_surveillance.db")
SQL_PATH = Path("sql/01_surveillance_queries.sql")
OUTPUT_DIR = Path("outputs/tables")

QUERY_NAMES = [
    "01_data_quality_audit",
    "02_high_priority_disparities",
    "03_cycle_over_cycle_trends",
    "04_health_authority_benchmarks",
]


def run_surveillance_queries() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read the SQL file and split into individual queries on semicolons
    raw_sql = SQL_PATH.read_text(encoding="utf-8")
    queries = [q.strip() for q in raw_sql.split(";") if q.strip()]

    with sqlite3.connect(DB_PATH) as conn:
        for name, query in zip(QUERY_NAMES, queries):
            print(f"\n{'=' * 70}")
            print(f"RUNNING QUERY: {name}")
            print(f"{'=' * 70}")

            df_result = pd.read_sql_query(query, conn)
            print(df_result.head(15).to_string(index=False))
            print(f"\nTotal rows returned: {len(df_result)}")

            out_file = OUTPUT_DIR / f"{name}.csv"
            df_result.to_csv(out_file, index=False)
            print(f"Saved full table to: {out_file}")


if __name__ == "__main__":
    run_surveillance_queries()