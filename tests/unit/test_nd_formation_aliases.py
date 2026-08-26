from pathlib import Path

from glasswell.seed.formations_nd import FORMATION_ALIASES

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REVIEW = REPOSITORY_ROOT / "docs" / "nd-formation-alias-review.md"


def test_the_review_table_and_seeded_aliases_are_the_same_40_decisions():
    rows: list[tuple[str, str, str, str]] = []
    for line in REVIEW.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Reported pool" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append((cells[0], cells[2], cells[3], cells[4]))

    assert rows == list(FORMATION_ALIASES)
