# ============================================================
# NAV CANADA — DAATS Phase 1 (PRJ02358)
# Sensor Data Quality Analysis: Consecutive Null Detection
# Author: Shadab
# Data: 181 airport weather sites | Nov 2020 – Oct 2021
# ============================================================

import pandas as pd
import warnings
warnings.filterwarnings("ignore")


# ============================================================
# STEP 0A: MySQL CONNECTION — Fetch Raw Data
# ============================================================

import mysql.connector

# Connect to MySQL database
conn = mysql.connector.connect(
    host="your_host",        # e.g. "localhost"
    user="your_username",    # e.g. "root"
    password="your_password",
    database="your_database" # e.g. "navcanada_weather"
)

# Pull all raw weather records into a DataFrame
query = """
    SELECT site_id, pressure, temperature, rel_humidity, last_updt_tmsp
    FROM your_table_name
"""
data = pd.read_sql(query, conn)
conn.close()

print(f"Raw data loaded: {data.shape[0]:,} rows, {data.shape[1]} columns")


# ============================================================
# STEP 0B: DATA CLEANING
# ============================================================

# Drop auto-generated index columns left over from previous CSV saves
unnamed_cols = [c for c in data.columns if "Unnamed" in c]
if unnamed_cols:
    data.drop(columns=unnamed_cols, inplace=True)

# Remove known bad/test site that does not represent a real station
data = data[data['site_id'] != '2YYC']

# Parse timestamp so time-based operations work correctly
data['last_updt_tmsp'] = pd.to_datetime(data['last_updt_tmsp'])

# Sort so consecutive null detection works in time order per site
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)

# Remove fully duplicate rows introduced by data collection overlaps
data = data.drop_duplicates()

# Reset index after sorting and deduplication
data = data.reset_index(drop=True)

# Mark all original rows as non-missing
# (missing communication rows will be added separately)
data['missing'] = 'Non missing'

# Load missing communication rows (timestamps where station went silent)
# These were identified separately and added to ensure time continuity
missing_communication = pd.read_csv("missing_communication.csv")

# Append missing communication rows and re-sort
data = pd.concat([data, missing_communication], ignore_index=True)
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)
data = data.reset_index(drop=True)

# Assign sensor platform type based on site_id
# HWOS+AWOS: dual-sensor sites; ATC-only: no official obs; HWOS: standard
HWOS_AWOS_SITES = {
    'CYAB', 'CYAY', 'СУСУ', 'CYDB', 'CYEK', 'CYFC', 'CYHK', 'CYHU', 'CYIO',
    'CYKE', 'CYLL', 'CYOJ', 'CYOO', 'CYPL', 'CYQF', 'CYOG', 'CYOL', 'CYQT',
    'CYRQ', 'CYTE', 'CYTZ', 'CYUX', 'CYVM', 'CYVO', 'CYVT', 'CYWK', 'CYXH',
    'CYXP', 'CYYB', 'CYYD', 'CYYO'
}
ATC_ONLY_SITES = {'CYAV', 'CYHC', 'CYJN', 'CYNJ', 'СУРК', 'CYRC', 'СУтР', 'CZBB', 'V26R', 'VHHA'}

def assign_sensor(site_id):
    if site_id in HWOS_AWOS_SITES:
        return 'HWOS+AWOS (uses AWOS sensors)'
    elif site_id in ATC_ONLY_SITES:
        return 'ATC-only (weather site with no official observations)'
    else:
        return 'HWOS'

data['sensor'] = data['site_id'].apply(assign_sensor)

# Save the cleaned dataset — this becomes the input for all analysis steps
data.to_csv("final_clean_data.csv", index=False)
print(f"Cleaned data saved: {data.shape[0]:,} rows")


# ============================================================
# SHARED FUNCTIONS
# Used across Steps 1–3 and Step 5
# ============================================================

def get_cons_all_sites(df, column):
    """
    Finds all consecutive null windows for a given sensor column.
    A 'consecutive' window is 2+ back-to-back null readings at the same site.
    Returns only the rows that are part of such a window.
    """
    df['last_updt_tmsp'] = pd.to_datetime(df['last_updt_tmsp'])
    result = pd.DataFrame(columns=df.columns)

    for site_id in df['site_id'].unique():
        site_df = df[df['site_id'] == site_id].reset_index(drop=True)

        # Detect where nulls start (transition from non-null to null)
        null_indices = site_df[column].isnull().astype(int).diff()
        consecutive_starts = null_indices[null_indices == 1].index - 1

        for idx in consecutive_starts:
            if idx + 1 < len(site_df):
                result = pd.concat([result, site_df.loc[[idx, idx + 1]]], ignore_index=True)

    return result.drop_duplicates()


