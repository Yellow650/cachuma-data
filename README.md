# Cachuma Dashboard Data

Backend data pipeline for the Cachuma Dashboard SwiftUI app.

Version 1 uses only the Santa Barbara County Rainfall and Reservoir Summary PDF:

https://files.countyofsb.org/pwd/hydrology/Rainfall%20Reports/rainfallreport.pdf

## Data Design

Historical data is stored as CSV in `data/history.csv`. CSV is the best fit here because the file is append-only, human-readable, easy to diff in Git, and each daily record is flat.

The app-facing file is JSON at `current.json`, because SwiftUI can consume it directly with `Codable` and it can include nested groups for reservoir, rainfall, source, and units.

## History CSV

Columns:

- `date`
- `capacity_percent`
- `storage_af`
- `elevation_ft`
- `rain_today_in`
- `rain_month_in`
- `rain_water_year_in`
- `last_updated`

The update script replaces the row for a report date if it already exists, so rerunning the workflow on the same day will not create duplicates.

## current.json Schema

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-07-06T16:00:00+00:00",
  "lastUpdated": "2026-07-06T08:00:00-07:00",
  "source": {
    "name": "Santa Barbara County Rainfall and Reservoir Summary",
    "url": "https://files.countyofsb.org/pwd/hydrology/Rainfall%20Reports/rainfallreport.pdf",
    "reportDate": "2026-07-06",
    "waterYear": 2026
  },
  "reservoir": {
    "name": "Cachuma Reservoir",
    "current": {
      "capacityPercent": 92.6,
      "storageAF": 178662,
      "elevationFT": 748.3
    },
    "changeSinceMonthStart": {
      "baselineDate": "2026-07-06",
      "capacityPercent": 0.0,
      "storageAF": 0,
      "elevationFT": 0.0
    },
    "changeSinceWaterYearStart": {
      "baselineDate": "2026-07-06",
      "capacityPercent": 0.0,
      "storageAF": 0,
      "elevationFT": 0.0
    }
  },
  "rainfall": {
    "station": "Cachuma Dam",
    "todayIn": 0.0,
    "monthToDateIn": 0.0,
    "waterYearToDateIn": 33.17
  },
  "units": {
    "capacityPercent": "%",
    "storageAF": "acre-feet",
    "elevationFT": "feet",
    "rainfallIn": "inches"
  }
}
```

The month and water-year change fields are calculated from the first available CSV record in the same calendar month and water year. On the first run, those changes are `0` because the baseline is the newly appended record.

## Running Locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/update_current.py
```

To test against a downloaded PDF:

```sh
.venv/bin/python scripts/update_current.py --pdf /path/to/rainfallreport.pdf
```

GitHub Actions runs once per day at 16:30 UTC, which is 9:30 AM Pacific during daylight saving time.

