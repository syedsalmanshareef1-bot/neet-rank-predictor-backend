"""
Seat eligibility rules — who can actually take a given seat.

The raw data stores, per record, a state, a quota string (in `cutoff_quota`
when present, otherwise `quota` — most states put a placeholder "State" in
`quota` and the real quota in `cutoff_quota`) and a state-specific category
code (Karnataka "GM"/"2AG", Tamil Nadu "OC Open", Gujarat "GQ-SE", ...).

On its own that data cannot answer the question a student actually asks:
"I'm from Karnataka, General category — which Maharashtra seats can I get?"
This module turns each record into three things the predictor can filter on:

  access        "domicile"  -> only candidates domiciled in that state
                "all_india" -> candidates from any state may apply
  seat_type     government | private | nri | in_service | minority |
                institutional | special
  category      general | obc | sc | st | ews | open (no category, e.g.
                management/NRI seats), plus pwd / female_only flags

Everything is a plain lookup table so it can be checked and corrected by
someone who knows a particular state's counselling rules. Quota strings not
listed in QUOTA_RULES (e.g. from a future import) fall back to keyword
heuristics in _guess_quota(), which err on the side of "domicile" — a
student is never told they're eligible for a home-state-only seat.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

GOVERNMENT = "government"
PRIVATE = "private"
NRI = "nri"
IN_SERVICE = "in_service"
MINORITY = "minority"
INSTITUTIONAL = "institutional"
SPECIAL = "special"

DOMICILE = "domicile"
ALL_INDIA = "all_india"

SEAT_TYPE_LABELS = {
    GOVERNMENT: "Government / state merit",
    PRIVATE: "Private / management",
    NRI: "NRI",
    IN_SERVICE: "In-service (govt doctors)",
    MINORITY: "Minority",
    INSTITUTIONAL: "Institutional preference",
    SPECIAL: "Special / regional quota",
}
DEFAULT_SEAT_TYPES = (GOVERNMENT, PRIVATE)

CATEGORY_LABELS = {
    "general": "General / UR / Open",
    "ews": "EWS",
    "obc": "OBC / BC / SEBC",
    "sc": "SC",
    "st": "ST",
    "open": "Open to all categories",
}
STUDENT_CATEGORIES = ("general", "ews", "obc", "sc", "st")

# ---------------------------------------------------------------------------
# Quota rules: effective quota string -> (seat_type, access)
# ---------------------------------------------------------------------------
Q = QUOTA_RULES = {
    # Andhra Pradesh
    "AP Govt-NS AP LOC": (GOVERNMENT, DOMICILE),
    "AP Govt-NS APUR": (GOVERNMENT, DOMICILE),
    "AP Govt-NS LOC (AU)": (GOVERNMENT, DOMICILE),
    "AP Govt-NS LOC (SVU)": (GOVERNMENT, DOMICILE),
    "AP Govt-Serv APUR": (IN_SERVICE, DOMICILE),
    "AP Govt-Serv LOC (AU)": (IN_SERVICE, DOMICILE),
    "AP Govt-Serv LOC (SVU)": (IN_SERVICE, DOMICILE),
    "APMgmt-CA SF": (PRIVATE, DOMICILE),
    "APMgmt-S1-All-CatB": (PRIVATE, ALL_INDIA),
    "APMgmt-S1B-LOC-CatB": (PRIVATE, DOMICILE),
    "APMgmt-S2-CatC-NRI": (NRI, ALL_INDIA),
    "APMgmt-S3-CatC-Inst": (PRIVATE, ALL_INDIA),
    # Assam
    "Assam Govt Quota": (GOVERNMENT, DOMICILE),
    "Assam SHQ Quota": (GOVERNMENT, DOMICILE),
    "Assam NEC Quota": (SPECIAL, DOMICILE),
    # Bihar
    "Bihar Govt Quota": (GOVERNMENT, DOMICILE),
    "Bihar DNB Seats": (GOVERNMENT, DOMICILE),
    "Bihar Priv-Open": (PRIVATE, ALL_INDIA),
    "Bihar Priv-NRI": (NRI, ALL_INDIA),
    "Bihar Priv-Minority": (MINORITY, DOMICILE),
    # Chandigarh (access decided per category prefix: UT- / IP- / All India-)
    "CHNDGH-Govt Quota": (GOVERNMENT, DOMICILE),
    # Chhattisgarh
    "CG Domicile": (GOVERNMENT, DOMICILE),
    "CG MBBS or Ins": (GOVERNMENT, DOMICILE),
    "CG Domicile-NRI": (NRI, DOMICILE),
    "CG MBBS or Ins-NRI": (NRI, DOMICILE),
    "CG Other State-NRI": (NRI, ALL_INDIA),
    "Other State": (GOVERNMENT, ALL_INDIA),
    # Delhi / Goa
    "Delhi State Quota": (GOVERNMENT, DOMICILE),
    "Goa Govt Quota": (GOVERNMENT, DOMICILE),
    # Gujarat
    "GUJ Govt-AllGujStud.": (GOVERNMENT, DOMICILE),
    "GUJ Govt-Inservice": (IN_SERVICE, DOMICILE),
    "GUJ Govt-Inst. Pref": (INSTITUTIONAL, DOMICILE),
    "GUJ Mgmt Quota": (PRIVATE, ALL_INDIA),
    "GUJ Mgmt-NRI": (NRI, ALL_INDIA),
    # Haryana
    "HAR Govt-All": (GOVERNMENT, ALL_INDIA),
    "HAR Priv-Govt Quota": (GOVERNMENT, ALL_INDIA),
    "HAR Govt-Inst. Pref": (INSTITUTIONAL, DOMICILE),
    "Haryana Priv IP": (INSTITUTIONAL, DOMICILE),
    "HAR Priv-Mgmt": (PRIVATE, ALL_INDIA),
    "Haryana Priv NRI": (NRI, ALL_INDIA),
    "HAR Priv-Minority": (MINORITY, DOMICILE),
    "Haryana DNB Serv": (IN_SERVICE, DOMICILE),
    # Himachal Pradesh
    "HP Govt Quota": (GOVERNMENT, DOMICILE),
    "HP Private-StateQuota": (GOVERNMENT, DOMICILE),
    "HP Priv All": (PRIVATE, ALL_INDIA),
    "HP Priv NRI": (NRI, ALL_INDIA),
    "HP DNB Serv": (IN_SERVICE, DOMICILE),
    # Jammu & Kashmir
    "JK Govt Quota": (GOVERNMENT, DOMICILE),
    "JK Priv-Govt Quota": (GOVERNMENT, DOMICILE),
    "JK Priv-Mgmt Quota": (PRIVATE, ALL_INDIA),
    "JK Priv-NRI": (NRI, ALL_INDIA),
    "JK Priv-Hindu Min.": (MINORITY, DOMICILE),
    # Jharkhand
    "JHKND Govt Quota": (GOVERNMENT, DOMICILE),
    # Karnataka (KEA)
    "KAR Govt Quota-Open": (GOVERNMENT, DOMICILE),
    "KAR Priv Seats-GMP": (GOVERNMENT, DOMICILE),
    "KAR Priv Seats-Open": (PRIVATE, ALL_INDIA),
    "KAR Others (Inst.Q)": (PRIVATE, ALL_INDIA),
    "KAR NRI Quota": (NRI, ALL_INDIA),
    "KAR Priv Seats-Min.": (MINORITY, DOMICILE),
    "KAR Govt Quota-InS": (IN_SERVICE, DOMICILE),
    "KAR DNB Serv": (IN_SERVICE, DOMICILE),
    # Kerala
    "KER Govt Quota": (GOVERNMENT, DOMICILE),
    "KER Self Fin. Seats": (PRIVATE, DOMICILE),
    "KER SF NRI Seats": (NRI, ALL_INDIA),
    # Madhya Pradesh
    "MP Govt Quota": (GOVERNMENT, DOMICILE),
    "MP Priv-Open": (PRIVATE, DOMICILE),
    "MP Govt-NonDomicile": (GOVERNMENT, ALL_INDIA),
    "MP Priv-NonDomicile": (PRIVATE, ALL_INDIA),
    "MP Priv-NRI": (NRI, DOMICILE),
    "MP Priv-NRINonDomicil": (NRI, ALL_INDIA),
    # Maharashtra (private / deemed institutional seats)
    "MNG": (PRIVATE, ALL_INDIA),
    "NRI": (NRI, ALL_INDIA),
    # Manipur (RIMS — seats reserved per beneficiary NE state)
    "NonRIMS-NEGrad": (SPECIAL, DOMICILE),
    "RIMS Grad-AIQGrad": (SPECIAL, DOMICILE),
    "RIMS Grad-Aru.Pra": (SPECIAL, DOMICILE),
    "RIMS Grad-Manip.": (SPECIAL, DOMICILE),
    "RIMS Grad-Megha.": (SPECIAL, DOMICILE),
    "RIMS Grad-Rajasthan": (SPECIAL, DOMICILE),
    "RIMS Grad-Sikkim": (SPECIAL, DOMICILE),
    "RIMS Grad-Tripura": (SPECIAL, DOMICILE),
    "RIMS Open-BenfStates": (SPECIAL, DOMICILE),
    "RIMS Spons-All": (SPECIAL, DOMICILE),
    "RIMS Spons-Aru.Pra": (SPECIAL, DOMICILE),
    "RIMS Spons-Manip.": (SPECIAL, DOMICILE),
    "RIMS Spons-Megha.": (SPECIAL, DOMICILE),
    "RIMS Spons-Nagal.": (SPECIAL, DOMICILE),
    "RIMS Spons-Sikkim": (SPECIAL, DOMICILE),
    "RIMS Spons-Tripura": (SPECIAL, DOMICILE),
    # Meghalaya
    "NEIGRIHMS Pass out": (INSTITUTIONAL, DOMICILE),
    "NEIGRIHMS-NEOpen": (SPECIAL, DOMICILE),
    # Odisha
    "Odisha-Govt Quota-Dir": (GOVERNMENT, DOMICILE),
    "Odisha-Govt Quota-InS": (IN_SERVICE, DOMICILE),
    "Odisha-DNB-InS Seats-Dir": (GOVERNMENT, DOMICILE),
    "Odisha-DNB-InS Seats-InS": (IN_SERVICE, DOMICILE),
    "Odisha-Mgmt Quota-Dir": (PRIVATE, ALL_INDIA),
    "Odisha-Mgmt Quota- InS": (IN_SERVICE, DOMICILE),
    # Puducherry
    "PY-Govt Quota": (GOVERNMENT, DOMICILE),
    "PY Mgmt-Open": (PRIVATE, ALL_INDIA),
    # Punjab
    "Punjab Domicile Seats": (GOVERNMENT, DOMICILE),
    "Punjab Open Quota (AI Basis)": (GOVERNMENT, ALL_INDIA),
    "Punjab Open Quota (AI Basis)-Converted": (GOVERNMENT, ALL_INDIA),
    "Punjab BFUHS IP Quota": (INSTITUTIONAL, DOMICILE),
    "Punjab Adesh IP Quota": (INSTITUTIONAL, DOMICILE),
    "Punjab SGRD IP Quota": (INSTITUTIONAL, DOMICILE),
    "Punjab CMC Minority Quota (Cat B)": (MINORITY, DOMICILE),
    "Punjab SGRD Sikh Minority Quota": (MINORITY, DOMICILE),
    "Punjab NRI Quota": (NRI, ALL_INDIA),
    "Punjab Sikh Minority NRI Quota": (NRI, ALL_INDIA),
    "Punjab DNB Serv": (IN_SERVICE, DOMICILE),
    # Rajasthan
    "RAJ Govt - Govt Quota": (GOVERNMENT, DOMICILE),
    "RAJ Priv-Govt Quota": (GOVERNMENT, DOMICILE),
    "RAJ Govt - Mgmt Quota": (PRIVATE, DOMICILE),
    "RAJ Priv-All India": (PRIVATE, ALL_INDIA),
    "RAJ Priv-Mgmt Quota": (PRIVATE, ALL_INDIA),
    "Raj DNB Serv": (IN_SERVICE, DOMICILE),
    # Sikkim
    "Sikkim Govt Quota": (GOVERNMENT, DOMICILE),
    "Sikkim Gen Quota": (PRIVATE, ALL_INDIA),
    "Sikkim Mgmt Quota": (PRIVATE, ALL_INDIA),
    # Tamil Nadu
    "TN Govt Quota": (GOVERNMENT, DOMICILE),
    "TN Govt-PwD": (GOVERNMENT, DOMICILE),
    "TN Mgmt Quota": (PRIVATE, ALL_INDIA),
    "TN NRI Quota": (NRI, ALL_INDIA),
    "TN Mgmt-Christian Min": (MINORITY, DOMICILE),
    "TN Mgmt-Malayalam Min": (MINORITY, DOMICILE),
    "TN Mgmt-Telugu Min": (MINORITY, DOMICILE),
    "TN-CMC Minority 20": (MINORITY, DOMICILE),
    "TN CMC-Minority Network": (MINORITY, DOMICILE),
    "TN CMC-General Merit": (PRIVATE, ALL_INDIA),
    "TN CMC-Inst Preference": (INSTITUTIONAL, DOMICILE),
    "TN CMC-Service": (IN_SERVICE, DOMICILE),
    # Telangana
    "Tel Govt-NS LOC": (GOVERNMENT, DOMICILE),
    "Tel Govt-Serv LOC": (IN_SERVICE, DOMICILE),
    "TELMgmt-MQ1-CatB-All": (PRIVATE, ALL_INDIA),
    "TELMgmt-MQ1-CatB-All Local": (PRIVATE, DOMICILE),
    "TELMgmt-MQ2-CatC-NRI": (NRI, ALL_INDIA),
    "TELMgmt-MQ3-CatC-Inst": (PRIVATE, ALL_INDIA),
    # Tripura
    "Tripura Govt Quota": (GOVERNMENT, DOMICILE),
    "Tripura Mgmt Quota": (PRIVATE, ALL_INDIA),
    "Tripura DNB Serv": (IN_SERVICE, DOMICILE),
    # Uttar Pradesh
    "UP Govt Quota": (GOVERNMENT, DOMICILE),
    "UP Priv-Open Quota": (PRIVATE, ALL_INDIA),
    "UP Priv-Min. Quota": (MINORITY, DOMICILE),
    "UP-DNB InS": (IN_SERVICE, DOMICILE),
    # Uttarakhand
    "UK-Govt Quota": (GOVERNMENT, DOMICILE),
    "UK Priv-Govt Quota": (GOVERNMENT, DOMICILE),
    "UK Priv-AllIndia/Mgmt": (PRIVATE, ALL_INDIA),
    "UK Priv-NRI": (NRI, ALL_INDIA),
    "UK DNB Serv": (IN_SERVICE, DOMICILE),
    # West Bengal
    "WB Govt Quota": (GOVERNMENT, DOMICILE),
    "WB Mgmt Quota": (PRIVATE, ALL_INDIA),
    "WB NRI Quota": (NRI, ALL_INDIA),
    "WB DNB Serv": (IN_SERVICE, DOMICILE),
}


def _guess_quota(quota: str) -> tuple[str, str]:
    """Fallback for quota strings not in QUOTA_RULES (future imports)."""
    q = quota.lower()
    local = bool(re.search(r"\b(loc|local|domicile|state quota)\b", q)) and "non" not in q
    if "nri" in q:
        return NRI, (DOMICILE if local else ALL_INDIA)
    if re.search(r"serv|\bins\b|inservice|in-service|\bgdo\b", q):
        return IN_SERVICE, DOMICILE
    if re.search(r"minority|\bmin\b|min\.", q):
        return MINORITY, DOMICILE
    if re.search(r"inst\.? ?pref|\bip\b|pass ?out", q):
        return INSTITUTIONAL, DOMICILE
    if re.search(r"all ?india|\bai basis\b|non ?domicile|other state", q):
        return (PRIVATE if "priv" in q else GOVERNMENT), ALL_INDIA
    if re.search(r"mgmt|management|\bmng\b|\bmq\d?\b", q):
        return PRIVATE, (DOMICILE if local else ALL_INDIA)
    return GOVERNMENT, DOMICILE


# ---------------------------------------------------------------------------
# Category mapping: raw state-specific code -> student category group
# ---------------------------------------------------------------------------
# Exact codes first (mostly Karnataka / Puducherry / Kerala short codes that
# can't be recognised by keyword).
_EXACT_CATEGORY = {
    # Karnataka (KEA)
    "GM": "general", "GMP": "general", "OPN": "general", "SCG": "sc", "STG": "st",
    "1G": "obc", "2AG": "obc", "2BG": "obc", "3AG": "obc", "3BG": "obc",
    "MNG": "open", "NRI": "open", "PGM": "general", "P1G": "obc", "P2AG": "obc",
    "P3BG": "obc", "P3AG": "obc", "PSTG": "st",
    "GMH": "general", "GMPH": "general", "PGMH": "general", "SCH": "sc", "STH": "st",
    "1H": "obc", "2AH": "obc", "2BH": "obc", "3AH": "obc", "3BH": "obc",
    # Puducherry
    "UGE": "general", "AGE": "open", "USC": "sc", "UOB": "obc", "UMB": "obc",
    "UEB": "obc", "UBM": "obc", "UST": "st", "UBT": "st",
    # Kerala
    "SM": "general", "EW": "ews", "EZ": "obc", "MU": "obc", "BH": "obc", "LA": "obc",
    "BX": "obc", "KU": "obc", "OE": "obc", "DV": "obc", "VK": "obc", "KN": "obc", "AC": "general",
    "NR": "open", "NC": "open", "NM": "open",
    # Gujarat management
    "MQ-MQ": "open", "NQ-NRI": "open",
    # Assam
    "SHQ": "general", "NEC": "general",
    # Sikkim
    "SQ": "general",
    # J&K
    "OM": "general", "RBA": "obc", "ALC/IB": "obc", "STK": "st", "STL": "st",
}

# Karnataka "…H" codes = Kalyana-Karnataka (Hyderabad-Karnataka) region seats.
_KAR_REGION_CODES = {"GMH", "SCH", "STH", "1H", "2AH", "2BH", "3AH", "3BH", "GMPH", "MEH", "MMH1", "MMH2", "PGMH"}
# Karnataka minority codes
_KAR_MINORITY_CODES = {"ME", "MM1", "MM2", "MC1", "MC2", "MA", "MU", "RC1", "RC2", "RC3"}


@dataclass(frozen=True)
class SeatInfo:
    quota_label: str        # the quota string to show a student
    seat_type: str
    access: str             # domicile | all_india
    category_group: str     # general | ews | obc | sc | st | open
    pwd: bool
    female_only: bool

    @property
    def open_to_all_india(self) -> bool:
        return self.access == ALL_INDIA


def _category_group(cat: str) -> str:
    c = cat.strip()
    if c in _EXACT_CATEGORY:
        return _EXACT_CATEGORY[c]
    u = c.upper()
    # Gujarat GQ-/UQ-/IQ- prefixes: OP / SE / SC / ST / EW
    m = re.match(r"^[GUI]Q-(OP|SE|SC|ST|EW)", u)
    if m:
        return {"OP": "general", "SE": "obc", "SC": "sc", "ST": "st", "EW": "ews"}[m.group(1)]
    # Strip prefixes such as "IP-", "UT-", "Group 1 - ", "All India-"
    u = re.sub(r"^(IP|UT|ALL INDIA|DQ)-", "", u)
    pm = re.match(r"^(UGE|USC|UST|UBT|UOB|UMB|UEB|UBM)\b", u)
    if pm:
        return _EXACT_CATEGORY[pm.group(1)]
    u = re.sub(r"^GROUP \d+ - ", "", u)
    tokens = re.split(r"[\s/\-()]+", u)
    first = tokens[0] if tokens else ""
    if "EWS" in tokens or first in ("EW",):
        return "ews"
    if first in ("SC", "SCA", "SCD", "SCG", "USC"):
        return "sc"
    if first.startswith("ST") and first not in ("STATE",):
        return "st"
    if first in ("OBC", "BC", "MBC", "EBC", "BCA", "BCB", "BCC", "BCD", "BCE", "BCM", "BC-I", "BC-II", "SEBC", "MOBC"):
        return "obc"
    if u.startswith("BC") or u.startswith("OBC") or u.startswith("MBC") or u.startswith("EBC"):
        return "obc"
    if first in ("UR", "OC", "GEN", "GENERAL", "OPEN", "GM", "OP", "UNRESERVED", "CMC"):
        return "general"
    if first in ("MNG", "MQ", "MQ1", "MQ2", "MQ3", "NRI", "S1A", "S1B", "S2", "S3", "MINORITY", "HM", "MM", "SM"):
        return "open"
    if "MINORITY" in u or "NRI" in u or "QUOTA" in u:
        return "open"
    return "general"


_KAR_PWD_CODES = {"PGM", "PGMH", "P1G", "P2AG", "P3AG", "P3BG", "PSTG", "PSCG"}


def _is_pwd(cat: str) -> bool:
    u = cat.upper()
    if u in _KAR_PWD_CODES:
        return True
    return bool(re.search(r"PWD|\bPH\b|-PH\b|/PH/|PHY|\bPD\b|-PD\b|DPW|PHO|^DQ-", u))


def _is_female(cat: str) -> bool:
    u = cat.upper()
    return bool(re.search(r"FEM|FEMALE|WOMEN", u))


def _category_overrides(state: str, cat: str, seat_type: str, access: str) -> tuple[str, str]:
    """Some categories change who can take the seat, regardless of quota."""
    u = cat.upper()
    if u.startswith("ALL INDIA-") or "NON DOMICILE" in u:
        access = ALL_INDIA
    if u.startswith("IP-") or u.endswith("-IP"):
        seat_type = INSTITUTIONAL
    if re.search(r"SERVICE|\bSERV\b|GDO", u) and seat_type in (GOVERNMENT, PRIVATE):
        seat_type = IN_SERVICE
    elif re.search(r"\bESM\b|\bFF\b|-GC\b|EXS|-MSP\b|ORPHAN", u) and seat_type in (GOVERNMENT, PRIVATE):
        seat_type = SPECIAL
    if re.search(r"MSM|MINORITY", u) and seat_type in (GOVERNMENT, PRIVATE):
        seat_type = MINORITY
    if u == "NRI" or u.startswith("NRI-") or "/NRI" in u:
        seat_type = NRI
    if state == "Karnataka":
        if u in _KAR_REGION_CODES:
            seat_type = SPECIAL
        elif u in _KAR_MINORITY_CODES:
            seat_type = MINORITY
    return seat_type, access


@lru_cache(maxsize=20000)
def classify(state: str | None, quota: str | None, cutoff_quota: str | None, category: str | None) -> SeatInfo:
    effective = (cutoff_quota or quota or "").strip()
    if effective in QUOTA_RULES:
        seat_type, access = QUOTA_RULES[effective]
    else:
        seat_type, access = _guess_quota(effective) if effective else (GOVERNMENT, DOMICILE)

    cat = (category or "").strip()
    if cat:
        seat_type, access = _category_overrides(state or "", cat, seat_type, access)
        group = _category_group(cat)
        pwd, female = _is_pwd(cat), _is_female(cat)
    else:
        group, pwd, female = "open", False, False

    if state == "Karnataka" and cat.upper() in _KAR_MINORITY_CODES:
        group = "open"
    # Management / NRI seats have no reservation — any category competes.
    if seat_type in (NRI,) or (seat_type == PRIVATE and group == "open"):
        group = "open"

    return SeatInfo(
        quota_label=effective or "—",
        seat_type=seat_type,
        access=access,
        category_group=group,
        pwd=pwd,
        female_only=female,
    )


def student_can_take(
    info: SeatInfo,
    *,
    seat_state: str | None,
    home_state: str | None,
    student_category: str | None,
    is_pwd: bool,
    is_female: bool,
    seat_types: set[str],
) -> bool:
    """True if a student with this profile is eligible to be allotted this seat."""
    if info.seat_type not in seat_types:
        return False
    if info.pwd and not is_pwd:
        return False
    if info.female_only and not is_female:
        return False

    is_home = bool(home_state) and home_state == seat_state
    if home_state and not is_home and info.access != ALL_INDIA:
        return False

    group = info.category_group
    if group in ("open", "general"):
        return True
    # Reserved seat: only for that category, and reservation benefits apply
    # only in the student's own state (outsiders compete as General).
    if not student_category or student_category == "general":
        return False
    if home_state and not is_home:
        return False
    return group == student_category
