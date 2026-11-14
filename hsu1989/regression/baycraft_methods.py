#!/usr/bin/env python3
"""Baycraft: interactive bay-planform analysis with selectable models.

Run:
    python baycraft.py [project.bay]

Requirements: Python 3.10+ with Tkinter and Pillow.
    python -m pip install Pillow

Models (select from the Model list; angles in degrees):
    Hsu1989: parabolic shoreline planform with sixth-degree polynomials.
    Carvalho(2026): four-coefficient fit to original digitized Figure 4 curves.
Projects store the geometry, scale, georeference, styles, and an embedded PNG.
Use --calculate JSON for calculations without opening a window.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import io
import json
import math
import os
import re
import sys
import tempfile
import tkinter as tk
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError:
    Image = ImageDraw = ImageFont = ImageTk = None


DEFAULT_LINE_WIDTH = 5
IMAGE_CANVAS_BACKGROUND = "#3a3a3a"
DEFAULT_INCREMENT = 5.0
DEFAULT_ANGLE_LIMIT = 150.0
MAX_CURVE_SAMPLES = 100_000
PROJECT_EXTENSION = ".bay"
PROJECT_VERSION = 4
MODEL_HSU = "Hsu1989"
MODEL_CARVALHO = "Carvalho(2026)"
MODELS = (MODEL_HSU, MODEL_CARVALHO)
DEFAULT_MODEL = MODEL_HSU
# Carvalho (2026): four-coefficient fit to exactly 152 original Figure 4
# curve-stroke readings. No origin anchors, interpolated curves or synthetic
# polynomial data enter fitting. theta and beta are numerical degrees.
# Fixed structural powers: theta 4/5, beta 4, transition 9.
CARVALHO_A = 0.5682572445429198
CARVALHO_B = 0.004187171633856026
CARVALHO_C = 61.93632919114241
CARVALHO_D = 187.81986781272167
CARVALHO_EQUATION = "R/Rb = A*beta / (theta^0.8 * (1+B*beta+(beta/C)^4*(1-exp(-(theta/D)^9))))"
CARVALHO_FIT_SAMPLES = 152
CARVALHO_FIT_RMSE = 0.008263129575754754
CARVALHO_FIT_MAX_AE = 0.03382599705080214
CARVALHO_FIT_R2 = 0.9989586406687158
CARVALHO_INDEPENDENT_COEFFICIENTS = (
    ('A', CARVALHO_A), ('B', CARVALHO_B),
    ('C', CARVALHO_C), ('D', CARVALHO_D),
)
HSU_BETA_MIN = 10.0
HSU_BETA_MAX = 80.0
CONTROL_LABELS = ("H", "E", "W")
GEOREFERENCE_LABEL = "G"
CONTROL_LABEL_COLOR = "#b40000"
OBJECT_TYPES = {"curve": "Parabola", "ruler": "Measure", "polygon": "Polygon"}

# Independent sixth-degree least-squares fits to Hsu & Evans (1989), Table 2.
# Rows: C0, C1, C2. Columns: coefficients a0 ... a6 of beta**0 ... beta**6.
# The 15 published observations (beta = 10, 15, ..., 80 degrees) were fitted
# with equal weights and without adding an artificial beta=0 observation.
# Coefficients are carried at full reported precision; beta is in degrees.
HSU_COEFFICIENTS = (
    (
        -2.5948717948720286e-02,
         9.4371469397480281e-03,
        -4.0811322978137366e-04,
         1.0108930697786255e-05,
        -1.7860566448803580e-07,
         1.1488449630866086e-09,
        -1.3026029125105853e-12,
    ),
    (
         1.3292717948718358e+00,
        -6.5720015956185304e-02,
         4.6454080433615905e-03,
        -1.5110565213940694e-04,
         2.7247346369948383e-06,
        -2.3730284988490486e-08,
         7.7202155716091587e-11,
    ),
    (
        -2.9170512820513572e-01,
         5.4566218941018596e-02,
        -4.1688146498725922e-03,
         1.4006101055807072e-04,
        -2.5540727510077560e-06,
         2.2867190600936895e-08,
        -7.7541566334136543e-11,
    ),
)

def pixel_int(value: float) -> int:
    """Convert a finite drawing coordinate to an integer pixel."""
    if not math.isfinite(value):
        raise ValueError("Drawing coordinates must be finite.")
    coordinate = round(value)
    if abs(coordinate) > 2_147_483_647:
        raise ValueError("Drawing coordinates exceed the supported image range.")
    return coordinate


def sincos(angle: float) -> tuple[float, float]:
    """Return sine and cosine of a radian angle."""
    return math.sin(angle), math.cos(angle)


def hsu_coefficients(beta: float) -> tuple[float, float, float]:
    """Return Hsu1989 sixth-degree fitted coefficients for beta in degrees."""
    if not math.isfinite(beta):
        raise ValueError("Beta must be a finite angle in degrees.")
    if not (HSU_BETA_MIN - 1e-9 <= beta <= HSU_BETA_MAX + 1e-9):
        raise ValueError(
            f"Hsu1989 is valid for {HSU_BETA_MIN:g}° <= beta <= "
            f"{HSU_BETA_MAX:g}° (received {beta:.6g}°)."
        )
    # Horner's method evaluates each polynomial using all seven coefficients.
    values = tuple(
        _horner_polynomial(coefficients, beta) for coefficients in HSU_COEFFICIENTS
    )
    if not all(math.isfinite(c) for c in values):
        raise ValueError("Hsu1989 coefficients are not finite.")
    return values


def _horner_polynomial(coefficients: tuple[float, ...], beta: float) -> float:
    """Evaluate a polynomial whose coefficients are in ascending power order."""
    value = 0.0
    for coefficient in reversed(coefficients):
        value = value * beta + coefficient
    return value

def planform_ratio(
    theta: float,
    beta: float,
    model: str = DEFAULT_MODEL,
    coefficients: tuple[float, ...] | None = None,
) -> float:
    """Return the selected shoreline ratio R(theta)/Rb; angles are in degrees."""
    if model not in MODELS:
        raise ValueError(f"Unrecognized planform model: {model!r}.")
    if not (math.isfinite(theta) and math.isfinite(beta)):
        raise ValueError("Theta and beta must be finite angles in degrees.")
    if theta < 0 or beta < 0:
        raise ValueError("Theta and beta must be non-negative angles in degrees.")
    if theta == 0:
        raise ValueError(f"{model} is undefined at theta=0 degrees (beta/theta).")
    if model == MODEL_CARVALHO:
        # Stable evaluation of 1-exp(-x) using expm1; no origin observations
        # are fitted and no normalization is applied at theta=beta.
        scaled_theta = theta / CARVALHO_D
        power = scaled_theta**9 if scaled_theta < 2.0 else math.inf
        gate = -math.expm1(-power)
        ratio = CARVALHO_A * beta / (
            theta**0.8 * (1.0 + CARVALHO_B*beta + (beta/CARVALHO_C)**4*gate)
        )
        if not math.isfinite(ratio):
            raise ValueError(f"{model} planform ratio is not finite.")
        return ratio
    if not (HSU_BETA_MIN - 1e-9 <= beta <= HSU_BETA_MAX + 1e-9):
        raise ValueError(
            f"Hsu1989 requires beta between {HSU_BETA_MIN:g}° and "
            f"{HSU_BETA_MAX:g}°."
        )
    coeffs = coefficients if coefficients is not None else hsu_coefficients(beta)
    if len(coeffs) != 3 or not all(math.isfinite(value) for value in coeffs):
        raise ValueError("Expected three finite parabolic coefficients.")
    c0, c1, c2 = coeffs
    b_over_theta = beta / theta
    ratio = c0 + c1 * b_over_theta + c2 * b_over_theta**2
    if not math.isfinite(ratio):
        raise ValueError(f"{model} planform ratio is not finite.")
    return ratio


def wave_direction_from(h, e, w) -> float:
    """Wave FROM azimuth clockwise from north, given a north-up source image.

    The E-W control line is a wave crest. The offshore normal is selected
    to point toward H. The bearing is not a geographic CRS transformation.
    """
    crest_x = float(w[0]) - e[0]
    crest_y = float(w[1]) - e[1]
    crest_length = math.hypot(crest_x, crest_y)
    if crest_length == 0:
        raise ValueError("Cannot determine wave direction: E and W coincide.")

    east, south = -crest_y, crest_x
    headland_east = float(h[0]) - e[0]
    headland_south = float(h[1]) - e[1]
    normal_dot = east * headland_east + south * headland_south
    if abs(normal_dot) <= 1e-12 * crest_length * math.hypot(
        headland_east, headland_south
    ):
        raise ValueError(
            "Cannot determine offshore wave direction: H lies on the E-W crest line."
        )
    if normal_dot < 0:
        east, south = -east, -south

    return math.degrees(math.atan2(east, -south)) % 360.0


def fmt_bearing(degrees: float) -> str:
    """Format a compass bearing, normalizing rounding at north."""
    if not math.isfinite(degrees):
        return "Undefined"
    return f"{round(degrees % 360.0, 2) % 360.0:.2f}°"


def distance(a, b) -> float:
    """Euclidean distance without fixed-width integer arithmetic."""
    return math.hypot(float(b[0]) - a[0], float(b[1]) - a[1])


def polygon_area(points) -> float:
    """Area in source-image square pixels (shoelace formula)."""
    if len(points) < 3:
        return 0.0
    ox, oy = points[0]
    return abs(
        math.fsum(
            (px - ox) * (qy - oy) - (qx - ox) * (py - oy)
            for (px, py), (qx, qy) in zip(points[1:-1], points[2:])
        )
    ) / 2.0


def polygon_center(points) -> tuple[float, float]:
    """Arithmetic mean of polygon vertices for positioning its label."""
    if not points:
        return (0.0, 0.0)
    return (
        math.fsum(point[0] for point in points) / len(points),
        math.fsum(point[1] for point in points) / len(points),
    )


def midpoint(a, b) -> tuple[float, float]:
    return ((float(a[0]) + b[0]) / 2, (float(a[1]) + b[1]) / 2)


def rotate_point(point, angle=0, anchor=(0, 0)) -> tuple[float, float]:
    sine, cosine = sincos(math.radians(angle))
    x, y = point[0] - anchor[0], point[1] - anchor[1]
    return (x * cosine - y * sine + anchor[0], x * sine + y * cosine + anchor[1])


def source_point(display_point, angle=0, scale=100, anchor=(0, 0)):
    """Inverse screen transform, retaining subpixel precision."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Display zoom must be positive and finite.")
    point = (
        display_point[0] * 100.0 / scale,
        display_point[1] * 100.0 / scale,
    )
    return rotate_point(point, -angle, anchor)


def transform_point(point, angle=0, scale=100, anchor=(0, 0)):
    x, y = rotate_point(point, angle, anchor)
    return (pixel_int(x * scale / 100.0), pixel_int(y * scale / 100.0))


@dataclass(slots=True)
class CurveResult:
    beta: float
    rb: float
    orientation_deg: float
    model: str
    coefficients: tuple[float, ...]
    wave_direction_deg: float  # Arrival bearing FROM north, clockwise.
    theta: list[float] = field(default_factory=list)
    radii: list[float] = field(default_factory=list)
    points: list[tuple[int, int]] = field(default_factory=list)
    source_points: list[tuple[float, float]] = field(default_factory=list)


def curve_geometry(
    h, e, w, increment=DEFAULT_INCREMENT, limit=DEFAULT_ANGLE_LIMIT,
    model=DEFAULT_MODEL,
) -> CurveResult:
    """Sample the H-E-W shoreline geometry in the source-image coordinate system.

    Theta equals beta on ray H-E. Increasing theta rotates the ray toward
    the E-W wave-crest direction; all geometric calculations retain full
    floating-point precision until display coordinates are generated.
    """
    if model not in MODELS:
        raise ValueError(f"Unrecognized planform model: {model!r}.")
    if not math.isfinite(increment) or increment <= 0:
        raise ValueError("Angle increment must be positive and finite.")
    if not math.isfinite(limit):
        raise ValueError("Angle limit must be finite.")
    if any(
        len(point) != 2 or not all(math.isfinite(value) for value in point)
        for point in (h, e, w)
    ):
        raise ValueError("Each control point requires two finite coordinates.")

    vx, vy = float(e[0]) - h[0], float(e[1]) - h[1]
    tx, ty = float(w[0]) - e[0], float(w[1]) - e[1]
    rb, crest_length = math.hypot(vx, vy), math.hypot(tx, ty)
    if rb == 0 or crest_length == 0:
        raise ValueError("H and E, and E and W, must be distinct points.")

    cross = vx * ty - vy * tx
    dot = vx * tx + vy * ty
    beta = math.degrees(math.atan2(abs(cross), -dot))
    if not math.isfinite(beta):
        raise ValueError("The reference points do not define a finite angle.")
    if limit < beta - 1e-10:
        raise ValueError(
            f"Maximum theta ({limit:.2f}°) must not be below beta ({beta:.2f}°)."
        )

    coefficients = hsu_coefficients(beta) if model == MODEL_HSU else ()
    direction = wave_direction_from(h, e, w)
    orientation = math.degrees(math.atan2(vy, vx)) % 360.0
    result = CurveResult(
        beta=beta,
        rb=rb,
        orientation_deg=orientation,
        model=model,
        coefficients=coefficients,
        wave_direction_deg=direction,
    )
    count = max(1, int(math.floor((limit - beta) / increment + 1e-12)) + 1)
    if count > MAX_CURVE_SAMPLES:
        raise ValueError("This increment produces more than 100,000 curve samples.")
    signed_turn = 1.0 if cross > 0 else -1.0
    base_angle = math.atan2(vy, vx)
    for index in range(count):
        theta = beta + index * increment
        rn = planform_ratio(theta, beta, model, coefficients) * rb
        angle = base_angle + signed_turn * math.radians(index * increment)
        x = float(h[0]) + rn * math.cos(angle)
        y = float(h[1]) + rn * math.sin(angle)
        result.theta.append(theta)
        result.radii.append(rn)
        result.source_points.append((x, y))
        result.points.append((pixel_int(x), pixel_int(y)))
    return result


