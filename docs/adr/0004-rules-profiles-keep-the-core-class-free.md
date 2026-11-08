# ADR-0004 — Rules profiles keep the calculation core class-free

- **Status**: accepted
- **Date**: 2026-11-08

## Context

Certification by ABS (Requirements for Certification of Lifting Appliances, January 2026)
or DNV (DNV-ST-0378, July 2019, amended October 2021) prescribes how in-service crane loads
are built: dynamic amplification, vessel motion, wind, inclination, and extra factors on
pedestal and slewing-bearing loads. The app had a typed per-hoist `daf` and one
document-wide environment. The design is in
`docs/superpowers/specs/2026-11-08-abs-dnv-crane-loads-design.md`.

The anti-goal is ABS- or DNV-specific branching inside `calculation/`. The load chart also
needs the dynamic factor inside its capacity search, because both standards make the factor
depend on the load being lifted.

## Decision

- **`rules/` is a pure, profile-based package** (no Qt). `AbsProfile` and `DnvProfile` take
  a resolved condition, the hoist and the geometry, and return the dynamic factor, the cases
  (ABS one most-severe in-service case; DNV Case I and Case II), a `LiftSetup` (lateral
  load, minimum side load, wind on the load), foundation factors (ABS PF and the 3.75x
  retaining load, DNV SF1) and `ProvenanceRecord`s (quantity, value, clause, formula,
  inputs, `computed` or `override`). `calculation/` stays class-free: it never names ABS or
  DNV and sees only a factor, case settings and multipliers.
- **Closed-form, invertible factors.** Each dynamic factor is affine in the hook load for
  the quantity the chart solves for (the classes in `rules/factors.py`, each with a closed-form
  inverse; the standard's clamp or floor is applied in closed form), so `compute_allowable_load` still
  inverts `baseline + s * H` exactly with no iteration on the load.
- **Two hooks are the only additions to the solver and the allowable search.** (The analysis
  point also gained the complete +x unit reactions, `lateral_x_unit_reactions`, so the hook
  lateral reaches the left/right support entities.)
  - `HookLateral(fraction_x, fraction_y, constant_x_kN, constant_y_kN, min_fraction)`
    (`calculation/results.py`): the horizontal force the live load puts at the hoist's support
    node, split into the part proportional to the hook force and the wind constant.
    `hook_lateral=None` reproduces legacy results bit for bit. See design section 9.
  - `DemandScale` (`calculation/allowable.py`): per-entity factors on demand,
    `dead * baseline + live(LL) * sensitivity * H`, which carry PF, SF1 and the retaining
    3.75x (a `<entity>_retaining` copy has its own scale).
- **Rope-only stiffness (documented deviation).** The hook stiffness is derived from rope
  EA/L of the boom hoist and the active hoist as series springs (virtual work), at the
  shortest rope over the hook's travel unless a condition gives `hook_height_override_m`.
  Boom and pedestal flexibility are ignored. A stiffer system gives a higher factor, so this
  is conservative. Both standards ask for all elements from the hook to the pedestal; results
  state that the stiffness is rope-only.
- **DNV accelerations are zero and SH is omitted.** Ship-motion inertia (DNV 4.1.5.1) is
  Case III, which is out of scope, so both DNV in-service cases carry no vessel
  accelerations; only heel/trim gives a lateral (`psi * W * sin(theta)`, Case II at 1.5x).
  Horizontal operational loads SH are omitted (owner decision) and the details say so.
- **The Scene follows the selected condition and case.** The Scene is a single state, so it
  runs under the chart's selected condition and the governing case's own case rather than
  taking its own rules inputs.
- **Manual `daf` override.** A `hook_daf` other than the default 1.0 replaces the standard's
  factor for every case of every condition. Both values are always computed, and the details
  and CSV show the override record with `source=override` next to the computed one.
- **Schema `11.1.0`** (minor bump): `rules`, `conditions`, per-hoist `rope` and
  `max_hoisting_speed_m_s`. Documents without `rules` load and compute as before.

## Consequences

- Adding a standard is a new profile in `rules/`; `calculation/` does not change.
- `tests/test_architecture.py` forbids `calculation/` importing `rules`; `core` imports
  `rules` at run time and `rules` imports `core` only for types.
- Reported numbers carry their clause trail (details panel, CSV columns).
- Known limitations, all documented in the design (sections 6 and 9.7):
  - ABS PF does not multiply the wind force on the suspended load (9.7 item 11). This is
    non-conservative by `(PF - 1) * F_wind,load`, at most half that force; the owner must
    confirm. `test_abs_pf_leaves_the_load_wind_unfactored_documented_limitation` pins it.
  - Heel/trim-below-minimum warnings (ABS Table 5A, DNV Table 4-1) are not implemented: the
    document has no vessel type. Entered values are used as entered.
  - The Hs-based default velocities (ABS Tables 6 and 7, DNV 8.2.2.3 and 8.2.2.5) are not
    used; offboard velocities are required inputs.
  - The hook lateral direction is free per limit and its magnitude is a 16-gon bound
    (at most 1.96 % high on magnitude limits); `GoverningCase` does not record the
    governing lateral.
