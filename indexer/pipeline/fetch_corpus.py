"""On-demand corpus fetcher for the Kubernetes Indexer Job and weekly CronJob.

When `/corpus` is not pre-populated by a fixture ConfigMap or host volume, the Job
downloads the verified public FAST-NUCES policy corpus into an ephemeral `/tmp`
staging directory (`emptyDir`), verifies SHA-256 integrity where pinned, and writes
`_index.json` for `pipeline.run.discover`.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

USER_AGENT = "RAHBAR-indexer-fetcher/1.0 (SE3005 Kubernetes Job; polite sequential fetch)"
PAUSE_SECONDS = 1.5

DEFAULT_SOURCES: list[dict[str, object]] = [
    {
        "name": "Undergraduate Academic Rules (Aug 2023)",
        "url": "http://nu.edu.pk/public/downloads/Academic-Rules-Undergrad-Aug-2023.pdf",
        "file": "undergraduate-academic-rules-aug-2023.pdf",
        "doc_version": "2023-08",
        "superseded": True,
        "sha256": "cddfe1f5e9770132e27d686abd1c2e6742ef4732f0c2f431ed514bc1691d2004",
    },
    {
        "name": "Academic Rules Handbook (Jun 2026)",
        "url": "https://nu.edu.pk/public/downloads/Academic_Rules_Handbook_2026.pdf",
        "file": "academic-rules-handbook-jun-2026.pdf",
        "doc_version": "2026-06",
        "superseded": False,
        "sha256": "4cfee3e191b84aeb9168f17656c7642212ff52b90f2780d028b33c154aa74b62",
    },
    {
        "name": "Prospectus 2026 - Academic Rules and Regulations",
        "url": "https://www.nu.edu.pk/Admissions/ProspectusUpload/Academic Rules and Regulations.pdf",
        "file": "prospectus-2026-academic-rules-and-regulations.pdf",
        "doc_version": "2026",
        "superseded": False,
        "sha256": "a7e7f6896a59eb9413c9e8826e6c4c018ebe52045d10cebfcba92ded10a3174a",
    },
    {
        "name": "Student Handbook (Jun 2026)",
        "url": "https://nu.edu.pk/public/downloads/Student_Handbook_2026.pdf",
        "file": "student-handbook-jun-2026.pdf",
        "doc_version": "2026-06",
        "superseded": False,
        "sha256": "717eb4b8d37e50185ffe952735c08ef19edd16074d547f10ebd22cf23da67c4d",
    },
    {
        "name": "Annual Report 2019-20",
        "url": "https://nu.edu.pk/public/downloads/AnnualReportForm/Annual Report 2019-20.pdf",
        "file": "annual-report-2019-20.pdf",
        "doc_version": "2019-20",
        "superseded": True,
        "sha256": "4d1961e340b13273bb039805ab5fd5e2c7bd0144a5bd5870f2ce4da13becd650",
    },
    {
        "name": "Annual Report 2023-24",
        "url": "https://nu.edu.pk/public/downloads/AnnualReportForm/Annual Report 2023-24.pdf",
        "file": "annual-report-2023-24.pdf",
        "doc_version": "2023-24",
        "superseded": False,
        "sha256": "3c9d89e84af24df4b939f10e32c620a3877b276acea1db52f1aae4098e5c057a",
    },
    {
        "name": "Fee Structure Policy",
        "url": "https://www.nu.edu.pk/Admissions/FeeStructure",
        "file": "fee-structure-policy.html",
        "doc_version": "2026-27",
        "superseded": False,
        "sha256": "ec8872ae77cac7e96e20e6979933f36b00aaeb0ab3f668a2116e521c655e7b90",
    },
    {
        "name": "Faculty Entrepreneurship and Technical Start-ups Policy",
        "url": "https://nu.edu.pk/OricResources/ResearchPolicies/27.pdf",
        "file": "faculty-entrepreneurship-and-technical-start-ups-policy.pdf",
        "doc_version": "2022-05",
        "superseded": False,
        "sha256": "c2d5c7648d1593daf34d5c0596ede476e8984b0551830cc1690017e6e22f1359",
    },
]


def _normalise_url(url: str) -> str:
    return quote(url, safe=":/?&=%#+,;@!$'()*~")


def fetch_to_staging(staging_dir: str) -> Path:
    """Download public FAST-NUCES corpus into `staging_dir` and write `_index.json`."""
    target = Path(staging_dir)
    target.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, connect=15.0),
    ) as client:
        for idx, doc in enumerate(DEFAULT_SOURCES):
            url = _normalise_url(str(doc["url"]))
            filename = str(doc.get("file") or Path(urlsplit(url).path).name)
            dest = target / filename
            if not dest.exists():
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                if idx + 1 < len(DEFAULT_SOURCES):
                    time.sleep(PAUSE_SECONDS)

            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            entries.append(
                {
                    "name": doc["name"],
                    "url": url,
                    "file": filename,
                    "sha256": digest,
                    "expected_sha256": doc.get("sha256", ""),
                    "sha256_match": digest == doc.get("sha256"),
                    "doc_version": doc["doc_version"],
                    "superseded": bool(doc["superseded"]),
                }
            )

    (target / "_index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return target

