"""Test helpers: tiny WAV generation + minimal org seeding."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


def make_wav(path, seconds: float = 1.0, freq: int = 200, sr: int = 8000,
             channels: int = 2) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        buf = bytearray()
        for i in range(int(sr * seconds)):
            left = int(3000 * math.sin(2 * math.pi * freq * i / sr))
            if channels == 2:
                right = int(3000 * math.sin(2 * math.pi * (freq * 2) * i / sr))
                buf += struct.pack("<hh", left, right)
            else:
                buf += struct.pack("<h", left)
        w.writeframes(bytes(buf))
    return path


def seed_org(db: Session) -> None:
    db.execute(text("INSERT INTO orgs(id,name) VALUES (1,'FitNova')"))
    db.execute(text("INSERT INTO teams(id,org_id,name) VALUES (1,1,'Pod A')"))
    db.execute(
        text(
            "INSERT INTO advisors(id,team_id,name,external_ids) "
            "VALUES (1,1,'Arjun', CAST('[\"AGT-1\"]' AS jsonb))"
        )
    )
    db.commit()
