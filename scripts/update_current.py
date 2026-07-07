#!/usr/bin/env python3
"""Update Cachuma Dashboard history.csv and current.json from the County PDF."""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pdfplumber


SOURCE_URL = "https://files.countyofsb.org/pwd/hydrology/Rainfall%20Reports/rainfallreport.pdf"
SOURCE_NAME = "Santa Barbara County Rainfall and Reservoir Summary"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")
CSV_FIELDS = [
    "date",
    "capacity_percent",
    "storage_af",
    "elevation_ft",
    "rain_today_in",
    "rain_month_in",
    "rain_water_year_in",
    "last_updated",
]


@dataclass(frozen=True)
class DailyRecord:
    report_date: date
    capacity_percent: float
    storage_af: int
    elevation_ft: float
    rain_today_in: float
    rain_month_in: float
    rain_water_year_in: float
    last_updated: datetime
    water_year: int


def parse_number(value: str) -> float:
    cleaned = value.replace(",", "").replace("%", "").replace("*", "")
    return float(cleaned)


def download_pdf(url: str) -> Path:
    request = Request(url, headers={"User-Agent": "cachuma-dashboard-data/1.0"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp.write(data)
    temp.close()
    return Path(temp.name)


def page_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def value_in_range(words: list[dict[str, Any]], top: float, x0: float, x1: float) -> str:
    candidates = [
        word
        for word in words
        if abs(word["top"] - top) <= 3 and word["x0"] >= x0 and word["x1"] <= x1
    ]
    if not candidates:
        raise ValueError(f"No PDF value found near top={top}, x={x0}-{x1}")
    return " ".join(word["text"] for word in sorted(candidates, key=lambda word: word["x0"]))


def find_row_top(words: list[dict[str, Any]], first: str, second: str) -> float:
    for word in words:
        if word["text"] != first:
            continue
        row_words = [
            candidate["text"]
            for candidate in words
            if abs(candidate["top"] - word["top"]) <= 3
        ]
        if second in row_words:
            return float(word["top"])
    raise ValueError(f"Could not find PDF row for {first} {second}")


def parse_pdf(pdf_path: Path) -> DailyRecord:
    text = page_text(pdf_path)
    updated_match = re.search(r"Updated\s+8am:\s+(\d{1,2}/\d{1,2}/\d{4})", text)
    water_year_match = re.search(r"Water\s+Year:\s+(\d{4})", text)
    if not updated_match or not water_year_match:
        raise ValueError("Could not find report date and water year in PDF")

    report_date = datetime.strptime(updated_match.group(1), "%m/%d/%Y").date()
    last_updated = datetime.combine(report_date, time(hour=8), tzinfo=LOCAL_TZ)
    water_year = int(water_year_match.group(1))

    with pdfplumber.open(pdf_path) as pdf:
        words = pdf.pages[0].extract_words(x_tolerance=1, y_tolerance=3)

    rainfall_top = find_row_top(words, "Cachuma", "Dam")
    reservoir_top = find_row_top(words, "Cachuma", "Reservoir")

    return DailyRecord(
        report_date=report_date,
        capacity_percent=parse_number(value_in_range(words, reservoir_top, 385, 428)),
        storage_af=round(parse_number(value_in_range(words, reservoir_top, 326, 376))),
        elevation_ft=parse_number(value_in_range(words, reservoir_top, 220, 266)),
        rain_today_in=parse_number(value_in_range(words, rainfall_top, 235, 270)),
        rain_month_in=parse_number(value_in_range(words, rainfall_top, 330, 365)),
        rain_water_year_in=parse_number(value_in_range(words, rainfall_top, 380, 418)),
        last_updated=last_updated,
        water_year=water_year,
    )


def record_to_csv_row(record: DailyRecord) -> dict[str, str]:
    return {
        "date": record.report_date.isoformat(),
        "capacity_percent": f"{record.capacity_percent:.1f}",
        "storage_af": str(record.storage_af),
        "elevation_ft": f"{record.elevation_ft:.2f}",
        "rain_today_in": f"{record.rain_today_in:.2f}",
        "rain_month_in": f"{record.rain_month_in:.2f}",
        "rain_water_year_in": f"{record.rain_water_year_in:.2f}",
        "last_updated": record.last_updated.isoformat(),
    }


def read_history(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_history(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def upsert_history(path: Path, record: DailyRecord) -> list[dict[str, str]]:
    rows = read_history(path)
    current_row = record_to_csv_row(record)
    rows = [row for row in rows if row.get("date") != current_row["date"]]
    rows.append(current_row)
    rows.sort(key=lambda row: row["date"])
    write_history(path, rows)
    return rows


def date_from_row(row: dict[str, str]) -> date:
    return date.fromisoformat(row["date"])


def water_year_start(for_date: date) -> date:
    year = for_date.year if for_date.month >= 9 else for_date.year - 1
    return date(year, 9, 1)


def baseline_row(rows: list[dict[str, str]], current_date: date, period: str) -> dict[str, str]:
    if period == "month":
        candidates = [
            row
            for row in rows
            if date_from_row(row).year == current_date.year
            and date_from_row(row).month == current_date.month
            and date_from_row(row) <= current_date
        ]
    elif period == "water_year":
        start = water_year_start(current_date)
        candidates = [
            row
            for row in rows
            if start <= date_from_row(row) <= current_date
        ]
    else:
        raise ValueError(f"Unknown period: {period}")

    if not candidates:
        raise ValueError(f"No history rows available for {period} baseline")
    return min(candidates, key=lambda row: row["date"])


def change_payload(current: DailyRecord, baseline: dict[str, str]) -> dict[str, Any]:
    return {
        "baselineDate": baseline["date"],
        "capacityPercent": round(current.capacity_percent - float(baseline["capacity_percent"]), 1),
        "storageAF": current.storage_af - round(float(baseline["storage_af"])),
        "elevationFT": round(current.elevation_ft - float(baseline["elevation_ft"]), 2),
    }


def build_current_json(record: DailyRecord, history_rows: list[dict[str, str]]) -> dict[str, Any]:
    month_baseline = baseline_row(history_rows, record.report_date, "month")
    water_year_baseline = baseline_row(history_rows, record.report_date, "water_year")

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lastUpdated": record.last_updated.isoformat(),
        "source": {
            "name": SOURCE_NAME,
            "url": SOURCE_URL,
            "reportDate": record.report_date.isoformat(),
            "waterYear": record.water_year,
        },
        "reservoir": {
            "name": "Cachuma Reservoir",
            "current": {
                "capacityPercent": record.capacity_percent,
                "storageAF": record.storage_af,
                "elevationFT": record.elevation_ft,
            },
            "changeSinceMonthStart": change_payload(record, month_baseline),
            "changeSinceWaterYearStart": change_payload(record, water_year_baseline),
        },
        "rainfall": {
            "station": "Cachuma Dam",
            "todayIn": record.rain_today_in,
            "monthToDateIn": record.rain_month_in,
            "waterYearToDateIn": record.rain_water_year_in,
        },
        "units": {
            "capacityPercent": "%",
            "storageAF": "acre-feet",
            "elevationFT": "feet",
            "rainfallIn": "inches",
        },
    }


def write_current_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, help="Use a local County PDF instead of downloading it.")
    parser.add_argument("--history", type=Path, default=Path("data/history.csv"))
    parser.add_argument("--current-json", type=Path, default=Path("current.json"))
    args = parser.parse_args()

    pdf_path = args.pdf or download_pdf(SOURCE_URL)
    record = parse_pdf(pdf_path)
    history_rows = upsert_history(args.history, record)
    current_payload = build_current_json(record, history_rows)
    write_current_json(args.current_json, current_payload)

    print(f"Updated {args.history} and {args.current_json} for {record.report_date.isoformat()}")


if __name__ == "__main__":
    main()

