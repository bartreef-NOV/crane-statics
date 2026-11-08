# ABS / DNV in-service crane loads: design

Status: draft for owner approval. Written after a brainstorming session with the application owner.
Standards basis: ABS *Requirements for Certification of Lifting Appliances*, January 2026 (`docs/rules/LiftingAppliancesjan2026.pdf`), and DNV-ST-0378 *Offshore and platform lifting appliances*, July 2019, amended October 2021 (`docs/rules/DNV-ST-0378.pdf`). Page numbers are the printed page numbers. The `.md` extracts in `docs/rules/` lose equations; always verify formulas against the PDFs.

## 1. Intent

Engineers run Crane Statics to (a) determine design loads for crane components and (b) plot capacity-vs-outreach load charts. Certification by ABS or DNV prescribes how the in-service loads are built (dynamic amplification, vessel motion, wind, inclination, extra factors on pedestal and slewing-bearing loads). Today the app has a manual per-hoist `daf` and one document-wide environment. This work adds the ABS and DNV load-building rules so the same crane can be assessed under a chosen standard across several lift scenarios, each with its own load chart.

### Goals
- A document selects one certifying standard (ABS or DNV). All results follow that standard's in-service rules.
- A document holds several user-defined lift conditions; each condition produces every load case its standard defines, with its own capacity chart and design loads.
- The dynamic factor is computed from the standard's formulas, not typed in.
- Each reported number can show its clause, inputs and whether it was computed or overridden.
- Documents without a `rules` section behave exactly as today.

### Non-goals
- Exceptional loadings (DNV Case III) and out-of-service cases.
- Acceptance checks: no allowable stresses, safety factors or pass/fail. The app reports loads only.
- Non-SI units. The app stays SI (t, m, kN).
- Boom and pedestal structural flexibility in the stiffness (see 3.3).
- Rigging weight as an input (it hangs from the hook and is already inside the weight on the hook).
- Fatigue, brakes, materials and every other section of the standards.

### Anti-goals
- ABS- or DNV-specific branching inside `calculation/`.
- Silent defaults: required velocities are never filled from the standards' simplified tables.
- A manual `daf` override that hides the fact that the rules would have given a different value.

## 2. Verified requirements (from the supplied PDFs)

