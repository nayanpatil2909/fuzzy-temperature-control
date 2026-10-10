"""
rules.py
========
Defines the 25-rule Mamdani fuzzy rule base for the temperature controller.

Rule structure:
    IF (Temperature Error is <E_LABEL>) AND (Rate of Error is <DE_LABEL>)
    THEN (Cooling Power is <OUTPUT_LABEL>)

Rule matrix (rows = Error, columns = Rate-of-Change of Error):
---------------------------------------------------------------------
        Δe →   NB     NS     ZE     PS     PB
  e ↓
  NB          VH     VH     VH     H      H
  NS          VH     H      H      M      L
  ZE          H      M      M      L      VL
  PS          M      L      L      VL     VL
  PB          L      VL     VL     VL     VL
---------------------------------------------------------------------

Physical rationale
------------------
  NB error  → room is MUCH hotter than target  → maximum cooling required
  NS error  → room is SLIGHTLY hotter           → high/medium cooling
  ZE error  → room is AT target                → moderate cooling to maintain
  PS error  → room is SLIGHTLY cooler           → minimal cooling
  PB error  → room is MUCH cooler               → nearly no cooling needed

  NB Δe → error worsening fast (room heating) → boost cooling
  PB Δe → error improving fast (room cooling) → reduce cooling

Output labels: VL (Very Low), L (Low), M (Medium), H (High), VH (Very High)
"""

# Linguistic label ordering (index → label)
ERROR_LABELS      = ["NB", "NS", "ZE", "PS", "PB"]
DELTA_ERROR_LABELS = ["NB", "NS", "ZE", "PS", "PB"]
OUTPUT_LABELS     = ["VL", "L", "M", "H", "VH"]

# 5×5 rule matrix
# RULE_MATRIX[i][j] = output label for ERROR_LABELS[i] × DELTA_ERROR_LABELS[j]
RULE_MATRIX: list[list[str]] = [
    # Δe→  NB     NS     ZE     PS     PB
    ["VH", "VH", "VH", "H",  "H" ],   # e = NB
    ["VH", "H",  "H",  "M",  "L" ],   # e = NS
    ["H",  "M",  "M",  "L",  "VL"],   # e = ZE
    ["M",  "L",  "L",  "VL", "VL"],   # e = PS
    ["L",  "VL", "VL", "VL", "VL"],   # e = PB
]


def get_output_label(e_label: str, de_label: str) -> str:
    """Look up the output label for a given (error, delta_error) label pair."""
    i = ERROR_LABELS.index(e_label)
    j = DELTA_ERROR_LABELS.index(de_label)
    return RULE_MATRIX[i][j]


def get_all_rules() -> list[dict]:
    """Return all 25 rules as a list of structured dicts for API/UI consumption."""
    rules = []
    rule_id = 1
    for i, e_lbl in enumerate(ERROR_LABELS):
        for j, de_lbl in enumerate(DELTA_ERROR_LABELS):
            output = RULE_MATRIX[i][j]
            rules.append({
                "rule_id":    rule_id,
                "e_label":    e_lbl,
                "de_label":   de_lbl,
                "output":     output,
                "antecedent": f"e = {e_lbl}  AND  Δe = {de_lbl}",
                "consequent": f"Cooling = {output}",
                "text": (
                    f"IF temperature error is {e_lbl} "
                    f"AND rate of error is {de_lbl} "
                    f"THEN cooling power is {output}"
                ),
            })
            rule_id += 1
    return rules


def get_rule_matrix_for_display() -> dict:
    """Return the rule matrix along with label metadata for grid display in the UI."""
    return {
        "error_labels":       ERROR_LABELS,
        "delta_error_labels": DELTA_ERROR_LABELS,
        "output_labels":      OUTPUT_LABELS,
        "matrix":             RULE_MATRIX,
        "rules":              get_all_rules(),
    }