@dataclass(slots=True)
class Tool:
    kind: str
    points: list[tuple[float, float]]
    name: str = ""
    angle: int = 0
    scale: int = 100
    anchor: tuple[int, int] = (0, 0)
    increment: float = DEFAULT_INCREMENT
    limit: float = DEFAULT_ANGLE_LIMIT
    color: str = "#00ff00"
    width: int = DEFAULT_LINE_WIDTH
    controls: bool = True
    labels: bool = True
    visible: bool = True
    number: int = 0

    def displayed_points(self):
        return [
            transform_point(p, self.angle, self.scale, self.anchor) for p in self.points
        ]

    def result(self, model=DEFAULT_MODEL):
        """Compute in image coordinates, then transform geometry for display."""
        result = curve_geometry(*self.points, self.increment, self.limit, model)
        result.points = [
            transform_point(p, self.angle, self.scale, self.anchor)
            for p in result.source_points
        ]
        return result

    def identifier(self):
        return f"{OBJECT_TYPES[self.kind]} {self.number}" if self.number else OBJECT_TYPES[self.kind]

    def title(self):
        return f"{self.identifier()} — {self.name}" if self.name else self.identifier()

    def length_m(self, pixel_size):
        """Canonical metric measurement; shared by canvas, export and sidebar."""
        return distance(self.points[0], self.points[1]) * pixel_size

    def area_m2(self, pixel_size):
        return polygon_area(self.points) * pixel_size**2


@dataclass(slots=True)
class Project:
    tools: list[Tool] = field(default_factory=list)
    name: str = "Untitled"
    model: str = DEFAULT_MODEL
    image: object = None
    width: int = 0
    height: int = 0
    pixel_size: float = 1.0  # Meters per stored image pixel.
    scale_defined: bool = False
    reference_pixel: tuple[float, float] | None = None
    reference_xy: tuple[float, float] | None = None
    zoom: int = 100
    rotation: int = 0
    center: tuple[int, int] = (0, 0)
    filename: str = ""
    next_numbers: dict[str, int] = field(
        default_factory=lambda: {kind: 1 for kind in OBJECT_TYPES}
    )

    def new_number(self, kind):
        number = self.next_numbers[kind]
        self.next_numbers[kind] += 1
        return number

    def reconcile_numbers(self):
        """Ensure unique positive object numbers within each object type."""
        used = {kind: set() for kind in OBJECT_TYPES}
        for tool in self.tools:
            if tool.number > 0 and tool.number not in used[tool.kind]:
                used[tool.kind].add(tool.number)
            else:
                tool.number = 0
        for tool in self.tools:
            if tool.number == 0:
                candidate = 1
                while candidate in used[tool.kind]:
                    candidate += 1
                tool.number = candidate
                used[tool.kind].add(candidate)
        for kind in OBJECT_TYPES:
            self.next_numbers[kind] = max(
                self.next_numbers.get(kind, 1), max(used[kind], default=0) + 1
            )

    def calibrate(self, displayed_distance: float, meters: float) -> None:
        """Anchor a measured display distance to the underlying image."""
        if not all(
            math.isfinite(value) and value > 0 for value in (displayed_distance, meters)
        ):
            raise ValueError("Calibration distances must be positive finite values.")
        self.pixel_size = meters / displayed_distance * self.zoom / 100.0
        self.scale_defined = True

    @property
    def georeferenced(self) -> bool:
        return (
            self.scale_defined
            and self.reference_pixel is not None
            and self.reference_xy is not None
        )

    def georeference(self, source_pixel, x: float, y: float) -> None:
        """Register one known Easting/Northing at a pixel on a north-up image."""
        if not self.scale_defined:
            raise ValueError("Calibrate the image scale before georeferencing.")
        if len(source_pixel) != 2 or not all(math.isfinite(v) for v in source_pixel):
            raise ValueError("Reference pixel coordinates must be finite.")
        if not all(math.isfinite(v) for v in (x, y)):
            raise ValueError("Easting and Northing must be finite numeric values.")
        if self.width > 0 and self.height > 0 and not (
            0 <= source_pixel[0] < self.width
            and 0 <= source_pixel[1] < self.height
        ):
            raise ValueError("Reference point must lie within the source image.")
        self.reference_pixel = (float(source_pixel[0]), float(source_pixel[1]))
        self.reference_xy = (float(x), float(y))

    def world_xy(self, image_pixel) -> tuple[float, float]:
        """Convert source pixels to planar metres (X east, Y north)."""
        px, py = image_pixel
        if self.georeferenced:
            x0, y0 = self.reference_pixel
            east, north = self.reference_xy
            return (
                east + (px - x0) * self.pixel_size,
                north - (py - y0) * self.pixel_size,
            )
        # Preserve the original image-coordinate behaviour until anchored.
        return (px * self.pixel_size, py * self.pixel_size)

    def image_xy(self, world_coordinates) -> tuple[float, float]:
        """Invert world_xy for coordinate editing; returns source pixels."""
        x, y = world_coordinates
        if not all(math.isfinite(v) for v in (x, y)):
            raise ValueError("Coordinates must be finite numbers.")
        if self.georeferenced:
            x0, y0 = self.reference_pixel
            east, north = self.reference_xy
            return (
                x0 + (x - east) / self.pixel_size,
                y0 - (y - north) / self.pixel_size,
            )
        return (x / self.pixel_size, y / self.pixel_size)

    def snapshot(self):
        result = copy.copy(self)
        result.tools = copy.deepcopy(self.tools)
        result.next_numbers = dict(self.next_numbers)
        return result

    def set_view(self, zoom=None, rotation=None):
        if zoom is not None:
            self.zoom = int(zoom)
            for tool in self.tools:
                tool.scale = self.zoom
        if rotation is not None:
            self.rotation = int(rotation)
            for tool in self.tools:
                tool.angle, tool.anchor = self.rotation, self.center