### ABS
| Item | Requirement | Source |
|---|---|---|
| Live load LL | SWL plus the weight of the gear (hook, block, wire, etc.) and any other connected component moving with the hook load | 2-1/7.41 |
| Onboard offshore lift | VDL = LL·VAF_onb; VAF_onb = 1.373 − LL/5220 + a_v, limited to [1.1 + a_v, 1.33 + a_v]; LL in kN | 2-2/9.3.1, p.53 |
| Offboard offshore lift | VDL = LL·VAF_offb; VAF_offb = 1 + v_r·√(K/(g·LL)), not less than VAF_onb; v_r = v_h + √(v_d² + v_c²) | 2-2/9.3.2, p.53 |
| Hoisting speed floor | v_h not less than v_hmin = 0.01 + 0.098·Hsig (Hsig ≤ 1.8 m); 0.067·(Hsig + 1) (Hsig > 1.8 m) | 2-2/9.3.2, p.54 |
| Stiffness K | As specified by the manufacturer, taking into account all elements from the hook through the pedestal structure | 2-2/9.3.2, p.53 |
| Heavy lift crane | SWL not less than 1570 kN; VAF = 1.1 in mild conditions, plus accelerations per 5.17; if those exceed 0.07 g the offshore rules apply; minimum side load 0.02·VDL | 2-2/11.1, 11.3, p.56-57 |
| Minimum side load (offshore, onboard) | Total horizontal side load at boom tip not less than 0.02·VDL | 2-2/9.3.1, p.53 |
| Vessel motion loads | Component vertical load VL_DL = DL(1 + a_v); horizontal HL_DL = DL·a_h at each component's centre of gravity; live-load horizontal HL_LL = VDL·a_h at boom tip; direction chosen to maximise loading | 2-2/5.17, p.47-48 |
| Pedestal factor | PF = 1.56 − LL/4000 (LL in kN), at most 1.5, at least 1.2 (offshore) or 1.0 (heavy lift); multiplies the horizontal and vertical loads due to the live load (including amplification) for pedestals, kingposts, foundations | 2-2/5.15, p.46 |
| Retaining components of the slewing ring | Designed for overturning moments and vertical loads from the 5.1 loads using 3.75 times the vertical design load; overturning moment from a combination of in-plane and side-plane loading | 2-2/5.13.5(c), p.46 |
| Wind | P = V²·Cs/1637 kN/m² (V in m/s); Cs from Table 4; default in-service 10.3 m/s; wind speeds are specified by the manufacturer | 2-2/5.19, p.49 |
| In-service combination | Dead loads; live and dynamic loads with the vertical amplification; vessel motions (5.17); wind (5.19); list/trim (5.21); load swing from non-vertical lift; snow and ice. "The analysis is to be based on the worst combination of the above loads, as applicable." So ABS has one most-severe in-service case, found by searching directions | 2-2/5.1.1, p.40 |
| Wind force | HL_wind = P·A, added to the horizontal loads of the live load and each crane component; projected live-load area A_LL = 0.1215·LL^(2/3) m² (LL in kN) unless the manufacturer specifies it; open truss work may use 30% of the projected block area per face | 2-2/5.19.3, p.50 |
| List/trim load | HL_SIA = L·sin√(list² + trim²), horizontal, at each component's centre of gravity and at the boom tip for the lifted load; L is the dead load including vertical acceleration effects, or the live load including the amplification factor | 2-2/5.21, p.50 |
| In-service minimum inclination, Table 5A | When not specified by the manufacturer: ship/barge in calm water 5° list / 2° trim; bottom-supported structure, TLP, spar 0.5° / 0.5°; semi-submersible 1.5° / 1.5°; drillship/FPSO 2.5° / 1° | 2-2/5.21 Table 5A, p.51 |

### DNV
| Item | Requirement | Source |
|---|---|---|
| Working load W | Static weight of the useful load plus the weight of the accessories (sheave blocks, hooks, lifting beams, grab, etc.). Safe working load excludes accessories | 4.1.2.1 |
| Dynamic factor | ψ = 1 + VR·√(C/(W·g)); C = geometric stiffness at the hook (kN/m), taken from the hook to the pedestal support structure; un-used rope modulus per the manufacturer | 4.1.3.2, p.54 |
| ψ floor | 1.3 for 10 kN < W ≤ 2500 kN; 1.5 − W/12500 for 2500 < W < 5000 kN; 1.1 for W > 5000 kN; W is the maximum working load for the load curve | 8.2.2.1, p.90 |
| Relative velocity | VR = 0.5·VL + √(Vin² + Vt²); if 0.5·VL < VH, VH replaces 0.5·VL | 8.2.2.1, p.90 |
| Minimum hoisting speed | VH = 0.1·(Hs + 1) for cargo operations toward supply boats; if VL < VH the derating chart is shaded with a note on operator skill | 8.2.2.2, p.91 |
| Heel/trim minimum, still water | Ships 5°/2°; barges (L < 4B) and catamarans 3°/2°; semi-submersibles 3°/3°; submersibles and jack-ups 1°/1° | 4.1.2.3, Table 4-1, p.54 |
| Case I | SG + ψ·SL + SH (no wind) | 4.2.2.1 |
| Case II | SG + ψ·SL + SH + SW; floating-vessel heel/trim at least 1.5 times the 4.1.2.3 values | 4.2.3.1-4.2.3.2 |
| Wind on suspended load | Largest area facing the wind; C = 1.2 containers and similar shapes, 1.0 arbitrary shapes | 4.2.3.3 |
| Foundation factor SF1 | Operator cabin above the slewing bearing: foundation, pedestal and slewing bearing with fasteners use the crane-member design loads times SF1 ≥ 1.3 (capacity up to 2500 kN) or ≥ 1.1 (2500 kN and more); fatigue excepted | 8.2.2.4, p.91 |

