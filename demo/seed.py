"""Seed demo data: 1 org, 3 teams, 9 advisors, ~25 calls.

Each call gets a distinct tiny WAV (so idempotency keys differ), a fixture that
drives its analysis, and a called_at spread over the last few weeks. Everything
runs through the real (mock-mode) pipeline, so every call has a full detail page
and the dashboards have trend lines. One dispute is left open for the TL inbox.

Run:  conda run -n callsense python demo/seed.py
"""

from __future__ import annotations

import math
import os
import random
import struct
import sys
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_backend = ROOT / "backend"
if _backend.exists():  # local repo layout
    sys.path.insert(0, str(_backend))
# else: running in the backend container where modules are already importable.

from sqlalchemy import text  # noqa: E402

from db.session import SessionLocal  # noqa: E402
from feedback import raise_dispute  # noqa: E402
from ingestion.envelope import CallEnvelope, derive_idempotency_key  # noqa: E402
from ingestion.service import ingest  # noqa: E402
from pipeline import worker  # noqa: E402
from pipeline.queue import PostgresJobQueue  # noqa: E402

AUDIO_DIR = Path(os.environ.get("SEED_AUDIO_DIR", str(ROOT / "demo" / "audio" / "store")))

TEAMS = ["Pod Alpha", "Pod Beta", "Pod Gamma"]
# (name, team_index, external_id)
ADVISORS = [
    ("Arjun Rao", 0, "AGT-1"), ("Priya Nair", 0, "AGT-2"), ("Rohit Sharma", 0, "AGT-3"),
    ("Sneha Iyer", 1, "AGT-4"), ("Karan Mehta", 1, "AGT-5"), ("Meera Das", 1, "AGT-6"),
    ("Vikram Singh", 2, "AGT-7"), ("Anjali Gupta", 2, "AGT-8"), ("Dev Kapoor", 2, "AGT-9"),
]
FIXTURE_MIX = (
    ["good_discovery"] * 5
    + ["over_promiser"] * 3
    + ["hidden_costs"] * 2
    + ["pushy_pressure"] * 2
    + ["non_sales"] * 1
)
N_CALLS = 25
TABLES = ["calls", "processing_jobs", "transcripts", "segments", "scores",
          "call_scores", "flags", "disputes", "calibration_examples",
          "audit_log", "advisors", "teams", "orgs"]


def make_wav(path: Path, seconds: float, freq: int, sr: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        buf = bytearray()
        for i in range(int(sr * seconds)):
            left = int(3000 * math.sin(2 * math.pi * freq * i / sr))
            right = int(3000 * math.sin(2 * math.pi * (freq * 2) * i / sr))
            buf += struct.pack("<hh", left, right)
        w.writeframes(bytes(buf))


def reset_and_seed_org() -> None:
    with SessionLocal() as s:
        s.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
        s.execute(text("INSERT INTO orgs(id, name) VALUES (1, 'FitNova (SkilloVilla)')"))
        for idx, name in enumerate(TEAMS, start=1):
            s.execute(text("INSERT INTO teams(id, org_id, name) VALUES (:id, 1, :n)"),
                      {"id": idx, "n": name})
        for aid, (name, team_idx, ext) in enumerate(ADVISORS, start=1):
            s.execute(
                text(
                    "INSERT INTO advisors(id, team_id, name, email, external_ids) "
                    "VALUES (:id, :tid, :n, :email, CAST(:ext AS jsonb))"
                ),
                {"id": aid, "tid": team_idx + 1, "n": name,
                 "email": name.split()[0].lower() + "@skillovilla.com",
                 "ext": f'["{ext}"]'},
            )
        # First advisor of each team leads it.
        for team_idx in range(3):
            leader = team_idx * 3 + 1
            s.execute(text("UPDATE teams SET team_leader_id = :lid WHERE id = :tid"),
                      {"lid": leader, "tid": team_idx + 1})
        s.commit()


def seed_calls() -> None:
    random.seed(7)
    queue = PostgresJobQueue()
    now = datetime.now(timezone.utc)
    for i in range(N_CALLS):
        name, team_idx, ext = ADVISORS[i % len(ADVISORS)]
        fixture = random.choice(FIXTURE_MIX)
        wav = AUDIO_DIR / f"call_{i:02d}.wav"
        make_wav(wav, seconds=1.0 + (i % 5) * 0.1, freq=180 + i * 7)
        audio = wav.read_bytes()
        called_at = now - timedelta(days=random.randint(0, 20), hours=random.randint(0, 12))
        env = CallEnvelope(
            source="folder",
            idempotency_key=derive_idempotency_key(audio, "folder"),
            audio_uri=str(wav),
            advisor_external_id=ext,
            org_id=1,
            called_at=called_at,
            language_hint="hi",
            raw_metadata={"fixture": fixture, "seed": True},
        )
        with SessionLocal() as s:
            ingest(s, env, queue)
            s.commit()

    handled = worker.run_until_idle(queue)
    print(f"pipeline processed {handled} jobs")

    # Leave one dispute open for the TL inbox demo.
    with SessionLocal() as s:
        row = s.execute(
            text(
                "SELECT f.id AS flag_id, c.advisor_id FROM flags f "
                "JOIN calls c ON c.id = f.call_id "
                "WHERE f.severity = 'critical' AND f.state = 'open' "
                "ORDER BY f.id LIMIT 1"
            )
        ).mappings().first()
        if row:
            raise_dispute(s, row["flag_id"],
                          "Customer explicitly asked about placement outcomes.",
                          row["advisor_id"])
            s.commit()
            print(f"opened demo dispute on flag {row['flag_id']}")


def summary() -> None:
    with SessionLocal() as s:
        for t in ["orgs", "teams", "advisors", "calls", "call_scores", "flags", "disputes"]:
            n = s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            print(f"  {t:14} {n}")
        org = s.execute(text("SELECT round(avg_composite::numeric,1) FROM v_org_scores")).scalar_one()
        print(f"  org avg composite: {org}")


if __name__ == "__main__":
    print("Seeding CallSense demo data...")
    reset_and_seed_org()
    seed_calls()
    summary()
    print("Done. Start the API and open the dashboard.")
