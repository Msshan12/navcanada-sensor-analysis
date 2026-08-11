# NAV CANADA — Sensor Data Quality Analysis

**End-to-end Python pipeline to detect and classify weather sensor failures across 188 Canadian airport stations from 80M+ records.**

Built as part of the DAATS Phase 1 project (PRJ02358) for NAV CANADA.

---

## Project Overview

Airport weather observation stations (HWOS/AWOS) record atmospheric data — temperature, pressure, and relative humidity — every minute. This project analyzes over **80 million records** collected from **188 sites** between November 2020 and October 2021 to:

- Detect **consecutive null windows** (sustained sensor outages)
- Identify **isolated single-minute null readings** (transient glitches)
- Classify failures by **sensor type and failure category**
- Merge findings with **missing communication timestamps** (station went silent entirely)
- Deliver insights through **Power BI dashboards** and formal client reports

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3 | Core data processing |
| Pandas | Data manipulation at scale |
| MySQL | Raw data source |
| mysql-connector-python | MySQL to Python connection |
| Power BI | Dashboard and visualization |
| Microsoft Word | Client report delivery |

---

## Key Findings

- **5.88 million** null records identified across all sensors
- **88%** of failures caused by **missing communication** (station went completely silent), not hardware faults
- **CYVT** had the most severe outage — a single event lasting **447,236 minutes (~310 days)**
- **CYKO** had the most frequent failures — **1,046 separate events**
- **188 unique sites** analyzed across Canada

### Failure Categories

| Category | Records | % of Total |
|---|---|---|
| All Missing | 5,166,448 | 87.8% |
| Pressure Missing | 425,458 | 7.2% |
| T & RH Missing | 252,337 | 4.3% |
| T or RH Missing | 38,969 | 0.7% |

---

## Project Structure

```
navcanada-sensor-analysis/
├── src/
│   └── pipeline.py          # Full end-to-end pipeline
├── data/
│   └── sample/              # Sample CSVs (100 rows each for demo)
│       ├── temperature_consecutive_sample.csv
│       ├── pressure_consecutive_sample.csv
│       └── humidity_consecutive_sample.csv
├── outputs/                 # Generated CSVs (gitignored — too large)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Pipeline Steps

```
MySQL Database
     │
     ▼
Step 0A  →  Connect to MySQL, fetch raw weather records
Step 0B  →  Data Cleaning (remove duplicates, bad sites, parse timestamps,
            assign sensor types, append missing communication rows)
     │
     ▼
Step 1   →  Temperature: detect consecutive null windows
Step 2   →  Pressure: detect consecutive null windows (chunked, 10M rows)
Step 3   →  Humidity: detect consecutive null windows
     │
     ▼
Step 4   →  Non-consecutive null detection (isolated single-minute gaps)
     │
     ▼
Step 5   →  Merge consecutive nulls with missing communication events,
            group into numbered events, classify sensor failure category
     │
     ▼
Step 6   →  Find rows in full dataset not captured in any event group
     │
     ▼
Output CSVs  →  Power BI Dashboards  →  Client Reports (NAV CANADA)
```

---

## How to Run

### 1. Clone the repository
```bash
git clone https://github.com/shan12/navcanada-sensor-analysis.git
cd navcanada-sensor-analysis
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure MySQL connection
Open `src/pipeline.py` and update the connection block:
```python
conn = mysql.connector.connect(
    host="your_host",
    user="your_username",
    password="your_password",
    database="your_database"
)
```

### 4. Run the pipeline
```bash
python src/pipeline.py
```

> **Note:** The full dataset is ~80M rows and not included in this repo due to size. Sample CSVs are provided in `data/sample/` for reference.

---

## Output Files

| File | Description |
|---|---|
| `final_clean_data.csv` | Cleaned dataset with sensor types and missing labels |
| `temperature_consecutive.csv` | Rows part of consecutive temperature null windows |
| `pressure_consecutive.csv` | Rows part of consecutive pressure null windows |
| `rel_humid_consecutive.csv` | Rows part of consecutive humidity null windows |
| `temperature_missing_timestamp_cosecutive.csv` | Temperature events merged with missing comm. |
| `pressure_all_cons_missing.csv` | Pressure events merged with missing comm. |
| `humid_all_con_missing.csv` | Humidity events merged with missing comm. |
| `merged_full_cons.csv` | All three sensors combined, deduplicated |
| `all_null_final_final.csv` | All isolated (non-consecutive) null rows |

---

## Sensor Types

| Type | Description |
|---|---|
| HWOS | Standard automated weather observation system |
| HWOS+AWOS | Dual-sensor sites using AWOS sensors |
| ATC-only | Air traffic control sites with no official observations |

---

## Author

**Shadab** — [GitHub](https://github.com/shan12)