Not applicable by owner decision: the Hs-based Vin, Vt, VL and v_d, v_c default formulas (DNV 8.2.2.3, 8.2.2.5; ABS Tables 6 and 7). They exist in the standards but the app requires the engineer to enter these velocities.

## 3. Decisions made with the owner

### 3.1 Document structure
- **`rules` section, once per document:** `standard: ABS | DNV`; ABS-only `crane_class: offshore | heavy_lift` (shipboard is out of scope); DNV-only `cabin_above_slewing_bearing: true | false`. `crane_class` is rejected under DNV (DNV-ST-0378 covers offshore and platform cranes; "heavy lift" appears there only as a definition). *The rejection under DNV is the builder's recommendation, not an explicit owner decision.*
- **Per hoist:** rope elastic modulus and metallic area, or EA directly; maximum steady hoisting speed (a fixed crane property). Same rope data for the boom hoist.
- **`conditions` list** replaces the single `environment` when `rules` is present. Each condition has: name, `lift: onboard | offboard`, wind speed, `vessel_motion` (accelerations, **heel and trim**, rotation), significant wave height Hs, Vin and Vt (required for offboard lifts), suspended-load projected wind area and drag coefficient (per condition).
- **Existing manual `daf`** stays as an override that wins over the computed factor; results flag when it is used.
- Under `heavy_lift`: onboard conditions only; accelerations above 0.07 g are rejected with a message pointing to the offshore requirements; no Hs, Vin, Vt.

