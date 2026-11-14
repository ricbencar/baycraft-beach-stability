"""Four-coefficient fit to 152 stored original Figure 4 curve readings.
Angles are numerical degrees. No interpolation or origin anchors were fitted.
r_ratio(theta,beta) = 0.56825724515506304*beta / (theta**0.8 * (1 + 0.0041871716600453499*beta + (beta/61.936329185906658)**4 * (1 - exp(-(theta/187.81986779226983)**9))))
"""
import math
A = 0.568257245155063
B = 0.00418717166004535
C = 61.93632918590666
D = 187.81986779226983

def r_ratio(theta: float, beta: float) -> float:
    if not (math.isfinite(theta) and math.isfinite(beta)):
        raise ValueError("Angles must be finite.")
    if theta <= 0 or beta < 0:
        raise ValueError("Require theta > 0 and beta >= 0 degrees.")
    power = (theta / D) ** 9 if theta / D < 2.0 else float("inf")
    gate = -math.expm1(-power)
    value = A*beta / (theta**0.8 * (1.0+B*beta+(beta/C)**4*gate))
    if not math.isfinite(value):
        raise ValueError("Non-finite model prediction.")
    return value