def create_events_with_count(df):
    """
    Groups consecutive null rows into numbered events per site.
    A new event begins whenever the time gap between rows exceeds 1 minute.
    Also adds event_count: how many rows belong to each event.
    """
    df['last_updt_tmsp'] = pd.to_datetime(df['last_updt_tmsp'])
    events = []

    for site_id in df['site_id'].unique():
        site_df = df[df['site_id'] == site_id].sort_values(by='last_updt_tmsp')

        # Any gap > 60 seconds marks the start of a new event
        time_diff = site_df['last_updt_tmsp'].diff().dt.total_seconds()
        new_event_mask = time_diff.fillna(0) > 60
        site_df['event'] = (new_event_mask.cumsum() + 1).astype(int)
        site_df['event_count'] = site_df.groupby('event')['last_updt_tmsp'].transform('size')

        events.append(site_df)

    return pd.concat(events)


def categorize_sensor_failures(df):
    """
    Classifies each row based on which sensors are missing:
    - All Missing:      pressure + temperature + rel_humidity all null
    - T & RH Missing:   temperature and rel_humidity null, pressure available
    - T or RH Missing:  only one of temperature/rel_humidity null
    - Pressure Missing: only pressure null
    """
    p_null = df['pressure'].isnull()
    t_null = df['temperature'].isnull()
    rh_null = df['rel_humidity'].isnull()
    p_ok = df['pressure'].notnull()
    t_ok = df['temperature'].notnull()
    rh_ok = df['rel_humidity'].notnull()

    df['Category'] = ''
    df.loc[p_null & t_ok & rh_ok,                          'Category'] = 'Pressure Missing'
    df.loc[p_ok   & t_null & rh_null,                      'Category'] = 'T & RH Missing'
    df.loc[(t_null & rh_ok & p_ok) | (t_ok & rh_null & p_ok), 'Category'] = 'T or RH Missing'
    df.loc[t_null & p_null & rh_null,                      'Category'] = 'All Missing'

    return df


# ============================================================
# STEP 1: Temperature — Consecutive Null Detection
# ============================================================

data = pd.read_csv("final_clean_data.csv")
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)

# Extract all rows that are part of a consecutive temperature null window
temp_consecutive = get_cons_all_sites(data, "temperature")
temp_consecutive.drop_duplicates(inplace=True)
temp_consecutive.to_csv("temperature_consecutive.csv", index=False)

print(f"Temperature consecutive nulls: {len(temp_consecutive):,} rows")


# ============================================================
# STEP 2: Pressure — Consecutive Null Detection
# Processed in 10M-row chunks due to dataset size (~80M rows)
# ============================================================

data = pd.read_csv("final_clean_data.csv")
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)
data = data.reset_index(drop=True)

# Split into chunks of 10M rows to avoid memory issues
CHUNK_SIZE = 10_000_000
chunks = [data.iloc[i:i + CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]

pressure_parts = [get_cons_all_sites(chunk, "pressure") for chunk in chunks]
pressure_consecutive = pd.concat(pressure_parts).drop_duplicates()
pressure_consecutive.to_csv("pressure_consecutive.csv", index=False)

print(f"Pressure consecutive nulls: {len(pressure_consecutive):,} rows")


# ============================================================
# STEP 3: Humidity — Consecutive Null Detection
# Also extracts missing communication rows for use in Step 5
# ============================================================

data = pd.read_csv("final_clean_data.csv")
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)

# Save missing communication rows separately — used to merge into events later
missing_communication = data[data["missing"] == "Missing Communication"]
missing_communication.to_csv("missing_communication.csv", index=False)

humidity_consecutive = get_cons_all_sites(data, "rel_humidity")
humidity_consecutive.drop_duplicates(inplace=True)
humidity_consecutive.to_csv("rel_humid_consecutive.csv", index=False)

print(f"Humidity consecutive nulls: {len(humidity_consecutive):,} rows")


# ============================================================
# STEP 4: Non-Consecutive Null Detection
# Finds isolated (single-minute) null readings not part of any
# consecutive window — a separate pattern from sustained outages
# ============================================================

