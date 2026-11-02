"""Tests for evaluation metrics: recall@k, citation validity, summarise, and gate."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.run_eval import citation_validity, gate, recall_at_k, summarise


def test_recall_at_k_exact_match() -> None:
    relevant = [{"source": "rules.pdf", "section": "1.21"}]
    retrieved = [
        {"source": "rules.pdf", "section": "1.21 Attendance", "score": 0.95},
        {"source": "other.pdf", "section": "2.1", "score": 0.80},
    ]
    # Found in top 1 -> recall@3 and recall@5 should be 1.0
    assert recall_at_k(relevant, retrieved, 3) == 1.0
    assert recall_at_k(relevant, retrieved, 1) == 1.0


def test_recall_at_k_miss() -> None:
    relevant = [{"source": "rules.pdf", "section": "5.4"}]
    retrieved = [
        {"source": "different.pdf", "section": "1.1", "score": 0.90},
    ]
    assert recall_at_k(relevant, retrieved, 3) == 0.0


def test_citation_validity_all_valid() -> None:
    resp = {
        "citations": [{"source": "rules.pdf", "section": "1.21"}],
        "retrieved": [{"source": "rules.pdf", "section": "1.21", "score": 0.9}],
    }
    assert citation_validity(resp) == 1.0


def test_citation_validity_hallucinated() -> None:
    resp = {
        "citations": [
            {"source": "rules.pdf", "section": "1.21"},
            {"source": "hallucinated.pdf", "section": "9.9"},
        ],
        "retrieved": [{"source": "rules.pdf", "section": "1.21", "score": 0.9}],
    }
    assert citation_validity(resp) == 0.5


def test_gate_pass_and_failure() -> None:
    good_results = {
        "recall@5": 0.88,
        "citation_validity": 1.0,
        "abstention_correctness": 1.0,
    }
    baseline = {"recall@5": 0.85}
    assert gate(good_results, baseline) == []

    bad_results = {
        "recall@5": 0.70,  # drop > 0.05
        "citation_validity": 0.80,  # < 0.95
        "abstention_correctness": 0.90,  # < 1.0
    }
    failures = gate(bad_results, baseline)
    assert len(failures) == 3
