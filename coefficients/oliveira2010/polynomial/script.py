#!/usr/bin/env python3
"""Fit the Oliveira & Barreiro (2010) workbook's parabolic coefficients.

Install:
    python -m pip install numpy openpyxl mpmath matplotlib
    python -m pip install scipy                 # optional minimax mode only

Run:
    python oliveira_polynomials.py oliveira2010_table1.xlsx
    python oliveira_polynomials.py "oliveira2010_table1(3).xlsx"
    python oliveira_polynomials.py --method minimax
    python oliveira_polynomials.py --degree 8 --prefix oliveira_degree8
    python oliveira_polynomials.py --one-based-labels

With no input argument, search the current directory and this script's directory
for oliveira2010_table1.xlsx, or one unambiguous numbered copy of that workbook.

Default: three independent, unweighted degree-six least-squares fits to ALL
records in sheet 'coeffs'. Keep duplicate observations. Use beta in DEGREES.
The source names are C0, C1, C2, in R/R0 = C0 + C1*q + C2*q**2, q=beta/alpha.
--one-based-labels renames these to C1, C2, C3 without changing any numbers.

Least squares uses an 80-decimal-digit QR solution in a scaled Chebyshev basis.
The expansion back into ordinary beta powers also uses high precision.
Minimax optionally uses SciPy/HiGHS to minimize the largest absolute error AT
THE INPUT ROWS. Its active constraints are refined in high precision and an
optimality certificate is checked when a nondegenerate active set is available.

Outputs, all next to one another in the working directory by default:
    oliveira_polynomials.txt       expanded equations, metrics, Python code
    oliveira_residuals.csv         every source record, predictions, residuals
    oliveira_coefficients.json     ordinary and scaled coefficients, metadata
    oliveira_fit.png               fitted curves and residuals (300 dpi)

The fit is an approximation to the supplied workbook, not an equation published
by Oliveira & Barreiro. More printed digits do not improve approximation error
or establish accuracy between observations. Do not extrapolate beyond the
reported beta interval. No origin, closure constraint, or outlier deletion is
introduced. The workbook itself is opened read-only and is not changed.

Numerical documentation:
    https://mpmath.org/doc/current/matrices.html
    https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import mpmath as mp
    import numpy as np
    from openpyxl import load_workbook
except ImportError as exc:
    raise SystemExit(
        f"Missing dependency: {exc.name}. Run:\n"
        "python -m pip install numpy openpyxl mpmath matplotlib"
    ) from exc


SOURCE_LABELS = ("C0", "C1", "C2")


@dataclass(frozen=True)
class Observation:
    row: int
    beach: str
    fit: str
    beta: str
    values: tuple[str, str, str]


def header_key(value):
    text = str(value or "").lower().translate(str.maketrans("₀₁₂₃", "0123"))
    text = text.replace("β", "beta")
    return re.sub(r"[^a-z0-9]", "", text)


def find_workbook(argument):
    if argument:
        path = Path(argument).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Workbook not found: {path}")
        return path
    directories = list(dict.fromkeys((Path.cwd(), Path(__file__).resolve().parent)))
    for directory in directories:
        exact = directory / "oliveira2010_table1.xlsx"
        if exact.is_file():
            return exact.resolve()
    candidates = sorted({p.resolve() for directory in directories
                         for p in directory.glob("oliveira2010_table1*.xlsx")
                         if not p.name.startswith("~$")})
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("No workbook found. Supply its path as the first argument.")
    raise ValueError("Several workbooks found. Supply one explicit path:\n" +
                     "\n".join(str(p) for p in candidates))


def decimal_cell(value, cell_name):
    if value is None or isinstance(value, bool):
        raise ValueError(f"Missing or invalid number at {cell_name}. "
                         "If it is a formula, recalculate and save the workbook in Excel.")
    text = str(value).strip().replace("−", "-")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        number = mp.mpf(text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid number at {cell_name}: {value!r}") from exc
    if not mp.isfinite(number):
        raise ValueError(f"Nonfinite number at {cell_name}: {value!r}")
    return text


def read_observations(path, requested_sheet):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        matches = [s for s in workbook.sheetnames if s.casefold() == requested_sheet.casefold()]
        if not matches:
            raise ValueError(f"Worksheet {requested_sheet!r} not found. "
                             f"Available sheets: {', '.join(workbook.sheetnames)}")
        sheet = workbook[matches[0]]
        columns = None
        records = []
        header_row = None
        for row_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if columns is None:
                keys = [header_key(value) for value in row]
                current = {}
                for field in ("beta", "c0", "c1", "c2"):
                    indices = [j for j, key in enumerate(keys) if key.startswith(field)]
                    if len(indices) == 1:
                        current[field] = indices[0]
                if len(current) == 4:
                    columns, header_row = current, row_no
                    for field, names in (("beach", ("praia", "beach")),
                                         ("fit", ("ajuste", "fit"))):
                        indices = [j for j, key in enumerate(keys)
                                   if any(key.startswith(name) for name in names)]
                        if indices:
                            columns[field] = indices[0]
                continue
            required = [row[columns[key]] for key in ("beta", "c0", "c1", "c2")]
            identifiers = [row[columns[key]] for key in ("beach", "fit") if key in columns]
            if all(v is None for v in required) and all(v is None for v in identifiers):
                continue
            numbers = [decimal_cell(value, f"{sheet.title}!row {row_no}, {field}")
                       for field, value in zip(("beta", "C0", "C1", "C2"), required)]
            def identifier(key):
                value = row[columns[key]] if key in columns else None
                return "" if value is None else str(value)
            records.append(Observation(row_no, identifier("beach"), identifier("fit"),
                                       numbers[0], tuple(numbers[1:])))
        if columns is None:
            raise ValueError(f"No beta/C0/C1/C2 header found in {sheet.title!r}.")
        if not records:
            raise ValueError("The coefficient table contains no observations.")
        return sheet.title, header_row, records
    finally:
        workbook.close()


def chebyshev_row(x, degree):
    values = [mp.mpf(1)]
    if degree:
        values.append(x)
    for _ in range(2, degree + 1):
        values.append(2 * x * values[-1] - values[-2])
    return values


def beta_power_basis(center, scale, degree):
    """Expand T_k((beta-center)/scale) using high-precision recurrences."""
    basis = [[mp.mpf(1)] + [mp.mpf(0)] * degree]
    if degree == 0:
        return basis
    shift, slope = -center / scale, 1 / scale
    basis.append([shift, slope] + [mp.mpf(0)] * (degree - 1))
    for k in range(2, degree + 1):
        term = [mp.mpf(0)] * (degree + 1)
        for j in range(degree + 1):
            term[j] = 2 * shift * basis[-1][j] - basis[-2][j]
            if j:
                term[j] += 2 * slope * basis[-1][j - 1]
        basis.append(term)
    return basis


def solve_minimax(design, y):
    """Minimize t subject to -t <= A*c-y <= t at every source row."""
    try:
        from scipy.optimize import linprog
    except ImportError as exc:
        raise ValueError("Minimax requires SciPy. Run: python -m pip install scipy") from exc
    n, p = design.rows, design.cols
    a_float = np.array(design.tolist(), dtype=float)
    y_float = np.array(list(y), dtype=float)
    inequalities = np.vstack((np.column_stack((a_float, -np.ones(n))),
                              np.column_stack((-a_float, -np.ones(n)))))
    objective = np.r_[np.zeros(p), 1.0]
    result = linprog(objective, A_ub=inequalities, b_ub=np.r_[y_float, -y_float],
                     bounds=[(None, None)] * p + [(0, None)], method="highs",
                     options={"primal_feasibility_tolerance": 1e-10,
                              "dual_feasibility_tolerance": 1e-10})
    if not result.success:
        raise ValueError(f"Minimax solver failed: {result.message}")
    coefficients = [mp.mpf(str(value)) for value in result.x[:p]]
    note = "HiGHS binary64 linear programming (feasibility tolerance 1e-10)"
    # Positive dual multipliers identify a minimal active constraint set.
    active = np.flatnonzero(np.asarray(result.ineqlin.marginals) < -1e-9)
    if len(active) == p + 1:
        active_matrix = mp.matrix(p + 1)
        active_rhs = mp.matrix(p + 1, 1)
        for i, index in enumerate(active):
            j, sign = int(index % n), 1 if index < n else -1
            for k in range(p):
                active_matrix[i, k] = sign * design[j, k]
            active_matrix[i, p] = -1
            active_rhs[i] = sign * y[j]
        try:
            refined = mp.lu_solve(active_matrix, active_rhs)
            dual = mp.lu_solve(active_matrix.T, mp.matrix([0] * p + [-1]))
            tolerance = mp.power(10, -(mp.mp.dps // 2)) * max(1, max(abs(v) for v in y))
            actual_max = max(abs(mp.fsum(design[j, k] * refined[k] for k in range(p)) - y[j])
                             for j in range(n))
            if (min(dual) >= -tolerance and refined[p] >= -tolerance
                    and actual_max <= refined[p] + tolerance):
                coefficients = list(refined[:p])
                note = (f"HiGHS active set refined at {mp.mp.dps} decimal digits; "
                        "primal feasibility and nonnegative dual certificate verified")
        except (ValueError, ZeroDivisionError):
            pass  # Keep and clearly label the original converged LP solution.
    return coefficients, note


def fit_series(design, values, basis, method):
    y = mp.matrix(values)
    if method == "least-squares":
        fitted, _ = mp.qr_solve(design, y)
        cheb = list(fitted)
        note = f"Unweighted least squares, QR, {mp.mp.dps} decimal digits"
    else:
        cheb, note = solve_minimax(design, y)
    powers = [mp.fsum(cheb[k] * basis[k][j] for k in range(design.cols))
              for j in range(design.cols)]
    predictions = [mp.fsum(design[j, k] * cheb[k] for k in range(design.cols))
                   for j in range(design.rows)]
    errors = [prediction - observed for prediction, observed in zip(predictions, values)]
    sse = mp.fsum(error * error for error in errors)
    mean = mp.fsum(values) / len(values)
    sst = mp.fsum((value - mean) ** 2 for value in values)
    r2 = None if sst == 0 else 1 - sse / sst
    worst = max(range(len(errors)), key=lambda j: abs(errors[j]))
    return dict(chebyshev=cheb, powers=powers, predictions=predictions, errors=errors,
                rmse=mp.sqrt(sse / len(values)), mae=mp.fsum(abs(e) for e in errors) / len(values),
                maximum=abs(errors[worst]), r2=r2, sse=sse, worst=worst, solver=note)


def expanded_equation(label, powers):
    result = f"{label}(beta) = {float(powers[0]):.16e}"
    for k, coefficient in enumerate(powers[1:], start=1):
        sign = " + " if coefficient >= 0 else " - "
        power = "*beta" if k == 1 else f"*beta^{k}"
        result += f"{sign}{abs(float(coefficient)):.16e}{power}"
    return result


def check_export(fits, center, scale, beta_min, beta_max):
    """Sample the effect of .16e coefficient export and binary64 Horner."""
    grid = np.linspace(float(beta_min), float(beta_max), 2001)
    checks = [mp.mpf(0)] * len(fits)
    exported = [[float(f"{float(v):.16e}") for v in fit["powers"]] for fit in fits]
    ordinary = [np.polynomial.polynomial.polyval(grid, coefficients) for coefficients in exported]
    for j, beta in enumerate(grid):
        row = chebyshev_row((mp.mpf(float(beta)) - center) / scale, len(exported[0]) - 1)
        for i, fit in enumerate(fits):
            exact = mp.fsum(c * t for c, t in zip(fit["chebyshev"], row))
            checks[i] = max(checks[i], abs(mp.mpf(float(ordinary[i][j])) - exact))
    for fit, error in zip(fits, checks):
        fit["export_error"] = error
    return len(grid)


def source_checks(records):
    signatures = [(mp.mpf(r.beta), *(mp.mpf(v) for v in r.values)) for r in records]
    groups = defaultdict(list)
    for record in records:
        groups[mp.mpf(record.beta)].append(record)
    messages = []
    for beta, group in sorted(groups.items()):
        for i, label in enumerate(SOURCE_LABELS):
            values = [mp.mpf(record.values[i]) for record in group]
            if max(values) != min(values):
                bound = (max(values) - min(values)) / 2
                messages.append(f"Conflicting {label} at beta={float(beta):g}: any single-valued "
                                f"fit has maximum error >= {float(bound):.9e} there.")
    return len(signatures) - len(set(signatures)), messages


def write_outputs(prefix, path, sheet, header_row, records, labels, fits, args,
                  center, scale, condition, export_points, pyplot):
    n = len(records)
    beta = [mp.mpf(record.beta) for record in records]
    lower, upper = min(beta), max(beta)
    duplicate_count, conflicts = source_checks(records)
    heading = ("EXPANDED SIXTH-DEGREE EQUATIONS" if args.degree == 6
               else f"EXPANDED DEGREE-{args.degree} EQUATIONS")
    lines = [heading, "-" * len(heading), ""]
    for label, fit in zip(labels, fits):
        lines.extend([expanded_equation(label, fit["powers"]), ""])
    lines.extend(["SOURCE AND FIT", "--------------",
                  f"Workbook: {path.name}", f"Worksheet: {sheet}; header row: {header_row}",
                  "Source columns: beta in degrees; C0 constant, C1 linear, C2 quadratic.",
                  "Workbook attribution: Oliveira & Barreiro (2010), Table 1, p. 127.",
                  f"Observations used: {n}; distinct beta values: {len(set(beta))}",
                  f"Exact repeated numeric records beyond first occurrences: {duplicate_count} (retained)",
                  f"Data interval: {float(lower):.12g} <= beta <= {float(upper):.12g} degrees",
                  f"Polynomial degree: {args.degree}; parameters per coefficient: {args.degree + 1}",
                  f"Method: {args.method}",
                  f"Scaled coordinate: x = (beta - {float(center):.16g}) / {float(scale):.16g}",
                  f"Scaled Chebyshev design condition number (binary64 diagnostic): {condition:.6g}",
                  "All input rows are used. No clipping, extra points, or coefficient normalization.",
                  "The separate 'Table 1' worksheet is not used as an additional data source.", ""])
    if args.one_based_labels:
        lines.extend(["DISPLAY LABEL MAPPING", "---------------------",
                      "Output C1 = source C0; output C2 = source C1; output C3 = source C2.",
                      "R/R0 = C1(beta) + C2(beta)*q + C3(beta)*q^2; q = beta/alpha.", ""])
    else:
        lines.extend(["R/R0 = C0(beta) + C1(beta)*q + C2(beta)*q^2; q = beta/alpha.", ""])
    lines.extend(["FIT ACCURACY AT THE SOURCE ROWS", "--------------------------------",
                  "Residual = fitted - observed. RMSE divides SSE by the number of source rows.",
                  f"{'Series':6s} {'R_squared':>17s} {'RMSE':>16s} {'MAE':>16s} {'Max_abs_error':>16s} {'SSE':>16s}"])
    for label, fit in zip(labels, fits):
        r2 = "undefined" if fit["r2"] is None else f"{float(fit['r2']):.12f}"
        lines.append(f"{label:6s} {r2:>17s} {float(fit['rmse']):16.9e} {float(fit['mae']):16.9e} "
                     f"{float(fit['maximum']):16.9e} {float(fit['sse']):16.9e}")
    lines.append("")
    for label, fit in zip(labels, fits):
        record = records[fit["worst"]]
        lines.append(f"{label}: largest error at beta={record.beta}, worksheet row {record.row}, "
                     f"beach={record.beach}, fit={record.fit}; {fit['solver']}.")
    lines.extend(["", "NUMERICAL EXPORT CHECK", "----------------------",
                  "Expanded coefficients contain 17 significant digits (.16e formatting).",
                  f"Binary64 Horner was compared with the fitted high-precision Chebyshev form at {export_points} grid points.",
                  "This sampled computational check is separate from the table-fitting errors above."])
    for label, fit in zip(labels, fits):
        lines.append(f"{label}: maximum sampled numerical discrepancy = {float(fit['export_error']):.9e}")
    lines.extend(["", "INTERPRETATION", "--------------",
                  "These are new regressions of the supplied coefficients, not published Oliveira polynomial equations.",
                  "Least squares minimizes the sum of squared table residuals for the selected degree.",
                  "Minimax minimizes the largest absolute table residual; it can increase RMSE.",
                  "Additional arithmetic digits do not remove the approximation error.",
                  "The interval above describes data coverage, not independently established model validity.",
                  "Neither high R-squared nor small table residuals establish accuracy between observations.",
                  "Avoid extrapolation. High degrees can oscillate between rows, especially across large beta gaps.",
                  "No condition C0+C1+C2=1 is imposed, because the supplied coefficients do not satisfy it exactly.",
                  "Use **, not ^, for exponentiation in Python. ^ is used only in the requested printed format."])
    if args.degree > 6:
        lines.append("A degree above six was explicitly selected. Check the plotted curve between observations.")
    lines.extend(conflicts)
    for label, fit in zip(labels, fits):
        if fit["export_error"] > max(mp.mpf("1e-10"), fit["rmse"] * mp.mpf("0.01")):
            lines.append(f"NUMERICAL WARNING: {label} loses accuracy in ordinary-power binary64 evaluation. "
                         "Prefer the scaled Chebyshev form saved in JSON.")
    lines.extend(["", "PYTHON COEFFICIENTS AND HORNER EVALUATOR", "---------------------------------------",
                  "# Ascending powers: constant, beta, beta**2, ..., beta**degree.", "COEFFICIENTS = {"])
    for label, fit in zip(labels, fits):
        numbers = ", ".join(f"{float(v):.16e}" for v in fit["powers"])
        lines.append(f"    {label!r}: ({numbers}),")
    lines.extend(["}", "", "def horner(coefficients, beta):", "    value = 0.0",
                  "    for coefficient in reversed(coefficients):",
                  "        value = value * beta + coefficient", "    return value", "",
                  "def coefficients(beta):", f"    if not {float(lower)!r} <= beta <= {float(upper)!r}:",
                  "        raise ValueError('beta is outside the fitted data interval')",
                  "    return tuple(horner(values, beta) for values in COEFFICIENTS.values())", ""])
    output_prefix = Path(prefix).expanduser().resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {key: Path(str(output_prefix) + suffix) for key, suffix in
             (("report", "_polynomials.txt"), ("residuals", "_residuals.csv"),
              ("coefficients", "_coefficients.json"), ("plot", "_fit.png"))}
    report = "\n".join(lines)
    paths["report"].write_text(report, encoding="utf-8")
    with paths["residuals"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["worksheet_row", "beach", "fit", "beta_deg"] +
                        [f"{label}_{field}" for label in labels for field in
                         ("observed", "fitted", "residual_fitted_minus_observed")])
        for j, record in enumerate(records):
            row = [record.row, record.beach, record.fit, record.beta]
            for i, fit in enumerate(fits):
                row.extend([record.values[i], f"{float(fit['predictions'][j]):.16e}",
                            f"{float(fit['errors'][j]):.16e}"])
            writer.writerow(row)
    payload = {"source_workbook": path.name, "sheet": sheet, "source_header_row": header_row,
               "n_observations": n, "duplicates_retained": duplicate_count, "method": args.method,
               "degree": args.degree, "arithmetic_decimal_digits": args.dps,
               "beta_unit": "degrees", "beta_interval": [float(lower), float(upper)],
               "scaled_coordinate": {"center": str(center), "half_range": str(scale)},
               "ordinary_power_order": "ascending; beta in degrees",
               "chebyshev_order": "T0, T1, ..., Tn; x=(beta-center)/half_range", "coefficients": {}}
    for source, label, fit in zip(SOURCE_LABELS, labels, fits):
        payload["coefficients"][label] = {
            "source_column": source, "solver": fit["solver"],
            "beta_powers": [float(v) for v in fit["powers"]],
            "beta_powers_decimal": [mp.nstr(v, args.dps - 10) for v in fit["powers"]],
            "scaled_chebyshev": [float(v) for v in fit["chebyshev"]],
            "scaled_chebyshev_decimal": [mp.nstr(v, args.dps - 10) for v in fit["chebyshev"]],
            "rmse": float(fit["rmse"]), "max_abs_error": float(fit["maximum"]),
            "r_squared": None if fit["r2"] is None else float(fit["r2"]),
            "sampled_export_error": float(fit["export_error"])}
    paths["coefficients"].write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if pyplot is not None:
        grid = np.linspace(float(lower), float(upper), 1601)
        x_grid = (grid - float(center)) / float(scale)
        beta_float = np.array(beta, dtype=float)
        fig, axes = pyplot.subplots(2, 3, figsize=(13.8, 7.5), sharex="col", layout="constrained",
                                    gridspec_kw={"height_ratios": [2.0, 1.0]})
        for i, (label, fit) in enumerate(zip(labels, fits)):
            predicted = np.polynomial.chebyshev.chebval(x_grid, [float(c) for c in fit["chebyshev"]])
            axes[0, i].plot(grid, predicted, color="#176b78", lw=1.8, label=f"Degree {args.degree}")
            axes[0, i].scatter(beta_float, [float(r.values[i]) for r in records], color="#e78b3c",
                               edgecolors="white", linewidths=0.5, s=30, zorder=3, label="Workbook")
            title = label if label == SOURCE_LABELS[i] else f"{label}  (source {SOURCE_LABELS[i]})"
            axes[0, i].set_title(title, fontsize=13, fontweight="bold")
            axes[0, i].set_ylabel("Coefficient (dimensionless)")
            axes[0, i].legend(frameon=False, fontsize=9)
            axes[0, i].text(0.97 if i == 1 else 0.03, 0.05,
                            f"RMSE {float(fit['rmse']):.3e}\nMax error {float(fit['maximum']):.3e}",
                            ha="right" if i == 1 else "left",
                            transform=axes[0, i].transAxes, fontsize=9,
                            bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none"})
            axes[1, i].axhline(0, color="#687481", lw=0.8)
            axes[1, i].scatter(beta_float, [float(e) for e in fit["errors"]], color="#176b78", s=19)
            axes[1, i].set_ylabel("Fitted - observed")
            axes[1, i].set_xlabel(r"$\beta$ (degrees)")
            axes[1, i].ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useMathText=True)
            for ax in axes[:, i]:
                ax.grid(alpha=0.18)
                ax.spines[["top", "right"]].set_visible(False)
        fig.suptitle(f"Oliveira workbook coefficient regressions | {args.method}\n"
                     f"{n} records; beta {float(lower):g} to {float(upper):g} degrees; degree {args.degree}",
                     fontsize=15)
        fig.savefig(paths["plot"], dpi=300, facecolor="white")
        if args.show:
            pyplot.show()
        pyplot.close(fig)
    else:
        paths.pop("plot")
    return report, paths


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workbook", nargs="?", help="Input .xlsx workbook (auto-detected if omitted)")
    parser.add_argument("--sheet", default="coeffs", help="Coefficient worksheet (default: coeffs)")
    parser.add_argument("--degree", type=int, default=6, help="Polynomial degree (default: 6)")
    parser.add_argument("--dps", type=int, default=80, help="Working decimal precision, at least 40 (default: 80)")
    parser.add_argument("--method", choices=("least-squares", "minimax"), default="least-squares")
    parser.add_argument("--prefix", help="Output path prefix; default oliveira, or oliveira_minimax in minimax mode")
    parser.add_argument("--one-based-labels", action="store_true", help="Display source C0/C1/C2 as C1/C2/C3")
    parser.add_argument("--no-plot", action="store_true", help="Skip the PNG plot; matplotlib is then not required")
    parser.add_argument("--show", action="store_true", help="Also open the plot window")
    args = parser.parse_args()
    if args.degree < 1:
        parser.error("--degree must be at least 1")
    if args.dps < 40:
        parser.error("--dps must be at least 40")
    if args.no_plot and args.show:
        parser.error("--show and --no-plot cannot be combined")
    return args


def main():
    args = parse_arguments()
    mp.mp.dps = args.dps
    try:
        path = find_workbook(args.workbook)
        sheet, header_row, records = read_observations(path, args.sheet)
        beta = [mp.mpf(record.beta) for record in records]
        if len(set(beta)) < args.degree + 1:
            raise ValueError(f"Degree {args.degree} requires at least {args.degree + 1} distinct beta values; "
                             f"found {len(set(beta))}.")
        center, scale = (min(beta) + max(beta)) / 2, (max(beta) - min(beta)) / 2
        design = mp.matrix([chebyshev_row((b - center) / scale, args.degree) for b in beta])
        basis = beta_power_basis(center, scale, args.degree)
        fits = [fit_series(design, [mp.mpf(r.values[i]) for r in records], basis, args.method)
                for i in range(3)]
        condition = float(np.linalg.cond(np.array(design.tolist(), dtype=float)))
        export_points = check_export(fits, center, scale, min(beta), max(beta))
        pyplot = None
        if not args.no_plot:
            try:
                import matplotlib
                if not args.show:
                    matplotlib.use("Agg")
                import matplotlib.pyplot as pyplot
            except ImportError as exc:
                raise ValueError("Plotting requires matplotlib. Install it or run with --no-plot.") from exc
        labels = ("C1", "C2", "C3") if args.one_based_labels else SOURCE_LABELS
        prefix = args.prefix or ("oliveira" if args.method == "least-squares" else "oliveira_minimax")
        report, paths = write_outputs(prefix, path, sheet, header_row, records, labels, fits, args,
                                      center, scale, condition, export_points, pyplot)
        print(report)
        print("FILES WRITTEN")
        for output in paths.values():
            print(output)
        return 0
    except (ValueError, OSError, ArithmeticError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