data = pd.read_csv("total_data.csv")

# Clean up unnamed index columns and bad site
unnamed_cols = [c for c in data.columns if "Unnamed" in c]
data.drop(columns=unnamed_cols, inplace=True)
data = data[data['site_id'] != '2YYC']
data.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)
data = data.drop_duplicates().reset_index(drop=True)

def get_non_consecutive_nulls(df, column):
    """
    Finds isolated single-minute null readings (time_recover == 1 min).
    These are NOT part of a sustained consecutive window.
    """
    df['last_updt_tmsp'] = pd.to_datetime(df['last_updt_tmsp'])
    result = pd.DataFrame()

    for site_id in df['site_id'].unique():
        site_df = df[df['site_id'] == site_id]
        null_df = site_df[site_df[column].isnull()].copy()
        null_df['time_recover'] = null_df['last_updt_tmsp'].diff().dt.total_seconds().div(60)
        # Keep only 1-minute gaps (isolated nulls) or the first null in a site
        isolated = null_df[(null_df['time_recover'] == 1) | (null_df['time_recover'].isnull())]
        result = pd.concat([result, isolated])

    return result

# Get non-consecutive nulls for each sensor
temp_non_con   = get_non_consecutive_nulls(data, "temperature")
pres_non_con   = pd.read_csv("pressure24.csv")   # pre-computed for pressure
humid_non_con  = pd.read_csv("humidity24.csv")    # pre-computed for humidity

temp_non_con.to_csv("temperature24.csv", index=False)

# Combine all three sensors and deduplicate
all_non_con = pd.concat([temp_non_con, pres_non_con, humid_non_con])
all_non_con = all_non_con.drop_duplicates().reset_index(drop=True)
all_non_con.drop(columns=["time_recover"], inplace=True)
all_non_con.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)

all_non_con.to_csv("consecative_null_values.csv", index=False)

# Find rows in the full dataset that are NOT in any consecutive window
# These are the truly isolated single-point failures
result_timestamps = pd.read_csv("consecative_null_values.csv")
result_timestamps['last_updt_tmsp'] = pd.to_datetime(result_timestamps['last_updt_tmsp'])
data['last_updt_tmsp'] = pd.to_datetime(data['last_updt_tmsp'])

non_con_only = (
    data.merge(result_timestamps, how='left', indicator=True)
    .loc[lambda x: x['_merge'] == 'left_only']
    .drop(columns='_merge')
)

# Keep only rows with at least one null sensor reading
null_rows = non_con_only[
    non_con_only['temperature'].isnull() |
    non_con_only['pressure'].isnull() |
    non_con_only['rel_humidity'].isnull()
]

# Filter bad site and assign sensor type
null_rows = null_rows[null_rows['site_id'] != '2YYC'].copy()
null_rows['sensor'] = null_rows['site_id'].apply(assign_sensor)
null_rows.sort_values(by=["site_id", "last_updt_tmsp"], inplace=True)

null_rows.to_csv("all_null_final_final.csv", index=False)
print(f"Non-consecutive null rows: {len(null_rows):,}")

# Find rows in all_null that are not already captured in the merged event dataset
all_null = pd.read_csv("all_null_final_final.csv")
merged_events = pd.read_csv("merged111.csv")

all_null['last_updt_tmsp'] = pd.to_datetime(all_null['last_updt_tmsp'])
merged_events['last_updt_tmsp'] = pd.to_datetime(merged_events['last_updt_tmsp'])

# Drop extra columns from merged_events before comparison
merged_events_clean = merged_events.drop(
    columns=["time_diff", "event", "event_duration_in_min", "category"],
    errors='ignore'
)

remaining_nulls = (
    all_null.merge(merged_events_clean, indicator=True, how='outer')
    .loc[lambda x: x['_merge'] == 'left_only']
    .drop(columns='_merge')
)

remaining_nulls.to_csv("all_null29.csv", index=False)
print(f"Remaining uncategorized nulls: {len(remaining_nulls):,}")


# ============================================================
# STEP 5: Merge Consecutive Nulls with Missing Communication
# Groups rows into events and classifies sensor failure type
# ============================================================

miss = pd.read_csv("missing_communication.csv")