### 3.2 Cases and outputs
- Each condition automatically produces every in-service case its standard defines (DNV Case I and Case II; ABS one most-severe in-service case). The engineer does not list cases.
- DNV Case II: the engineer enters the Case I heel and trim in `vessel_motion`; the DNV profile applies the 1.5 factor itself (builder's assumption, confirm).
- One capacity chart per condition. No envelope across conditions.
- Reported design loads include the pedestal factor (ABS PF, DNV SF1) for pedestal and slewing-bearing loads, and the ABS retaining-component load: live-load term (vertical and horizontal) at 3.75·VDL, dead-load effects at 1.0, PF not applied.
- Loads only; no acceptance checks.
- Traceability: each reported value carries clause, inputs, computed-or-overridden. Shown in an in-app details view and as extra columns in the chart CSV export.

### 3.3 Stiffness and dynamic factor
- Vertical hook stiffness (force at the hook per unit hook deflection) is derived, not entered: from rope EA/L of the boom hoist and the active hoist (series model, full rope length including the winch run and the dead-end fall), per outreach, using the existing reeving geometry. It is evaluated at the worst case over the hook's travel (shortest rope), unless a condition gives a hook-height override. Boom and pedestal flexibility are ignored. Owner rationale: higher stiffness gives a higher dynamic factor, so this is conservative. Results state that the stiffness is rope-only. The standards ask for all elements from the hook to the pedestal, so this is a documented deviation.
- The dynamic factor applies to the whole live load / working load (payload plus lower block mass plus suspended rope from the boom tip to the hook), both standards. For DNV the suspended rope is not named in the accessories list in 4.1.2.1; including it is an interpretation to confirm.
- Rated load shown on the chart is the weight lifted by the hook (full hook weight, including any rigging below it).
- The factor depends on the load (DNV: W; ABS: LL), so it is evaluated inside the chart's capacity search. The existing `DynamicFactor.hook_force_kN(payload)` interface supports this.

### 3.4 Compatibility
- A document with no `rules` section loads and gives exactly today's results. The schema gets a minor version bump.
- SI only.

## 4. Architecture (recommendation, not a standards requirement)
- New pure-Python `rules` package (no Qt) with an ABS profile and a DNV profile. Names are a guess until `tests/test_architecture.py` is checked. A profile takes the resolved condition, the hoist and the geometry and returns: a `DynamicFactor` object; the case list with per-case load settings (wind, heel/trim, minimum side load); post-factors (PF, SF1, 3.75×); and provenance records.
- `calculation/` sees only a dynamic factor, per-case load settings and multipliers. It never names ABS or DNV.
- `LoadCondition` (see `core/load_condition.py`) grows into a list of named conditions.
- A new calculation derives vertical hook stiffness per outreach from rope EA/L.
- Provenance records flow to the details view and the CSV export.

## 5. Calls made by the design author (not owner decisions; check these)
- **Hoisting speed below the minimum** (ABS v_hmin, DNV VH): not an error. The condition's results carry a "below minimum hoisting speed" warning; the CSV has a flag column. DNV's shaded chart region is deferred (no new renderer concept in this work).
- **Heel/trim below the standards' minimums** (ABS Table 5A, DNV Table 4-1): warning only, same mechanism.
- **DNV ψ floor:** the floor uses the largest working load on the condition's chart curve; the formula uses the working load at the point being evaluated.
- **ABS PF and the 3.75× load** use LL as ABS defines it (SWL plus hook block plus suspended rope). PF is evaluated from the **unamplified** LL (`PF = 1.56 − LL/4000`, LL = SWL + hook + suspended rope, no VAF); the loads PF multiplies are the live-load loads including the amplification (5.15).
- **`environment` when `rules` is present:** wind speed and `vessel_motion` move into conditions and are rejected under `environment`; gravity and air density stay there. A `rules` section with no conditions is rejected.
- **Manual `daf` override** applies to every case of every condition. Both values (computed and overridden) are always computed so the details view can show the difference.
- **0.07 g test for ABS heavy lift** is applied to each of |a_v| and |a_h| separately (the text says "these accelerations exceed 0.07 g").
- **Heavy lift and the 3.75× rule:** 5.13.5(c) cites 7, 9 and 11, so it applies to heavy lift; PF's heavy-lift floor is 1.0 (verified, p.46).

## 6. Unresolved (must be settled or verified before the affected work)
1. DNV barge / bulk-carrier case (8.2.2.5) uses a factor k that was not located; out of scope while Vin and Vt are required inputs.
2. Hook stiffness is settled (owner): a series spring model of the boom-hoist rope and the active-hoist rope, each as EA/L. L is the full rope length including the winch run, and every fall counts, including the dead-end fall. Stiffness is evaluated at the worst case over the hook's travel, which is the shortest rope (hook highest) because stiffer gives a higher ψ. An optional per-condition hook-height override (offboard lifts) replaces the worst case with the stiffness at that hook height. The field name is the builder's choice (the owner called it a "minimum hook height" override).
3. DNV wind on the crane structure (4.1.6) was not read; the existing structural wind areas are assumed to serve.
4. Heel/trim-below-minimum warnings (ABS 2-2/5.21 Table 5A, DNV 4.1.2.3 Table 4-1), which section 5 calls for, are **not implemented**. Both tables depend on the vessel or unit type, and the document has no vessel-type input. The entered heel and trim are used as entered.

Resolved by the owner: DNV horizontal operational loads SH are **out of scope** (Case I = SG + ψ·SL, Case II adds SW; the details view states that SH is omitted). `crane_class` is rejected under DNV, the profile applies the 1.5× Case II heel/trim, and the suspended rope counts in DNV's working load (all confirmed).

## 7. Validation approach
No independent reference cases exist. They are built **before** the implementation and serve as its acceptance criteria (owner decision). They must be built: hand calculations from the standards' equations, written separately from the app's code, covering ABS onboard, ABS offboard, ABS heavy lift, DNV Case I and Case II, the ψ floor ranges, PF clamps, SF1, and the 3.75× load. Someone qualified signs off each. The existing 22689 validation workbook (`docs/crane-statics-validation-22689.xlsx`) covers the legacy path only.

## 8. Left to the builder
Module and class names, schema field names, phasing, internal data structures for provenance, test layout, and UI layout of the details view.

## 9. Lateral live-load model

This section is the design note for the horizontal loads that the live load puts on the boom tip. It was written before the implementation.

### 9.1 What the standards ask for
- **ABS vessel motion, 2-2/5.17 (p.47-48):** `HL_LL = VDL · a_h`, with a_h in g, applied at the boom tip. "The angle of application of the horizontal loads is to be taken as such so as to induce the maximum loading on the crane."
- **ABS list and trim, 2-2/5.21 (p.50):** `HL_SIA = L · sin√(list² + trim²)`, applied at the boom tip for the lifted load. L is the live load including the vertical amplification, so L = VDL.
- **ABS wind, 2-2/5.19 (p.49-50):**
  - `HL_wind = P · A`, with `P = V² · Cs / 1637` kN/m² (V in m/s);
  - Cs is the condition's `load_drag_coefficient`;
  - A is the condition's `load_wind_area_m2`. When that area is 0, the 5.19.3 default `A_LL = 0.1215 · LL^(2/3)` m² applies (LL in kN), evaluated as described in 9.2.
- **ABS minimum side load, 2-2/9.3.1 (p.53), 9.3.2 (p.55) and 11.3 (p.57):** the total horizontal side load at the boom tip, including vessel motion, wind and inclination, is not to be less than `0.02 · VDL`.
- **DNV, 4.2.2 and 4.2.3:**
  - No ship-motion inertia: that belongs to Case III, which is out of scope.
  - The heel/trim of the case gives `W_hook · sin θ`. Case I uses the entered heel and trim. Case II uses 1.5 times them.
  - Case II adds wind on the suspended load (4.2.3.3): the largest area facing the wind, with C = 1.2 for containers and similar shapes and 1.0 for arbitrary shapes, entered as `load_drag_coefficient`.
  - The DNV wind force on the load is the app's standard aerodynamic wind force `F = 0.5 · ρ · C · V² · A / 1000` kN (`calculation.solver.crane_solver.wind_force_kN`). It is the same formula the solver applies to every structural wind area; ρ is `environment.air_density_kg_m3`.
  - Case I has no wind: its `CaseSpec` wind speed is 0.
  - DNV has no minimum side load.

### 9.2 Chosen formulas

H is the hook force: the amplified live load, VDL for ABS and ψ·W for DNV. `calculation/` takes the lateral load as a standard-neutral `HookLateral(fraction_x, fraction_y, constant_x_kN, constant_y_kN, min_fraction)`. The lateral force acting at the hoist's support node, which is where the off-lead force already enters, is

```
l(H) = f'·H + c        f' = (fraction_x, fraction_y) floored:  |f'| = max(|f|, min_fraction)
```

- **Fractions `f`** are the parts proportional to H: `a/g` and `sin(incline)`. The floor keeps the direction of `f`; when `f = 0` it acts along +x.
- **Constants `c`** are the wind force on the load, which is not proportional to H. `constant_x_kN` and `constant_y_kN` are the forces for a wind blowing along the x and y axes. A solve applies `constant_x · w_x` and `constant_y · w_y`, where `w = (V_x|V_x|, V_y|V_y|)/V²` are the signed squared direction cosines of the solve's wind. This is the same scaling as the structural wind, so an axis wind gives ±1 on one axis, and a solve without wind gives no constant.
- **`hook_lateral=None`** reproduces today's results bit for bit.

The `rules` profiles fill `LiftSetup.lateral` (`LateralSpec`, which now also carries the load wind force as a function of wind speed). Core turns it into a `HookLateral`:

| Term | ABS | DNV |
|---|---|---|
| H-proportional magnitude `r_c` | `hypot(a_x, a_y)/g + sin θ`, θ = √(list² + trim²) | `sin θ_case` (Case II: 1.5 × heel and trim) |
| Floor `m` | 0.02 | 0 |
| Load wind force at speed V | `V² · Cs · A / 1637` | `0.5 · ρ · C · V² · A / 1000` (the solver's wind formula) |
| Area A when `load_wind_area_m2` = 0 | `0.1215 · LL_max^(2/3)` (owner ruling, see below) | none: no wind on the load |
| Wind speed V | the condition's | Case I: 0; Case II: the condition's |

- **ABS default area:** `LL_max = (chart_max_load_t + hook mass + suspended rope) · g`, the same W the DNV ψ floor uses.
  - It is evaluated at the chart's maximum load, so the area is a constant and the solve stays linear in H. This is conservative.
  - It is set in `rules/abs_profile.py`.
  - The condition carries a warning, and a provenance record, saying that the default **was applied** at chart-max LL.
- **Retaining-component load (Task 12):** the 3.75× factor scales the H-proportional terms (`r`, the floor). It does not scale the wind constant. The owner confirmed this matches the intent. That is why the fractions and the constants are kept separate.

### 9.3 Composition with the off-lead and side-lead channels

An analysis point already carries unit responses to 1 kN of horizontal force at the support node:
- `offlead_lateral_unit_*` for crane-frame x, which is in the boom plane;
- `sidelead_lateral_unit_reactions` for y, which is out of the plane.

The hook lateral uses the **same unit-response mechanism**:
- sensitivity gains `f'_x · X + f'_y · Y`;
- baseline gains `c_x w_x · X + c_y w_y · Y`;
- X is the x unit and Y is the y unit. Rope tensions only see X.

Leads and the hook lateral add **linearly** at the support node: `sin(offlead) + f'_x` on x, and `sin(sidelead) + f'_y` on y.

One addition was needed. The existing x unit (`offlead_lateral_unit_reactions`) does not contain the left/right support entities (`heel_left`, `front_leg_right`, ...). An x force at the centreline splits half and half between them. The point therefore gains a complete x unit, `lateral_x_unit_reactions`: the off-lead unit plus 0.5 × its totals on each side. The hook lateral uses that complete unit (see 9.7, item 7).

### 9.4 Direction: maximising the demand

**Wind constant**
- The wind on the load blows with the structural wind. `candidate_wind_directions` (±X, ±Y) and the envelope's wind corners already enumerate those directions.
- In the chart envelope, the load-wind baseline is added to the wind probes: `wind_x += c_x · X` and `wind_y += c_y · Y`.
- Superposition then carries it to every wind corner and every wind angle with the structural wind, so no extra case is enumerated.
- The probes themselves (and their compute cache) stay free of the hook lateral.

**H-proportional part**
- Its direction is free: any horizontal direction u. ABS chooses the angle of application "so as to induce the maximum loading", and a chart point is already the worst over slew.
- The accelerations and the incline are taken in the same direction, so their magnitudes add (`r_c` above). The direction is chosen per limit, independently of the vessel sign case and slew the structural loads are enveloped over. This is conservative.
- In `chart_envelope.envelope_capacity_case`, each lead sign case (`_leads`, `lead_points` ~372) gains lateral candidates `r·u` with `r = max(r_c, m)`:
  - **Linear limits** (`_linear_capacity`): the limit quantity responds to the lateral as `R = (R_x, R_y)`, read from points composed with a unit x and a unit y lateral. Its sensitivity is largest at `u* = R/|R|`. The capacity `(L − B)/s` is smallest for the largest s, so `u*` is the exact worst direction. `−u*` is evaluated as well, and the lower capacity is kept. Both are real cases.
  - **Magnitude limits** (`_magnitude_capacity`: resultant, fradial, mradial, bearing line loads): the demand is convex in the lateral vector. The candidates are the 16 vertices of a polygon that circumscribes the circle `|l_H| = r`, at radius `r / cos(π/16)`. A hook load feasible at every vertex is feasible on the whole circle, so the result is never above the true minimum. It overestimates the H-proportional lateral by at most 1.96 %.
- **Solver** (`calculation/solver/crane_solver.py` off-lead at the support node ~376-446, `engine._augment_point_with_out_of_plane_loads` ~458):
  - A single solve takes exact signed values, like every other input, and adds `l` through the units described in 9.3.
  - `compute_omnidirectional_allowable_load` passes the same `HookLateral` to each of its wind directions, so the wind constant follows each wind.
- **`EnvelopeCase`** records the signed lateral fractions it was evaluated at, as `GoverningCase` does.
- **Auto-Set** (`limit_auto_set`): it maximises an opaque demand at the contractual hook force. For each wind/lead case it takes the worst of the 16 circumscribed-polygon directions, which is again conservative by at most 1.96 % of the lateral term.
- **Scene:** a single state, with no limit to maximise.
  - The direction is the Scene's crane-frame horizontal inertia direction, `−(a_x, a_y)` of its resolved motion with tilt folded in. When that is zero, the direction is +x.
  - The magnitude comes from the Scene condition.
  - The wind constant is taken at the Scene's wind speed and direction.
  - The drawn loads show the in-plane (x) part at the sheave, so the equilibrium check closes. The out-of-plane part is not drawn, like the side lead.

### 9.5 Where the minimum floor acts in the superposition

The floor `|l| ≥ m·H` is nonlinear in general: it is a magnitude, and the wind term is not proportional to H. It is made linear as follows:
- It acts on the **H-proportional part only**: `r = max(r_c, m)`. It is applied before the direction is maximised, so every candidate remains `baseline + s·H`, linear in H.
- Because the direction of `r·u` is free, the floor also holds in every direction, not only along the computed lateral.
- The load wind and the user's off-lead and side-lead add on top of the floored part. They are not counted toward the floor.
- Where the floor governs, this overstates the side load by at most the load wind force plus the lead force. It never understates it.
- An affine `baseline + s·H` per candidate is exactly what `compute_allowable_load` inverts, so no iteration on H is needed.

### 9.6 Worked example (ABS list/trim)

Given H = VDL = 1000 kN, list 5°, trim 2°, no accelerations and no wind:
- θ = √(5² + 2²) = 5.38516°.
- `r_c = sin 5.38516° = 0.0938505`. This is above the floor 0.02, so `r = 0.0938505`.
- `HL_SIA = 1000 · 0.0938505 = 93.85 kN` (`tests/rules_reference.abs_list_trim_load(1000, 5, 2) = 93.85`).

The solver adds this force at the support node: the point's sensitivity gains `0.0938505 · X`, and at H = 1000 kN every reaction changes by `93.85 · X`. The total horizontal platform reaction changes by 93.85 kN.

### 9.7 Decisions made without owner (conservative options, check these)
1. **Direction freedom.** The H-proportional lateral may point in any horizontal direction, chosen per limit. It is independent of the vessel sign case and slew that the structure's inertia is enveloped over, and the accelerations and the incline add in one direction.
2. **The floor covers only the H-proportional part.** The wind on the load and the off-lead/side-lead are added on top of `max(r_c, m)·H`, not counted toward the 0.02·VDL minimum.
3. **Leads and the hook lateral add linearly.** The ABS 9.3.2 combination formula for deck motion of the supporting vessel and own-vessel motion is lost in the text extract, and the linear sum bounds any root-sum-square combination.
4. **DNV incline lateral uses the amplified hook force,** `ψ·W·sin θ`, not `W·sin θ`.
5. **Polygon overestimate.** Magnitude limits and Auto-Set use a 16-gon circumscribing the circle of directions, which overestimates the lateral term by at most 1.96 %. Linear chart limits use the exact worst direction.
6. **Scene direction.** The Scene points the lateral along its own horizontal inertia (+x when there is none). `GoverningCase` records the governing lateral fractions, but the Scene does not apply them yet (carried to Task 14 with the rest of the Scene's rules migration).
7. **Finding (pre-existing, not changed).** `core/lead_channels.compose_lead_channel_point` adds the off-lead to the hinge totals but not to the left/right support entities. The chart envelope's off-lead effect on `heel_left`, `front_leg_right`, and so on is therefore missing: at GT283 MH 45°, offlead 5° and sidelead 3°, the `front_leg_left` Fz sensitivity composes to 4.880 instead of the solver's 5.240. Legacy results are kept bit for bit, so this is reported to the owner, not fixed. The hook lateral uses the complete x unit and is not affected.
