#!/usr/bin/env python3
"""Mirror County historical chart PDFs and generate historical.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


OUTPUT_DIR = Path("historical")
MANIFEST_PATH = Path("historical.json")


@dataclass(frozen=True)
class HistoricalDocument:
    id: str
    title: str
    subtitle: str
    kind: str
    source_url: str
    local_path: Path
    page_count: int


DOCUMENTS = [
    HistoricalDocument(
        id="rainfall-cachuma-dam-yearly",
        title="Cachuma Dam Yearly Rainfall",
        subtitle="1953-2024",
        kind="rainfall",
        source_url="https://files.countyofsb.org/pwd/hydrology/historic%20data/rainfall/yearly%20graphs/332graph.pdf",
        local_path=OUTPUT_DIR / "rainfall-cachuma-dam-yearly.pdf",
        page_count=1,
    ),
    HistoricalDocument(
        id="cachuma-storage-history",
        title="Cachuma Reservoir Storage",
        subtitle="1985-2026 and 1959-2026",
        kind="reservoir",
        source_url="https://files.countyofsb.org/pwd/hydrology/Historic%20Data/Reservoirs/Cachuma%20Storage%201960%20to%20Present.pdf",
        local_path=OUTPUT_DIR / "cachuma-storage-history.pdf",
        page_count=2,
    ),
]


def download(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "cachuma-dashboard-data/1.0"})
    with urlopen(request, timeout=45) as response:
        data = response.read()

    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded data from {url} is not a PDF")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "documents": [
            {
                "id": document.id,
                "title": document.title,
                "subtitle": document.subtitle,
                "kind": document.kind,
                "sourceUrl": document.source_url,
                "url": document.local_path.as_posix(),
                "pageCount": document.page_count,
            }
            for document in DOCUMENTS
        ],
    }


def main() -> None:
    for document in DOCUMENTS:
        download(document.source_url, document.local_path)

    MANIFEST_PATH.write_text(json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8")
    print(f"Updated {MANIFEST_PATH} and {len(DOCUMENTS)} historical PDFs")


if __name__ == "__main__":
    main()

