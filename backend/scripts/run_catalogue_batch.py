"""Run the real ingestion pipeline over a batch of source definitions, in parallel, in a non-production database.

    python -m scripts.run_catalogue_batch SOURCES.json [--workers N] [--discover] [--process] [--test]

* register: each definition is proposed (existing names are kept) and moved to ``testing``.
  Sources stay in testing: approving one needs a recorded terms-of-use review, which is a human
  decision this script never makes. The pipeline discovers and processes for testing sources.
* --test: source tests (real fetches of the leads), recorded on each source.
* --discover: real discovery runs (candidates recorded).
* --process: fetch, extract, validate and de-duplicate every due candidate, with N workers leasing
  candidates (``FOR UPDATE SKIP LOCKED``), each source's own politeness delay and robots rules.

Refuses to run against a production database. One failing source never stops the batch.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.intelligence import pipeline, registry
from app.intelligence.definitions import SourceDefinition
from app.intelligence.source_test import run_source_test
from app.models import AcquisitionSource
from app.models.enums import SourceStatus


def register(path: str) -> list[str]:
    payload = json.load(open(path))
    names = []
    with SessionLocal() as db:
        for raw in payload["sources"]:
            raw = {k: v for k, v in raw.items() if not k.startswith("_")}
            definition = SourceDefinition.model_validate(raw)
            source = db.scalar(select(AcquisitionSource).where(AcquisitionSource.name == definition.name))
            if source is None:
                try:
                    with db.begin_nested():
                        source = registry.create_source(db, definition)
                except registry.SourceRegistryError as error:
                    print(f"  not registered: {definition.name}: {error}", file=sys.stderr)
                    continue
            if SourceStatus(source.status) == SourceStatus.PROPOSED:
                registry.change_status(db, source, SourceStatus.TESTING)
            names.append(source.name)
        db.commit()
    return names


def _one(name: str, action: str) -> str:
    with SessionLocal() as db:
        source = db.scalar(select(AcquisitionSource).where(AcquisitionSource.name == name))
        try:
            if action == "test":
                report = run_source_test(db, source, sample=4)
                db.commit()
                return f"{'PASS' if report.passed else 'FAIL'} {name}: leads={report.leads} ok={report.fetched_ok} failed={report.fetched_failed}"
            report = pipeline.run_discovery(db, source)
            return f"{name}: leads={len(report.accepted)} new={report.new} rejected={len(report.rejected)} error={report.error}"
        except Exception as error:  # noqa: BLE001 - one source must not stop the batch
            db.rollback()
            return f"ERROR {name}: {type(error).__name__}: {error}"[:300]


def fan_out(names: list[str], action: str, workers: int) -> None:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, name, action) for name in names]
        for future in as_completed(futures):
            print("  " + future.result(), flush=True)


def _process_worker(names: set[str]) -> dict:
    totals: dict[str, int] = {}
    with SessionLocal() as db:
        ids = set(db.scalars(select(AcquisitionSource.id).where(AcquisitionSource.name.in_(names))))
        while True:
            report = pipeline.process_candidates(db, limit=10)
            if report.processed == 0:
                break
            for state, n in report.by_state.items():
                totals[state] = totals.get(state, 0) + n
    return totals


def process(names: list[str], workers: int) -> None:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: _process_worker(set(names)), range(workers)))
    merged: dict[str, int] = {}
    for result in results:
        for state, n in result.items():
            merged[state] = merged.get(state, 0) + n
    print("  processed by state:", merged)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--process", action="store_true")
    args = parser.parse_args()
    if settings.is_production:
        raise SystemExit("Refusing: APP_ENV is production. Run batches in a local or staging database.")
    names = register(args.sources)
    print(f"{len(names)} sources registered (testing)")
    if args.test:
        fan_out(names, "test", args.workers)
    if args.discover:
        fan_out(names, "discover", args.workers)
    if args.process:
        process(names, args.workers)


if __name__ == "__main__":
    main()
