"""Shared, inspectable reference data for synthetic claims and the rules engine.

This is deliberately small and hand-curated (synthetic, not real fee schedules)
so both the seed generator (Phase 1) and the detection rules (Phase 2) reason
over the *same* tables. Keeping it here — not duplicated in each module — means a
flag's trigger can always be traced back to a concrete, auditable reference.
"""
from __future__ import annotations

# --- Procedure pricing (synthetic "allowed" amounts, USD) --------------------
# Plausible CPT codes with invented, internally-consistent prices. Billed
# amounts in the seed are marked up from these; "allowed" is what a payer would
# permit, and is what the ROI estimate is computed from.
CPT_ALLOWED: dict[str, float] = {
    "99213": 75.00,   # office visit, established patient, low complexity
    "99214": 110.00,  # office visit, established patient, moderate complexity
    "80061": 19.00,   # lipid panel (comprehensive)
    "82465": 9.00,    # cholesterol, serum (lipid component)
    "83718": 10.00,   # HDL cholesterol (lipid component)
    "84478": 8.00,    # triglycerides (lipid component)
    "80053": 14.50,   # comprehensive metabolic panel (comprehensive)
    "82040": 7.00,    # albumin, serum (CMP component)
    "84075": 7.00,    # alkaline phosphatase (CMP component)
    "84450": 7.00,    # transferase, AST (CMP component)
}

CPT_NAMES: dict[str, str] = {
    "99213": "Office visit, established patient (low)",
    "99214": "Office visit, established patient (moderate)",
    "80061": "Lipid panel",
    "82465": "Cholesterol, serum",
    "83718": "HDL cholesterol",
    "84478": "Triglycerides",
    "80053": "Comprehensive metabolic panel",
    "82040": "Albumin, serum",
    "84075": "Alkaline phosphatase",
    "84450": "Transferase (AST)",
}

# --- Unbundling reference -----------------------------------------------------
# A comprehensive ("panel") code and the component codes that, billed
# separately on the same date, indicate unbundling. Detection compares a claim's
# line set to these; ROI compares (sum of components allowed) vs the panel.
BUNDLES: dict[str, dict] = {
    "80061": {
        "name": "Lipid panel",
        "components": ["82465", "83718", "84478"],
    },
    "80053": {
        "name": "Comprehensive metabolic panel",
        "components": ["82040", "84075", "84450"],
    },
}

# --- Modifier semantics -------------------------------------------------------
# Modifiers that legitimately make an otherwise-identical same-day service a
# distinct, separately-payable event. Their presence is what turns a true
# duplicate / unbundling positive into a near-miss the rules must NOT flag.
DISTINCT_SERVICE_MODIFIERS: set[str] = {
    "59",  # distinct procedural service
    "76",  # repeat procedure, same physician
    "77",  # repeat procedure, different physician
    "91",  # repeat clinical diagnostic lab test
    "RT",  # right side
    "LT",  # left side
}

# --- Network values -----------------------------------------------------------
NETWORK_IN = "in"
NETWORK_OUT = "out"


def panel_for_components(cpts: set[str]) -> str | None:
    """Return the comprehensive code whose components are all present in `cpts`."""
    for panel, spec in BUNDLES.items():
        if set(spec["components"]).issubset(cpts):
            return panel
    return None
