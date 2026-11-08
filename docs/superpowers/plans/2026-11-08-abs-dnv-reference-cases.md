# ABS / DNV reference cases (sign-off sheet)

Oracle: `tests/rules_reference.py` (no `src` imports). Tests: `tests/test_rules_reference.py`.
Page numbers are printed page numbers. g = 9.81 m/s^2. Each case gives inputs, hand arithmetic, and the oracle value.

Sign-off status: PENDING. Reviewer: ______  Date: ______

## ABS (Requirements for Certification of Lifting Appliances, Jan 2026)

| # | Case | Clause, page | Inputs | Hand arithmetic | Oracle |
|---|---|---|---|---|---|
| A1 | Onboard VAF, mid range | 2-2/9.3.1, p.53 | LL 1000 kN, a_v 0 | 1.373 - 1000/5220 = 1.373 - 0.191571 | 1.181429 |
| A2 | Onboard VAF, cap | 2-2/9.3.1, p.53 | LL 100, a_v 0 | 1.373 - 0.019157 = 1.3538, capped at 1.33 | 1.33 |
| A3 | Onboard VAF, floor | 2-2/9.3.1, p.53 | LL 2000, a_v 0 | 1.373 - 0.383142 = 0.9899, floored at 1.1 | 1.1 |
| A4 | Onboard VAF with a_v | 2-2/9.3.1, p.53 | LL 1000, a_v 0.05 | 1.373 - 0.191571 + 0.05 (limits 1.15 to 1.38) | 1.231429 |
| A5 | Relative velocity | 2-2/9.3.2, p.53 | v_h 0.5, v_d 0.8, v_c 0.6 | 0.5 + sqrt(0.64 + 0.36) = 0.5 + 1.0 | 1.5 |
| A6 | Offboard VAF | 2-2/9.3.2, p.53 | LL 1000, K 5000 kN/m, v_r 1.5, a_v 0 | sqrt(5000/(9.81*1000)) = sqrt(0.509684) = 0.713922; 1 + 1.5*0.713922 | 2.070883 |
| A7 | Offboard never below onboard | 2-2/9.3.2, p.53 | LL 1000, K 5000, v_r 0 | 1 + 0 = 1.0 < 1.181429, so onboard governs | 1.181429 |
| A8 | v_hmin, Hsig <= 1.8 | 2-2/9.3.2, p.54 | Hsig 1.0 m | 0.01 + 0.098*1.0 | 0.108 |
| A9 | v_hmin, Hsig > 1.8 | 2-2/9.3.2, p.54 | Hsig 2.0 m | 0.067*(2.0 + 1) | 0.201 |
| A10 | Heavy lift VAF | 2-2/11.3, p.56-57 | a_v 0.05 | 1.1 + 0.05 | 1.15 |
| A11 | PF mid | 2-2/5.15, p.46 | LL 1000, offshore | 1.56 - 1000/4000 = 1.56 - 0.25 | 1.31 |
| A12 | PF upper clamp | 2-2/5.15, p.46 | LL 0, offshore | 1.56, clamped to 1.5 | 1.5 |
| A13 | PF offshore floor | 2-2/5.15, p.46 | LL 2000, offshore | 1.56 - 0.5 = 1.06, floored at 1.2 | 1.2 |
| A14 | PF heavy lift, unclamped | 2-2/5.15, p.46 | LL 2000, heavy lift | 1.56 - 0.5 | 1.06 |
| A15 | PF heavy lift floor | 2-2/5.15, p.46 | LL 3000, heavy lift | 1.56 - 0.75 = 0.81, floored at 1.0 | 1.0 |
| A16 | Live load wind area | 2-2/5.19.3, p.50 | LL 1000 kN | 0.1215 * 1000^(2/3) = 0.1215 * 100 | 12.15 m^2 |
| A17 | Wind pressure | 2-2/5.19, p.49 | V 20 m/s, Cs 1.0 | 400*1.0/1637 | 0.244350 kN/m^2 |
| A18 | List/trim load | 2-2/5.21, p.50 | L 1000 kN, list 5 deg, trim 2 deg | sqrt(25 + 4) = 5.385165 deg; sin = 0.093851; * 1000 | 93.85 kN |

Not yet covered by the oracle: the 3.75x retaining-component load (5.13.5(c), p.46) is a plain multiplier on the vertical live-load term (3.75 * VDL); it is exercised in the later load-building tasks.

## DNV-ST-0378 (July 2019, amended October 2021)

| # | Case | Clause, page | Inputs | Hand arithmetic | Oracle |
|---|---|---|---|---|---|
| D1 | Dynamic factor psi | 4.1.3.2, p.54 | C 5000 kN/m, W 1000 kN, V_R 1.3 | 1 + 1.3*sqrt(5000/(1000*9.81)) = 1 + 1.3*0.713922 | 1.928098 |
| D2 | psi floor band 1 | 8.2.2.1, p.90 | W 2000 kN | 1.3 for 10 < W <= 2500 | 1.3 |
| D3 | psi floor band 2 | 8.2.2.1, p.90 | W 3000 kN | 1.5 - 3000/12500 = 1.5 - 0.24 | 1.26 |
| D4 | psi floor band 3 | 8.2.2.1, p.90 | W 6000 kN | 1.1 for W > 5000 | 1.1 |
| D5 | Minimum hoist speed V_H | 8.2.2.2, p.91 | Hs 2.0 m | 0.1*(2.0 + 1) | 0.3 |
| D6 | Relative velocity, V_H governs | 8.2.2.1, p.90 | V_L 0.5, V_in 0.8, V_t 0.6, Hs 2.0 | 0.5*V_L = 0.25 < V_H 0.3, so 0.3 + sqrt(0.64 + 0.36) | 1.3 |
| D7 | SF1 small crane | 8.2.2.4, p.91 | SWL 2000 kN | 1.3 for up to 2500 kN | 1.3 |
| D8 | SF1 large crane | 8.2.2.4, p.91 | SWL 3000 kN | 1.1 for 2500 kN and more | 1.1 |

## Hook stiffness (series rope model, spec section 3.3 / 6 item 2; not a clause of either standard)

K = 1 / sum(t^2 * L / EA), t = rope tension per unit hook load.

| # | Case | Inputs (t, L m, EA kN) | Hand arithmetic | Oracle |
|---|---|---|---|---|
| H1 | One rope, 2 falls | (0.5, 100, 100000) | t^2 L/EA = 0.25*100/100000 = 2.5e-4; K = 1/2.5e-4 | 4000 kN/m |
| H2 | Hoist plus boom hoist | (0.5, 100, 100000), (0.5, 50, 200000) | 2.5e-4 + 0.25*50/200000 = 2.5e-4 + 0.625e-4 = 3.125e-4; K = 1/3.125e-4 | 3200 kN/m |

## Reviewer notes

- Equations were checked against the rendered PDF pages for ABS 9.3.1/9.3.2 (p.53), ABS 5.15 (p.46) and DNV 8.2.2.1 (p.90). The remaining equations (ABS 5.19, 5.21, 11.3, v_hmin; DNV 4.1.3.2, 8.2.2.2, 8.2.2.4) are taken from the spec's verified-requirements tables and should be re-checked by the reviewer against the PDF.
- The DNV psi floor is undefined at W exactly 5000 kN and for W <= 10 kN; the oracle returns 1.1 and 1.3 respectively (the formula is continuous at 5000 kN).
- DNV SF1 at exactly 2500 kN: the oracle uses 1.1 ("2500 kN and more").
