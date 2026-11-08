"""Independent hand-calculation oracle for the ABS / DNV crane-load rules.

Written only from the standards' equations. It imports nothing from ``src``.
SI units: kN, m, s. Page numbers are printed page numbers.

ABS: Requirements for Certification of Lifting Appliances, January 2026.
DNV: DNV-ST-0378, July 2019 (amended October 2021).
"""

from __future__ import annotations

import math

G = 9.81  # m/s^2, ABS 2-2/9.3.2 (p.53)


def abs_vaf_onboard(ll_kN: float, a_v_g: float) -> float:
    """ABS 2-2/9.3.1 (p.53): 1.373 - LL/5220 + a_v, within [1.1+a_v, 1.33+a_v]."""
    raw = 1.373 - ll_kN / 5220.0 + a_v_g
    return min(max(raw, 1.1 + a_v_g), 1.33 + a_v_g)


def abs_v_hmin(h_sig: float) -> float:
    """ABS 2-2/9.3.2 (p.54): 0.01 + 0.098*Hsig (Hsig <= 1.8 m), else 0.067*(Hsig+1)."""
    if h_sig <= 1.8:
        return 0.01 + 0.098 * h_sig
    return 0.067 * (h_sig + 1.0)


def abs_v_r(v_h: float, v_d: float, v_c: float) -> float:
    """ABS 2-2/9.3.2 (p.53): v_r = v_h + sqrt(v_d^2 + v_c^2)."""
    return v_h + math.sqrt(v_d**2 + v_c**2)


def abs_vaf_offboard(ll_kN: float, k_kN_m: float, v_r: float, a_v_g: float) -> float:
    """ABS 2-2/9.3.2 (p.53): 1 + v_r*sqrt(K/(g*LL)), not less than the onboard VAF."""
    raw = 1.0 + v_r * math.sqrt(k_kN_m / (G * ll_kN))
    return max(raw, abs_vaf_onboard(ll_kN, a_v_g))


def abs_heavy_lift_vaf(a_v_g: float) -> float:
    """ABS 2-2/11.3 (p.56-57): VAF = 1.1 in mild conditions, plus a_v."""
    return 1.1 + a_v_g


def abs_pedestal_factor(ll_kN: float, crane_class: str) -> float:
    """ABS 2-2/5.15 (p.46): PF = 1.56 - LL/4000, max 1.5, min 1.2 offshore / 1.0 heavy lift."""
    lower = {"offshore": 1.2, "heavy_lift": 1.0}[crane_class]
    return min(max(1.56 - ll_kN / 4000.0, lower), 1.5)


def abs_list_trim_load(l_kN: float, list_deg: float, trim_deg: float) -> float:
    """ABS 2-2/5.21 (p.50): HL_SIA = L*sin(sqrt(list^2 + trim^2)), angles in degrees."""
    return l_kN * math.sin(math.radians(math.hypot(list_deg, trim_deg)))


def abs_live_load_wind_area(ll_kN: float) -> float:
    """ABS 2-2/5.19.3 (p.50): A_LL = 0.1215*LL^(2/3) m^2, LL in kN."""
    return float(0.1215 * ll_kN ** (2.0 / 3.0))


def abs_wind_pressure(v_m_s: float, cs: float) -> float:
    """ABS 2-2/5.19 (p.49): P = V^2*Cs/1637 kN/m^2, V in m/s."""
    return v_m_s**2 * cs / 1637.0


def dnv_psi(c: float, w_kN: float, v_r: float) -> float:
    """DNV 4.1.3.2 (p.54): psi = 1 + VR*sqrt(C/(W*g)); C in kN/m, W in kN."""
    return 1.0 + v_r * math.sqrt(c / (w_kN * G))


def dnv_psi_floor(w_kN: float) -> float:
    """DNV 8.2.2.1 (p.90): 1.3 up to 2500 kN, 1.5 - W/12500 to 5000 kN, 1.1 above.

    The standard states the 1.3 band for W > 10 kN; below that is not defined
    and 1.3 is returned.
    """
    if w_kN <= 2500.0:
        return 1.3
    if w_kN < 5000.0:
        return 1.5 - w_kN / 12500.0
    return 1.1


def dnv_v_h(h_s: float) -> float:
    """DNV 8.2.2.2 (p.91): VH = 0.1*(Hs + 1)."""
    return 0.1 * (h_s + 1.0)


def dnv_v_r(v_l: float, v_in: float, v_t: float, h_s: float) -> float:
    """DNV 8.2.2.1 (p.90): VR = 0.5*VL + sqrt(Vin^2+Vt^2); VH replaces 0.5*VL if larger."""
    lift = max(0.5 * v_l, dnv_v_h(h_s))
    return lift + math.sqrt(v_in**2 + v_t**2)


def dnv_sf1(swl_kN: float) -> float:
    """DNV 8.2.2.4 (p.91): SF1 >= 1.3 up to 2500 kN, >= 1.1 for 2500 kN and more."""
    return 1.3 if swl_kN < 2500.0 else 1.1


def hook_stiffness(ropes: list[tuple[float, float, float]]) -> float:
    """Series rope model: K = 1 / sum(t^2 * L / EA).

    Each tuple is (tension per unit hook load, reeved length m, EA kN).
    Design-owner model (spec section 6 item 2), not a clause of either standard.
    """
    return 1.0 / sum(t**2 * length / ea for t, length, ea in ropes)
