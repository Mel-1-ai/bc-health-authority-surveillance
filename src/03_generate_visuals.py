import sqlite3
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

DB_PATH = Path("data/processed/bc_surveillance.db")
FIG_DIR = Path("outputs/figures")

# Consistent color palette for BC Regional Health Authorities
HA_PALETTE = {
    "Northern Health": "#D95F02",         # Burnt orange
    "Interior Health": "#7570B3",         # Slate purple
    "Fraser Health": "#1B9E77",           # Teal green
    "Vancouver Coastal Health": "#2B8CBE" # Coastal blue
}

plt.rcParams.update({
    "font.sans-serif": "DejaVu Sans",
    "axes.edgecolor": "#CCCCCC",
    "axes.linewidth": 0.8,
})


def load_surveillance_data() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM hsda_surveillance;", conn)


def filter_total_age(df: pd.DataFrame) -> pd.DataFrame:
    """Select the 'Total, ...' age group for each indicator, or fall back to mean across ages."""
    has_total = df["age_group"].str.contains("Total", case=False, na=False)
    if has_total.any():
        return df[has_total].copy()
    return df.copy()


def plot_chronic_risk_gradient(df: pd.DataFrame) -> None:
    """Figure 1: Regional Chronic Risk Gradient with 95% Confidence Intervals."""
    latest_cycle = df["ref_date"].max()
    indicators = [
        "Body mass index, adjusted self-reported, adult (18 years and over), obese",
        "Current smoker, daily",
    ]
    short_titles = {
        indicators[0]: "Adult Obesity (18+ years)",
        indicators[1]: "Daily Smoking",
    }

    base = df[
        (df["ref_date"] == latest_cycle)
        & (df["sex"] == "Both sexes")
        & (df["indicator"].isin(indicators))
        & (df["is_suppressed"] == 0)
    ].copy()

    # Keep 'Total, ...' age row per indicator/HSDA; if absent for an indicator, aggregate across age groups
    pieces = []
    for ind in indicators:
        ind_sub = base[base["indicator"] == ind]
        tot = ind_sub[ind_sub["age_group"].str.contains("Total", case=False, na=False)]
        if not tot.empty:
            pieces.append(tot)
        else:
            agg_ind = (
                ind_sub.groupby(["health_authority", "hsda_name", "indicator"], as_index=False)
                .agg({
                    "prevalence_pct": "mean",
                    "ci_95_low": "mean",
                    "ci_95_high": "mean",
                    "data_quality_flag": "first",
                })
            )
            pieces.append(agg_ind)
    sub = pd.concat(pieces, ignore_index=True)

    # Order HSDAs by obesity prevalence so the north-south gradient is clear
    order_df = (
        sub[sub["indicator"] == indicators[0]]
        .dropna(subset=["prevalence_pct"])
        .sort_values("prevalence_pct", ascending=True)
    )
    hsda_order = order_df["hsda_name"].tolist()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    fig.suptitle(
        f"BC Regional Chronic Risk Gradient by Health Service Delivery Area ({latest_cycle})",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    for ax, ind in zip(axes, indicators):
        ind_df = (
            sub[sub["indicator"] == ind]
            .set_index("hsda_name")
            .reindex(hsda_order)
            .reset_index()
        )

        for _, row in ind_df.iterrows():
            if pd.isna(row["prevalence_pct"]):
                continue
            color = HA_PALETTE.get(row["health_authority"], "#555555")
            y_pos = row["hsda_name"]
            est = row["prevalence_pct"]
            low_ci = row["ci_95_low"] if pd.notna(row["ci_95_low"]) else est
            high_ci = row["ci_95_high"] if pd.notna(row["ci_95_high"]) else est

            ax.errorbar(
                est,
                y_pos,
                xerr=[[est - low_ci], [high_ci - est]],
                fmt="o",
                color=color,
                ecolor=color,
                elinewidth=2,
                capsize=4,
                markersize=8,
            )
            flag_txt = " (E)" if row["data_quality_flag"] == "E" else ""
            ax.text(
                high_ci + 0.8,
                y_pos,
                f"{est:.1f}%{flag_txt}",
                va="center",
                fontsize=9,
                color="#333333",
            )

        max_x = ind_df["ci_95_high"].fillna(ind_df["prevalence_pct"]).max()
        ax.set_xlim(0, (max_x if pd.notna(max_x) else 50) + 8)
        ax.set_title(short_titles[ind], fontsize=12, fontweight="bold", pad=10)
        ax.set_xlabel("Prevalence (%) with 95% Confidence Interval", fontsize=10)
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=9, label=ha)
        for ha, c in HA_PALETTE.items()
    ]
    fig.legend(
        handles=handles,
        title="Regional Health Authority",
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )

    fig.text(
        0.01,
        -0.05,
        "Source: Statistics Canada CCHS. Note: (E) indicates high sampling variability; interpret with caution.",
        fontsize=8.5,
        color="#555555",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 0.94])
    out_path = FIG_DIR / "fig1_chronic_risk_gradient.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def plot_primary_care_vs_health(df: pd.DataFrame) -> None:
    """Figure 2: Primary Care Attachment vs. Self-Reported General Health Across Cycles."""
    target_inds = [
        "Has a regular healthcare provider",
        "Perceived health, very good or excellent",
    ]
    sub = df[
        (df["sex"] == "Both sexes")
        & (df["indicator"].isin(target_inds))
        & (df["is_suppressed"] == 0)
    ].copy()

    # Prefer 'Total, ...' age group where present
    tot_mask = sub["age_group"].str.contains("Total", case=False, na=False)
    if tot_mask.any():
        sub = sub[tot_mask]

    agg = (
        sub.groupby(["ref_date", "cycle_start_year", "health_authority", "indicator"], as_index=False)
        ["prevalence_pct"]
        .mean()
        .sort_values("cycle_start_year")
    )

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=False)
    fig.suptitle(
        "Primary Care Attachment & Perceived General Health Trends by BC Health Authority",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    titles = {
        target_inds[0]: "Has a Regular Healthcare Provider (%)",
        target_inds[1]: "Perceived Health: Very Good or Excellent (%)",
    }

    for ax, ind in zip(axes, target_inds):
        ind_df = agg[agg["indicator"] == ind]
        for ha, color in HA_PALETTE.items():
            ha_df = ind_df[ind_df["health_authority"] == ha]
            ax.plot(
                ha_df["ref_date"],
                ha_df["prevalence_pct"],
                marker="o",
                linewidth=2.3,
                markersize=7,
                color=color,
                label=ha,
            )

        ax.set_title(titles[ind], fontsize=11.5, fontweight="bold", pad=10)
        ax.set_xlabel("CCHS Survey Cycle", fontsize=10)
        ax.set_ylabel("Mean HSDA Prevalence (%)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="x", rotation=20)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        title="Regional Health Authority",
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, -0.03),
    )

    fig.text(
        0.01,
        -0.06,
        "Source: Statistics Canada CCHS (Both sexes). Points represent mean HSDA prevalence per Health Authority.",
        fontsize=8.5,
        color="#555555",
    )

    plt.tight_layout(rect=[0, 0.05, 1, 0.93])
    out_path = FIG_DIR / "fig2_primary_care_vs_health.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def plot_surveillance_data_equity(df: pd.DataFrame) -> None:
    """Figure 3: Small-Area CCHS Data Quality & Suppression Audit by Health Authority."""
    counts = (
        df.groupby(["health_authority", "data_quality_flag"])
        .size()
        .unstack(fill_value=0)
    )

    for col in ["Reliable", "E", "F"]:
        if col not in counts.columns:
            counts[col] = 0
    counts = counts[["Reliable", "E", "F"]]

    pcts = counts.div(counts.sum(axis=1), axis=0) * 100
    pcts = pcts.sort_values("Reliable", ascending=True)

    fig, ax = plt.subplots(figsize=(10.5, 5))
    flag_colors = {
        "Reliable": "#2B8CBE",
        "E": "#FDB863",
        "F": "#E66101",
    }
    flag_labels = {
        "Reliable": "Reliable Estimate (Unflagged)",
        "E": "Flag 'E': High Sampling Variability (Use with Caution)",
        "F": "Flag 'F': Suppressed (Unreliable / Privacy Protection)",
    }

    left_bottom = pd.Series(0.0, index=pcts.index)
    for flag in ["Reliable", "E", "F"]:
        bars = ax.barh(
            pcts.index,
            pcts[flag],
            left=left_bottom,
            color=flag_colors[flag],
            edgecolor="white",
            height=0.58,
            label=flag_labels[flag],
        )
        for bar, val in zip(bars, pcts[flag]):
            if val >= 5.0:
                text_color = "white" if flag != "E" else "#222222"
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=9.5,
                    fontweight="bold",
                    color=text_color,
                )
        left_bottom += pcts[flag]

    ax.set_title(
        "The Rural Surveillance Blind Spot: CCHS Estimate Reliability by BC Health Authority",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.set_xlabel("Percentage of Total HSDA Sub-Population Records (%)", fontsize=10)
    ax.set_xlim(0, 100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=1,
        frameon=False,
        fontsize=9.5,
    )

    fig.text(
        0.01,
        -0.25,
        "Source: Statistics Canada CCHS extract (n = 4,241 HSDA records across all cycles, age groups, and sexes).",
        fontsize=8.5,
        color="#555555",
    )

    plt.tight_layout()
    out_path = FIG_DIR / "fig3_surveillance_data_equity.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    surveillance_df = load_surveillance_data()
    plot_chronic_risk_gradient(surveillance_df)
    plot_primary_care_vs_health(surveillance_df)
    plot_surveillance_data_equity(surveillance_df)
    print("\nAll Milestone 4 epidemiological figures generated successfully!")