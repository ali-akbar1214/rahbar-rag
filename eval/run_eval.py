#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _match_section(expected_sec: str, actual_sec: str) -> bool:
    """Check section match using prefix, substring, or clause numbering."""
    exp = expected_sec.lower().strip()
    act = actual_sec.lower().strip()
    if exp in act or act in exp:
        return True
    exp_tokens = set(exp.split())
    act_tokens = set(act.split())
    return len(exp_tokens.intersection(act_tokens)) > 0


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions).
    """
    if not relevant:
        return None

    top_k = retrieved[:k]
    matched = 0

    for rel in relevant:
        rel_source = rel.get("source", "").lower()
        rel_sec = rel.get("section", "").lower()
        found = False
        for ret in top_k:
            ret_source = ret.get("source", "").lower()
            ret_sec = ret.get("section", "").lower()
            if rel_source in ret_source or ret_source in rel_source:
                if not rel_sec or _match_section(rel_sec, ret_sec):
                    found = True
                    break
        if found:
            matched += 1

    return matched / len(relevant)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations.
    """
    citations = response.get("citations") or []
    if not citations:
        return None

    retrieved = response.get("retrieved") or []
    retrieved_sources = {r.get("source", "").lower() for r in retrieved}

    valid_count = 0
    for c in citations:
        c_source = c.get("source", "").lower()
        if any(c_source in rs or rs in c_source for rs in retrieved_sources):
            valid_count += 1

    return valid_count / len(citations)


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json.
    """
    recalls_3: list[float] = []
    recalls_5: list[float] = []
    citations: list[float] = []
    abstentions: list[bool] = []
    by_type: dict[str, list[float]] = {}

    for row in rows:
        qtype = row.get("type", "ordinary")
        relevant = row.get("relevant") or []
        retrieved = row.get("response", {}).get("retrieved") or []

        r3 = recall_at_k(relevant, retrieved, 3)
        r5 = recall_at_k(relevant, retrieved, 5)
        cv = citation_validity(row.get("response", {}))

        if r3 is not None:
            recalls_3.append(r3)
        if r5 is not None:
            recalls_5.append(r5)
            by_type.setdefault(qtype, []).append(r5)
        if cv is not None:
            citations.append(cv)

        if row.get("must_abstain"):
            answered = row.get("response", {}).get("answered_from_context", True)
            abstentions.append(not answered)

    avg_r3 = round(sum(recalls_3) / len(recalls_3), 4) if recalls_3 else 0.0
    avg_r5 = round(sum(recalls_5) / len(recalls_5), 4) if recalls_5 else 0.0
    avg_cv = round(sum(citations) / len(citations), 4) if citations else 1.0
    abstention_rate = round(sum(1 for a in abstentions if a) / len(abstentions), 4) if abstentions else 1.0

    type_breakdown = {t: round(sum(vals) / len(vals), 4) for t, vals in by_type.items() if vals}

    return {
        "recall@3": avg_r3,
        "recall@5": avg_r5,
        "citation_validity": avg_cv,
        "abstention_correctness": abstention_rate,
        "type_recall5": type_breakdown,
        "total_questions": len(rows),
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []

    # 1. Abstention correctness gate (must be 100%)
    abstention = results.get("abstention_correctness", 0.0)
    if abstention < REQUIRED_ABSTENTION:
        failures.append(
            f"Gate Failure: Abstention correctness {abstention * 100:.1f}% is below required {REQUIRED_ABSTENTION * 100:.1f}%"
        )

    # 2. Citation validity gate (must be >= 95%)
    validity = results.get("citation_validity", 0.0)
    if validity < MIN_CITATION_VALIDITY:
        failures.append(
            f"Gate Failure: Citation validity {validity * 100:.1f}% is below minimum {MIN_CITATION_VALIDITY * 100:.1f}%"
        )

    # 3. Regression gate against baseline
    if baseline:
        base_recall5 = baseline.get("recall@5", 0.0)
        curr_recall5 = results.get("recall@5", 0.0)
        if curr_recall5 < (base_recall5 - MAX_RECALL5_DROP):
            failures.append(
                f"Gate Failure: recall@5 dropped from baseline {base_recall5:.4f} to {curr_recall5:.4f} "
                f"(exceeding max allowable drop of {MAX_RECALL5_DROP})"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })

    results = summarise(rows)
    print(json.dumps(results, indent=2))

    baseline = None
    if args.baseline.exists() and not args.update_baseline:
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except Exception:
            pass

    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Updated baseline in {args.baseline}")

    failed_reasons = gate(results, baseline)
    if failed_reasons:
        for reason in failed_reasons:
            print(f"FAIL: {reason}", file=sys.stderr)
        return 1

    print("PASS: all evaluation gates passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
