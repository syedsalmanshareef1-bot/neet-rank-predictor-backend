"""
Direct ports of the normalization + identity-key functions from the
original frontend (normInst, normField, keyParts, strictKey, looseKey).
Keeping these byte-for-byte equivalent is what lets years of existing
frontend data import cleanly without creating duplicate colleges/records.
"""
import re


def norm_inst(s: str | None) -> str:
    """Mirrors normInst() in the original <script>."""
    if not s:
        return ""
    s = s.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def norm_field(s: str | None) -> str:
    """Mirrors normField() in the original <script>."""
    if s is None:
        return ""
    return str(s).strip().lower()


def key_parts(
    state: str | None,
    authority: str | None,
    exam: str | None,
    institute: str | None,
    course: str | None,
    category: str | None,
    quota: str | None,
    seat_type: str | None,
) -> dict:
    return {
        "state": norm_field(state),
        "authority": norm_field(authority),
        "exam": norm_field(exam),
        "inst": norm_inst(institute),
        "course": norm_field(course),
        "category": norm_field(category),
        "quota": norm_field(quota),
        "seatType": norm_field(seat_type),
    }


def strict_key(**kwargs) -> str:
    p = key_parts(**kwargs)
    return "||".join(
        [p["state"], p["authority"], p["exam"], p["inst"], p["course"], p["category"], p["quota"], p["seatType"]]
    )


def loose_key(**kwargs) -> str:
    p = key_parts(**kwargs)
    return "||".join([p["state"], p["inst"], p["course"], p["category"], p["quota"], p["seatType"]])


ROUND_KEY_RE = re.compile(r"^(\d{4})-(Final|R\d+)$", re.IGNORECASE)


def parse_round_key(round_key: str) -> tuple[int, str]:
    """
    Splits "2025-R2" -> (2025, "R2"), "2024-Final" -> (2024, "Final").
    Raises ValueError if the shape doesn't match, so bad data is rejected
    at import time rather than silently miscategorized.
    """
    m = ROUND_KEY_RE.match((round_key or "").strip())
    if not m:
        raise ValueError(f"Unrecognized round key format: {round_key!r} (expected e.g. '2025-R2' or '2025-Final')")
    year = int(m.group(1))
    round_name = m.group(2)
    if round_name.lower() != "final":
        round_name = round_name.upper()
    else:
        round_name = "Final"
    return year, round_name


def make_round_key(year: int, round_name: str) -> str:
    round_name = (round_name or "").strip()
    if round_name.lower() == "final":
        round_name = "Final"
    else:
        round_name = round_name.upper()
        if not round_name.startswith("R"):
            round_name = "R" + round_name
    return f"{year}-{round_name}"
