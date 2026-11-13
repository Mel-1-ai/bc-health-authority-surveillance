-- ============================================================================
-- BC Health Authority Population Health Surveillance Queries
-- Database: data/processed/bc_surveillance.db (Table: hsda_surveillance)
-- ============================================================================

-- 1. DATA QUALITY & STATCAN SUPPRESSION AUDIT BY HEALTH AUTHORITY
-- Evaluates survey reliability ('Reliable' vs. 'E' high sampling variability vs. suppressed)
SELECT 
    health_authority,
    data_quality_flag,
    COUNT(*) AS record_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY health_authority), 1) AS pct_of_ha_records
FROM hsda_surveillance
GROUP BY health_authority, data_quality_flag
ORDER BY health_authority, record_count DESC;


-- 2. HIGH-PRIORITY REGIONAL DISPARITIES (LATEST AVAILABLE CYCLE)
-- Flags HSDAs with rates statistically significantly higher than the BC provincial rate
SELECT 
    ref_date,
    health_authority,
    hsda_name,
    indicator,
    sex,
    age_group,
    prevalence_pct,
    ci_95_low,
    ci_95_high,
    data_quality_flag
FROM hsda_surveillance
WHERE ref_date = (SELECT MAX(ref_date) FROM hsda_surveillance)
  AND prov_diff_code = 1
  AND is_suppressed = 0
ORDER BY health_authority, hsda_name, indicator;


-- 3. CYCLE-OVER-CYCLE PREVALENCE CHANGE USING WINDOW FUNCTIONS (BOTH SEXES)
-- Tracks temporal shifts across CCHS cycles for each HSDA and indicator
WITH base_trends AS (
    SELECT 
        health_authority,
        hsda_name,
        indicator,
        age_group,
        ref_date,
        cycle_start_year,
        prevalence_pct,
        LAG(prevalence_pct) OVER (
            PARTITION BY hsda_name, indicator, age_group 
            ORDER BY cycle_start_year
        ) AS prev_cycle_pct,
        data_quality_flag
    FROM hsda_surveillance
    WHERE sex = 'Both sexes'
      AND is_suppressed = 0
)
SELECT 
    health_authority,
    hsda_name,
    indicator,
    age_group,
    ref_date,
    prev_cycle_pct,
    prevalence_pct AS current_cycle_pct,
    ROUND(prevalence_pct - prev_cycle_pct, 2) AS pct_point_change,
    data_quality_flag
FROM base_trends
WHERE prev_cycle_pct IS NOT NULL
ORDER BY ABS(prevalence_pct - prev_cycle_pct) DESC
LIMIT 25;


-- 4. REGIONAL HEALTH AUTHORITY SUMMARY BENCHMARK (LATEST CYCLE, BOTH SEXES)
-- Compares mean HSDA prevalence across BC's four mainland/northern health authorities
SELECT 
    health_authority,
    indicator,
    COUNT(DISTINCT hsda_name) AS reporting_hsdas,
    ROUND(AVG(prevalence_pct), 2) AS mean_prevalence_pct,
    ROUND(MIN(prevalence_pct), 2) AS min_hsda_pct,
    ROUND(MAX(prevalence_pct), 2) AS max_hsda_pct
FROM hsda_surveillance
WHERE ref_date = (SELECT MAX(ref_date) FROM hsda_surveillance)
  AND sex = 'Both sexes'
  AND is_suppressed = 0
GROUP BY health_authority, indicator
ORDER BY indicator, mean_prevalence_pct DESC;