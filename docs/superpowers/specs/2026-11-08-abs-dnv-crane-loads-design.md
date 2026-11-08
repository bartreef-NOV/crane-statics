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
- **ABS PF and the 3.75× load** use LL as ABS defines it (SWL plus hook block plus suspended rope), including the amplification factor for PF.
- **`environment` when `rules` is present:** wind speed and `vessel_motion` move into conditions and are rejected under `environment`; gravity and air density stay there. A `rules` section with no conditions is rejected.
- **Manual `daf` override** applies to every case of every condition. Both values (computed and overridden) are always computed so the details view can show the difference.
- **0.07 g test for ABS heavy lift** is applied to each of |a_v| and |a_h| separately (the text says "these accelerations exceed 0.07 g").
- **Heavy lift and the 3.75× rule:** 5.13.5(c) cites 7, 9 and 11, so it applies to heavy lift; PF's heavy-lift floor is 1.0 (verified, p.46).

## 6. Unresolved (must be settled or verified before the affected work)
1. DNV barge / bulk-carrier case (8.2.2.5) uses a factor k that was not located; out of scope while Vin and Vt are required inputs.
2. Hook stiffness is settled (owner): a series spring model of the boom-hoist rope and the active-hoist rope, each as EA/L. L is the full rope length including the winch run, and every fall counts, including the dead-end fall. Stiffness is evaluated at the worst case over the hook's travel, which is the shortest rope (hook highest) because stiffer gives a higher ψ. An optional per-condition hook-height override (offboard lifts) replaces the worst case with the stiffness at that hook height. The field name is the builder's choice (the owner called it a "minimum hook height" override).
3. DNV wind on the crane structure (4.1.6) was not read; the existing structural wind areas are assumed to serve.

Resolved by the owner: DNV horizontal operational loads SH are **out of scope** (Case I = SG + ψ·SL, Case II adds SW; the details view states that SH is omitted). `crane_class` is rejected under DNV, the profile applies the 1.5× Case II heel/trim, and the suspended rope counts in DNV's working load (all confirmed).

## 7. Validation approach
No independent reference cases exist. They are built **before** the implementation and serve as its acceptance criteria (owner decision). They must be built: hand calculations from the standards' equations, written separately from the app's code, covering ABS onboard, ABS offboard, ABS heavy lift, DNV Case I and Case II, the ψ floor ranges, PF clamps, SF1, and the 3.75× load. Someone qualified signs off each. The existing 22689 validation workbook (`docs/crane-statics-validation-22689.xlsx`) covers the legacy path only.

## 8. Left to the builder
Module and class names, schema field names, phasing, internal data structures for provenance, test layout, and UI layout of the details view.
