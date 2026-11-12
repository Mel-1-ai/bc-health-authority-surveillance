import sqlite3
from pathlib import Path
import pandas as pd

# File paths
RAW_PATH = Path("data/raw/bc_health_indicators.csv")
PROCESSED_CSV = Path("data/processed/bc_hsda_surveillance_clean.csv")
DB_PATH = Path("data/processed/bc_surveillance.db")

# Map BC Health Service Delivery Areas (HSDAs) to Parent Regional Health Authorities
HSDA_TO_HA = {
    "East Kootenay": "Interior Health",
    "Kootenay-Boundary": "Interior Health",
    "Okanagan": "Interior Health",
    "Thompson/Cariboo": "Interior Health",
    "Fraser South": "Fraser Health",
    "Vancouver": "Vancouver Coastal Health",
    "Northwest": "Northern Health",
    "Northern Interior": "Northern Health",
    "Northeast": "Northern Health",
}

# Decode Statistics Canada provincial comparison codes
PROV_DIFF_MAP = {
    -1.0: "Significantly lower than BC",
    0.0: "Not statistically different from BC",
    1.0: "Significantly higher than BC",
}


def load_and_clean(filepath: Path) -> pd.DataFrame:
    print(f"Loading raw StatCan extract from {filepath}...")
    df = pd.read_csv(filepath)

    # 1. Clean geography names and assign parent Regional Health Authority
    df["hsda_name"] = (
        df["GEO"]
        .str.replace(" Health Service Delivery Area, British Columbia", "", regex=False)
        .str.strip()
    )
    df["health_authority"] = df["hsda_name"].map(HSDA_TO_HA)

    # 2. Extract cycle start year for chronological sorting
    df["cycle_start_year"] = df["REF_DATE"].str.slice(0, 4).astype(int)

    # 3. Standardize column names to snake_case
    df = df.rename(
        columns={
            "REF_DATE": "ref_date",
            "DGUID": "dguid",
            "Age group": "age_group",
            "Sex": "sex",
            "Indicators": "indicator",
            "Characteristics": "characteristic",
            "VALUE": "value",
            "STATUS": "status",
        }
    )

    # 4. Extract data quality flags associated with the point estimate ('Percent')
    est_status = (
        df[df["characteristic"] == "Percent"][
            ["ref_date", "hsda_name", "age_group", "sex", "indicator", "status"]
        ]
        .rename(columns={"status": "data_quality_flag"})
        .fillna({"data_quality_flag": "Reliable"})
    )

    # 5. Pivot Characteristics from long format into wide analytical columns
    index_cols = [
        "ref_date",
        "cycle_start_year",
        "health_authority",
        "hsda_name",
        "dguid",
        "age_group",
        "sex",
        "indicator",
    ]

    wide_df = df.pivot_table(
        index=index_cols,
        columns="characteristic",
        values="value",
        aggfunc="first",
    ).reset_index()

    wide_df.columns.name = None
    wide_df = wide_df.rename(
        columns={
            "Percent": "prevalence_pct",
            "Low 95% confidence interval, percent": "ci_95_low",
            "High 95% confidence interval, percent": "ci_95_high",
            "Statistically different from the provincial rate": "prov_diff_code",
        }
    )

    # 6. Merge quality flags and add human-readable labels
    clean_df = wide_df.merge(
        est_status,
        on=["ref_date", "hsda_name", "age_group", "sex", "indicator"],
        how="left",
    )
    clean_df["prov_comparison"] = clean_df["prov_diff_code"].map(PROV_DIFF_MAP)
    clean_df["is_suppressed"] = clean_df["prevalence_pct"].isna().astype(int)

    return clean_df


def export_outputs(df: pd.DataFrame) -> None:
    PROCESSED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV, index=False)

    with sqlite3.connect(DB_PATH) as conn:
        df.to_sql("hsda_surveillance", conn, if_exists="replace", index=False)
        conn.execute(
            "CREATE INDEX idx_surveillance_lookup ON hsda_surveillance (indicator, ref_date, hsda_name);"
        )

    print(f"Success! Exported {len(df):,} cleaned rows to:")
    print(f"  - CSV: {PROCESSED_CSV}")
    print(f"  - SQLite DB: {DB_PATH}")


if __name__ == "__main__":
    cleaned_df = load_and_clean(RAW_PATH)
    export_outputs(cleaned_df)
    