def _finite_number(value, name, minimum=None):
    """Validate numeric fields before using project data."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _project_integer(value, name, minimum=None, maximum=None):
    value = _finite_number(value, name, minimum)
    if int(value) != value or (maximum is not None and value > maximum):
        raise ValueError(f"Invalid integer for {name}.")
    return int(value)


def _project_point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two coordinates.")
    return tuple(
        _project_integer(component, name, -2_147_483_648, 2_147_483_647)
        for component in value
    )


def _project_metric_point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two coordinates.")
    return tuple(float(_finite_number(v, name)) for v in value)


def _source_image_point(value, name):
    """Validate source-image positions without discarding subpixel accuracy."""
    px, py = _project_metric_point(value, name)
    if abs(px) > 2_147_483_647 or abs(py) > 2_147_483_647:
        raise ValueError(f"{name} coordinates exceed the supported pixel range.")
    return (px, py)


def load_project(filename):
    """Read a Baycraft project, including its embedded image and styles."""
    with Path(filename).open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict) or data.get("format") != "baycraft":
        raise ValueError("This is not a Baycraft project.")
    version = data.get("version")
    if isinstance(version, bool) or version not in (1, 2, 3, PROJECT_VERSION):
        raise ValueError("Unsupported Baycraft project version.")
    model = data.get("model", DEFAULT_MODEL)
    if version in (1, 2) and model not in MODELS:
        model = MODEL_HSU
    if model not in MODELS:
        raise ValueError(f"Unsupported Baycraft planform model: {model!r}.")
    # A missing calibration flag is treated conservatively: 1 m/pixel alone
    # does not prove that scale has been calibrated.
    if "scale_defined" in data:
        if not isinstance(data["scale_defined"], bool):
            raise ValueError("Project scale_defined must be true or false.")
        scale_defined = data["scale_defined"]
    else:
        scale_defined = data.get("pixel_size", 1.0) != 1.0
    project = Project(
        name=str(data.get("name", "Untitled")),
        scale_defined=scale_defined,
        reference_pixel=(
            _project_metric_point(data["reference_pixel"], "Reference pixel")
            if data.get("reference_pixel") is not None else None
        ),
        reference_xy=(
            _project_metric_point(data["reference_xy"], "Reference coordinates")
            if data.get("reference_xy") is not None else None
        ),
        model=model,
        filename=str(Path(filename).resolve()),
        width=_project_integer(data.get("width", 0), "Image width", 0),
        height=_project_integer(data.get("height", 0), "Image height", 0),
        pixel_size=_finite_number(data.get("pixel_size", 1.0), "Pixel size", 1e-12),
        zoom=_project_integer(data.get("zoom", 100), "Zoom", 10, 500),
        rotation=_project_integer(data.get("rotation", 0), "Rotation"),
        center=_project_point(data.get("center", [0, 0]), "Image center"),
    )
    if (project.reference_pixel is None) != (project.reference_xy is None):
        raise ValueError("A georeferenced project requires both reference pixel and XY.")
    if project.reference_pixel is not None and not project.scale_defined:
        raise ValueError("Georeferenced project has no calibrated scale.")
    next_numbers = data.get("next_numbers", {})
    if not isinstance(next_numbers, dict):
        raise TypeError("Object numbering data must be a dictionary.")
    for kind in OBJECT_TYPES:
        project.next_numbers[kind] = _project_integer(
            next_numbers.get(kind, 1), f"Next {kind} number", 1
        )
    if data.get("scale_reference", "display") == "display":
        project.pixel_size *= project.zoom / 100.0
    elif data["scale_reference"] != "image":
        raise ValueError("Unsupported scale reference.")
    tool_data = data.get("tools", [])
    if not isinstance(tool_data, list):
        raise TypeError("Project tools must be a list.")
    for item in tool_data:
        if not isinstance(item, dict):
            raise TypeError("Invalid project tool.")
        kind = item.get("kind")
        if kind not in {"curve", "ruler", "polygon"}:
            raise ValueError("Unsupported project tool.")
        point_data = item.get("points", [])
        if not isinstance(point_data, list):
            raise TypeError("Tool points must be a list.")
        points = [_source_image_point(point, "Tool point") for point in point_data]
        if (
            (kind == "curve" and len(points) != 3)
            or (kind == "ruler" and len(points) != 2)
            or (kind == "polygon" and len(points) < 3)
        ):
            raise ValueError("Incorrect number of tool points.")
        color = item.get("color", "#00ff00")
        if (
            not isinstance(color, str)
            or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
        ):
            raise ValueError("Tool color must be a six-digit hexadecimal color.")
        style = {}
        for key in ("controls", "labels", "visible"):
            value = item.get(key, True)
            if not isinstance(value, bool):
                raise TypeError(f"{key} must be true or false.")
            style[key] = value
        increment = _finite_number(
            item.get("increment", DEFAULT_INCREMENT), "Angle increment", 1e-12
        )
        limit = _finite_number(item.get("limit", DEFAULT_ANGLE_LIMIT), "Angle limit")
        if max(0.0, limit) / increment > MAX_CURVE_SAMPLES + 1:
            raise ValueError("The requested curve has too many samples.")
        project.tools.append(
            Tool(
                kind=kind,
                points=points,
                name=str(item.get("name", "")),
                angle=_project_integer(
                    item.get("angle", project.rotation), "Tool rotation"
                ),
                scale=_project_integer(
                    item.get("scale", project.zoom), "Tool scale", 10, 500
                ),
                anchor=_project_point(
                    item.get("anchor", project.center), "Tool anchor"
                ),
                increment=increment,
                limit=limit,
                color=color,
                width=_project_integer(
                    item.get("width", DEFAULT_LINE_WIDTH), "Line width", 1, 20
                ),
                number=_project_integer(item.get("number", 0), "Object number", 0),
                **style,
            )
        )
    project.reconcile_numbers()
    encoded = data.get("image_png")
    if encoded is not None:
        if Image is None:
            raise RuntimeError(
                "Install image support with: python -m pip install Pillow"
            )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise ValueError("Invalid embedded image data.") from exc
        with Image.open(io.BytesIO(raw)) as image:
            project.image = image.convert("RGB")
            project.image.load()
        project.width, project.height = project.image.size
    return project


def save_project(project, filename):
    """Save a self-contained project atomically to avoid partial files."""
    data = {
        "format": "baycraft",
        "version": PROJECT_VERSION,
        "name": project.name,
        "model": project.model,
        "width": project.width,
        "height": project.height,
        "pixel_size": project.pixel_size,
        "scale_defined": project.scale_defined,
        "reference_pixel": project.reference_pixel,
        "reference_xy": project.reference_xy,
        "scale_reference": "image",
        "zoom": project.zoom,
        "rotation": project.rotation,
        "center": project.center,
        "next_numbers": project.next_numbers,
        "tools": [asdict(tool) for tool in project.tools],
        "image_png": None,
    }
    if project.image is not None:
        if Image is None:
            raise RuntimeError("Pillow is required to save images.")
        buffer = io.BytesIO()
        project.image.convert("RGB").save(buffer, format="PNG")
        data["image_png"] = base64.b64encode(buffer.getvalue()).decode("ascii")
    path = Path(filename)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def fmt(value, decimals=2):
    if not math.isfinite(value):
        return (
            "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        )
    text = f"{value:,.{decimals}f}"
    return text.rstrip("0").rstrip(".") if decimals else text


def build_technical_report(project: Project, selected_index=None) -> str:
    """Prepare the full active-model technical report and sampled curve tables."""
    model = project.model
    if model not in MODELS:
        raise ValueError(f"Unsupported model: {model!r}.")
    image_state = (
        f"{project.width} x {project.height} image pixels"
        if project.image is not None else "No image imported"
    )
    report_objects = [
        (i, item) for i, item in enumerate(project.tools)
        if item.kind in {"curve", "polygon"}
    ]
    counts = {kind: sum(t.kind == kind for _, t in report_objects) for kind in ("curve", "polygon")}
    lines = [
        "BAYCRAFT - BAY PLANFORM TECHNICAL REPORT",
        "=" * 77,
        f"Planform model:      {model}",
        f"Background image:    {image_state}",
        f"Image scale:         {project.pixel_size:.12g} m / source-image pixel",
        f"Georeferenced:       {'Yes' if project.georeferenced else 'No'}",
        f"Current view:        zoom {project.zoom}%; rotation {project.rotation} degrees",
        f"Objects:             {counts['curve']} planform curves; "
        f"{counts['polygon']} polygons",
        "Coordinate system:   " + (
            "user-supplied planar XY (X east, Y north), metres"
            if project.georeferenced else "local image XY; x rightwards, y downwards"
        ),
        "Units:               lengths/radii in m; areas in m^2; angles in degrees",
        "",
        "1. METHOD AND EQUATIONS",
        "-" * 77,
        f"The H-E-W control geometry establishes beta and Rb and the {model}",
        "empirical model generates an idealized beach planform for comparison",
        "with an observed shoreline using three defining control points.",
        "",
        "Control points:",
        "  H = wave diffraction point (upcoast headland / structure tip)",
        "  E = downcoast beach control point",
        "  W = point along the downcoast wave-crest/tangent line",
        "  Rb = distance H-E",
        "  dEW = distance E-W; dHW = distance H-W",
        "",
        "Reference-angle geometry:",
        "  dAB = sqrt((xB-xA)^2 + (yB-yA)^2)",
        "  Rb = sqrt((xE-xH)^2 + (yE-yH)^2)",
        "  beta = acos((Rb^2 + dEW^2 - dHW^2) / (2 Rb dEW))",
        "  beta is evaluated in degrees from the H-E-W control points.",
        "",
        "Incident wave direction (FROM bearing, degrees clockwise from north):",
        "  0 = waves FROM N, 90 = FROM E, 180 = FROM S, 270 = FROM W.",
        "  E-W represents a wave crest, so wave approach is normal to E-W.",
        "  The offshore-facing normal is assumed to point toward H (headland tip).",
        "  The source image is assumed north-up, with x increasing eastward",
        "  and y increasing southward. View rotation is not map georeferencing.",
        "  For a rotated/unreferenced source image, rotate/georeference the",
        "  original map to north-up before interpreting geographic bearing.",
        "",
    ]
    if project.georeferenced:
        px, py = project.reference_pixel
        wx, wy = project.reference_xy
        insertion = lines.index("1. METHOD AND EQUATIONS")
        lines[insertion:insertion] = [
            f"Reference pixel:     column={px:.6f}, row={py:.6f} (source image)",
            f"Reference location:  X={wx:.6f} m, Y={wy:.6f} m",
            "Reference system:    supplied metric XY; EPSG/CRS not specified",
            "North-up assumption: original image top corresponds to north",
            "",
        ]
    if model == MODEL_HSU:
        lines += [
            "HSU1989 - PARABOLIC PLANFORM EQUATION",
            "  R(theta) / Rb = C0 + C1 (beta/theta) + C2 (beta/theta)^2",
            "  R(theta) = Rb [C0 + C1 beta/theta + C2 (beta/theta)^2]",
            "  theta(k) = beta + k Delta_theta, k = 0,1,..., theta <= theta_max",
            "  Rb and R(theta) have units of length; coefficients and ratios",
            "  are dimensionless. beta and theta use the SAME angle units",
            "  (degrees). The model is undefined at theta = 0 degrees.",
            "",
            "Sixth-degree coefficient polynomials fitted to",
            "Hsu & Evans (1989), Table 2 (15 observations, equal weights).",
            "  Ci(beta) = a0 + a1*beta + a2*beta^2 + a3*beta^3",
            "             + a4*beta^4 + a5*beta^5 + a6*beta^6",
            f"  Fitting reference-angle range: {HSU_BETA_MIN:g} to {HSU_BETA_MAX:g} degrees.",
            "  Polynomials apply only within the published 10° to 80° interval.",
            "",
        ]
    else:
        lines += [
            "CARVALHO(2026) - FOUR-COEFFICIENT IMAGE-CURVE APPROXIMATION",
            "  " + CARVALHO_EQUATION,
            "  R(theta) = Rb * r_ratio(theta,beta)",
            "  theta(k) = beta + k Delta_theta, k = 0,1,..., theta <= theta_max",
            "  theta and beta are numerical degrees; theta>0 and beta>=0.",
            "  Fixed model powers: theta=4/5, beta=4, transition=9.",
            "  Four fitted coefficients (full precision):",
            *[f"    {name} = {value:+.17g}" for name, value in CARVALHO_INDEPENDENT_COEFFICIENTS],
            "  Rb and R(theta) have length units; the ratio is dimensionless.",
            "  r(theta,0)=0 follows from the formula, not fitted origin anchors.",
            "  R(beta)/Rb is NOT forced to 1; the curve is not snapped to E.",
            "  Fit: 152 ORIGINAL image-digitized curve-stroke readings only.",
            "  No interpolated theta curves or synthetic Hsu values are fitted.",
            "  The 11 original theta curves span 30..270 degrees.",
            "  Digitized beta values span 5..80 degrees, within visible curves.",
            "  Grid theta=30..270 by 10 and beta=0..80 by 5 is prediction only",
            "  except where an exact original digitized reading is present.",
            f"  Reference RMSE = {CARVALHO_FIT_RMSE:.12f}; R2 = {CARVALHO_FIT_R2:.12f};",
            f"  Max absolute error = {CARVALHO_FIT_MAX_AE:.12f}.",
            "  These errors measure agreement with a digitized scan, not field accuracy.",
            "  Outside the digitized angular support, use is extrapolation.",
            "  Positive theta outside 30..270 is evaluated, but accuracy is unverified.",
            "",
        ]
    lines += [
        "Sampling and mapped coordinates:",
        "  Polar positions are evaluated in source-image coordinates from H",
        "  after resolving the orientation of H-E-W. Zoom and rotation alter",
        "  the display, not the original image-coordinate metric results.",
        "  Where a reference point is supplied (px0,py0) -> (X0,Y0):",
        "    X = X0 + (image_x - px0)*pixel_size  [east increases right]",
        "    Y = Y0 - (image_y - py0)*pixel_size  [north increases up]",
        "  Otherwise local image XY is used: x = image_x*pixel_size,",
        "  y = image_y*pixel_size (image y increases downwards).",
        "  These coordinates are invariant under display zoom/rotation.",
        "  L(m) = L(source pixels) * pixel_size",
        "  A(m^2) = A(source pixels^2) * pixel_size^2",
        "  Polygon area = 0.5*abs(sum_i(x_i*y_(i+1)-x_(i+1)*y_i)).",
        "  Polygon perimeter joins the last vertex to the first.",
        "",
        "Georeferencing assumes an original north-up, unskewed image, an",
        "accurate uniform scale, and supplied XY in a projected metric system.",
        "No EPSG code or map projection is inferred from one reference point.",
        "Physical accuracy depends on map scale, distortion and control quality.",
        "",
        "2. PROJECT OBJECTS AND COMPUTED RESULTS",
        "-" * 77,
    ]
    if not report_objects:
        lines.append("No planform or polygon objects in the project.")
    for report_index, (index, tool) in enumerate(report_objects, 1):
        lines += [
            "",
            f"2.{report_index} {tool.title()}",
            "~" * 77,
            f"Object type: {tool.kind}",
            f"Object ID: {tool.identifier()}",
            f"Custom name: {tool.name or '(none)'}",
            f"Selected on Results click: {'Yes' if index == selected_index else 'No'}",
            f"Visible: {tool.visible}; labels: {tool.labels}; control lines: {tool.controls}",
            f"Line color: {tool.color}; line width: {tool.width} pixels",
            "Control point XY (metres; original pixel column/row in brackets):",
        ]
        for j, (x, y) in enumerate(tool.points):
            label = CONTROL_LABELS[j] if tool.kind == "curve" else f"P{j + 1}"
            east, north = project.world_xy((x, y))
            lines.append(
                f"  {label:>3}: X={east:>15.7f} m  Y={north:>15.7f} m "
                f"[pixel column={x:.3f}, row={y:.3f}]"
            )
        if tool.kind == "polygon":
            perimeter = sum(
                distance(a, b) for a, b in
                zip(tool.points, tool.points[1:] + tool.points[:1])
            ) * project.pixel_size
            lines += [
                f"  Number of vertices = {len(tool.points)}",
                f"  Enclosed area      = {tool.area_m2(project.pixel_size):.9f} m^2",
                f"  Perimeter          = {perimeter:.9f} m",
            ]
        elif tool.kind == "curve":
            lines += [
                f"  Applied model             = {model}",
                f"  Angular step Delta_theta = {tool.increment:.9g} degrees",
                f"  Maximum theta            = {tool.limit:.9g} degrees",
            ]
            try:
                result = curve_geometry(
                    *tool.points, tool.increment, tool.limit, model
                )
                beta, radius = result.beta, tool.length_m(project.pixel_size)
                lines += [
                    f"  Rb (H-E)                 = {radius:.9f} m",
                    f"  dEW                      = {distance(tool.points[1],tool.points[2])*project.pixel_size:.9f} m",
                    f"  dHW                      = {distance(tool.points[0],tool.points[2])*project.pixel_size:.9f} m",
                    f"  Reference angle beta     = {beta:.9f} degrees",
                    f"  Wave direction (FROM)    = {fmt_bearing(result.wave_direction_deg)} "
                    "clockwise from north (north-up image assumed)",
                    f"  Curve orientation angle = {result.orientation_deg:.9f} degrees (image convention)",
                ]
                for i, value in enumerate(result.coefficients):
                    lines.append(f"  C{i}(beta) = {value:+.12g}")
                if model == MODEL_CARVALHO:
                    lines += [
                        "  " + CARVALHO_EQUATION,
                        *[f"  Carvalho {name} = {value:+.17g}" for name, value in CARVALHO_INDEPENDENT_COEFFICIENTS],
                        "  R(beta)/Rb is evaluated without normalization.",
                    ]
                ratio_at_beta = planform_ratio(beta, beta, model, result.coefficients)
                lines += [
                    f"  Model R(beta)/Rb          = {ratio_at_beta:.12g}",
                    f"  Model radius at theta=beta = {radius*ratio_at_beta:.9f} m",
                    f"  Number of output samples   = {len(result.theta)}",
                    "",
                    "  Sampled equilibrium planform:",
                    "  index    theta (deg)         R(theta) (m)       R(theta)/Rb         X (m)           Y (m)",
                ]
                for k, (theta, rad, (x, y)) in enumerate(
                    zip(result.theta, result.radii, result.source_points, strict=True), 1
                ):
                    east, north = project.world_xy((x, y))
                    lines.append(
                        f"  {k:>5d}  {theta:>14.2f}  {rad*project.pixel_size:>19.2f}"
                        f"  {rad/result.rb:>17.2f}  "
                        f"{east:>14.2f}  {north:>14.2f}"
                    )
            except (ValueError, OverflowError, ZeroDivisionError) as error:
                lines.append(f"  CURVE CALCULATION ERROR: {error}")
    lines += [
        "",
        "3. INTERPRETATION AND LIMITATIONS",
        "-" * 77,
        f"Compare the {model} modeled planform with the observed shoreline.",
        "Close alignment can be consistent with near-static equilibrium for",
        "the assumed predominant waves. Differences may arise from sediment",
        "supply, wave climate, engineering structures, reference-point choice,",
        "image distortion, or other processes. No erosion-rate, sediment-budget,",
        "or time-evolution prediction is made by the model overlay.",
        "",
        "4. MODEL REFERENCES / PROVENANCE",
        "-" * 77,
    ]
    if model == MODEL_HSU:
        lines += [
            "Hsu, J.R.C. and Evans, C. (1989). Parabolic bay shapes and applications.",
            "  Proceedings of the Institution of Civil Engineers, Part 2, 87, 557-570.",
            "  Table 2: coefficients C0, C1 and C2 for beta = 10° to 80°.",
            "  Sixth-degree polynomial regression with 15 equally weighted values.",
        ]
    else:
        lines += [
            "Carvalho (2026). Four-coefficient approximation to original",
            "  Hsu (1989) Figure 4 plotted curve-centreline readings.",
            "  " + CARVALHO_EQUATION,
            "  152 original digitized readings; 11 source theta profiles.",
            "  No common-origin anchors, interpolated references or synthetic data fitted.",
            "  Fixed powers selected from a finite candidate-form search.",
            "  theta and beta are inserted as numerical degree values.",
            "  Unobserved angular combinations are predictions, not graph observations.",
        ]
    lines += ["", "END OF REPORT", ""]
    return "\n".join(lines)


def save_technical_report(project: Project, filename, selected_index=None):
    """Write output.txt atomically (Unicode UTF-8) and return its path."""
    target = Path(filename)
    report = build_technical_report(project, selected_index)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=target.name + ".", suffix=".tmp", delete=False,
            newline="\n",
        ) as output:
            temporary_path = Path(output.name)
            output.write(report)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return target


class _WindowsWindow:
    """Keep native maximization inside the work area without border resizing."""

    WM_GETMINMAXINFO = 0x0024
    WM_NCHITTEST = 0x0084
    WM_SYSCOMMAND = 0x0112
    SC_SIZE = 0xF000

    def __init__(self, widget):
        import ctypes

        self.ctypes = ctypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.common = ctypes.WinDLL("comctl32", use_last_error=True)

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]

        class Rect(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_int32) for name in ("left", "top", "right", "bottom")
            ]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("size", ctypes.c_uint32),
                ("monitor", Rect),
                ("work", Rect),
                ("flags", ctypes.c_uint32),
            ]

        class MinMaxInfo(ctypes.Structure):
            _fields_ = [
                (name, Point)
                for name in (
                    "reserved",
                    "max_size",
                    "max_position",
                    "min_track",
                    "max_track",
                )
            ]

        self.Rect, self.MonitorInfo, self.MinMaxInfo = Rect, MonitorInfo, MinMaxInfo
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
        )
        self.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.user32.GetAncestor.restype = ctypes.c_void_p
        self.user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.user32.MonitorFromWindow.restype = ctypes.c_void_p
        self.user32.GetMonitorInfoW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(MonitorInfo),
        ]
        self.user32.GetMonitorInfoW.restype = ctypes.c_int
        self.user32.IsZoomed.argtypes = [ctypes.c_void_p]
        self.user32.IsZoomed.restype = ctypes.c_int
        self.user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(Rect)]
        self.user32.GetWindowRect.restype = ctypes.c_int
        self.user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self.user32.SetWindowPos.restype = ctypes.c_int
        self.common.SetWindowSubclass.argtypes = [
            ctypes.c_void_p,
            callback_type,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        self.common.SetWindowSubclass.restype = ctypes.c_int
        self.common.RemoveWindowSubclass.argtypes = [
            ctypes.c_void_p,
            callback_type,
            ctypes.c_size_t,
        ]
        self.common.RemoveWindowSubclass.restype = ctypes.c_int
        self.common.DefSubclassProc.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.common.DefSubclassProc.restype = ctypes.c_ssize_t
        self.window = self.user32.GetAncestor(widget.winfo_id(), 2)
        self.callback = callback_type(self._procedure)
        if not self.window or not self.common.SetWindowSubclass(
            self.window, self.callback, 1, 0
        ):
            raise OSError("Cannot configure the main window's sizing rules.")
        self.attached = True

    def monitor_info(self):
        info = self.MonitorInfo()
        info.size = self.ctypes.sizeof(info)
        monitor = self.user32.MonitorFromWindow(self.window, 2)
        return (
            info
            if self.user32.GetMonitorInfoW(monitor, self.ctypes.byref(info))
            else None
        )

    def _procedure(self, window, message, wparam, lparam, _identifier, _data):
        if message == self.WM_SYSCOMMAND and wparam & 0xFFF0 == self.SC_SIZE:
            return 0
        result = self.common.DefSubclassProc(window, message, wparam, lparam)
        if message == self.WM_GETMINMAXINFO and lparam:
            info = self.monitor_info()
            if info is not None:
                limits = self.ctypes.cast(
                    lparam, self.ctypes.POINTER(self.MinMaxInfo)
                ).contents
                work, monitor = info.work, info.monitor
                width, height = work.right - work.left, work.bottom - work.top
                limits.max_position.x = work.left - monitor.left
                limits.max_position.y = work.top - monitor.top
                limits.max_size.x, limits.max_size.y = width, height
                limits.max_track.x, limits.max_track.y = width, height
                limits.min_track.x = min(limits.min_track.x, width)
                limits.min_track.y = min(limits.min_track.y, height)
                return 0
        elif message == self.WM_NCHITTEST and 10 <= result <= 17:
            return 18  # A non-resizing border; the title bar remains movable.
        return result

    def ensure_work_area(self):
        """Check the settled outer frame, including its menu and decorations."""
        if not self.attached or not self.user32.IsZoomed(self.window):
            return
        info, rect = self.monitor_info(), self.Rect()
        if info is None or not self.user32.GetWindowRect(
            self.window, self.ctypes.byref(rect)
        ):
            return
        work = info.work
        if (
            rect.left < work.left
            or rect.top < work.top
            or rect.right > work.right
            or rect.bottom > work.bottom
        ):
            self.user32.SetWindowPos(
                self.window,
                None,
                work.left,
                work.top,
                work.right - work.left,
                work.bottom - work.top,
                0x0014,
            )

    def detach(self):
        if self.attached:
            self.common.RemoveWindowSubclass(self.window, self.callback, 1)
            self.attached = False


class BaycraftApp(tk.Tk):
    def __init__(self, filename=None):
        super().__init__()
        self.title("Baycraft")
        self._windows_window = None
        self._configure_fonts()
        self.after_idle(self._fit_window_to_screen)
        self.project = Project()
        self.history, self.future = [], []
        self.dirty = False
        self.selected = None
        self.mode = "select"
        self.pending = []
        self.drag = None
        self.preview_xy = None
        self.image_cache = None
        self.photo = None
        self._photo_bitmap = None
        self._syncing = False
        self.status = tk.StringVar(
            value="Import an image, then choose Parabola and click H, E, W."
        )
        self.coordinates = tk.StringVar(value="")
        self.zoom_var = tk.IntVar(value=100)
        self.rotation_var = tk.IntVar(value=0)
        self.model_var = tk.StringVar(value=self.project.model)
        self.mode_var = tk.StringVar(value="select")
        self.name_var = tk.StringVar()
        self.step_var = tk.StringVar(value="10")
        self.limit_var = tk.StringVar(value="150")
        self.line_var = tk.IntVar(value=DEFAULT_LINE_WIDTH)
        self.controls_var = tk.BooleanVar(value=True)
        self.labels_var = tk.BooleanVar(value=True)
        self.info_var = tk.StringVar(value="Select an object to view its properties.")
        self._widgets()
        self._bindings()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.refresh()
        if filename:
            self.after_idle(lambda: self.open_project(filename))

    def _configure_fonts(self):
        """Slightly enlarge standard widgets and emphasize control labels."""
        for name in tkfont.names(self):
            font = tkfont.nametofont(name, root=self)
            size = font.cget("size")
            font.configure(size=size + 2 if size >= 0 else size - 3)
        self.gui_font = tkfont.nametofont("TkDefaultFont", root=self)
        self.control_label_font = self.gui_font.copy()
        self.control_label_font.configure(
            size=max(16, abs(self.gui_font.cget("size")) + 5),
            weight="bold",
        )
        self.option_add("*Font", self.gui_font)
        self.option_add("*Menu.font", tkfont.nametofont("TkMenuFont", root=self))
        style = ttk.Style(self)
        style.configure(".", font=self.gui_font)
        style.configure("Treeview", rowheight=self.gui_font.metrics("linespace") + 6)
        style.configure("Treeview.Heading", font=self.gui_font)

    def _fit_window_to_screen(self):
        """Start maximized using the window manager's taskbar-aware sizing."""
        self.update_idletasks()
        if sys.platform == "win32":
            # Keep the normal native frame so Windows can reserve the taskbar.
            # Manual resizing is blocked by window messages instead of Tk flags.
            self.resizable(True, True)
            self.geometry(
                f"{max(1, self.winfo_screenwidth() - 80)}x"
                f"{max(1, self.winfo_screenheight() - 160)}+40+40"
            )
            self.update_idletasks()
            try:
                self._windows_window = _WindowsWindow(self)
            except OSError as exc:
                self.status.set(str(exc))
            self.state("zoomed")
            if self._windows_window is not None:
                self.after(200, self._windows_window.ensure_work_area)
            return
        self.resizable(False, False)
        self.geometry("+0+0")
        self.after(80, self._finish_screen_fit)

    def destroy(self):
        if self._windows_window is not None:
            self._windows_window.detach()
        super().destroy()

    def _finish_screen_fit(self):
        """Allow the window manager to place its decorations before measuring."""
        left = max(0, self.winfo_rootx())
        top = max(0, self.winfo_rooty())
        border = max(1, left)
        width = self.winfo_screenwidth() - left - border
        height = self.winfo_screenheight() - top - border
        self.geometry(f"{max(1, width)}x{max(1, height)}+0+0")

    def _widgets(self):
        menu = tk.Menu(self)
        self.configure(menu=menu)
        file = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="File", menu=file)
        for label, command, shortcut in [
            ("New", self.new_project, "Ctrl+N"),
            ("Open…", self.open_project, "Ctrl+O"),
            ("Import Image…", self.import_image, "Ctrl+I"),
            ("Save", self.save, "Ctrl+S"),
            ("Save As…", lambda: self.save(True), "Ctrl+Shift+S"),
        ]:
            file.add_command(label=label, command=command, accelerator=shortcut)
        file.add_separator()
        file.add_command(label="Export Image…", command=self.export_image)
        file.add_command(
            label="Print…", command=self.print_project, accelerator="Ctrl+P"
        )
        file.add_separator()
        file.add_command(label="Close", command=self.new_project)
        file.add_command(label="Exit", command=self.close_app)
        edit = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Edit", menu=edit)
        edit.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit.add_separator()
        edit.add_command(
            label="Delete", command=self.delete_selected, accelerator="Delete"
        )
        edit.add_command(label="Edit Color…", command=self.edit_color)
        edit.add_command(label="Numeric Results", command=self.numeric_results)
        view = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="View", menu=view)
        view.add_command(
            label="Zoom in", command=lambda: self.set_view(zoom=self.project.zoom + 10)
        )
        view.add_command(
            label="Zoom out", command=lambda: self.set_view(zoom=self.project.zoom - 10)
        )
        view.add_command(label="Original size", command=lambda: self.set_view(zoom=100))
        view.add_command(label="Fit Image", command=self.fit_image)
        view.add_separator()
        view.add_command(
            label="Rotate +90°",
            command=lambda: self.set_view(rotation=self.project.rotation + 90),
        )
        view.add_command(
            label="Rotate −90°",
            command=lambda: self.set_view(rotation=self.project.rotation - 90),
        )
        helpmenu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Help", menu=helpmenu)
        helpmenu.add_command(label="Help", command=self.help)
        helpmenu.add_command(
            label="About",
            command=lambda: messagebox.showinfo("About Baycraft", __doc__, parent=self),
        )
        top = ttk.Frame(self, padding=(5, 4))
        top.pack(fill="x")
        for text, command in [
            ("New", self.new_project),
            ("Open", self.open_project),
            ("Save", self.save),
            ("Import", self.import_image),
            ("Undo", self.undo),
            ("Redo", self.redo),
        ]:
            ttk.Button(top, text=text, command=command, width=max(5, len(text))).pack(
                side="left", padx=2
            )
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        for text, mode in [
            ("Select", "select"),
            ("Pan", "pan"),
            ("Zoom", "zoom"),
            ("Scale", "scale"),
            ("Georeference", "georeference"),
        ]:
            ttk.Radiobutton(
                top,
                text=text,
                value=mode,
                variable=self.mode_var,
                command=lambda m=mode: self.set_mode(m),
            ).pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(top, text="Zoom %").pack(side="left", padx=(4, 3))
        zoom = ttk.Spinbox(
            top,
            from_=10,
            to=500,
            increment=10,
            width=5,
            textvariable=self.zoom_var,
            command=self.view_inputs,
        )
        zoom.pack(side="left")
        zoom.bind("<Return>", self.view_inputs)
        ttk.Label(top, text="Rotate °").pack(side="left", padx=(10, 3))
        rotate = ttk.Spinbox(
            top,
            from_=-360,
            to=360,
            increment=5,
            width=5,
            textvariable=self.rotation_var,
            command=self.view_inputs,
        )
        rotate.pack(side="left")
        rotate.bind("<Return>", self.view_inputs)
        ttk.Button(top, text="Fit", command=self.fit_image, width=4).pack(
            side="left", padx=4
        )
        tools = ttk.Frame(self, padding=(5, 0, 5, 4))
        tools.pack(fill="x")
        for text, mode in [
            ("Parabola", "curve"),
            ("Polygon", "polygon"),
            ("Measure", "ruler"),
        ]:
            ttk.Radiobutton(
                tools,
                text=text,
                value=mode,
                variable=self.mode_var,
                command=lambda m=mode: self.set_mode(m),
            ).pack(side="left", padx=6)
        ttk.Separator(tools, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(tools, text="Results", command=self.numeric_results).pack(
            side="left", padx=2
        )
        ttk.Button(tools, text="Color", command=self.edit_color).pack(
            side="left", padx=2
        )
        ttk.Button(tools, text="Export", command=self.export_image).pack(
            side="left", padx=2
        )
        ttk.Label(tools, text="H → E → W").pack(side="left", padx=12)
        ttk.Separator(tools, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(tools, text="Model").pack(side="left", padx=(4, 5))
        self.model_selector = ttk.Combobox(
            tools, textvariable=self.model_var, values=MODELS,
            state="readonly", width=20,
        )
        self.model_selector.pack(side="left", padx=(0, 6))
        self.model_selector.bind("<<ComboboxSelected>>", self.set_model)
        split = self.workspace = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=5)
        # Keep the native and Tkinter left panels at the same nominal width.
        # Reserve most of the available height for Properties and Measurements.
        sidebar_width = max(390, self.gui_font.measure("0") * 34 + 32)
        objects_height = max(146, min(200, round(self.winfo_screenheight() * 0.22)))
        side = self.sidebar = ttk.Frame(
            split, width=sidebar_width, padding=(0, 0, 6, 0)
        )
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(0, weight=0, minsize=objects_height)
        side.rowconfigure(1, weight=1)
        split.add(side, weight=0)
        objects = self.objects_panel = ttk.LabelFrame(
            side, text="Project objects", padding=6, height=objects_height
        )
        objects.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        objects.grid_propagate(False)
        objects.columnconfigure(0, weight=1)
        objects.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(objects, show="tree", selectmode="browse", height=6)
        self.tree.grid(row=0, column=0, sticky="nsew")
        object_scroll = ttk.Scrollbar(
            objects, orient="vertical", command=self.tree.yview
        )
        object_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=object_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.tree_select)
        self.tree.bind("<Double-1>", lambda e: self.numeric_results())
        properties = self.properties_panel = ttk.LabelFrame(
            side, text="Properties", padding=6
        )
        properties.grid(row=1, column=0, sticky="nsew")
        properties.rowconfigure(6, weight=1)
        ttk.Label(properties, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(properties, textvariable=self.name_var, width=12).grid(
            row=0, column=1, sticky="ew", pady=1
        )
        for row, text, var in [
            (1, "Angle step (°)", self.step_var),
            (2, "Angle limit (°)", self.limit_var),
        ]:
            ttk.Label(properties, text=text).grid(row=row, column=0, sticky="w")
            ttk.Entry(properties, textvariable=var, width=9).grid(
                row=row, column=1, sticky="ew", pady=1
            )
        ttk.Label(properties, text="Line width").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(
            properties, from_=1, to=20, textvariable=self.line_var, width=7
        ).grid(row=3, column=1, sticky="ew", pady=1)
        ttk.Checkbutton(
            properties,
            text="Control lines",
            variable=self.controls_var,
            command=self.apply_properties,
        ).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Checkbutton(
            properties,
            text="Labels",
            variable=self.labels_var,
            command=self.apply_properties,
        ).grid(row=4, column=1, sticky="w", pady=2)
        actions = ttk.Frame(properties)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(actions, text="Apply", width=6, command=self.apply_properties).pack(
            side="left", fill="x", expand=True, padx=(0, 3)
        )
        ttk.Button(
            actions, text="Coordinates", width=12, command=self.edit_points
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(actions, text="Delete", width=6, command=self.delete_selected).pack(
            side="left", fill="x", expand=True
        )
        details_height = self.gui_font.metrics("linespace") * 5 + 28
        details = ttk.LabelFrame(
            properties, text="Measurements", padding=(6, 4), height=details_height
        )
        details.grid(row=6, column=0, columnspan=2, sticky="nsew")
        details.grid_propagate(False)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        ttk.Label(
            details,
            textvariable=self.info_var,
            justify="left",
            wraplength=sidebar_width - 50,
        ).grid(row=0, column=0, sticky="nw")
        properties.columnconfigure(1, weight=1)
        surface = ttk.Frame(split)
        split.add(surface, weight=1)
        self.canvas = tk.Canvas(
            surface, bg=IMAGE_CANVAS_BACKGROUND, highlightthickness=0, cursor="arrow"
        )
        horizontal = ttk.Scrollbar(
            surface, orient="horizontal", command=self.canvas.xview
        )
        vertical = ttk.Scrollbar(surface, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(
            xscrollcommand=horizontal.set, yscrollcommand=vertical.set
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        surface.rowconfigure(0, weight=1)
        surface.columnconfigure(0, weight=1)
        foot = ttk.Frame(self, padding=(7, 5))
        foot.pack(side="bottom", fill="x", before=split)
        ttk.Label(foot, textvariable=self.status).pack(side="left")
        ttk.Label(foot, textvariable=self.coordinates).pack(side="right")
        self.context = tk.Menu(self, tearoff=False)
        self.context.add_command(label="Numeric Results", command=self.numeric_results)
        self.context.add_command(label="Edit Color…", command=self.edit_color)
        self.context.add_command(label="Delete Vertex", command=self.delete_vertex)
        self.context.add_separator()
        self.context.add_command(label="Delete Object", command=self.delete_selected)

    def _bindings(self):
        for sequence, command in [
            ("<Control-n>", self.new_project),
            ("<Control-o>", self.open_project),
            ("<Control-i>", self.import_image),
            ("<Control-s>", self.save),
            ("<Control-Shift-S>", lambda: self.save(True)),
            ("<Control-z>", self.undo),
            ("<Control-y>", self.redo),
            ("<Control-p>", self.print_project),
            ("<Escape>", self.cancel),
            ("<Delete>", self.delete_selected),
        ]:
            self.bind(sequence, lambda event, c=command: c())
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion_drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Double-Button-1>", self.double_click)
        self.canvas.bind("<Button-3>", self.popup)
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind(
            "<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1)
        )
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.canvas.bind(
            "<Control-MouseWheel>",
            lambda e: self.set_view(
                zoom=self.project.zoom + (10 if e.delta > 0 else -10)
            ),
        )

    def current(self):
        return (
            self.project.tools[self.selected]
            if self.selected is not None
            and 0 <= self.selected < len(self.project.tools)
            else None
        )

    def set_model(self, event=None):
        """Apply the selected model to all curves, retaining undo and redo."""
        if self._syncing:
            return
        model = self.model_var.get()
        if model not in MODELS or model == self.project.model:
            self.model_var.set(self.project.model)
            return
        self.checkpoint()
        self.project.model = model
        self.refresh()
        self.status.set(f"Model set to {model} for all planform curves.")

    def checkpoint(self):
        self.history.append(self.project.snapshot())
        self.history = self.history[-100:]
        self.future.clear()
        self.dirty = True

    def undo(self):
        if self.history:
            self.future.append(self.project.snapshot())
            self.project = self.history.pop()
            self.selected = None
            self.dirty = True
            self.cancel()

    def redo(self):
        if self.future:
            self.history.append(self.project.snapshot())
            self.project = self.future.pop()
            self.selected = None
            self.dirty = True
            self.cancel()

    def confirm_save(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Baycraft", "Do you want to save changes to Document?", parent=self
        )
        return False if answer is None else self.save() if answer else True

    def new_project(self):
        if not self.confirm_save():
            return
        self.project = Project()
        self.history.clear()
        self.future.clear()
        self.dirty = False
        self.selected = None
        self.cancel()

    def open_project(self, filename=None):
        if not self.confirm_save():
            return
        if filename is None:
            filename = filedialog.askopenfilename(
                parent=self,
                title="Open Baycraft Project",
                filetypes=[
                    ("Baycraft Project", "*.bay"),
                    ("JSON", "*.json"),
                    ("All files", "*.*"),
                ],
            )
        if not filename:
            return
        try:
            project = load_project(filename)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            messagebox.showerror("Cannot open project", str(exc), parent=self)
            return
        self.project = project
        self.selected = None
        self.history.clear()
        self.future.clear()
        self.dirty = False
        self.cancel()
        self.refresh()
        self.status.set("Opened " + str(filename))

    def save(self, save_as=False):
        filename = self.project.filename
        if not filename or save_as:
            filename = filedialog.asksaveasfilename(
                parent=self,
                title="Save Baycraft Project",
                defaultextension=PROJECT_EXTENSION,
                filetypes=[("Baycraft Project", "*.bay")],
            )
        if not filename:
            return False
        previous_name = self.project.name
        self.project.name = Path(filename).stem
        try:
            save_project(self.project, filename)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self.project.name = previous_name
            messagebox.showerror("Cannot save project", str(exc), parent=self)
            return False
        self.project.filename = str(filename)
        self.dirty = False
        self.refresh()
        self.status.set("Saved " + str(filename))
        return True

    def import_image(self):
        if Image is None:
            messagebox.showerror(
                "Pillow required",
                "Install image support with:\npython -m pip install Pillow",
                parent=self,
            )
            return
        filename = filedialog.askopenfilename(
            parent=self,
            title="Import Image File",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return
        try:
            with Image.open(filename) as source:
                bitmap = source.convert("RGB")
                bitmap.load()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot import image", str(exc), parent=self)
            return
        self.checkpoint()
        self.project.image = bitmap
        self.project.pixel_size = 1.0
        self.project.scale_defined = False
        self.project.reference_pixel = None
        self.project.reference_xy = None
        self.project.width, self.project.height = bitmap.size
        self.project.center = (bitmap.width // 2, bitmap.height // 2)
        self.project.set_view(rotation=self.project.rotation)
        self.refresh()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.status.set(
            "Image imported. Select Parabola, then click the diffraction point H."
        )

    def close_app(self):
        if self.confirm_save():
            self.destroy()

    def set_mode(self, mode, *, redraw=True):
        if mode == "georeference" and not self.project.scale_defined:
            self.mode_var.set(self.mode)
            messagebox.showwarning(
                "Image scale required",
                "Set the image scale before assigning reference X/Y coordinates.",
                parent=self,
            )
            return
        if mode == "georeference" and self.project.image is None:
            self.mode_var.set(self.mode)
            messagebox.showwarning(
                "Image required", "Import an image before georeferencing.", parent=self
            )
            return
        self.pending.clear()
        self.preview_xy = None
        self.mode = mode
        self.mode_var.set(mode)
        self.canvas.configure(
            cursor={"select": "arrow", "pan": "fleur", "zoom": "crosshair"}.get(
                mode, "crosshair"
            )
        )
        self.status.set(
            {
                "curve": "Click the wave diffraction point (H).",
                "ruler": "Click the first measurement point.",
                "polygon": "Click polygon vertices; double-click or Enter to finish.",
                "scale": "Click the first end of a known distance.",
                "georeference": "Click a known point in the image and enter X (Easting), Y (Northing).",
                "select": "Select an object or drag its red control handles.",
                "pan": "Drag to pan the image.",
                "zoom": "Click to zoom in. Shift-click to zoom out.",
            }[mode]
        )
        self.canvas.bind("<Return>", lambda e: self.finish_polygon())
        if redraw:
            self.draw()

    def cancel(self):
        self.drag = None
        self.selected = None
        self.set_mode("select", redraw=False)
        self.refresh()

    def view_inputs(self, event=None):
        try:
            self.set_view(self.zoom_var.get(), self.rotation_var.get())
        except (ValueError, tk.TclError):
            self.status.set("Enter a valid zoom percentage and rotation angle.")

    def set_view(self, zoom=None, rotation=None):
        zoom = min(500, max(10, int(zoom))) if zoom is not None else None
        rotation = int(rotation) if rotation is not None else None
        if (zoom is None or zoom == self.project.zoom) and (
            rotation is None or rotation == self.project.rotation
        ):
            return
        self.checkpoint()
        self.project.set_view(zoom, rotation)
        self.pending.clear()
        self.refresh()

    def fit_image(self):
        if self.project.width and self.project.height:
            w, h = self.canvas.winfo_width() - 30, self.canvas.winfo_height() - 30
            self.set_view(
                zoom=min(w / self.project.width, h / self.project.height) * 100,
                rotation=0,
            )
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)

    def xy(self, event):
        return (
            pixel_int(self.canvas.canvasx(event.x)),
            pixel_int(self.canvas.canvasy(event.y)),
        )

    @staticmethod
    def near_segment(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        u = (
            max(
                0,
                min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)),
            )
            if dx or dy
            else 0
        )
        return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)

    def hit_test(self, xy):
        for index in range(len(self.project.tools) - 1, -1, -1):
            t = self.project.tools[index]
            if not t.visible:
                continue
            points = t.displayed_points()
            if any(distance(p, xy) < 10 for p in points):
                return index
            if t.kind == "curve":
                with suppress(ValueError):
                    points = t.result(self.project.model).points
            if t.kind == "polygon":
                points = points + points[:1]
            if any(self.near_segment(xy, a, b) < 8 for a, b in pairwise(points)):
                return index
        return None

    def press(self, event):
        self.canvas.focus_set()
        xy = self.xy(event)
        if self.mode == "pan":
            self.canvas.scan_mark(event.x, event.y)
            return
        if self.mode == "zoom":
            self.set_view(zoom=self.project.zoom + (-10 if event.state & 1 else 10))
            return
        if self.mode == "georeference":
            source_pixel = source_point(
                xy, self.project.rotation, self.project.zoom, self.project.center
            )
            if not (0 <= source_pixel[0] < self.project.width
                    and 0 <= source_pixel[1] < self.project.height):
                self.status.set("Choose a reference point inside the image.")
                return
            self._georeference_dialog(source_pixel)
            return
        if self.mode != "select":
            if not self.pending or xy != self.pending[-1]:
                self.pending.append(xy)
            if self.mode == "curve":
                if len(self.pending) == 3:
                    self.finish_tool("curve")
                else:
                    self.status.set(
                        (
                            "",
                            "Click the downcoast beach control point (E).",
                            "Click the wave-crest tangent endpoint (W).",
                        )[len(self.pending)]
                    )
            elif self.mode == "ruler" and len(self.pending) == 2:
                self.finish_tool("ruler")
            elif self.mode == "scale":
                if len(self.pending) == 2:
                    pixels = distance(*self.pending)
                    if pixels == 0:
                        self.status.set("Choose two different calibration points.")
                        self.pending.clear()
                    else:
                        meters = simpledialog.askfloat(
                            "Scale",
                            "Known distance in meters:",
                            parent=self,
                            minvalue=1e-12,
                        )
                        if meters is not None:
                            self.checkpoint()
                            self.project.calibrate(pixels, meters)
                            self.status.set(
                                f"Scale calibrated: {fmt(meters)} m between the selected points."
                            )
                        self.pending.clear()
                        self.mode = "select"
                        self.mode_var.set("select")
                        self.canvas.configure(cursor="arrow")
                        self.refresh()
                else:
                    self.status.set("Click the other end of the known distance.")
            self.draw()
            return
        current = self.current()
        if current:
            for vertex, p in enumerate(current.displayed_points()):
                if abs(p[0] - xy[0]) <= 6 and abs(p[1] - xy[1]) <= 6:
                    self.drag = (vertex, self.project.snapshot())
                    return
        self.selected = self.hit_test(xy)
        self.refresh()

    def _georeference_dialog(self, source_pixel):
        """Enter a metric X/Y pair for one clicked source-image pixel."""
        dialog = tk.Toplevel(self)
        dialog.title("Georeference image")
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=("Reference point on north-up image: "
                  f"pixel ({source_pixel[0]:.2f}, {source_pixel[1]:.2f})"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 9))
        ttk.Label(
            frame, text="Enter coordinates in a projected metric system (metres)."
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        initial = self.project.world_xy(source_pixel) if self.project.georeferenced else None
        east_var = tk.StringVar(value=f"{initial[0]:.6f}" if initial else "")
        north_var = tk.StringVar(value=f"{initial[1]:.6f}" if initial else "")
        ttk.Label(frame, text="X (Easting, m)").grid(row=2, column=0, sticky="w", pady=4)
        east_entry = ttk.Entry(frame, textvariable=east_var, width=23)
        east_entry.grid(row=2, column=1, padx=(9, 0), pady=4)
        ttk.Label(frame, text="Y (Northing, m)").grid(row=3, column=0, sticky="w", pady=4)
        north_entry = ttk.Entry(frame, textvariable=north_var, width=23)
        north_entry.grid(row=3, column=1, padx=(9, 0), pady=4)

        def confirm(event=None):
            try:
                x, y = float(east_var.get().strip()), float(north_var.get().strip())
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError("Enter finite numeric values for X and Y.")
                self.checkpoint()
                self.project.georeference(source_pixel, x, y)
            except ValueError as exc:
                messagebox.showerror("Invalid coordinates", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.set_mode("select", redraw=False)
            self.refresh()
            self.status.set(f"Image georeferenced: X={x:.3f} m, Y={y:.3f} m.")

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(buttons, text="Apply", command=confirm).pack(side="right")
        dialog.bind("<Return>", confirm)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()
        east_entry.focus_set()
        self.wait_window(dialog)

    def finish_tool(self, kind):
        self.checkpoint()
        # Creation clicks are in display coordinates; store their inverse transform.
        raw = [
            source_point(
                p, self.project.rotation, self.project.zoom, self.project.center
            )
            for p in self.pending
        ]
        tool = Tool(
            kind,
            raw,
            angle=self.project.rotation,
            scale=self.project.zoom,
            anchor=self.project.center,
            width=DEFAULT_LINE_WIDTH,
            number=self.project.new_number(kind),
        )
        self.project.tools.append(tool)
        self.selected = len(self.project.tools) - 1
        self.pending.clear()
        self.mode = "select"
        self.mode_var.set("select")
        self.canvas.configure(cursor="arrow")
        self.status.set(
            "Drag the red handles to adjust the object. Numeric Results shows the curve values."
        )
        self.refresh()

    def finish_polygon(self):
        if self.mode == "polygon" and len(self.pending) >= 3:
            self.finish_tool("polygon")

    def double_click(self, event):
        if self.mode == "polygon":
            self.finish_polygon()
            return "break"
        current = self.current()
        if self.mode == "select" and current and current.kind == "polygon":
            xy = self.xy(event)
            points = current.displayed_points()
            segments = [
                (self.near_segment(xy, a, b), i)
                for i, (a, b) in enumerate(
                    zip(points, points[1:] + points[:1], strict=True)
                )
            ]
            if segments:
                dist, index = min(segments)
                if dist < 10:
                    self.checkpoint()
                    current.points.insert(
                        index + 1,
                        source_point(xy, current.angle, current.scale, current.anchor),
                    )
                    self.refresh()

    def motion_drag(self, event):
        if self.mode == "pan":
            self.canvas.scan_dragto(event.x, event.y, gain=1)
        elif self.drag is not None and self.current():
            tool = self.current()
            tool.points[self.drag[0]] = source_point(
                self.xy(event), tool.angle, tool.scale, tool.anchor
            )
            self.draw()
            self.update_info()

    def release(self, event):
        if self.drag is not None:
            before = self.drag[1]
            if before.tools != self.project.tools:
                self.history.append(before)
                self.history = self.history[-100:]
                self.future.clear()
                self.dirty = True
            self.drag = None
            self.refresh()

    def motion(self, event):
        xy = self.xy(event)
        image_xy = source_point(
            xy, self.project.rotation, self.project.zoom, self.project.center
        )
        east, north = self.project.world_xy(image_xy)
        self.coordinates.set(f"X: {east:.2f} m   Y: {north:.2f} m")
        if self.pending:
            self.preview_xy = xy
            self.draw()

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) * 3, "units")

    def popup(self, event):
        self.context_xy = self.xy(event)
        hit = self.hit_test(self.context_xy)
        if hit is not None:
            self.selected = hit
            self.refresh()
        try:
            self.context.tk_popup(event.x_root, event.y_root)
        finally:
            self.context.grab_release()

    def delete_vertex(self):
        t = self.current()
        if t and t.kind == "polygon" and len(t.points) > 3:
            points = t.displayed_points()
            index = min(
                range(len(points)),
                key=lambda i: distance(
                    points[i], getattr(self, "context_xy", points[0])
                ),
            )
            self.checkpoint()
            t.points.pop(index)
            self.refresh()

    def delete_selected(self):
        if self.current():
            self.checkpoint()
            self.project.tools.pop(self.selected)
            self.selected = None
            self.refresh()

    def tree_select(self, event):
        if self._syncing:
            return
        selection = self.tree.selection()
        self.selected = (
            int(selection[0]) if selection and selection[0].isdigit() else None
        )
        self.update_properties()
        self.draw()

    def edit_color(self):
        t = self.current()
        if t:
            selected = colorchooser.askcolor(t.color, parent=self, title="Line Color")[
                1
            ]
            if selected:
                self.checkpoint()
                t.color = selected
                self.refresh()

    def apply_properties(self):
        t = self.current()
        if not t or self._syncing:
            return
        try:
            step, limit, width = (
                float(self.step_var.get()),
                float(self.limit_var.get()),
                int(self.line_var.get()),
            )
            if (
                not math.isfinite(step)
                or step <= 0
                or not math.isfinite(limit)
                or not 1 <= width <= 20
            ):
                raise ValueError(
                    "Use a positive finite increment, a finite limit, and line width 1–20."
                )
            if max(0, limit) / step > MAX_CURVE_SAMPLES:
                raise ValueError(
                    "Choose an increment that produces at most 100,000 samples."
                )
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid properties", str(exc), parent=self)
            return
        self.checkpoint()
        t.name = self.name_var.get().strip()
        t.increment, t.limit, t.width = step, limit, width
        t.controls, t.labels = self.controls_var.get(), self.labels_var.get()
        self.refresh()

    def edit_points(self):
        t = self.current()
        if not t:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Edit Point Coordinates")
        dialog.transient(self)
        entries = []
        ttk.Label(
            dialog,
            text=("Georeferenced XY (m)" if self.project.georeferenced
                  else "Local image XY (m)"),
        ).grid(
            row=0, column=0, columnspan=3, padx=12, pady=8
        )
        for i, (x, y) in enumerate(t.points):
            name = CONTROL_LABELS[i] if t.kind == "curve" else str(i + 1)
            ttk.Label(dialog, text=name).grid(row=i + 1, column=0, padx=8)
            world_x, world_y = self.project.world_xy((x, y))
            vx = tk.StringVar(value=f"{world_x:.12f}".rstrip("0").rstrip("."))
            vy = tk.StringVar(value=f"{world_y:.12f}".rstrip("0").rstrip("."))
            ttk.Entry(dialog, textvariable=vx, width=19).grid(
                row=i + 1, column=1, padx=4, pady=3
            )
            ttk.Entry(dialog, textvariable=vy, width=19).grid(
                row=i + 1, column=2, padx=4, pady=3
            )
            entries.append((vx, vy))

        def apply():
            try:
                coordinates = [(float(x.get()), float(y.get())) for x, y in entries]
                if any(not math.isfinite(v) for point in coordinates for v in point):
                    raise ValueError("Coordinates must be finite meter values.")
                points = [
                    _source_image_point(self.project.image_xy(point), "Control point")
                    for point in coordinates
                ]
            except ValueError as exc:
                messagebox.showerror("Invalid coordinate", str(exc), parent=dialog)
                return
            self.checkpoint()
            t.points = points
            self.refresh()
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply).grid(
            row=len(entries) + 1, column=1, pady=10
        )
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(
            row=len(entries) + 1, column=2, pady=10
        )

    def refresh(self):
        self._syncing = True
        self.model_var.set(self.project.model)
        self.zoom_var.set(self.project.zoom)
        self.rotation_var.set(self.project.rotation)
        scroll = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self.project.tools):
            self.tree.insert("", "end", iid=str(i), text=t.title())
        if self.current():
            self.tree.selection_set(str(self.selected))
        self.tree.yview_moveto(scroll)
        if self.current():
            self.tree.see(str(self.selected))
        name = Path(self.project.filename).name if self.project.filename else "Untitled"
        self.title(f"{'● ' if self.dirty else ''}Baycraft — {name}")
        self._syncing = False
        self.update_properties()
        self.draw()

    def update_properties(self):
        t = self.current()
        self._syncing = True
        self.name_var.set(t.name if t else "")
        self.step_var.set(str(t.increment) if t else "10")
        self.limit_var.set(str(t.limit) if t else "150")
        self.line_var.set(t.width if t else DEFAULT_LINE_WIDTH)
        self.controls_var.set(t.controls if t else True)
        self.labels_var.set(t.labels if t else True)
        self._syncing = False
        self.update_info()

    def update_info(self):
        t = self.current()
        scale = "Lengths: m  ·  Areas: m²"
        if t is None:
            xy_state = (
                "Georeferenced X/Y (metres)"
                if self.project.georeferenced else "XY georeference not defined"
            )
            self.info_var.set(
                "Select an object to view its properties.\n" + xy_state
                + "\n\n" + scale
            )
            return
        points = t.displayed_points()
        if t.kind == "curve":
            try:
                r = t.result(self.project.model)
                summary = (
                    f"Model: {self.project.model}\n"
                    f"β = {fmt(r.beta)}°  ·  Rb = {fmt(t.length_m(self.project.pixel_size))} m\n"
                    f"Wave from: {fmt_bearing(r.wave_direction_deg)} (north-up image)\n"
                )
                if r.model == MODEL_HSU:
                    summary += (
                        f"C0 = {r.coefficients[0]:.9g}\n"
                        f"C1 = {r.coefficients[1]:.9g}\n"
                        f"C2 = {r.coefficients[2]:.9g}\n"
                    )
                else:
                    summary += (
                        "Four-coefficient Figure 4 fit\n"
                        f"A={CARVALHO_A:.7g}, B={CARVALHO_B:.7g}\n"
                        f"C={CARVALHO_C:.7g}, D={CARVALHO_D:.7g}\n"
                        "θ and β in degrees; no endpoint normalization\n"
                    )
                self.info_var.set(summary + f"Samples: {len(r.radii)}")
            except ValueError as exc:
                self.info_var.set(str(exc))
        elif t.kind == "ruler":
            self.info_var.set(
                f"Distance: {fmt(t.length_m(self.project.pixel_size))} m\n\n{scale}"
            )
        else:
            self.info_var.set(
                f"Area: {fmt(t.area_m2(self.project.pixel_size))} m²\nVertices: {len(points)}\n\n{scale}"
            )

    def display_image(self):
        p = self.project
        if p.image is None:
            return None, (0, 0)
        cache_key = (id(p.image), p.zoom, p.rotation, p.center)
        if self.image_cache and self.image_cache[0] == cache_key:
            return self.image_cache[1:]
        s = p.zoom / 100.0
        sine, cosine = sincos(math.radians(p.rotation))
        corners = [
            rotate_point(x, p.rotation, p.center)
            for x in ((0, 0), (p.width, 0), (0, p.height), (p.width, p.height))
        ]
        left, top = (
            math.floor(min(x * s for x, y in corners)),
            math.floor(min(y * s for x, y in corners)),
        )
        right, bottom = (
            math.ceil(max(x * s for x, y in corners)),
            math.ceil(max(y * s for x, y in corners)),
        )
        size = (max(1, right - left), max(1, bottom - top))
        if size[0] * size[1] > 100000000:
            raise ValueError(
                "The displayed image would exceed 100 million pixels. Reduce zoom."
            )
        ax, ay = p.center
        affine = (
            cosine / s,
            sine / s,
            (cosine * left + sine * top) / s + ax - cosine * ax - sine * ay,
            -sine / s,
            cosine / s,
            (-sine * left + cosine * top) / s + ay + sine * ax - cosine * ay,
        )
        bitmap = p.image.transform(
            size,
            Image.Transform.AFFINE,
            affine,
            resample=Image.Resampling.NEAREST,
            fillcolor=IMAGE_CANVAS_BACKGROUND,
        )
        self.image_cache = (cache_key, bitmap, (left, top))
        return bitmap, (left, top)

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        extent = [
            0,
            0,
            max(self.project.width * self.project.zoom / 100, 1000),
            max(self.project.height * self.project.zoom / 100, 700),
        ]
        try:
            bitmap, origin = self.display_image()
            if bitmap is not None:
                # Reuse the Tk bitmap when only vector overlays change.
                if self.photo is None or self._photo_bitmap is not bitmap:
                    self.photo = ImageTk.PhotoImage(bitmap, master=self)
                    self._photo_bitmap = bitmap
                canvas.create_image(*origin, anchor="nw", image=self.photo)
                extent = [
                    origin[0],
                    origin[1],
                    origin[0] + bitmap.width,
                    origin[1] + bitmap.height,
                ]
            else:
                canvas.create_rectangle(
                    0, 0, extent[2], extent[3],
                    fill=IMAGE_CANVAS_BACKGROUND, outline=""
                )
        except (ValueError, MemoryError) as exc:
            self.status.set(str(exc))
        for i, t in enumerate(self.project.tools):
            if not t.visible:
                continue
            points = t.displayed_points()
            selected = i == self.selected
            try:
                if t.kind == "curve":
                    result = t.result(self.project.model)
                    h, e, w = points
                    if t.controls or selected:
                        canvas.create_line(
                            *h, *e, *w, fill="black", width=t.width, dash=(3, 3)
                        )
                        canvas.create_line(
                            *h,
                            h[0] + e[0] - w[0],
                            h[1] + e[1] - w[1],
                            fill="black",
                            width=t.width,
                            dash=(3, 3),
                        )
                    if len(result.points) > 1:
                        canvas.create_line(
                            *[n for xy in result.points for n in xy],
                            fill=t.color,
                            width=t.width,
                        )
                    if len(result.points) <= 2000:
                        for x, y in result.points:
                            r = t.width
                            canvas.create_oval(
                                x - r, y - r, x + r, y + r,
                                fill=t.color, outline="",
                            )
                    if t.labels:
                        canvas.create_text(
                            h[0] + 10,
                            h[1] + 10,
                            text=f"{t.identifier()}  β = {fmt(result.beta)}°",
                            anchor="sw",
                            fill="black",
                        )
                        canvas.create_text(
                            *midpoint(h, e),
                            text=fmt(t.length_m(self.project.pixel_size)) + " m",
                            anchor="sw",
                            fill="black",
                        )
                    if selected:
                        for label, xy in zip(CONTROL_LABELS, points, strict=True):
                            canvas.create_text(
                                xy[0] + 10,
                                xy[1] - 10,
                                text=label,
                                anchor="sw",
                                fill=CONTROL_LABEL_COLOR,
                                font=self.control_label_font,
                            )
                elif t.kind == "ruler":
                    canvas.create_line(
                        *points[0], *points[1], fill=t.color, width=t.width
                    )
                    canvas.create_text(
                        *midpoint(*points),
                        text=f"{t.identifier()}: {fmt(t.length_m(self.project.pixel_size))} m",
                        anchor="sw",
                        fill=t.color,
                    )
                elif points:
                    canvas.create_polygon(
                        *[n for xy in points for n in xy],
                        fill="white",
                        stipple="gray12",
                        outline=t.color,
                        width=t.width,
                    )
                    # Use calibrated image geometry, independent of the view.
                    cx, cy = polygon_center(t.points)
                    canvas.create_text(
                        *transform_point((cx, cy), t.angle, t.scale, t.anchor),
                        text=f"{t.identifier()}: {fmt(t.area_m2(self.project.pixel_size))} m²",
                        anchor="sw",
                        fill=t.color,
                    )
                if selected:
                    for x, y in points:
                        canvas.create_rectangle(
                            x - 4,
                            y - 4,
                            x + 4,
                            y + 4,
                            fill="red",
                            outline="red",
                            tags="handle",
                        )
                for x, y in points:
                    extent = [
                        min(extent[0], x),
                        min(extent[1], y),
                        max(extent[2], x),
                        max(extent[3], y),
                    ]
            except (ValueError, OverflowError) as exc:
                self.status.set(str(exc))
        if self.pending:
            preview = self.pending + ([self.preview_xy] if self.preview_xy else [])
            if len(preview) > 1:
                canvas.create_line(
                    *[n for xy in preview for n in xy],
                    fill="#007000",
                    width=DEFAULT_LINE_WIDTH,
                    dash=(3, 3),
                )
            for i, (x, y) in enumerate(self.pending):
                canvas.create_rectangle(
                    x - 4, y - 4, x + 4, y + 4, fill="red", outline="red"
                )
                if self.mode == "curve":
                    canvas.create_text(
                        x + 10,
                        y - 10,
                        text=CONTROL_LABELS[min(i, 2)],
                        anchor="sw",
                        fill=CONTROL_LABEL_COLOR,
                        font=self.control_label_font,
                    )
        if self.project.georeferenced:
            gx, gy = transform_point(
                self.project.reference_pixel,
                self.project.rotation,
                self.project.zoom,
                self.project.center,
            )
            canvas.create_rectangle(
                gx - 4, gy - 4, gx + 4, gy + 4, fill="red", outline="red"
            )
            canvas.create_text(
                gx + 10,
                gy - 10,
                text=GEOREFERENCE_LABEL,
                anchor="sw",
                fill=CONTROL_LABEL_COLOR,
                font=self.control_label_font,
            )
        bbox = canvas.bbox("all")
        if bbox:
            extent = [
                min(extent[0], bbox[0]),
                min(extent[1], bbox[1]),
                max(extent[2], bbox[2]),
                max(extent[3], bbox[3]),
            ]
        canvas.configure(
            scrollregion=(
                extent[0] - 10,
                extent[1] - 10,
                extent[2] + 30,
                extent[3] + 30,
            )
        )

    def _results_window(self, tool, *, width=760, height=650):
        """Create a neatly laid-out, scrollable results window."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Baycraft Results — {tool.title()}")
        dialog.transient(self)
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(width, max(540, screen_w - 80))
        height = min(height, max(440, screen_h - 110))
        x = max(0, self.winfo_rootx() + (self.winfo_width() - width) // 2)
        y = max(0, self.winfo_rooty() + (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(540, width), min(440, height))
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        return dialog

    def _result_table(self, parent, columns, headings, widths):
        """Use right-aligned numeric cells and alternating rows for legibility."""
        style = ttk.Style(self)
        style.configure(
            "BaycraftResults.Treeview",
            font=self.gui_font,
            rowheight=max(29, self.gui_font.metrics("linespace") + 12),
        )
        heading_font = self.gui_font.copy()
        heading_font.configure(weight="bold")
        style.configure("BaycraftResults.Treeview.Heading", font=heading_font)
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="browse",
            style="BaycraftResults.Treeview",
        )
        for col, heading, col_width in zip(columns, headings, widths, strict=True):
            table.heading(col, text=heading, anchor="center")
            table.column(
                col, width=col_width, minwidth=max(60, col_width // 2),
                anchor="center" if col == "index" else "e", stretch=True,
            )
        table.tag_configure("even", background="#ffffff", foreground="#232323")
        table.tag_configure("odd", background="#eef2f6", foreground="#232323")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return frame, table

    def _show_curve_results(self, tool, result):
        dialog = self._results_window(tool, width=980)
        summary = ttk.LabelFrame(dialog, text="Planform analysis", padding=(14, 10))
        summary.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        radius = tool.length_m(self.project.pixel_size)
        ratio = planform_ratio(
            result.beta, result.beta, self.project.model, result.coefficients
        )
        ttk.Label(summary, text=f"Model: {self.project.model}").grid(
            row=0, column=0, sticky="w", pady=2
        )
        ttk.Label(summary, text=f"Reference angle β: {result.beta:.2f}°").grid(
            row=0, column=1, sticky="w", pady=2
        )
        ttk.Label(summary, text=f"Reference radius Rb: {radius:.2f} m").grid(
            row=1, column=0, sticky="w", pady=2
        )
        ttk.Label(summary, text=f"Angular increment: {tool.increment:.2f}°").grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Label(summary, text=f"R(β)/Rb: {ratio:.4f}").grid(
            row=2, column=0, sticky="w", pady=2
        )
        ttk.Label(summary, text=f"Number of samples: {len(result.theta)}").grid(
            row=2, column=1, sticky="w", pady=2
        )
        ttk.Label(
            summary,
            text=f"Wave direction (from): {fmt_bearing(result.wave_direction_deg)}",
        ).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(
            summary,
            text="Clockwise from N · north-up source image assumed",
        ).grid(row=3, column=1, sticky="w", pady=2)
        ttk.Label(
            summary,
            text=("   ".join(
                f"C{i} = {coefficient:.6f}"
                for i, coefficient in enumerate(result.coefficients)
            ) if result.model == MODEL_HSU else
                CARVALHO_EQUATION + "\nθ, β in degrees; A, B, C, D listed in output.txt"),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        table_group = ttk.LabelFrame(
            dialog, text="Sampled equilibrium planform", padding=(10, 8)
        )
        table_group.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        table_group.columnconfigure(0, weight=1)
        table_group.rowconfigure(0, weight=1)
        frame, table = self._result_table(
            table_group,
            ("index", "theta", "radius", "east", "north"),
            ("No.", "θ (degrees)", "Rn (m)", "X (m)", "Y (m)"),
            (65, 130, 130, 220, 220),
        )
        frame.grid(row=0, column=0, sticky="nsew")
        records = []
        for i, (theta, rn, source_xy) in enumerate(
            zip(result.theta, result.radii, result.source_points, strict=True), 1
        ):
            x, y = self.project.world_xy(source_xy)
            row = (
                str(i), f"{theta:.2f}", f"{rn * self.project.pixel_size:.2f}",
                f"{x:.2f}", f"{y:.2f}",
            )
            records.append(row)
            table.insert("", "end", values=row, tags=("odd" if i % 2 else "even",))

        footer = ttk.Frame(dialog, padding=(16, 4, 16, 14))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            footer,
            text=f"{len(records)} rows · length in metres",
        ).pack(side="left")

        def copy_table():
            header = "No.\tTheta (deg)\tRn (m)\tX (m)\tY (m)"
            self.clipboard_clear()
            self.clipboard_append(
                "\n".join([header] + ["\t".join(row) for row in records])
            )

        ttk.Button(footer, text="Close", command=dialog.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(footer, text="Copy Table", command=copy_table).pack(side="right")

    def _show_measure_results(self, tool):
        dialog = self._results_window(tool, width=610, height=300)
        group = ttk.LabelFrame(dialog, text=tool.title(), padding=(18, 16))
        group.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        a, b = tool.points
        point1 = self.project.world_xy(a)
        point2 = self.project.world_xy(b)
        for line in (
            f"Measured distance: {tool.length_m(self.project.pixel_size):.2f} m",
            f"P1: X = {point1[0]:.2f} m,  Y = {point1[1]:.2f} m",
            f"P2: X = {point2[0]:.2f} m,  Y = {point2[1]:.2f} m",
        ):
            ttk.Label(group, text=line).pack(anchor="w", pady=4)
        ttk.Label(
            dialog, text="Measure objects are not included in output.txt."
        ).grid(row=1, column=0, sticky="nw", padx=22)
        ttk.Button(dialog, text="Close", command=dialog.destroy).grid(
            row=2, column=0, sticky="e", padx=18, pady=12
        )

    def _show_polygon_results(self, tool):
        dialog = self._results_window(tool, width=770, height=550)
        group = ttk.LabelFrame(dialog, text=tool.title(), padding=(18, 12))
        group.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        perimeter = sum(
            distance(a, b)
            for a, b in zip(tool.points, tool.points[1:] + tool.points[:1])
        ) * self.project.pixel_size
        for line in (
            f"Enclosed area: {tool.area_m2(self.project.pixel_size):.2f} m²",
            f"Perimeter: {perimeter:.2f} m",
            f"Vertices: {len(tool.points)}",
        ):
            ttk.Label(group, text=line).pack(anchor="w", pady=2)
        coordinates = ttk.LabelFrame(
            dialog, text="Polygon vertex coordinates", padding=(10, 8)
        )
        coordinates.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        coordinates.columnconfigure(0, weight=1)
        coordinates.rowconfigure(0, weight=1)
        frame, table = self._result_table(
            coordinates,
            ("index", "east", "north"),
            ("Vertex", "X (m)", "Y (m)"),
            (90, 265, 265),
        )
        frame.grid(row=0, column=0, sticky="nsew")
        records = []
        for i, pixel_xy in enumerate(tool.points, 1):
            x, y = self.project.world_xy(pixel_xy)
            row = (str(i), f"{x:.2f}", f"{y:.2f}")
            records.append(row)
            table.insert("", "end", values=row, tags=("odd" if i % 2 else "even",))
        footer = ttk.Frame(dialog, padding=(16, 4, 16, 14))
        footer.grid(row=2, column=0, sticky="ew")

        def copy_table():
            self.clipboard_clear()
            self.clipboard_append(
                "\n".join(["Vertex\tX (m)\tY (m)"]
                          + ["\t".join(record) for record in records])
            )

        ttk.Button(footer, text="Close", command=dialog.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(footer, text="Copy Table", command=copy_table).pack(side="right")

    def _show_project_results(self, report_text, report_file=None):
        """Display the complete technical report even when no object is selected."""
        dialog = tk.Toplevel(self)
        dialog.title("Baycraft Results — Project")
        dialog.transient(self)
        width = min(980, max(540, self.winfo_screenwidth() - 80))
        height = min(690, max(440, self.winfo_screenheight() - 110))
        left = max(0, self.winfo_rootx() + (self.winfo_width() - width) // 2)
        top = max(0, self.winfo_rooty() + (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{left}+{top}")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        title = f"Complete Baycraft technical report — {self.project.model}"
        ttk.Label(dialog, text=title).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 5)
        )
        body = ttk.Frame(dialog, padding=(12, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        text = tk.Text(
            body, wrap="none", font=tkfont.nametofont("TkFixedFont", root=self),
            undo=False
        )
        text.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        text.insert("1.0", report_text)
        text.configure(state="disabled")
        footer = ttk.Frame(dialog, padding=(14, 8))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            footer,
            text=(f"output.txt: {report_file}" if report_file else "output.txt was not saved")
        ).pack(side="left")

        def copy_report():
            self.clipboard_clear()
            self.clipboard_append(report_text)

        ttk.Button(footer, text="Close", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Copy Report", command=copy_report).pack(
            side="right", padx=(0, 8)
        )
        return dialog

    def numeric_results(self):
        """Always show results and write output.txt when image scale is defined.

        The report covers every parabola and polygon irrespective of selection.
        The detailed result for a selected object remains available as before;
        when nothing is selected, show the complete report in a text window.
        """
        if not self.project.scale_defined:
            message = (
                "Define the image scale before viewing results.\n\n"
                "Select Scale, click two points a known distance apart, "
                "and enter that distance in metres."
            )
            self.status.set("Define image scale first using the Scale tool.")
            messagebox.showwarning("Image scale required", message, parent=self)
            return

        tool = self.current()
        selected_index = self.selected if tool is not None else None
        report_text = build_technical_report(self.project, selected_index)
        report_folder = (
            Path(self.project.filename).parent
            if self.project.filename else Path.cwd()
        )
        report_file = report_folder / "output.txt"
        saved_path = None
        attempted = set()
        errors = []
        candidates = (
            report_file,
            Path.cwd() / "output.txt",
            Path(__file__).resolve().parent / "output.txt",
            Path(tempfile.gettempdir()) / "output.txt",
        )
        for candidate in candidates:
            key = str(candidate.resolve())
            if key in attempted:
                continue
            attempted.add(key)
            try:
                save_technical_report(self.project, candidate, selected_index)
                saved_path = candidate
                break
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"{candidate}: {exc}")
        if saved_path is not None:
            self.status.set(f"Results report saved: {saved_path}")
            if saved_path.resolve() != report_file.resolve():
                messagebox.showwarning(
                    "Report saved to alternate location",
                    f"Cannot write the preferred output.txt.\n"
                    f"Report saved instead to:\n{saved_path}", parent=self,
                )
        else:
            self.status.set("Cannot save output.txt; results remain available.")
            messagebox.showerror(
                "Cannot save output.txt", "\n".join(errors), parent=self
            )

        if tool is None:
            self._show_project_results(report_text, saved_path)
            return
        if tool.kind == "curve":
            try:
                result = tool.result(self.project.model)
                self._show_curve_results(tool, result)
            except (ValueError, OverflowError, ZeroDivisionError) as exc:
                # Invalid curve geometry is already recorded in the full report.
                self._show_project_results(report_text, saved_path)
                self.status.set(f"Curve calculation: {exc}")
        elif tool.kind == "polygon":
            self._show_polygon_results(tool)
        elif tool.kind == "ruler":
            self._show_measure_results(tool)
        else:
            self._show_project_results(report_text, saved_path)

    def export_image(self):
        if self.project.image is None:
            return  # No image: no dialog, export, or other side effect.
        if Image is None:
            messagebox.showerror(
                "Pillow required",
                "Install Pillow to export raster images.",
                parent=self,
            )
            return
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Export Image",
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("TIFF", "*.tif *.tiff"),
                ("JPEG", "*.jpg *.jpeg"),
            ],
        )
        if not filename:
            return
        try:
            self.render_export().save(filename)
            self.status.set("Image exported: " + filename)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Export Image", str(exc), parent=self)

    def render_export(self):
        """Render the current planform as a standalone raster, without handles."""
        if Image is None:
            raise RuntimeError("Pillow is required for raster output.")
        if self.project.image is None:
            raise ValueError("Cannot export without an imported image.")
        bitmap, origin = self.display_image()
        output = bitmap.copy().convert("RGB")
        draw = ImageDraw.Draw(output, "RGBA")
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = ImageFont.load_default()

        def offset(p):
            return (p[0] - origin[0], p[1] - origin[1])

        def dashed(a, b, color, width):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if not length:
                return
            for step in range(0, int(length) + 1, 6):
                s, e = step / length, min(step + 3, length) / length
                draw.line(
                    [
                        (a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1])),
                        (a[0] + e * (b[0] - a[0]), a[1] + e * (b[1] - a[1])),
                    ],
                    fill=color,
                    width=width,
                )

        for tool in self.project.tools:
            if not tool.visible:
                continue
            points = [offset(p) for p in tool.displayed_points()]
            if tool.kind == "curve":
                result = tool.result(self.project.model)
                h, e, w = points
                if tool.controls:
                    for a, b in [
                        (h, e),
                        (e, w),
                        (h, (h[0] + e[0] - w[0], h[1] + e[1] - w[1])),
                    ]:
                        dashed(a, b, "black", tool.width)
                curve = [offset(p) for p in result.points]
                if len(curve) > 1:
                    draw.line(curve, fill=tool.color, width=tool.width)
                if len(curve) <= 2000:
                    for x, y in curve:
                        r = tool.width
                        draw.ellipse(
                            (x - r, y - r, x + r, y + r), fill=tool.color
                        )
                if tool.labels:
                    draw.text(
                        (h[0] + 10, h[1]),
                        f"{tool.identifier()}  β = {fmt(result.beta)}°",
                        fill="black",
                        font=font,
                    )
                    draw.text(
                        offset(midpoint(*tool.displayed_points()[:2])),
                        fmt(tool.length_m(self.project.pixel_size)) + " m",
                        fill="black",
                        font=font,
                    )
            elif tool.kind == "ruler":
                draw.line(points, fill=tool.color, width=tool.width)
                draw.text(
                    offset(midpoint(*tool.displayed_points())),
                    f"{tool.identifier()}: {fmt(tool.length_m(self.project.pixel_size))} m",
                    fill=tool.color,
                    font=font,
                )
            elif len(points) > 2:
                draw.polygon(
                    points,
                    fill=(255, 255, 255, 50),
                    outline=tool.color,
                    width=tool.width,
                )
                draw.text(
                    offset(
                        transform_point(
                            polygon_center(tool.points),
                            tool.angle,
                            tool.scale,
                            tool.anchor,
                        )
                    ),
                    f"{tool.identifier()}: {fmt(tool.area_m2(self.project.pixel_size))} m²",
                    fill=tool.color,
                    font=font,
                )
        if self.project.georeferenced:
            gx, gy = offset(
                transform_point(
                    self.project.reference_pixel,
                    self.project.rotation,
                    self.project.zoom,
                    self.project.center,
                )
            )
            draw.rectangle((gx - 4, gy - 4, gx + 4, gy + 4), fill="red", outline="red")
            draw.text((gx + 10, gy - 10), GEOREFERENCE_LABEL, fill=CONTROL_LABEL_COLOR, font=font)
        return output

    def print_project(self):
        if self.project.image is None:
            return
        if Image is None:
            messagebox.showerror(
                "Print", "Pillow is required to prepare the print image.", parent=self
            )
            return
        try:
            # Windows image print wizard supplies preview, paper and printer choice.
            fd, path = tempfile.mkstemp(prefix="baycraft_print_", suffix=".png")
            os.close(fd)
            self.render_export().save(path)
            if sys.platform == "win32":
                os.startfile(path, "print")
                self.status.set("Print image prepared: " + path)
            else:
                messagebox.showinfo(
                    "Print",
                    "Open this image in your image viewer to print:\n" + path,
                    parent=self,
                )
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Print", str(exc), parent=self)

    def help(self):
        messagebox.showinfo(
            "Baycraft Help",
            "1. Import a map or aerial/satellite image.\n"
            "2. Select Hsu1989 or Carvalho(2026) from the Model list. "
            "The selected model applies to all curves.\n"
            "3. Choose Parabola, then click H (diffraction point), E (downcoast "
            "control), and W (wave-crest tangent endpoint). Drag the handles "
            "to adjust these points.\n"
            "4. Hsu1989 uses sixth-degree C0, C1, C2 polynomials fitted "
            "for beta = 10 to 80 degrees. Carvalho(2026) uses an "
            "four-coefficient image-curve model: "
            "R/Rb=A*beta/[theta^0.8*(1+B*beta+(beta/C)^4*(1-exp(-(theta/D)^9)))]. "
            "Theta and beta are numerical degrees. The model fits only 152 original "
            "image-digitized curve readings, without origin anchors or interpolated references. "
            "R(beta)/Rb is not forced to 1. Extrapolation outside the digitized support "
            "is not validated.\n"
            "5. Change angle increment, angle limit, line width, and labels "
            "under Properties. The selected model applies to all curves, "
            "including their image exports and numeric results.\n"
            "6. Define image scale before opening Results. Results works "
            "even without a selected object; only planform curves and polygons are "
            "included in output.txt. The planform table can be copied.\n"
            "7. Scale: click the endpoints of a known distance and enter its "
            "length in metres. Lengths use metres and areas square metres.\n"
            "8. Georeference: after setting scale, select Georeference, click "
            "one known position in the source image, and enter X Easting "
            "and Y Northing in metres. North is assumed up. The reference "
            "is stored in .bay files; all reported XY then use that "
            "coordinate system (its EPSG code is not inferred).\n"
            "9. Wave direction is reported as a FROM bearing clockwise from "
            "north (N=0, E=90, S=180, W=270). The E-W crest normal "
            "facing toward H is taken as offshore. The source image must "
            "be north-up for a geographic bearing; view rotation is ignored.\n"
            "10. Polygon: click vertices, then double-click or press Enter. "
            "Measure: click two endpoints.\n"
            "11. Save/Open uses .bay projects with embedded images, styles, "
            "calibration, georeference, and the selected model. "
            "Export defaults to PNG.\n\n"
            "Esc cancels. Delete removes selection. Ctrl+Z/Y undo/redo. "
            "The fixed-size window fills the available screen and may be "
            "moved by its title bar. Object numbers are independent by type.",
            parent=self,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Baycraft: Hsu1989 and Carvalho(2026) bay-planform models"
    )
    parser.add_argument("project", nargs="?", help="Baycraft project to open")
    parser.add_argument(
        "--calculate",
        metavar="JSON",
        help='Calculate without a window: {"h":[x,y],"e":[x,y],"w":[x,y],'
        '"increment":10,"limit":150}. For georeferenced XY output also supply '
        '"pixel_size" (m/pixel), "reference_pixel" and "reference_xy".',
    )
    parser.add_argument(
        "--model", choices=MODELS,
        help="Model for --calculate (overrides the model in its JSON).",
    )
    args = parser.parse_args()
    if args.calculate:
        try:
            data = json.loads(args.calculate)
            result = curve_geometry(
                tuple(data["h"]),
                tuple(data["e"]),
                tuple(data["w"]),
                data.get("increment", DEFAULT_INCREMENT),
                data.get("limit", DEFAULT_ANGLE_LIMIT),
                args.model or data.get("model", DEFAULT_MODEL),
            )
            payload = asdict(result)
            geo_keys = ("pixel_size", "reference_pixel", "reference_xy")
            supplied = [key in data for key in geo_keys]
            if any(supplied):
                if not all(supplied):
                    raise ValueError(
                        "Provide pixel_size, reference_pixel and reference_xy "
                        "together for georeferenced JSON output."
                    )
                size = float(_finite_number(data["pixel_size"], "Pixel size", 1e-12))
                project = Project(pixel_size=size, scale_defined=True)
                x, y = _project_metric_point(data["reference_xy"], "Reference XY")
                project.georeference(
                    _project_metric_point(data["reference_pixel"], "Reference pixel"),
                    x, y,
                )
                payload["points"] = [
                    list(project.world_xy(pixel)) for pixel in result.source_points
                ]
                payload["coordinate_system"] = (
                    "User-supplied metric XY (X east, Y north); "
                    "north-up original image; EPSG unspecified"
                )
                payload["points_unit"] = "m"
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            parser.error(str(exc))
        print(json.dumps(payload, indent=2))
        return
    app = BaycraftApp(args.project)
    app.mainloop()


if __name__ == "__main__":
    main()