def process_sensor_events(consecutive_csv, miss_df, drop_sensor_col=True):
    """
    Full pipeline for one sensor:
    1. Load consecutive null rows
    2. Merge with missing communication timestamps
    3. Group into events, drop single-row events (not real outages)
    4. Re-group to get final clean events
    5. Categorize sensor failure type
    6. Assign sensor platform type
    """
    df = pd.read_csv(consecutive_csv)

    if drop_sensor_col and 'sensor' in df.columns:
        df.drop(columns=['sensor'], inplace=True)

    # Combine consecutive nulls with missing communication rows
    combined = pd.concat([df, miss_df], ignore_index=True)

    # First pass: create events and remove single-row events
    # (single rows are noise — real outages have 2+ consecutive minutes)
    combined = create_events_with_count(combined)
    combined = combined[combined['event_count'] != 1]
    combined.drop(columns=['event', 'event_count'], inplace=True)

    # Second pass: re-group after removing noise to get clean event numbers
    combined = create_events_with_count(combined)
    combined['missing'] = combined['missing'].fillna('Non missing')

    # Classify what is missing per row
    combined = categorize_sensor_failures(combined)

    # Assign sensor platform type
    combined['sensor'] = combined['site_id'].apply(assign_sensor)

    return combined


# --- Temperature Events ---
temp_df = process_sensor_events("temperature_consecutive.csv", miss)
temp_df.drop(columns=['Category2'], errors='ignore', inplace=True)
temp_df.to_csv("temperature_missing_timestamp_cosecutive.csv", index=False)
temp_df.to_csv("temperature_con_missing.csv", index=False)
print(f"Temperature events: {temp_df['event'].nunique():,}")

# --- Pressure Events ---
pressure_df = process_sensor_events("pressure_consecutive.csv", miss, drop_sensor_col=False)
pressure_df.drop(columns=['sensor', 'Category2'], errors='ignore', inplace=True)
pressure_df = pressure_df.reset_index(drop=True)
pressure_df.to_csv("pressure_all_cons_missing.csv", index=False)
print(f"Pressure events: {pressure_df['event'].nunique():,}")

# --- Humidity Events ---
humid_df = process_sensor_events("pressure_consecutive.csv", miss, drop_sensor_col=False)
humid_df.drop(columns=['Category2'], errors='ignore', inplace=True)
humid_df.to_csv("humid_event_missing_tmsp.csv", index=False)
humid_df.to_csv("humid_all_con_missing.csv", index=False)
print(f"Humidity events: {humid_df['event'].nunique():,}")


# ============================================================
# STEP 6: Find Rows in Full Data NOT in Any Consecutive Group
# These are the rows with nulls that were never part of an event
# ============================================================

# Load all three processed consecutive datasets
temp  = pd.read_csv("temperature_con_missing.csv")
pres  = pd.read_csv("pressure_all_cons_missing.csv")
humid = pd.read_csv("humid_all_con_missing.csv")

# Fix inconsistent missing label if present
humid['missing'] = humid['missing'].fillna('Non missing')

# Combine all consecutive null rows into one dataset and deduplicate
full_con = pd.concat([temp, pres, humid], ignore_index=True)
full_con = full_con.drop_duplicates(subset=[
    "site_id", "pressure", "temperature", "rel_humidity",
    "last_updt_tmsp", "missing", "event", "event_count", "Category", "sensor"
])

# Free memory before the large merge
del temp, pres, humid

# Save the merged consecutive dataset
full_con.to_csv("merged_full_cons.csv", index=False)

# Load the full clean dataset and find rows not in any consecutive group
# Done in chunks to handle the ~80M row dataset without memory overflow
full_data = pd.read_csv("final_clean_data.csv")
full_con_reloaded = pd.read_csv("merged_full_cons.csv")

MERGE_CHUNK_SIZE = 10_000
chunks = [full_data.iloc[i:i + MERGE_CHUNK_SIZE] for i in range(0, len(full_data), MERGE_CHUNK_SIZE)]

non_consecutive_rows = []
for chunk in chunks:
    merged_chunk = chunk.merge(full_con_reloaded, how='left', indicator=True)
    not_in_events = merged_chunk[merged_chunk['_merge'] == 'left_only'].drop(columns='_merge')
    non_consecutive_rows.append(not_in_events)

# These rows had nulls but were never captured in any consecutive event window
remaining = pd.concat(non_consecutive_rows, ignore_index=True)
print(f"Rows in full data not in any consecutive event: {len(remaining):,}")
