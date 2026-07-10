"""rollup views (advisor/team/org)

Executes db/views.sql (the single source of truth for the view DDL) so the
rollup views ship with the schema.

Revision ID: rollup_views_0002
Revises: c0395f1a6a82
Create Date: 2026-07-10 18:56:00
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rollup_views_0002"
down_revision: Union[str, None] = "c0395f1a6a82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# .../db/alembic/versions/<this>.py -> parents[2] == .../db
VIEWS_SQL = Path(__file__).resolve().parents[2] / "views.sql"


def upgrade() -> None:
    op.execute(VIEWS_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_org_scores")
    op.execute("DROP VIEW IF EXISTS v_team_scores")
    op.execute("DROP VIEW IF EXISTS v_advisor_scores")
