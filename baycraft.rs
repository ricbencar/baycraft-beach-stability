// ============================================================================
// BAYCRAFT — COASTAL BAY PLANFORM ANALYSIS — NATIVE WINDOWS / RUST 2021
// ============================================================================
// SOURCE       : baycraft.rs (single Rust source file)
// TARGET       : Windows 10/11 x64, MSYS2 UCRT64, x86_64-pc-windows-gnu
// DEPENDENCIES : Rust standard library and native Windows DLLs only.
//                Builds directly with rustc; no external crates are required.
// GRAPHICS     : Win32 GDI, GDI+ (included with Windows), common dialogs.
// PROJECTS     : self-contained .bay JSON, including embedded PNG bitmap.
// OUTPUTS      : output.txt (UTF-8), PNG/JPEG/TIFF image export, .bay projects.
// NUMERICS     : IEEE binary64, degrees for reference and ray angles.
// RUST         : Rust 1.88 or newer; edition 2021.
// ORGANIZATION : engine (models/geometry), formatting, persistence (project I/O),
//                reporting, raster, win32 (native ABI), windows_gui (application).
// The GUI and --calculate interface use the same numerical engine.
//
// 1. INSTALL AND COMPILE — MSYS2 UCRT64
// -----------------------------------
// Install MSYS2 from https://www.msys2.org/ and use the "MSYS2 UCRT64" shell.
// Do not mix /ucrt64/bin with /mingw64/bin or a separate rustup toolchain.
//
//     pacman -Syu
//
// Reopen the UCRT64 shell if requested, then run pacman -Syu again. Install:
//
//     pacman -S --needed base-devel mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-rust
//
// Confirm the installation in the SAME terminal:
//
//     echo "$MSYSTEM"                # UCRT64
//     command -v rustc               # /ucrt64/bin/rustc
//     command -v gcc                 # /ucrt64/bin/gcc
//     rustc -vV                      # host x86_64-pc-windows-gnu
//
// Open the source directory (example C:\baycraft becomes /c/baycraft):
//
//     cd /c/baycraft
//
// COMPILE — CPU-OPTIMIZED NATIVE WINDOWS GUI, SINGLE COMMAND:
//
//     rustc --edition=2021 --target x86_64-pc-windows-gnu -C linker=gcc -C opt-level=3 -C codegen-units=1 -C lto=fat -C target-cpu=native -C prefer-dynamic=no -C panic=unwind -C strip=symbols baycraft.rs -o baycraft.exe
//
// PORTABLE x86-64 GUI (NO target-specific CPU instructions):
//
//     rustc --edition=2021 --target x86_64-pc-windows-gnu -C linker=gcc -C opt-level=3 -C codegen-units=1 -C lto=fat -C target-cpu=x86-64 -C prefer-dynamic=no -C panic=unwind -C strip=symbols baycraft.rs -o baycraft.exe
//
// DIAGNOSTIC WINDOWS CONSOLE BUILD (if the GUI cannot open):
//
//     rustc --edition=2021 --target x86_64-pc-windows-gnu --cfg 'feature="debug_console"' -C linker=gcc -C debuginfo=1 -C opt-level=0 baycraft.rs -o baycraft_debug.exe
//     ./baycraft_debug.exe
//
// Startup errors also display a Windows dialog and are recorded in:
//     %TEMP%\baycraft_startup.log
//
// RUN AND INSPECT IMPORTED DLLS:
//
//     ./baycraft.exe
//     objdump -p baycraft.exe | grep -i 'DLL Name'
//
// The executable uses the Windows subsystem (no console window). System DLLs
// such as USER32.dll, GDI32.dll, GDIPLUS.dll and COMDLG32.dll are not bundled.
// 'prefer-dynamic=no' does not guarantee static linkage of all MinGW support
// libraries. Inspect DLL imports before deployment. For optional static GNU
// support-library linkage, append -C link-arg=-static -C link-arg=-static-libgcc
// before the .rs filename, and retest the executable.
//
// GUI WORKFLOW
// ------------
// Import a north-up image, calibrate Scale using a known distance, optionally
// use Georeference to identify one image pixel with planar X/Y coordinates.
// Select Parabola and click H, E, W. Polygon
// closes on double-click. Measure takes two clicks. Results writes output.txt
// and opens a report window even when no object is selected. Ctrl+wheel zooms;
// Pan+left-drag or middle-button drag pans the canvas.
// Wave FROM azimuth: 0 North, 90 East, 180 South, 270 West.
// Geographic XY: X=Xref+(pixel_x-xref)*scale; Y=Yref-(pixel_y-yref)*scale.
// A one-point anchor assumes north-up, no skew and uniform scale; it does not
// identify an EPSG/CRS or compensate for source-image map distortion.
// ============================================================================

#![cfg_attr(
    all(windows, not(any(feature = "headless", feature = "debug_console"))),
    windows_subsystem = "windows"
)]

use std::path::Path;
#[cfg(all(windows, not(feature = "headless")))]
use std::path::PathBuf;

type ResultT<T> = Result<T, String>;

// Internal modules keep the calculation engine independent of the window system.
use engine::*;
#[cfg(all(windows, not(feature = "headless")))]
use formatting::*;
use persistence::*;
use reporting::*;

mod formatting {
    use super::engine::normalized_degrees;

    pub(crate) fn fmt_general(v: f64, digits: usize) -> String {
        if !v.is_finite() {
            return if v.is_nan() {
                "nan".into()
            } else if v > 0.0 {
                "inf".into()
            } else {
                "-inf".into()
            };
        }
        if v == 0.0 {
            return if v.is_sign_negative() {
                "-0".into()
            } else {
                "0".into()
            };
        }
        let digits = digits.max(1);
        // General format chooses notation after rounding to significant digits.
        let scientific = format!("{:.*e}", digits - 1, v);
        let (mantissa, exponent_text) = scientific.split_once('e').unwrap_or((&scientific, "0"));
        let exponent: i32 = exponent_text.parse().unwrap_or(0);
        if exponent < -4 || exponent >= digits as i32 {
            let mant = if mantissa.contains('.') {
                mantissa.trim_end_matches('0').trim_end_matches('.')
            } else {
                mantissa
            };
            format!("{mant}e{exponent:+03}")
        } else {
            let decimals = (digits as i32 - 1 - exponent).max(0) as usize;
            if decimals == 0 {
                format!("{v:.0}")
            } else {
                format!("{:.*}", decimals, v)
                    .trim_end_matches('0')
                    .trim_end_matches('.')
                    .to_string()
            }
        }
    }
    pub(crate) fn fmt_bearing(v: f64) -> String {
        if !v.is_finite() {
            return "Undefined".into();
        }
        let text = format!("{:.2}", normalized_degrees(v));
        format!("{}°", if text == "360.00" { "0.00" } else { &text })
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn fmt_display(value: f64, decimals: usize) -> String {
        if !value.is_finite() {
            return if value.is_nan() {
                "NaN".into()
            } else if value.is_sign_positive() {
                "Infinity".into()
            } else {
                "-Infinity".into()
            };
        }
        let fixed = format!("{value:.decimals$}");
        let (integer, fraction) = fixed.split_once('.').unwrap_or((&fixed, ""));
        let (sign, digits) = integer
            .strip_prefix('-')
            .map_or(("", integer), |s| ("-", s));
        let mut result = String::with_capacity(fixed.len() + digits.len() / 3);
        result.push_str(sign);
        for (index, digit) in digits.chars().enumerate() {
            if index > 0 && (digits.len() - index).is_multiple_of(3) {
                result.push(',');
            }
            result.push(digit);
        }
        let fraction = fraction.trim_end_matches('0');
        if !fraction.is_empty() {
            result.push('.');
            result.push_str(fraction);
        }
        result
    }
}

mod engine {
    use super::ResultT;
    use super::formatting::fmt_general;
    use std::sync::Arc;

    // Ordinary powers of beta, ascending from degree 0 through degree 6.
    // Oliveira2010: equal-weight fits of all 48 supplied table observations.
    #[allow(clippy::excessive_precision)] // Retain the exported coefficient digits verbatim.
    pub(crate) const OLIVEIRA: [[f64; 7]; 3] = [
        [
            8.9379927134888931e-02,
            -7.4010747230969986e-03,
            5.0128072495406347e-04,
            -1.3097394953416148e-05,
            1.1423122564951566e-07,
            -5.2045195736435901e-10,
            1.6282762116787805e-12,
        ],
        [
            8.8162348805414326e-01,
            1.5146321651759101e-02,
            -6.9703159306350117e-04,
            1.6757848070587428e-05,
            4.1151569864693824e-08,
            -2.8320953879636758e-09,
            1.5079413405730286e-11,
        ],
        [
            1.8740249891403760e-02,
            -7.3238336183188302e-03,
            2.6842398440550411e-04,
            -1.0866508661427859e-05,
            7.9276852802049855e-08,
            9.9295446608229346e-11,
            -2.6583961939866272e-13,
        ],
    ];
    // Hsu1989: equal-weight fits of the 15 published table observations.
    #[allow(clippy::excessive_precision)] // Retain the exported coefficient digits verbatim.
    pub(crate) const HSU: [[f64; 7]; 3] = [
        [
            -2.5948717948720286e-02,
            9.4371469397480281e-03,
            -4.0811322978137366e-04,
            1.0108930697786255e-05,
            -1.7860566448803580e-07,
            1.1488449630866086e-09,
            -1.3026029125105853e-12,
        ],
        [
            1.3292717948718358e00,
            -6.5720015956185304e-02,
            4.6454080433615905e-03,
            -1.5110565213940694e-04,
            2.7247346369948383e-06,
            -2.3730284988490486e-08,
            7.7202155716091587e-11,
        ],
        [
            -2.9170512820513572e-01,
            5.4566218941018596e-02,
            -4.1688146498725922e-03,
            1.4006101055807072e-04,
            -2.5540727510077560e-06,
            2.2867190600936895e-08,
            -7.7541566334136543e-11,
        ],
    ];
    pub(crate) const MAX_SAMPLES: usize = 100_000;
    pub(crate) const DEFAULT_INCREMENT: f64 = 5.0;
    pub(crate) const DEFAULT_LIMIT: f64 = 150.0;
    pub(crate) const DEFAULT_WIDTH: i32 = 5;
    pub(crate) const CONTROL_LABELS: [&str; 3] = ["H", "E", "W"];
    pub(crate) const MAX_PIXEL: f64 = 2_147_483_647.0;

    #[derive(Debug, Copy, Clone, PartialEq)]
    pub(crate) struct Pt {
        pub(crate) x: f64,
        pub(crate) y: f64,
    }
    impl Pt {
        pub(crate) const fn new(x: f64, y: f64) -> Self {
            Self { x, y }
        }
        pub(crate) fn distance(self, other: Self) -> f64 {
            (other.x - self.x).hypot(other.y - self.y)
        }
        pub(crate) fn finite(self) -> bool {
            self.x.is_finite() && self.y.is_finite()
        }
        pub(crate) fn scale(self, scale: f64) -> Self {
            Self::new(self.x * scale, self.y * scale)
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn rotated(self, degrees: f64, anchor: Self) -> Self {
            let angle = degrees.to_radians();
            let (sine, cosine) = (angle.sin(), angle.cos());
            let x = self.x - anchor.x;
            let y = self.y - anchor.y;
            Self::new(
                x * cosine - y * sine + anchor.x,
                x * sine + y * cosine + anchor.y,
            )
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn transformed(self, degrees: i32, scale: i32, anchor: Self) -> Self {
            let point = self.rotated(f64::from(degrees), anchor);
            Self::new(
                (point.x * f64::from(scale) / 100.0).round_ties_even(),
                (point.y * f64::from(scale) / 100.0).round_ties_even(),
            )
        }
    }

    #[derive(Debug, Default, Copy, Clone, PartialEq, Eq)]
    pub(crate) enum Model {
        #[default]
        Oliveira2010,
        Hsu1989,
    }
    impl Model {
        pub(crate) const ALL: [Self; 2] = [Self::Oliveira2010, Self::Hsu1989];
        pub(crate) const fn text(self) -> &'static str {
            match self {
                Self::Oliveira2010 => "Oliveira2010",
                Self::Hsu1989 => "Hsu1989",
            }
        }
        pub(crate) const fn beta_range(self) -> (f64, f64) {
            match self {
                Self::Oliveira2010 => (22.19, 88.29),
                Self::Hsu1989 => (10.0, 80.0),
            }
        }
        pub(crate) fn parse(text: &str) -> ResultT<Self> {
            match text {
                "Oliveira2010" => Ok(Self::Oliveira2010),
                "Hsu1989" => Ok(Self::Hsu1989),
                _ => Err(format!("Unrecognized planform model: {text:?}.")),
            }
        }
    }

    #[derive(Debug, Copy, Clone, PartialEq, Eq)]
    pub(crate) enum Kind {
        Curve,
        Polygon,
        Measure,
    }
    impl Kind {
        pub(crate) fn name(self) -> &'static str {
            match self {
                Self::Curve => "Parabola",
                Self::Polygon => "Polygon",
                Self::Measure => "Measure",
            }
        }
        pub(crate) fn code(self) -> &'static str {
            match self {
                Self::Curve => "curve",
                Self::Polygon => "polygon",
                Self::Measure => "ruler",
            }
        }
        pub(crate) fn index(self) -> usize {
            match self {
                Self::Curve => 0,
                Self::Polygon => 1,
                Self::Measure => 2,
            }
        }
        pub(crate) fn from_str(text: &str) -> ResultT<Self> {
            match text {
                "curve" => Ok(Self::Curve),
                "polygon" => Ok(Self::Polygon),
                "ruler" => Ok(Self::Measure),
                _ => Err("Unsupported project tool.".into()),
            }
        }
    }

    #[derive(Clone, Debug, PartialEq, Eq)]
    pub(crate) struct Color {
        pub(crate) rgb: u32,
        pub(crate) text: String,
    }
    impl Color {
        pub(crate) fn from_rgb(value: u32) -> Self {
            let rgb = value & 0x00ff_ffff;
            Self {
                rgb,
                text: format!("#{rgb:06x}"),
            }
        }
        pub(crate) fn parse(value: &str) -> ResultT<Self> {
            if value.len() != 7
                || !value.starts_with('#')
                || !value.as_bytes()[1..].iter().all(u8::is_ascii_hexdigit)
            {
                return Err("Tool color must be a six-digit hexadecimal color.".into());
            }
            let rgb = u32::from_str_radix(&value[1..], 16).map_err(|error| error.to_string())?;
            Ok(Self {
                rgb,
                text: value.to_owned(),
            })
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn rgb(&self) -> u32 {
            self.rgb
        }
        pub(crate) fn text(&self) -> &str {
            &self.text
        }
    }

    #[derive(Clone, Debug)]
    pub(crate) struct Tool {
        pub(crate) kind: Kind,
        pub(crate) points: Vec<Pt>,
        pub(crate) angle: i32,
        pub(crate) scale: i32,
        pub(crate) anchor: Pt,
        pub(crate) increment: f64,
        pub(crate) limit: f64,
        pub(crate) color: Color,
        pub(crate) width: i32,
        pub(crate) visible: bool,
        pub(crate) number: u32,
    }
    impl Tool {
        pub(crate) fn new(kind: Kind, points: Vec<Pt>, number: u32, zoom: i32, rotation: i32, anchor: Pt) -> Self {
            Self {
                kind,
                points,
                angle: rotation,
                scale: zoom,
                anchor,
                increment: DEFAULT_INCREMENT,
                limit: DEFAULT_LIMIT,
                color: Color::from_rgb(0x00ff00),
                width: DEFAULT_WIDTH,
                visible: true,
                number,
            }
        }
        pub(crate) fn identifier(&self) -> String {
            if self.number == 0 {
                self.kind.name().into()
            } else {
                format!("{} {}", self.kind.name(), self.number)
            }
        }
        pub(crate) fn length_m(&self, pixel_size: f64) -> f64 {
            self.points[0].distance(self.points[1]) * pixel_size
        }
        pub(crate) fn area_m2(&self, pixel_size: f64) -> f64 {
            polygon_area(&self.points) * squared(pixel_size)
        }
        pub(crate) fn curve(&self, model: Model) -> ResultT<Curve> {
            let [h, e, w] = self.points.as_slice() else {
                return Err("A parabola requires exactly three control points.".into());
            };
            curve_geometry(*h, *e, *w, self.increment, self.limit, model)
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn display_point(&self, point: Pt) -> Pt {
            point.transformed(self.angle, self.scale, self.anchor)
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn display_points(&self) -> Vec<Pt> {
            self.points.iter().map(|&point| self.display_point(point)).collect()
        }
    }

    pub(crate) fn squared(value: f64) -> f64 {
        // Retain floating-point power rounding instead of an optimized multiply.
        value.powf(std::hint::black_box(2.0))
    }

    pub(crate) fn normalized_degrees(value: f64) -> f64 {
        let result = value.rem_euclid(360.0);
        if result == 0.0 {
            0.0
        } else {
            result
        }
    }

    // Compensated partials retain the correctly rounded finite sum for translated
    // polygon area and vertex-centre calculations.
    pub(crate) fn accurate_sum(values: impl IntoIterator<Item = f64>) -> f64 {
        let mut partials: Vec<f64> = Vec::new();
        for mut x in values {
            let mut count = 0;
            for index in 0..partials.len() {
                let mut y = partials[index];
                if x.abs() < y.abs() {
                    std::mem::swap(&mut x, &mut y);
                }
                let hi = x + y;
                let lo = y - (hi - x);
                if lo != 0.0 {
                    partials[count] = lo;
                    count += 1;
                }
                x = hi;
            }
            partials.truncate(count);
            if x != 0.0 {
                partials.push(x);
            }
        }
        let Some(mut hi) = partials.pop() else {
            return 0.0;
        };
        let mut lo = 0.0;
        while let Some(y) = partials.pop() {
            let x = hi;
            hi = x + y;
            lo = y - (hi - x);
            if lo != 0.0 {
                break;
            }
        }
        if partials
            .last()
            .is_some_and(|last| (lo < 0.0 && *last < 0.0) || (lo > 0.0 && *last > 0.0))
        {
            let y = lo * 2.0;
            let x = hi + y;
            if x - hi == y {
                hi = x;
            }
        }
        hi
    }

    pub(crate) fn polygon_area(points: &[Pt]) -> f64 {
        if points.len() < 3 {
            return 0.0;
        }
        let origin = points[0];
        accurate_sum(points[1..].windows(2).map(|edge| {
            let (a, b) = (edge[0], edge[1]);
            (a.x - origin.x) * (b.y - origin.y) - (b.x - origin.x) * (a.y - origin.y)
        }))
        .abs()
            / 2.0
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn polygon_center(points: &[Pt]) -> Pt {
        if points.is_empty() {
            return Pt::new(0.0, 0.0);
        }
        Pt::new(
            accurate_sum(points.iter().map(|p| p.x)) / points.len() as f64,
            accurate_sum(points.iter().map(|p| p.y)) / points.len() as f64,
        )
    }
    pub(crate) fn polygon_perimeter(points: &[Pt]) -> f64 {
        if points.len() < 3 {
            return 0.0;
        }
        (0..points.len())
            .map(|i| points[i].distance(points[(i + 1) % points.len()]))
            .sum()
    }

    #[derive(Clone, Debug)]
    pub(crate) struct Project {
        pub(crate) tools: Vec<Tool>,
        // Project-file metadata is consumed by the native GUI and its serializer.
        #[cfg_attr(any(not(windows), feature = "headless"), allow(dead_code))]
        pub(crate) name: String,
        pub(crate) model: Model,
        pub(crate) width: i32,
        pub(crate) height: i32,
        pub(crate) pixel_size: f64,
        pub(crate) scale_defined: bool,
        pub(crate) ref_pixel: Option<Pt>,
        pub(crate) ref_xy: Option<Pt>,
        pub(crate) zoom: i32,
        pub(crate) rotation: i32,
        pub(crate) center: Pt,
        pub(crate) filename: String,
        pub(crate) image_png: Arc<[u8]>,
        pub(crate) next_numbers: [u32; 3],
    }
    impl Default for Project {
        fn default() -> Self {
            Self {
                tools: Vec::new(),
                name: "Untitled".into(),
                model: Model::default(),
                width: 0,
                height: 0,
                pixel_size: 1.0,
                scale_defined: false,
                ref_pixel: None,
                ref_xy: None,
                zoom: 100,
                rotation: 0,
                center: Pt::new(0.0, 0.0),
                filename: String::new(),
                image_png: Arc::default(),
                next_numbers: [1; 3],
            }
        }
    }
    impl Project {
        pub(crate) fn georeferenced(&self) -> bool {
            self.scale_defined && self.ref_pixel.is_some() && self.ref_xy.is_some()
        }
        pub(crate) fn world(&self, p: Pt) -> Pt {
            if self.georeferenced() {
                if let (Some(origin), Some(reference)) = (self.ref_pixel, self.ref_xy) {
                    return Pt::new(
                        reference.x + (p.x - origin.x) * self.pixel_size,
                        reference.y - (p.y - origin.y) * self.pixel_size,
                    );
                }
            }
            p.scale(self.pixel_size)
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn source(&self, p: Pt) -> Pt {
            if self.georeferenced() {
                if let (Some(origin), Some(reference)) = (self.ref_pixel, self.ref_xy) {
                    return Pt::new(
                        origin.x + (p.x - reference.x) / self.pixel_size,
                        origin.y - (p.y - reference.y) / self.pixel_size,
                    );
                }
            }
            Pt::new(p.x / self.pixel_size, p.y / self.pixel_size)
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn new_number(&mut self, kind: Kind) -> u32 {
            let mut number = self.next_numbers[kind.index()].max(1);
            while self
                .tools
                .iter()
                .any(|tool| tool.kind == kind && tool.number == number)
            {
                number = number.checked_add(1).unwrap_or(1);
            }
            self.next_numbers[kind.index()] = number.checked_add(1).unwrap_or(1);
            number
        }
        pub(crate) fn reconcile_numbers(&mut self) -> ResultT<()> {
            for kind in [Kind::Curve, Kind::Polygon, Kind::Measure] {
                let mut used = std::collections::HashSet::new();
                for tool in self.tools.iter_mut().filter(|tool| tool.kind == kind) {
                    if tool.number == 0 || !used.insert(tool.number) {
                        tool.number = 0;
                    }
                }
                let mut number = 1u32;
                for tool in self
                    .tools
                    .iter_mut()
                    .filter(|tool| tool.kind == kind && tool.number == 0)
                {
                    while used.contains(&number) {
                        number = number.checked_add(1).ok_or("Too many numbered objects.")?;
                    }
                    tool.number = number;
                    used.insert(number);
                }
                let highest = used.into_iter().max().unwrap_or(0);
                self.next_numbers[kind.index()] = self.next_numbers[kind.index()].max(
                    highest
                        .checked_add(1)
                        .ok_or("Object number exceeds the supported range.")?,
                );
            }
            Ok(())
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn calibrated(&mut self, display_distance: f64, meters: f64) -> ResultT<()> {
            if !display_distance.is_finite()
                || !meters.is_finite()
                || display_distance <= 0.0
                || meters <= 0.0
            {
                return Err("Calibration distances must be positive finite values.".into());
            }
            let pixel_size = meters / display_distance * (f64::from(self.zoom) / 100.0);
            if !pixel_size.is_finite() || pixel_size < 1e-12 {
                return Err("Calibrated pixel size must be finite and at least 1e-12.".into());
            }
            self.pixel_size = pixel_size;
            self.scale_defined = true;
            Ok(())
        }
        pub(crate) fn georeference(&mut self, point: Pt, world: Pt) -> ResultT<()> {
            if !self.scale_defined {
                return Err("Calibrate the image scale before georeferencing.".into());
            }
            if !point.finite() || !world.finite() {
                return Err("Reference pixel and XY coordinates must be finite.".into());
            }
            if self.width > 0
                && self.height > 0
                && (point.x < 0.0
                    || point.y < 0.0
                    || point.x >= f64::from(self.width)
                    || point.y >= f64::from(self.height))
            {
                return Err("Reference point must lie within the source image.".into());
            }
            self.ref_pixel = Some(point);
            self.ref_xy = Some(world);
            Ok(())
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn set_zoom(&mut self, zoom: i32) {
            self.zoom = zoom.clamp(10, 500);
            for tool in &mut self.tools {
                tool.scale = self.zoom;
            }
        }
        #[cfg(all(windows, not(feature = "headless")))]
        pub(crate) fn set_rotation(&mut self, rotation: i32) {
            self.rotation = rotation;
            for tool in &mut self.tools {
                tool.angle = rotation;
                tool.anchor = self.center;
            }
        }
    }

    pub(crate) fn pixel_int(value: f64) -> ResultT<i32> {
        if !value.is_finite() {
            return Err("Drawing coordinates must be finite.".into());
        }
        let coordinate = value.round_ties_even();
        if coordinate.abs() > MAX_PIXEL {
            return Err("Drawing coordinates exceed the supported image range.".into());
        }
        Ok(coordinate as i32)
    }
    pub(crate) fn horner(coefficients: &[f64; 7], beta: f64) -> f64 {
        coefficients
            .iter()
            .rev()
            .fold(0.0, |value, &coefficient| value * beta + coefficient)
    }
    pub(crate) fn model_coefficients(beta: f64, model: Model) -> ResultT<[f64; 3]> {
        let (minimum, maximum) = model.beta_range();
        if !beta.is_finite() {
            return Err("Beta must be a finite angle in degrees.".into());
        }
        if !(minimum - 1e-9..=maximum + 1e-9).contains(&beta) {
            return Err(format!(
                "{} requires {minimum}° <= beta <= {maximum}° (received {}°).",
                model.text(),
                fmt_general(beta, 6)
            ));
        }
        let coefficients = match model {
            Model::Oliveira2010 => &OLIVEIRA,
            Model::Hsu1989 => &HSU,
        };
        let values = coefficients.map(|row| horner(&row, beta));
        if values.iter().any(|value| !value.is_finite()) {
            return Err(format!("{} coefficients are not finite.", model.text()));
        }
        Ok(values)
    }
    pub(crate) fn planform_ratio(
        theta: f64,
        beta: f64,
        model: Model,
        coefficients: Option<[f64; 3]>,
    ) -> ResultT<f64> {
        if !theta.is_finite() || !beta.is_finite() {
            return Err("Theta and beta must be finite angles in degrees.".into());
        }
        if theta < 0.0 || beta < 0.0 {
            return Err("Theta and beta must be non-negative angles in degrees.".into());
        }
        if theta == 0.0 {
            return Err(format!("{} is undefined at theta=0 degrees.", model.text()));
        }
        let (minimum, maximum) = model.beta_range();
        if !(minimum - 1e-9..=maximum + 1e-9).contains(&beta) {
            return Err(format!(
                "{} requires beta between {minimum}° and {maximum}°.",
                model.text()
            ));
        }
        let values = match coefficients {
            Some(values) => values,
            None => model_coefficients(beta, model)?,
        };
        if values.iter().any(|value| !value.is_finite()) {
            return Err("Expected three finite parabolic coefficients.".into());
        }
        let [c0, c1, c2] = values;
        let ratio = beta / theta;
        let value = c0 + c1 * ratio + c2 * squared(ratio);
        if !value.is_finite() {
            return Err(format!("{} planform ratio is not finite.", model.text()));
        }
        Ok(value)
    }
    pub(crate) fn wave_direction(h: Pt, e: Pt, w: Pt) -> ResultT<f64> {
        let crest_x = w.x - e.x;
        let crest_y = w.y - e.y;
        let length = crest_x.hypot(crest_y);
        if length == 0.0 {
            return Err("Cannot determine wave direction: E and W coincide.".into());
        }
        let (mut east, mut south) = (-crest_y, crest_x);
        let headland = Pt::new(h.x - e.x, h.y - e.y);
        let normal_dot = east * headland.x + south * headland.y;
        if normal_dot.abs() <= 1e-12 * length * headland.x.hypot(headland.y) {
            return Err(
                "Cannot determine offshore wave direction: H lies on the E-W crest line.".into(),
            );
        }
        if normal_dot < 0.0 {
            east = -east;
            south = -south;
        }
        Ok(normalized_degrees(east.atan2(-south).to_degrees()))
    }
    #[derive(Clone, Debug)]
    pub(crate) struct Curve {
        pub(crate) beta: f64,
        pub(crate) rb: f64,
        pub(crate) orientation: f64,
        pub(crate) direction: f64,
        pub(crate) coeff: [f64; 3],
        pub(crate) angles: Vec<f64>,
        pub(crate) radii: Vec<f64>,
        pub(crate) points: Vec<Pt>,
    }
    pub(crate) fn curve_geometry(h: Pt, e: Pt, w: Pt, increment: f64, limit: f64, model: Model) -> ResultT<Curve> {
        if !increment.is_finite() || increment <= 0.0 {
            return Err("Angle increment must be positive and finite.".into());
        }
        if !limit.is_finite() {
            return Err("Angle limit must be finite.".into());
        }
        if !h.finite() || !e.finite() || !w.finite() {
            return Err("Each control point requires two finite coordinates.".into());
        }
        let (vx, vy) = (e.x - h.x, e.y - h.y);
        let (tx, ty) = (w.x - e.x, w.y - e.y);
        let rb = vx.hypot(vy);
        let crest = tx.hypot(ty);
        if rb == 0.0 || crest == 0.0 {
            return Err("H and E, and E and W, must be distinct points.".into());
        }
        let cross = vx * ty - vy * tx;
        let dot = vx * tx + vy * ty;
        let beta = cross.abs().atan2(-dot).to_degrees();
        if !beta.is_finite() {
            return Err("The reference points do not define a finite angle.".into());
        }
        if limit < beta - 1e-10 {
            return Err(format!(
                "Maximum theta ({limit:.2}°) must not be below beta ({beta:.2}°)."
            ));
        }
        let coeff = model_coefficients(beta, model)?;
        let direction = wave_direction(h, e, w)?;
        let intervals = ((limit - beta) / increment + 1e-12).floor();
        if !intervals.is_finite() || intervals >= MAX_SAMPLES as f64 {
            return Err("This increment produces more than 100,000 curve samples.".into());
        }
        let count = (intervals + 1.0).max(1.0) as usize;
        let base_angle = vy.atan2(vx);
        let sign = if cross > 0.0 { 1.0 } else { -1.0 };
        let mut result = Curve {
            beta,
            rb,
            orientation: normalized_degrees(base_angle.to_degrees()),
            direction,
            coeff,
            angles: Vec::with_capacity(count),
            radii: Vec::with_capacity(count),
            points: Vec::with_capacity(count),
        };
        for index in 0..count {
            let offset = index as f64 * increment;
            let theta = beta + offset;
            let radius = planform_ratio(theta, beta, model, Some(coeff))? * rb;
            let angle = base_angle + sign * offset.to_radians();
            let point = Pt::new(h.x + radius * angle.cos(), h.y + radius * angle.sin());
            pixel_int(point.x)?;
            pixel_int(point.y)?;
            result.angles.push(theta);
            result.radii.push(radius);
            result.points.push(point);
        }
        Ok(result)
    }
}

// ============================================================================
// JSON: strict UTF-8 parser and writer without third-party Rust crates.
// ============================================================================
mod json {
    use super::ResultT;
    use std::collections::BTreeMap;
    #[derive(Clone, Debug)]
    pub enum V {
        Null,
        Bool(bool),
        Int(i64),
        Num(f64),
        Str(String),
        Arr(Vec<V>),
        Obj(BTreeMap<String, V>),
    }
    impl V {
        pub fn get(&self, key: &str) -> Option<&V> {
            if let Self::Obj(v) = self {
                v.get(key)
            } else {
                None
            }
        }
        pub fn str(&self) -> Option<&str> {
            if let Self::Str(s) = self {
                Some(s)
            } else {
                None
            }
        }
        pub fn num(&self) -> Option<f64> {
            match self {
                Self::Int(n) => Some(*n as f64),
                Self::Num(n) => Some(*n),
                _ => None,
            }
        }
        pub fn arr(&self) -> Option<&[V]> {
            if let Self::Arr(a) = self {
                Some(a)
            } else {
                None
            }
        }
        pub fn number_checked(&self, key: &str, default: f64) -> ResultT<f64> {
            let value = match self.get(key) {
                None => default,
                Some(Self::Int(value)) => *value as f64,
                Some(Self::Num(value)) => *value,
                Some(_) => return Err(format!("{key} must be a finite number.")),
            };
            if value.is_finite() {
                Ok(value)
            } else {
                Err(format!("{key} must be a finite number."))
            }
        }
        pub fn string_checked(&self, key: &str, default: &str) -> ResultT<String> {
            match self.get(key) {
                None => Ok(default.to_owned()),
                Some(Self::Str(value)) => Ok(value.clone()),
                Some(_) => Err(format!("{key} must be a string.")),
            }
        }
        pub fn scalar_text(&self) -> ResultT<String> {
            match self {
                Self::Null => Ok("None".into()),
                Self::Bool(value) => Ok(if *value { "True" } else { "False" }.into()),
                Self::Int(value) => Ok(value.to_string()),
                Self::Num(value) => float_text(*value),
                Self::Str(value) => Ok(value.clone()),
                Self::Arr(_) | Self::Obj(_) => Err("Project name must be a scalar value.".into()),
            }
        }
        pub fn bool_checked(&self, key: &str, default: bool) -> ResultT<bool> {
            match self.get(key) {
                None => Ok(default),
                Some(Self::Bool(value)) => Ok(*value),
                Some(_) => Err(format!("{key} must be true or false.")),
            }
        }
    }
    fn float_text(value: f64) -> ResultT<String> {
        // Choose the shortest rounded decimal that retains every binary bit.
        let (precision, scientific) = (0..=16)
            .find_map(|precision| {
                let text = format!("{value:.precision$e}");
                text.parse::<f64>()
                    .is_ok_and(|parsed| parsed.to_bits() == value.to_bits())
                    .then_some((precision, text))
            })
            .ok_or("Cannot format the project name's numeric value.")?;
        let (mantissa, exponent) = scientific
            .split_once('e')
            .ok_or("Cannot format the project name's numeric exponent.")?;
        let exponent = exponent.parse::<i32>().map_err(|error| error.to_string())?;
        if !(-4..16).contains(&exponent) {
            Ok(format!("{mantissa}e{exponent:+03}"))
        } else {
            let decimals = (precision as i32 - exponent).max(0) as usize;
            let text = format!("{value:.decimals$}");
            Ok(if decimals == 0 {
                format!("{text}.0")
            } else {
                text
            })
        }
    }
    pub fn quote(s: &str) -> String {
        let mut out = String::from("\"");
        for c in s.chars() {
            match c {
                '\"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
                c => out.push(c),
            }
        }
        out.push('"');
        out
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub fn number(v: f64) -> String {
        if v.is_finite() {
            format!("{v}")
        } else {
            "null".into()
        }
    }
    pub fn parse(text: &str) -> ResultT<V> {
        let mut p = Parser {
            s: text.as_bytes(),
            i: 0,
        };
        let value = p.value(0)?;
        p.ws();
        if p.i != p.s.len() {
            Err(format!("Unexpected JSON data at byte {}", p.i))
        } else {
            Ok(value)
        }
    }
    struct Parser<'a> {
        s: &'a [u8],
        i: usize,
    }
    impl Parser<'_> {
        fn ws(&mut self) {
            while self.i < self.s.len() && matches!(self.s[self.i], b' ' | b'\n' | b'\r' | b'\t') {
                self.i += 1;
            }
        }
        fn take(&mut self, b: u8) -> bool {
            self.ws();
            if self.s.get(self.i) == Some(&b) {
                self.i += 1;
                true
            } else {
                false
            }
        }
        fn byte(&mut self) -> ResultT<u8> {
            let b = *self.s.get(self.i).ok_or("Truncated JSON")?;
            self.i += 1;
            Ok(b)
        }
        fn chars4(&mut self) -> ResultT<u32> {
            let mut u = 0;
            for _ in 0..4 {
                let c = self.byte()?;
                let d = (c as char)
                    .to_digit(16)
                    .ok_or("Invalid JSON Unicode escape")?;
                u = (u << 4) | d;
            }
            Ok(u)
        }
        fn string(&mut self) -> ResultT<String> {
            if !self.take(b'"') {
                return Err("Expected JSON string".into());
            }
            let mut out = String::new();
            let mut start = self.i;
            loop {
                let c = self.byte()?;
                if c == b'"' {
                    out.push_str(
                        std::str::from_utf8(&self.s[start..self.i - 1])
                            .map_err(|e| e.to_string())?,
                    );
                    return Ok(out);
                }
                if c < 0x20 {
                    return Err("Unescaped JSON control character".into());
                }
                if c == b'\\' {
                    out.push_str(
                        std::str::from_utf8(&self.s[start..self.i - 1])
                            .map_err(|e| e.to_string())?,
                    );
                    let escaped = self.byte()?;
                    match escaped {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\x08'),
                        b'f' => out.push('\x0c'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let mut scalar = self.chars4()?;
                            if (0xd800..=0xdbff).contains(&scalar) {
                                if self.byte()? != b'\\' || self.byte()? != b'u' {
                                    return Err("Expected low surrogate".into());
                                }
                                let low = self.chars4()?;
                                if !(0xdc00..=0xdfff).contains(&low) {
                                    return Err("Invalid low surrogate".into());
                                }
                                scalar = 0x10000 + (scalar - 0xd800) * 1024 + (low - 0xdc00);
                            }
                            out.push(char::from_u32(scalar).ok_or("Invalid Unicode scalar")?);
                        }
                        _ => return Err("Invalid JSON escape".into()),
                    }
                    start = self.i;
                }
            }
        }
        fn value(&mut self, depth: u32) -> ResultT<V> {
            if depth > 80 {
                return Err("JSON nesting exceeds limit".into());
            }
            self.ws();
            match self.s.get(self.i).copied() {
                Some(b'{') => {
                    self.i += 1;
                    let mut o = BTreeMap::new();
                    if self.take(b'}') {
                        return Ok(V::Obj(o));
                    }
                    loop {
                        let key = self.string()?;
                        if !self.take(b':') {
                            return Err("Missing JSON colon".into());
                        }
                        let val = self.value(depth + 1)?;
                        o.insert(key, val);
                        if self.take(b'}') {
                            break;
                        }
                        if !self.take(b',') {
                            return Err("Missing JSON comma".into());
                        }
                    }
                    Ok(V::Obj(o))
                }
                Some(b'[') => {
                    self.i += 1;
                    let mut a = Vec::new();
                    if self.take(b']') {
                        return Ok(V::Arr(a));
                    }
                    loop {
                        a.push(self.value(depth + 1)?);
                        if self.take(b']') {
                            break;
                        }
                        if !self.take(b',') {
                            return Err("Missing JSON comma".into());
                        }
                    }
                    Ok(V::Arr(a))
                }
                Some(b'"') => Ok(V::Str(self.string()?)),
                Some(b't') if self.s[self.i..].starts_with(b"true") => {
                    self.i += 4;
                    Ok(V::Bool(true))
                }
                Some(b'f') if self.s[self.i..].starts_with(b"false") => {
                    self.i += 5;
                    Ok(V::Bool(false))
                }
                Some(b'n') if self.s[self.i..].starts_with(b"null") => {
                    self.i += 4;
                    Ok(V::Null)
                }
                Some(b'-' | b'0'..=b'9') => {
                    let start = self.i;
                    if self.s[self.i] == b'-' {
                        self.i += 1;
                    }
                    match self.s.get(self.i) {
                        Some(b'0') => {
                            self.i += 1;
                        }
                        Some(b'1'..=b'9') => {
                            while self.s.get(self.i).is_some_and(u8::is_ascii_digit) {
                                self.i += 1;
                            }
                        }
                        _ => return Err("Invalid JSON integer part".into()),
                    }
                    if self.s.get(self.i) == Some(&b'.') {
                        self.i += 1;
                        let old = self.i;
                        while self.s.get(self.i).is_some_and(|b| b.is_ascii_digit()) {
                            self.i += 1;
                        }
                        if self.i == old {
                            return Err("Invalid JSON decimal".into());
                        }
                    }
                    if self.s.get(self.i).is_some_and(|b| *b == b'e' || *b == b'E') {
                        self.i += 1;
                        if self.s.get(self.i).is_some_and(|b| *b == b'+' || *b == b'-') {
                            self.i += 1;
                        }
                        let old = self.i;
                        while self.s.get(self.i).is_some_and(|b| b.is_ascii_digit()) {
                            self.i += 1;
                        }
                        if self.i == old {
                            return Err("Invalid JSON exponent".into());
                        }
                    }
                    let token = std::str::from_utf8(&self.s[start..self.i])
                        .map_err(|error| error.to_string())?;
                    if !token.contains(['.', 'e', 'E']) {
                        if let Ok(value) = token.parse::<i64>() {
                            return Ok(V::Int(value));
                        }
                    }
                    let v = token.parse::<f64>().map_err(|error| error.to_string())?;
                    if !v.is_finite() {
                        return Err("Nonfinite JSON number".into());
                    }
                    Ok(V::Num(v))
                }
                _ => Err(format!("Invalid JSON at byte {}", self.i)),
            }
        }
    }
}
mod b64 {
    use super::ResultT;
    #[cfg(all(windows, not(feature = "headless")))]
    pub fn append_encoded(bytes: &[u8], s: &mut String) {
        const ABC: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        s.reserve(bytes.len().div_ceil(3) * 4);
        for chunk in bytes.chunks(3) {
            let a = chunk[0];
            let b = *chunk.get(1).unwrap_or(&0);
            let c = *chunk.get(2).unwrap_or(&0);
            s.push(ABC[(a >> 2) as usize] as char);
            s.push(ABC[(((a & 3) << 4) | (b >> 4)) as usize] as char);
            s.push(if chunk.len() > 1 {
                ABC[(((b & 15) << 2) | (c >> 6)) as usize] as char
            } else {
                '='
            });
            s.push(if chunk.len() > 2 {
                ABC[(c & 63) as usize] as char
            } else {
                '='
            });
        }
    }
    pub fn decode(s: &str) -> ResultT<Vec<u8>> {
        if !s.len().is_multiple_of(4) {
            return Err("Invalid base64 length".into());
        }
        let mut out = Vec::with_capacity(s.len() / 4 * 3);
        for (i, chunk) in s.as_bytes().chunks(4).enumerate() {
            let mut v = [0u32; 4];
            let mut pad = 0;
            for j in 0..4 {
                if chunk[j] == b'=' {
                    if j < 2 || (j == 2 && chunk[3] != b'=') || i != s.len() / 4 - 1 {
                        return Err("Invalid base64 padding".into());
                    }
                    pad += 1;
                } else {
                    if pad > 0 {
                        return Err("Invalid base64 padding order".into());
                    }
                    v[j] = match chunk[j] {
                        b'A'..=b'Z' => (chunk[j] - b'A') as u32,
                        b'a'..=b'z' => (chunk[j] - b'a' + 26) as u32,
                        b'0'..=b'9' => (chunk[j] - b'0' + 52) as u32,
                        b'+' => 62,
                        b'/' => 63,
                        _ => return Err("Invalid base64 digit".into()),
                    };
                }
            }
            let n = v[0] << 18 | v[1] << 12 | v[2] << 6 | v[3];
            out.push((n >> 16) as u8);
            if pad < 2 {
                out.push((n >> 8) as u8);
            }
            if pad == 0 {
                out.push(n as u8);
            }
        }
        Ok(out)
    }
}

mod persistence {
    use super::{b64, json, ResultT};
    use super::engine::*;
    use std::fmt::Write as _;
    use std::path::Path;
    #[cfg(all(windows, not(feature = "headless")))]
    use std::path::PathBuf;

    pub(crate) fn point_from_json(value: &json::V) -> ResultT<Pt> {
        let coordinates = value.arr().ok_or("Expected a coordinate array.")?;
        if coordinates.len() != 2 {
            return Err("Each coordinate must have exactly two numbers.".into());
        }
        let point = Pt::new(
            coordinates[0].num().ok_or("Invalid X coordinate.")?,
            coordinates[1].num().ok_or("Invalid Y coordinate.")?,
        );
        if !point.finite() {
            return Err("Coordinates must be finite.".into());
        }
        Ok(point)
    }
    pub(crate) fn source_point_from_json(value: &json::V) -> ResultT<Pt> {
        let point = point_from_json(value)?;
        if point.x.abs() > MAX_PIXEL || point.y.abs() > MAX_PIXEL {
            return Err("Tool point coordinates exceed the supported pixel range.".into());
        }
        Ok(point)
    }
    pub(crate) fn integer_point_from_json(value: &json::V) -> ResultT<Pt> {
        let point = point_from_json(value)?;
        for coordinate in [point.x, point.y] {
            checked_integer(
                coordinate,
                "Image point",
                f64::from(i32::MIN),
                f64::from(i32::MAX),
            )?;
        }
        Ok(point)
    }
    pub(crate) fn maybe_point(value: Option<&json::V>) -> ResultT<Option<Pt>> {
        match value {
            None | Some(json::V::Null) => Ok(None),
            Some(value) => point_from_json(value).map(Some),
        }
    }
    pub(crate) fn checked_integer(value: f64, name: &str, minimum: f64, maximum: f64) -> ResultT<f64> {
        if !value.is_finite() || value.fract() != 0.0 || !(minimum..=maximum).contains(&value) {
            return Err(format!("Invalid integer for {name}."));
        }
        Ok(value)
    }
    pub(crate) fn integer_field(
        value: &json::V,
        key: &str,
        default: f64,
        minimum: f64,
        maximum: f64,
    ) -> ResultT<f64> {
        checked_integer(value.number_checked(key, default)?, key, minimum, maximum)
    }
    pub(crate) fn positive_number(value: f64, name: &str, minimum: f64) -> ResultT<f64> {
        if !value.is_finite() || value < minimum {
            return Err(format!("{name} must be finite and at least {minimum}."));
        }
        Ok(value)
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn point_json(point: Pt) -> String {
        format!("[{},{}]", json::number(point.x), json::number(point.y))
    }
    pub(crate) fn append_points(
        output: &mut String,
        points: impl IntoIterator<Item = Pt>,
    ) -> ResultT<()> {
        output.push('[');
        for (index, point) in points.into_iter().enumerate() {
            if !point.finite() {
                return Err("Output coordinates must be finite.".into());
            }
            if index != 0 {
                output.push(',');
            }
            let _ = write!(output, "[{},{}]", point.x, point.y);
        }
        output.push(']');
        Ok(())
    }
    // Project files normally embed PNG. Its IHDR supplies the actual image size,
    // independent of stale project metadata. GDI+ validates and decodes the complete
    // image when the native GUI installs the project; other supported formats are
    // passed through to that decoder unchanged.
    pub(crate) fn embedded_png_size(bytes: &[u8]) -> ResultT<Option<(i32, i32)>> {
        if !bytes.starts_with(b"\x89PNG") {
            return Ok(None);
        }
        if bytes.len() < 33
            || &bytes[..8] != b"\x89PNG\r\n\x1a\n"
            || bytes[8..12] != [0, 0, 0, 13]
            || &bytes[12..16] != b"IHDR"
        {
            return Err("Invalid embedded PNG header.".into());
        }
        let width = u32::from_be_bytes(bytes[16..20].try_into().map_err(|_| "Invalid PNG width.")?);
        let height = u32::from_be_bytes(
            bytes[20..24]
                .try_into()
                .map_err(|_| "Invalid PNG height.")?,
        );
        if width == 0 || height == 0 || width > i32::MAX as u32 || height > i32::MAX as u32 {
            return Err("Embedded PNG dimensions exceed the supported image range.".into());
        }
        let valid_depth = match bytes[25] {
            0 => matches!(bytes[24], 1 | 2 | 4 | 8 | 16),
            2 | 4 | 6 => matches!(bytes[24], 8 | 16),
            3 => matches!(bytes[24], 1 | 2 | 4 | 8),
            _ => false,
        };
        if !valid_depth || bytes[26] != 0 || bytes[27] != 0 || bytes[28] > 1 {
            return Err("Invalid embedded PNG image format.".into());
        }
        let mut crc = u32::MAX;
        for &byte in &bytes[12..29] {
            crc ^= u32::from(byte);
            for _ in 0..8 {
                crc = if crc & 1 == 0 {
                    crc >> 1
                } else {
                    (crc >> 1) ^ 0xedb8_8320
                };
            }
        }
        if (!crc).to_be_bytes() != bytes[29..33] {
            return Err("Invalid embedded PNG header checksum.".into());
        }
        Ok(Some((width as i32, height as i32)))
    }

    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn validate_project(project: &Project) -> ResultT<()> {
        positive_number(project.pixel_size, "Pixel size", 1e-12)?;
        if project.width < 0 || project.height < 0 || !(10..=500).contains(&project.zoom) {
            return Err("Invalid image dimensions or project zoom.".into());
        }
        for point in [project.center]
            .into_iter()
            .chain(project.tools.iter().map(|tool| tool.anchor))
        {
            for coordinate in [point.x, point.y] {
                checked_integer(
                    coordinate,
                    "Image point",
                    f64::from(i32::MIN),
                    f64::from(i32::MAX),
                )?;
            }
        }
        if project.ref_pixel.is_some() != project.ref_xy.is_some()
            || (project.ref_pixel.is_some() && !project.scale_defined)
        {
            return Err(
                "A georeferenced project requires calibrated scale and both reference coordinates."
                    .into(),
            );
        }
        if project
            .ref_pixel
            .into_iter()
            .chain(project.ref_xy)
            .any(|point| !point.finite())
        {
            return Err("Reference coordinates must be finite.".into());
        }
        if project.next_numbers.contains(&0) {
            return Err("Object numbering must be positive.".into());
        }
        for tool in &project.tools {
            let valid_count = match tool.kind {
                Kind::Curve => tool.points.len() == 3,
                Kind::Measure => tool.points.len() == 2,
                Kind::Polygon => tool.points.len() >= 3,
            };
            if !valid_count {
                return Err("Incorrect number of tool points.".into());
            }
            if tool
                .points
                .iter()
                .any(|point| !point.finite() || point.x.abs() > MAX_PIXEL || point.y.abs() > MAX_PIXEL)
            {
                return Err("Tool point coordinates exceed the supported pixel range.".into());
            }
            positive_number(tool.increment, "Angle increment", 1e-12)?;
            if !tool.limit.is_finite()
                || tool.limit.max(0.0) / tool.increment > MAX_SAMPLES as f64 + 1.0
            {
                return Err(
                    "The requested curve has too many samples or a nonfinite angle limit.".into(),
                );
            }
            if !(10..=500).contains(&tool.scale) || !(1..=20).contains(&tool.width) {
                return Err("Invalid object scale or line width.".into());
            }
        }
        Ok(())
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn project_to_json(project: &Project) -> ResultT<String> {
        validate_project(project)?;
        let mut output = String::new();
        let _ = writeln!(output, "{{\n  \"format\": \"baycraft\",\n  \"version\": 4,");
        let _ = writeln!(output, "  \"name\": {},", json::quote(&project.name));
        let _ = writeln!(
            output,
            "  \"model\": {},",
            json::quote(project.model.text())
        );
        let _ = writeln!(
            output,
            "  \"width\": {}, \"height\": {},",
            project.width, project.height
        );
        let _ = writeln!(
            output,
            "  \"pixel_size\": {},",
            json::number(project.pixel_size)
        );
        let _ = writeln!(
            output,
            "  \"scale_defined\": {},",
            project.scale_defined
        );
        let _ = writeln!(
            output,
            "  \"reference_pixel\": {},",
            project.ref_pixel.map(point_json).unwrap_or("null".into())
        );
        let _ = writeln!(
            output,
            "  \"reference_xy\": {},",
            project.ref_xy.map(point_json).unwrap_or("null".into())
        );
        let _ = writeln!(output, "  \"scale_reference\": \"image\",");
        let _ = writeln!(
            output,
            "  \"zoom\": {}, \"rotation\": {},",
            project.zoom, project.rotation
        );
        let _ = writeln!(output, "  \"center\": {},", point_json(project.center));
        let _ = writeln!(
            output,
            "  \"next_numbers\": {{\"curve\": {}, \"polygon\": {}, \"ruler\": {}}},",
            project.next_numbers[0], project.next_numbers[1], project.next_numbers[2]
        );
        output.push_str("  \"tools\": [\n");
        for (index, tool) in project.tools.iter().enumerate() {
            if index > 0 {
                output.push_str(",\n");
            }
            let _ = write!(output, "    {{\"kind\": {}, \"points\": ", json::quote(tool.kind.code()));
            append_points(&mut output, tool.points.iter().copied())?;
            output.push_str(",\n");
            let _ = writeln!(
                output,
                "      \"angle\": {}, \"scale\": {}, \"anchor\": {},",
                tool.angle,
                tool.scale,
                point_json(tool.anchor)
            );
            let _ = writeln!(
                output,
                "      \"increment\": {}, \"limit\": {}, \"color\": {}, \"width\": {},",
                json::number(tool.increment),
                json::number(tool.limit),
                json::quote(tool.color.text()),
                tool.width
            );
            let _ = write!(
                output,
                "      \"controls\": true, \"labels\": true, \"visible\": {}, \"number\": {}}}",
                tool.visible,
                tool.number
            );
        }
        output.push_str("\n  ],\n  \"image_png\": ");
        if project.image_png.is_empty() {
            output.push_str("null");
        } else {
            // The base64 alphabet contains no JSON quote or escape characters.
            output.push('"');
            b64::append_encoded(&project.image_png, &mut output);
            output.push('"');
        }
        output.push_str("\n}\n");
        Ok(output)
    }
    pub(crate) fn project_from_json(source: &str) -> ResultT<Project> {
        let root = json::parse(source)?;
        if !matches!(root, json::V::Obj(_))
            || root.get("format").and_then(json::V::str) != Some("baycraft")
        {
            return Err("This is not a Baycraft project.".into());
        }
        let version = integer_field(&root, "version", 0.0, 1.0, 4.0)? as u8;
        // Projects without an explicit model use Hsu1989.
        let model = match root.get("model") {
            None => Model::Hsu1989,
            Some(json::V::Str(value)) => match Model::parse(value) {
                Ok(model) => model,
                Err(_) if version <= 2 => Model::Hsu1989,
                Err(error) => return Err(error),
            },
            Some(_) if version <= 2 => Model::Hsu1989,
            Some(_) => return Err("Unsupported Baycraft planform model.".into()),
        };
        let pixel_size = positive_number(root.number_checked("pixel_size", 1.0)?, "Pixel size", 1e-12)?;
        let mut project = Project {
            name: root
                .get("name")
                .map(json::V::scalar_text)
                .transpose()?
                .unwrap_or_else(|| "Untitled".into()),
            model,
            width: integer_field(&root, "width", 0.0, 0.0, f64::from(i32::MAX))? as i32,
            height: integer_field(&root, "height", 0.0, 0.0, f64::from(i32::MAX))? as i32,
            pixel_size,
            scale_defined: root.bool_checked("scale_defined", pixel_size != 1.0)?,
            ref_pixel: maybe_point(root.get("reference_pixel"))?,
            ref_xy: maybe_point(root.get("reference_xy"))?,
            zoom: integer_field(&root, "zoom", 100.0, 10.0, 500.0)? as i32,
            rotation: integer_field(
                &root,
                "rotation",
                0.0,
                f64::from(i32::MIN),
                f64::from(i32::MAX),
            )? as i32,
            center: root
                .get("center")
                .map(integer_point_from_json)
                .transpose()?
                .unwrap_or(Pt::new(0.0, 0.0)),
            ..Project::default()
        };
        if project.ref_pixel.is_some() != project.ref_xy.is_some() {
            return Err("A georeferenced project requires both reference pixel and XY.".into());
        }
        if project.ref_pixel.is_some() && !project.scale_defined {
            return Err("Georeferenced project has no calibrated scale.".into());
        }
        if let Some(numbering) = root.get("next_numbers") {
            if !matches!(numbering, json::V::Obj(_)) {
                return Err("Object numbering data must be a dictionary.".into());
            }
            for kind in [Kind::Curve, Kind::Polygon, Kind::Measure] {
                project.next_numbers[kind.index()] =
                    integer_field(numbering, kind.code(), 1.0, 1.0, f64::from(u32::MAX))? as u32;
            }
        }
        match root.string_checked("scale_reference", "display")?.as_str() {
            "display" => {
                project.pixel_size = positive_number(
                    project.pixel_size * (f64::from(project.zoom) / 100.0),
                    "Pixel size",
                    1e-12,
                )?;
            }
            "image" => {}
            _ => return Err("Unsupported scale reference.".into()),
        }
        if let Some(items) = root.get("tools") {
            for item in items.arr().ok_or("Project tools must be a list.")? {
                if !matches!(item, json::V::Obj(_)) {
                    return Err("Invalid project tool.".into());
                }
                let kind = Kind::from_str(&item.string_checked("kind", "")?)?;
                let point_data = match item.get("points") {
                    None => &[][..],
                    Some(value) => value.arr().ok_or("Tool points must be a list.")?,
                };
                let points = point_data
                    .iter()
                    .map(source_point_from_json)
                    .collect::<ResultT<Vec<_>>>()?;
                let valid_count = match kind {
                    Kind::Curve => points.len() == 3,
                    Kind::Measure => points.len() == 2,
                    Kind::Polygon => points.len() >= 3,
                };
                if !valid_count {
                    return Err("Incorrect number of tool points.".into());
                }
                let increment = positive_number(
                    item.number_checked("increment", DEFAULT_INCREMENT)?,
                    "Angle increment",
                    1e-12,
                )?;
                let limit = item.number_checked("limit", DEFAULT_LIMIT)?;
                if limit.max(0.0) / increment > MAX_SAMPLES as f64 + 1.0 {
                    return Err("The requested curve has too many samples.".into());
                }
                let mut tool = Tool::new(
                    kind,
                    points,
                    0,
                    project.zoom,
                    project.rotation,
                    project.center,
                );
                tool.angle = integer_field(
                    item,
                    "angle",
                    f64::from(project.rotation),
                    f64::from(i32::MIN),
                    f64::from(i32::MAX),
                )? as i32;
                tool.scale = integer_field(item, "scale", f64::from(project.zoom), 10.0, 500.0)? as i32;
                tool.anchor = item
                    .get("anchor")
                    .map(integer_point_from_json)
                    .transpose()?
                    .unwrap_or(project.center);
                tool.increment = increment;
                tool.limit = limit;
                tool.color = Color::parse(&item.string_checked("color", "#00ff00")?)?;
                tool.width = integer_field(item, "width", f64::from(DEFAULT_WIDTH), 1.0, 20.0)? as i32;
                tool.visible = item.bool_checked("visible", true)?;
                tool.number = integer_field(item, "number", 0.0, 0.0, f64::from(u32::MAX))? as u32;
                project.tools.push(tool);
            }
        }
        project.reconcile_numbers()?;
        match root.get("image_png") {
            None | Some(json::V::Null) => {}
            Some(json::V::Str(encoded)) => {
                project.image_png = b64::decode(encoded)?.into();
                if project.image_png.is_empty() {
                    return Err("Invalid embedded image data.".into());
                }
                if let Some((width, height)) = embedded_png_size(&project.image_png)? {
                    project.width = width;
                    project.height = height;
                }
            }
            Some(_) => return Err("Invalid embedded image data.".into()),
        }
        Ok(project)
    }
    #[cfg(all(windows, not(feature = "headless")))]
    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, new_name: *const u16, flags: u32) -> i32;
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn replace_file_atomic(temporary: &Path, target: &Path) -> ResultT<()> {
        use std::os::windows::ffi::OsStrExt;
        let source: Vec<u16> = temporary
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        let destination: Vec<u16> = target
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        // MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH. Both paths share a
        // directory, so a successful replacement cannot degrade into a copy.
        if unsafe { MoveFileExW(source.as_ptr(), destination.as_ptr(), 0x9) } == 0 {
            return Err(format!(
                "Cannot atomically replace {}: {}",
                target.display(),
                std::io::Error::last_os_error()
            ));
        }
        Ok(())
    }
    /// Own a reserved temporary path; dropping it removes the file unless persisted.
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) struct TemporaryFile {
        pub(crate) path: PathBuf,
        keep: bool,
    }
    #[cfg(all(windows, not(feature = "headless")))]
    impl TemporaryFile {
        pub(crate) fn reserve(parent: &Path, prefix: &std::ffi::OsStr, suffix: &str) -> ResultT<(Self, std::fs::File)> {
            use std::sync::atomic::{AtomicU64, Ordering};
            static SEQUENCE: AtomicU64 = AtomicU64::new(0);
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
                .map(|time| time.as_nanos()).unwrap_or(0);
            for _ in 0..64 {
                let mut name = prefix.to_os_string();
                name.push(format!(".{}.{stamp}.{}{suffix}", std::process::id(), SEQUENCE.fetch_add(1, Ordering::Relaxed)));
                let path = parent.join(name);
                match std::fs::OpenOptions::new().write(true).create_new(true).open(&path) {
                    Ok(file) => return Ok((Self { path, keep: false }, file)),
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                    Err(error) => return Err(format!("{}: {error}", path.display())),
                }
            }
            Err("Cannot reserve a unique temporary file.".into())
        }
        pub(crate) fn image() -> ResultT<Self> {
            let (temporary, file) = Self::reserve(&std::env::temp_dir(), std::ffi::OsStr::new("baycraft"), ".png")?;
            drop(file);
            Ok(temporary)
        }
        pub(crate) fn persist(mut self) -> PathBuf {
            self.keep = true;
            self.path.clone()
        }
    }
    #[cfg(all(windows, not(feature = "headless")))]
    impl Drop for TemporaryFile {
        fn drop(&mut self) {
            if !self.keep {
                let _ = std::fs::remove_file(&self.path);
            }
        }
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn atomic_write(target: &Path, contents: &[u8]) -> ResultT<()> {
        use std::io::Write as _;
        let name = target.file_name().ok_or("The path must contain a file name.")?;
        let parent = target.parent().unwrap_or_else(|| Path::new("."));
        let (temporary, mut file) = TemporaryFile::reserve(parent, name, ".tmp")?;
        // The file must close before TemporaryFile removes its path on Windows.
        // Even the error path explicitly drops the handle before returning.
        let result = (|| -> std::io::Result<()> {
            file.write_all(contents)?;
            file.flush()?;
            file.sync_all()?;
            if file.metadata()?.len() != contents.len() as u64 {
                return Err(std::io::Error::other("The temporary file has an unexpected size."));
            }
            Ok(())
        })();
        drop(file);
        result.map_err(|error| format!("{}: {error}", target.display()))?;
        replace_file_atomic(&temporary.path, target)
    }

    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn save_project(project: &Project, path: &Path) -> ResultT<()> {
        atomic_write(path, project_to_json(project)?.as_bytes())
    }
    pub(crate) fn load_project(path: &Path) -> ResultT<Project> {
        let content = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
        let mut project = project_from_json(&content)?;
        project.filename = path
            .canonicalize()
            .unwrap_or_else(|_| path.to_path_buf())
            .to_string_lossy()
            .into_owned();
        Ok(project)
    }
}

mod reporting {
    use super::engine::*;
    use super::formatting::*;
    use std::fmt::Write as _;
    #[cfg(all(windows, not(feature = "headless")))]
    use super::{persistence::atomic_write, ResultT};
    #[cfg(all(windows, not(feature = "headless")))]
    use std::path::{Path, PathBuf};

    pub(crate) fn report(p: &Project, selected: Option<usize>) -> String {
        let mut s = String::new();
        macro_rules! line {($($arg:tt)*)=>{{let _=writeln!(s,$($arg)*);}}}
        let curves = p.tools.iter().filter(|t| t.kind == Kind::Curve).count();
        let polys = p.tools.iter().filter(|t| t.kind == Kind::Polygon).count();
        line!("BAYCRAFT - BAY PLANFORM TECHNICAL REPORT");
        line!("{}", "=".repeat(77));
        line!("Planform model:      {}", p.model.text());
        if p.image_png.is_empty() {
            line!("Background image:    No image imported");
        } else {
            line!(
                "Background image:    {} x {} image pixels",
                p.width,
                p.height
            );
        }
        line!(
            "Image scale:         {} m / source-image pixel",
            fmt_general(p.pixel_size, 12)
        );
        line!(
            "Georeferenced:       {}",
            if p.georeferenced() { "Yes" } else { "No" }
        );
        line!(
            "Current view:        zoom {}%; rotation {} degrees",
            p.zoom,
            p.rotation
        );
        line!(
            "Objects:             {} planform curves; {} polygons",
            curves,
            polys
        );
        line!(
            "Coordinate system:   {}",
            if p.georeferenced() {
                "user-supplied planar XY (X east, Y north), metres"
            } else {
                "local image XY; x rightwards, y downwards"
            }
        );
        line!("Units:               lengths/radii in m; areas in m^2; angles in degrees");
        line!("");
        if let (Some(px), Some(w)) = (p.ref_pixel, p.ref_xy) {
            if p.georeferenced() {
                line!(
                    "Reference pixel:     column={:.6}, row={:.6} (source image)",
                    px.x,
                    px.y
                );
                line!("Reference location:  X={:.6} m, Y={:.6} m", w.x, w.y);
                line!("Reference system:    supplied metric XY; EPSG/CRS not specified");
                line!("North-up assumption: original image top corresponds to north");
                line!("");
            }
        }
        line!("1. METHOD AND EQUATIONS");
        line!("{}", "-".repeat(77));
        line!(
            "The H-E-W control geometry establishes beta and Rb and the {}",
            p.model.text()
        );
        s.push_str(r#"coefficient model generates an idealized beach planform for comparison
with an observed shoreline using three defining control points.

Control points:
  H = wave diffraction point (upcoast headland / structure tip)
  E = downcoast beach control point
  W = point along the downcoast wave-crest/tangent line
  Rb = distance H-E
  dEW = distance E-W; dHW = distance H-W

Reference-angle geometry:
  dAB = sqrt((xB-xA)^2 + (yB-yA)^2)
  Rb = sqrt((xE-xH)^2 + (yE-yH)^2)
  beta = acos((Rb^2 + dEW^2 - dHW^2) / (2 Rb dEW))
  beta is evaluated in degrees from the H-E-W control points.

Incident wave direction (FROM bearing, degrees clockwise from north):
  0 = waves FROM N, 90 = FROM E, 180 = FROM S, 270 = FROM W.
  E-W represents a wave crest, so wave approach is normal to E-W.
  The offshore-facing normal is assumed to point toward H (headland tip).
  The source image is assumed north-up, with x increasing eastward
  and y increasing southward. View rotation is not map georeferencing.
  For a rotated/unreferenced source image, rotate/georeference the
  original map to north-up before interpreting geographic bearing.

"#);
        {
            line!(
                "{} - PARABOLIC PLANFORM EQUATION",
                p.model.text().to_uppercase()
            );
            s.push_str(r#"  R(theta) / Rb = C0 + C1 (beta/theta) + C2 (beta/theta)^2
  R(theta) = Rb [C0 + C1 beta/theta + C2 (beta/theta)^2]
  theta(k) = beta + k Delta_theta, k = 0,1,..., theta <= theta_max
  Rb and R(theta) have units of length; coefficients and ratios
  are dimensionless. beta and theta use the SAME angle units
  (degrees). The model is undefined at theta = 0 degrees.

"#);
            let (source, observations) = match p.model {
                Model::Oliveira2010 => (
                    "the supplied Oliveira2010 workbook,",
                    "'coeffs' worksheet (48 observations, equal weights; one duplicate retained).",
                ),
                Model::Hsu1989 => (
                    "Hsu & Evans (1989),",
                    "Table 2 (15 observations, equal weights).",
                ),
            };
            line!("Sixth-degree coefficient polynomials fitted to {}", source);
            line!("{}", observations);
            s.push_str(r#"  Ci(beta) = a0 + a1*beta + a2*beta^2 + a3*beta^3
             + a4*beta^4 + a5*beta^5 + a6*beta^6
"#);
            let (beta_min, beta_max) = p.model.beta_range();
            line!(
                "  Fitting reference-angle range: {} to {} degrees.",
                fmt_general(beta_min, 6),
                fmt_general(beta_max, 6)
            );
            s.push_str(r#"  Evaluation is restricted to this data interval; no extrapolation is applied.
  The polynomials are software-derived regressions of tabulated coefficients.
  C0, C1 and C2 are fitted independently; their sum is not forced to one.

"#);
        }
        s.push_str(r#"Sampling and mapped coordinates:
  Polar positions are evaluated in source-image coordinates from H
  after resolving the orientation of H-E-W. Zoom and rotation alter
  the display, not the original image-coordinate metric results.
  Where a reference point is supplied (px0,py0) -> (X0,Y0):
    X = X0 + (image_x - px0)*pixel_size  [east increases right]
    Y = Y0 - (image_y - py0)*pixel_size  [north increases up]
  Otherwise local image XY is used: x = image_x*pixel_size,
  y = image_y*pixel_size (image y increases downwards).
  These coordinates are invariant under display zoom/rotation.
  L(m) = L(source pixels) * pixel_size
  A(m^2) = A(source pixels^2) * pixel_size^2
  Polygon area = 0.5*abs(sum_i(x_i*y_(i+1)-x_(i+1)*y_i)).
  Polygon perimeter joins the last vertex to the first.

Georeferencing assumes an original north-up, unskewed image, an
accurate uniform scale, and supplied XY in a projected metric system.
No EPSG code or map projection is inferred from one reference point.
Physical accuracy depends on map scale, distortion and control quality.

2. PROJECT OBJECTS AND COMPUTED RESULTS
"#);
        line!("{}", "-".repeat(77));
        if curves + polys == 0 {
            line!("No planform or polygon objects in the project.");
        }
        let mut nr = 0;
        for (index, t) in p.tools.iter().enumerate() {
            if t.kind == Kind::Measure {
                continue;
            }
            nr += 1;
            line!("");
            line!("2.{} {}", nr, t.identifier());
            line!("{}", "~".repeat(77));
            line!("Object type: {}", t.kind.code());
            line!("Object ID: {}", t.identifier());
            line!(
                "Selected on Results click: {}",
                if selected == Some(index) { "Yes" } else { "No" }
            );
            line!(
                "Visible: {}; labels: True; control lines: True",
                if t.visible { "True" } else { "False" }
            );
            line!(
                "Line color: {}; line width: {} pixels",
                t.color.text(),
                t.width
            );
            line!("Control point XY (metres; original pixel column/row in brackets):");
            for (j, pt) in t.points.iter().enumerate() {
                let mark = if t.kind == Kind::Curve {
                    CONTROL_LABELS.get(j).copied().unwrap_or("P").to_string()
                } else {
                    format!("P{}", j + 1)
                };
                let world = p.world(*pt);
                line!(
                    "  {:>3}: X={:>15.7} m  Y={:>15.7} m [pixel column={:.3}, row={:.3}]",
                    mark,
                    world.x,
                    world.y,
                    pt.x,
                    pt.y
                );
            }
            if t.kind == Kind::Polygon {
                line!("  Number of vertices = {}", t.points.len());
                line!("  Enclosed area      = {:.9} m^2", t.area_m2(p.pixel_size));
                line!(
                    "  Perimeter          = {:.9} m",
                    polygon_perimeter(&t.points) * p.pixel_size
                );
            } else {
                line!("  Applied model             = {}", p.model.text());
                line!(
                    "  Angular step Delta_theta = {} degrees",
                    fmt_general(t.increment, 9)
                );
                line!(
                    "  Maximum theta            = {} degrees",
                    fmt_general(t.limit, 9)
                );
                match t.curve(p.model) {
                    Ok(c) => {
                        line!(
                            "  Rb (H-E)                 = {:.9} m",
                            t.length_m(p.pixel_size)
                        );
                        line!(
                            "  dEW                      = {:.9} m",
                            t.points[1].distance(t.points[2]) * p.pixel_size
                        );
                        line!(
                            "  dHW                      = {:.9} m",
                            t.points[0].distance(t.points[2]) * p.pixel_size
                        );
                        line!("  Reference angle beta     = {:.9} degrees", c.beta);
                        line!("  Wave direction (FROM)    = {} clockwise from north (north-up image assumed)",fmt_bearing(c.direction));
                        line!(
                            "  Curve orientation angle = {:.9} degrees (image convention)",
                            c.orientation
                        );
                        for (i, v) in c.coeff.iter().enumerate() {
                            line!(
                                "  C{}(beta) = {}{}",
                                i,
                                if v.is_sign_negative() { "" } else { "+" },
                                fmt_general(*v, 12)
                            );
                        }
                        let ratio =
                            planform_ratio(c.beta, c.beta, p.model, Some(c.coeff)).unwrap_or(f64::NAN);
                        line!("  Model R(beta)/Rb          = {}", fmt_general(ratio, 12));
                        line!(
                            "  Model radius at theta=beta = {:.9} m",
                            c.rb * p.pixel_size * ratio
                        );
                        line!("  Number of output samples   = {}", c.angles.len());
                        line!("");
                        line!("  Sampled equilibrium planform:");
                        line!("  index    theta (deg)         R(theta) (m)       R(theta)/Rb         X (m)           Y (m)");
                        for (j, pt) in c.points.iter().enumerate() {
                            let world = p.world(*pt);
                            line!(
                                "  {:>5}  {:>14.2}  {:>19.2}  {:>17.2}  {:>14.2}  {:>14.2}",
                                j + 1,
                                c.angles[j],
                                c.radii[j] * p.pixel_size,
                                c.radii[j] / c.rb,
                                world.x,
                                world.y
                            );
                        }
                    }
                    Err(e) => line!("  CURVE CALCULATION ERROR: {}", e),
                }
            }
        }
        s.push_str(r#"
3. INTERPRETATION AND LIMITATIONS
"#);
        line!("{}", "-".repeat(77));
        line!(
            "Compare the {} modeled planform with the observed shoreline.",
            p.model.text()
        );
        s.push_str(r#"Close alignment can be consistent with near-static equilibrium for
the assumed predominant waves. Differences may arise from sediment
supply, wave climate, engineering structures, reference-point choice,
image distortion, or other processes. No erosion-rate, sediment-budget,
or time-evolution prediction is made by the model overlay.

4. MODEL REFERENCES / PROVENANCE
"#);
        line!("{}", "-".repeat(77));
        if p.model == Model::Oliveira2010 {
            s.push_str(r#"Oliveira and Barreiro (2010). Coastal Engineering, 57, 124-131.
  Table 1, p. 127: parabolic-model fitting coefficients for Portuguese beaches.
  Numerical source: supplied oliveira2010_table1 workbook, 'coeffs' worksheet.
  Independent sixth-degree least-squares regressions of 48 coefficient sets
  at beta = 22.19° to 88.29°; the repeated numeric record is retained.
  The fit uses the worksheet's C0 (constant), C1 (linear), C2 (quadratic).
  Scaled Chebyshev QR fitting at 80 decimal digits; runtime Horner evaluation
  uses the exported 17-significant-digit ordinary-power coefficients.
  These polynomial equations are software-derived, not published equations
  attributed to Oliveira and Barreiro. Table agreement does not establish
  independent physical accuracy or accuracy between the observed beta values.
"#);
        } else {
            s.push_str(r#"Hsu, J.R.C. and Evans, C. (1989). Parabolic bay shapes and applications.
  Proceedings of the Institution of Civil Engineers, Part 2, 87, 557-570.
  Table 2: coefficients C0, C1 and C2 for beta = 10° to 80°.
  Sixth-degree polynomial regression with 15 equally weighted values.
"#);
        }
        line!("");
        line!("END OF REPORT");
        s
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn report_path(project: &Project) -> PathBuf {
        // Saved projects write beside the .bay file; unsaved projects write in the
        // working directory.
        let path = if project.filename.is_empty() {
            PathBuf::from("output.txt")
        } else {
            Path::new(&project.filename)
                .parent()
                .unwrap_or(Path::new("."))
                .join("output.txt")
        };
        if path.is_absolute() {
            path
        } else {
            std::env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(path)
        }
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn write_report_file(path: &Path, contents: &str) -> ResultT<PathBuf> {
        atomic_write(path, contents.as_bytes())?;
        Ok(path.to_path_buf())
    }
    #[cfg(all(windows, not(feature = "headless")))]
    pub(crate) fn save_report_with_fallback(
        p: &Project,
        text: &str,
    ) -> ResultT<(PathBuf, Option<String>)> {
        // Report generation is independent of the selected object's result-window
        // calculation. A malformed curve is recorded as a diagnostic in output.txt.
        let primary = report_path(p);
        match write_report_file(&primary, text) {
            Ok(path) => Ok((path, None)),
            Err(first_error) => {
                let mut alternatives = Vec::<PathBuf>::new();
                if let Ok(cwd) = std::env::current_dir() {
                    alternatives.push(cwd.join("output.txt"));
                }
                if let Ok(exe) = std::env::current_exe() {
                    if let Some(dir) = exe.parent() {
                        alternatives.push(dir.join("output.txt"));
                    }
                }
                alternatives.push(std::env::temp_dir().join("output.txt"));
                let mut attempted = std::collections::HashSet::from([primary.clone()]);
                for candidate in alternatives {
                    if !attempted.insert(candidate.clone()) {
                        continue;
                    }
                    if let Ok(path) = write_report_file(&candidate, text) {
                        return Ok((
                            path,
                            Some(format!(
                                "Could not write {} ({first_error}). Report saved instead to {}",
                                primary.display(),
                                candidate.display()
                            )),
                        ));
                    }
                }
                Err(format!("Cannot write output.txt at {} ({first_error}), nor in the working, executable or temporary directories.",
                    primary.display()))
            }
        }
    }
}

fn curve_to_json(c: &Curve, model: Model, georeference: Option<&Project>) -> ResultT<String> {
    use std::fmt::Write as _;

    fn append_numbers(output: &mut String, values: &[f64]) {
        output.push('[');
        for (index, value) in values.iter().enumerate() {
            if index != 0 {
                output.push(',');
            }
            let _ = write!(output, "{value}");
        }
        output.push(']');
    }

    let mut output = String::new();
    let _ = write!(output,
        "{{\n  \"beta\": {},\n  \"rb\": {},\n  \"orientation_deg\": {},\n  \"model\": {},\n  \"coefficients\": ",
        c.beta, c.rb, c.orientation, json::quote(model.text()));
    append_numbers(&mut output, &c.coeff);
    let _ = write!(output, ",\n  \"wave_direction_deg\": {},\n  \"theta\": ", c.direction);
    append_numbers(&mut output, &c.angles);
    output.push_str(",\n  \"radii\": ");
    append_numbers(&mut output, &c.radii);
    output.push_str(",\n  \"points\": ");
    if let Some(project) = georeference {
        append_points(&mut output, c.points.iter().map(|&point| project.world(point)))?;
    } else {
        append_points(
            &mut output,
            c.points.iter().map(|point| {
                Pt::new(
                    f64::from(point.x.round_ties_even() as i32),
                    f64::from(point.y.round_ties_even() as i32),
                )
            }),
        )?;
    }
    output.push_str(",\n  \"source_points\": ");
    append_points(&mut output, c.points.iter().copied())?;
    if georeference.is_some() {
        output.push_str(",\n  \"coordinate_system\": ");
        output.push_str(&json::quote(
            "User-supplied metric XY (X east, Y north); north-up original image; EPSG unspecified",
        ));
        output.push_str(",\n  \"points_unit\": \"m\"");
    }
    output.push_str("\n}");
    Ok(output)
}
fn calculate_arg(src: &str, override_model: Option<Model>) -> ResultT<String> {
    let data = json::parse(src)?;
    if !matches!(data, json::V::Obj(_)) {
        return Err("--calculate requires a JSON object.".into());
    }
    let field = |key: &str| data.get(key).ok_or_else(|| format!("Missing field: {key}"));
    let source_point = |key: &str| source_point_from_json(field(key)?);
    let model = if let Some(m) = override_model {
        m
    } else {
        Model::parse(&data.string_checked("model", Model::default().text())?)?
    };
    let c = curve_geometry(
        source_point("h")?,
        source_point("e")?,
        source_point("w")?,
        data.number_checked("increment", DEFAULT_INCREMENT)?,
        data.number_checked("limit", DEFAULT_LIMIT)?,
        model,
    )?;
    let keys = ["pixel_size", "reference_pixel", "reference_xy"];
    let supplied = keys.iter().filter(|&&key| data.get(key).is_some()).count();
    let mut location = None;
    if supplied > 0 {
        if supplied != keys.len() {
            return Err("Provide pixel_size, reference_pixel and reference_xy together for georeferenced JSON output".into());
        }
        let pixel_size = data.number_checked("pixel_size", 1.0)?;
        if !pixel_size.is_finite() || pixel_size < 1e-12 {
            return Err("pixel_size must be a positive finite metric distance".into());
        }
        let pixel = point_from_json(field("reference_pixel")?)?;
        let world = point_from_json(field("reference_xy")?)?;
        let mut project = Project {
            pixel_size,
            scale_defined: true,
            ..Project::default()
        };
        project.georeference(pixel, world)?;
        location = Some(project);
    }
    curve_to_json(&c, model, location.as_ref())
}

// ============================================================================
// RGB IMAGE GEOMETRY
// ============================================================================
#[cfg(all(windows, not(feature = "headless")))]
mod raster {
    pub struct Image {
        pub width: usize,
        pub height: usize,
        pub pixels: Vec<u8>,
    }

    pub struct Transformed {
        pub image: Image,
        pub origin: (f64, f64),
    }

    fn storage(width: usize, height: usize, fill: u8) -> Result<Vec<u8>, String> {
        let count = width
            .checked_mul(height)
            .and_then(|n| n.checked_mul(3))
            .ok_or("Image dimensions exceed the supported allocation range.")?;
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(count)
            .map_err(|_| "Not enough memory for the image.".to_owned())?;
        pixels.resize(count, fill);
        Ok(pixels)
    }

    impl Image {
        pub fn blank(width: usize, height: usize) -> Result<Self, String> {
            if width == 0 || height == 0 {
                return Err("Image dimensions must be positive.".into());
            }
            Ok(Self {
                width,
                height,
                pixels: storage(width, height, 0)?,
            })
        }

        pub fn transformed(
            &self,
            zoom: i32,
            rotation: i32,
            anchor: (f64, f64),
        ) -> Result<Transformed, String> {
            if zoom <= 0 || !anchor.0.is_finite() || !anchor.1.is_finite() {
                return Err(
                    "Image transform parameters must be finite and scale must be positive.".into(),
                );
            }
            let angle = f64::from(rotation).to_radians();
            let (sine, cosine) = (angle.sin(), angle.cos());
            let scale = f64::from(zoom) / 100.0;
            let rotate = |point: (f64, f64)| {
                let (x, y) = (point.0 - anchor.0, point.1 - anchor.1);
                (
                    (x * cosine - y * sine + anchor.0) * scale,
                    (x * sine + y * cosine + anchor.1) * scale,
                )
            };
            let corners = [
                (0.0, 0.0),
                (self.width as f64, 0.0),
                (0.0, self.height as f64),
                (self.width as f64, self.height as f64),
            ]
            .map(rotate);
            let left = corners
                .iter()
                .map(|p| p.0)
                .fold(f64::INFINITY, f64::min)
                .floor();
            let top = corners
                .iter()
                .map(|p| p.1)
                .fold(f64::INFINITY, f64::min)
                .floor();
            let right = corners
                .iter()
                .map(|p| p.0)
                .fold(f64::NEG_INFINITY, f64::max)
                .ceil();
            let bottom = corners
                .iter()
                .map(|p| p.1)
                .fold(f64::NEG_INFINITY, f64::max)
                .ceil();
            let width = (right - left).max(1.0);
            let height = (bottom - top).max(1.0);
            if !width.is_finite() || !height.is_finite() || width * height > 100_000_000.0 {
                return Err(
                    "The displayed image would exceed 100 million pixels. Reduce zoom.".into(),
                );
            }
            let (width, height) = (width as usize, height as usize);
            let mut output = Self {
                width,
                height,
                pixels: storage(width, height, 0x3a)?,
            };
            let (ax, ay) = anchor;
            let affine = [
                cosine / scale,
                sine / scale,
                (cosine * left + sine * top) / scale + ax - cosine * ax - sine * ay,
                -sine / scale,
                cosine / scale,
                (-sine * left + cosine * top) / scale + ay + sine * ax - cosine * ay,
            ];
            self.sample_affine(&mut output, affine);
            Ok(Transformed {
                image: output,
                origin: (left, top),
            })
        }

        fn copy_pixel(&self, output: &mut Self, destination: usize, x: i64, y: i64) {
            if x >= 0 && y >= 0 && (x as usize) < self.width && (y as usize) < self.height {
                let source = (y as usize * self.width + x as usize) * 3;
                output.pixels[destination..destination + 3]
                    .copy_from_slice(&self.pixels[source..source + 3]);
            }
        }

        fn sample_affine(&self, output: &mut Self, a: [f64; 6]) {
            let (width, height) = (output.width, output.height);
            let coordinate = |value: f64| if value < 0.0 { -1 } else { value as i64 };
            if a[1] == 0.0 && a[3] == 0.0 {
                // A separable scale advances the same source-centre sequence
                // for every output row, without quantizing its increments.
                let mut y = a[5] + a[4] * 0.5;
                for row in 0..height {
                    let mut x = a[2] + a[0] * 0.5;
                    for column in 0..width {
                        self.copy_pixel(
                            output,
                            (row * width + column) * 3,
                            coordinate(x),
                            coordinate(y),
                        );
                        x += a[0];
                    }
                    y += a[4];
                }
                return;
            }
            let within_fixed_range = |x: f64, y: f64| {
                (x * a[0] + y * a[1] + a[2]).abs() < 32768.0
                    && (x * a[3] + y * a[4] + a[5]).abs() < 32768.0
            };
            if [
                (0.0, 0.0),
                (width as f64, height as f64),
                (0.0, height as f64),
                (width as f64, 0.0),
            ]
            .iter()
            .all(|&(x, y)| within_fixed_range(x, y))
            {
                // Use a signed 16.16 source-centre grid for rotated images.
                // Wider accumulators avoid overflow at the grid boundaries.
                let fixed = |value: f64| (value * 65536.0 + 0.5).floor() as i64;
                let (dx, dy, row_dx, row_dy) = (fixed(a[0]), fixed(a[3]), fixed(a[1]), fixed(a[4]));
                let mut row_x = fixed(a[2] + a[0] * 0.5 + a[1] * 0.5);
                let mut row_y = fixed(a[5] + a[3] * 0.5 + a[4] * 0.5);
                for row in 0..height {
                    let (mut x, mut y) = (row_x, row_y);
                    for column in 0..width {
                        self.copy_pixel(output, (row * width + column) * 3, x >> 16, y >> 16);
                        x += dx;
                        y += dy;
                    }
                    row_x += row_dx;
                    row_y += row_dy;
                }
            } else {
                let mut row_x = a[2] + a[1] * 0.5 + a[0] * 0.5;
                let mut row_y = a[5] + a[4] * 0.5 + a[3] * 0.5;
                for row in 0..height {
                    let (mut x, mut y) = (row_x, row_y);
                    for column in 0..width {
                        self.copy_pixel(
                            output,
                            (row * width + column) * 3,
                            coordinate(x),
                            coordinate(y),
                        );
                        x += a[0];
                        y += a[3];
                    }
                    row_x += a[1];
                    row_y += a[4];
                }
            }
        }
    }
}

// ============================================================================
// WINDOWS GRAPHICAL APPLICATION: standard controls, GDI / GDI+ and common dialogs.
// ============================================================================
// Native Windows ABI: declarations only, independent of application state.
#[cfg(all(windows, not(feature = "headless")))]
mod win32 {
    use std::ffi::c_void;
    pub(super) type H = isize;
    pub(super) const WS_CHILD: u32 = 0x40000000;
    pub(super) const WS_VISIBLE: u32 = 0x10000000;
    pub(super) const WS_BORDER: u32 = 0x00800000;
    pub(super) const WS_VSCROLL: u32 = 0x00200000;
    pub(super) const WS_HSCROLL: u32 = 0x00100000;
    pub(super) const WS_CAPTION: u32 = 0x00c00000;
    pub(super) const WS_SYSMENU: u32 = 0x00080000;
    pub(super) const WS_MINIMIZEBOX: u32 = 0x00020000;
    pub(super) const WS_POPUP: u32 = 0x80000000;
    pub(super) const WS_CLIPCHILDREN: u32 = 0x02000000;
    pub(super) const ES_MULTILINE: u32 = 0x0004;
    pub(super) const ES_AUTOVSCROLL: u32 = 0x0040;
    pub(super) const ES_AUTOHSCROLL: u32 = 0x0080;
    pub(super) const ES_READONLY: u32 = 0x0800;
    pub(super) const EM_LIMITTEXT: u32 = 0x00C5;
    pub(super) const BS_GROUPBOX: u32 = 0x0007;
    pub(super) const WM_CREATE: u32 = 0x0001;
    pub(super) const WM_DESTROY: u32 = 0x0002;
    pub(super) const WM_CLOSE: u32 = 0x0010;
    pub(super) const WM_CANCELMODE: u32 = 0x001f;
    pub(super) const WM_CAPTURECHANGED: u32 = 0x0215;
    pub(super) const WM_SETREDRAW: u32 = 0x000b;
    pub(super) const WM_SIZE: u32 = 0x0005;
    pub(super) const WM_COMMAND: u32 = 0x0111;
    pub(super) const WM_PAINT: u32 = 0x000F;
    pub(super) const WM_ERASEBKGND: u32 = 0x0014;
    pub(super) const WM_LBUTTONDOWN: u32 = 0x0201;
    pub(super) const WM_LBUTTONUP: u32 = 0x0202;
    pub(super) const WM_LBUTTONDBLCLK: u32 = 0x0203;
    pub(super) const WM_RBUTTONUP: u32 = 0x0205;
    pub(super) const WM_MOUSEMOVE: u32 = 0x0200;
    pub(super) const WM_MOUSEWHEEL: u32 = 0x020A;
    pub(super) const WM_MBUTTONDOWN: u32 = 0x0207;
    pub(super) const WM_MBUTTONUP: u32 = 0x0208;
    pub(super) const WM_HSCROLL: u32 = 0x0114;
    pub(super) const WM_VSCROLL: u32 = 0x0115;
    pub(super) const WM_KEYDOWN: u32 = 0x0100;
    pub(super) const WM_SETFONT: u32 = 0x0030;
    pub(super) const WM_GETMINMAXINFO: u32 = 0x0024;
    pub(super) const WM_SETCURSOR: u32 = 0x0020;
    pub(super) const TVM_INSERTITEMW: u32 = 0x1100 + 50;
    pub(super) const TVM_DELETEITEM: u32 = 0x1100 + 1;
    pub(super) const TVM_SETINDENT: u32 = 0x1100 + 7;
    pub(super) const TVM_GETNEXTITEM: u32 = 0x1100 + 10;
    pub(super) const TVM_SELECTITEM: u32 = 0x1100 + 11;
    pub(super) const TVM_ENSUREVISIBLE: u32 = 0x1100 + 20;
    pub(super) const TVM_SETITEMHEIGHT: u32 = 0x1100 + 27;
    pub(super) const TVGN_FIRSTVISIBLE: usize = 5;
    pub(super) const TVGN_CARET: usize = 9;
    pub(super) const TVI_ROOT: H = -65536;
    pub(super) const TVI_LAST: H = -65534;
    pub(super) const UDM_SETBUDDY: u32 = 0x0400 + 105;
    pub(super) const UDM_SETACCEL: u32 = 0x0400 + 107;
    pub(super) const UDM_SETRANGE32: u32 = 0x0400 + 111;
    pub(super) const UDM_SETPOS32: u32 = 0x0400 + 113;
    pub(super) const UDN_DELTAPOS: u32 = (-722_i32) as u32;
    pub(super) const SB_HORZ: i32 = 0;
    pub(super) const SB_VERT: i32 = 1;
    pub(super) const SIF_ALL: u32 = 0x17;
    pub(super) const PS_SOLID: i32 = 0;
    pub(super) const TRANSPARENT: i32 = 1;
    pub(super) const SRCCOPY: u32 = 0xCC0020;
    pub(super) const OFN_NOCHANGEDIR: u32 = 0x0000_0008;
    pub(super) const OFN_EXPLORER: u32 = 0x00080000;
    pub(super) const OFN_FILEMUSTEXIST: u32 = 0x1000;
    pub(super) const OFN_PATHMUSTEXIST: u32 = 0x0800;
    pub(super) const OFN_OVERWRITEPROMPT: u32 = 0x0002;
    pub(super) const CC_RGBINIT: u32 = 0x1;
    pub(super) const CC_FULLOPEN: u32 = 0x2;
    pub(super) const MF_STRING: u32 = 0;
    pub(super) const MF_POPUP: u32 = 0x10;
    pub(super) const MF_SEPARATOR: u32 = 0x800;
    pub(super) const MB_ICONERROR: u32 = 0x10;
    pub(super) const MB_ICONWARNING: u32 = 0x30;
    pub(super) const MB_YESNOCANCEL: u32 = 0x3;
    pub(super) const MB_ICONQUESTION: u32 = 0x20;
    pub(super) const IDYES: i32 = 6;
    pub(super) const IDNO: i32 = 7;
    pub(super) const IDC_ARROW: usize = 32512;
    pub(super) const IDC_CROSS: usize = 32515;
    pub(super) const IDC_SIZEALL: usize = 32646;
    pub(super) const COLOR_WINDOW: isize = 5;
    pub(super) const PIXEL_FORMAT_32BPP_ARGB: i32 = 0x0026200A;
    pub(super) const PIXEL_FORMAT_24BPP_RGB: i32 = 0x00021808;
    pub(super) const WS_TABSTOP: u32 = 0x0001_0000;
    pub(super) const BS_RADIOBUTTON: u32 = 4;
    pub(super) const BM_SETCHECK: u32 = 0x00f1;
    pub(super) const CB_ADDSTRING: u32 = 0x0143;
    pub(super) const CB_GETCURSEL: u32 = 0x0147;
    pub(super) const CB_SETCURSEL: u32 = 0x014e;
    pub(super) const CBN_SELCHANGE: usize = 1;
    pub(super) const CF_UNICODETEXT: u32 = 13;
    pub(super) const GMEM_MOVEABLE: u32 = 2;

    #[repr(C)]
    #[derive(Copy, Clone, Default)]
    pub(super) struct Point {
        pub(super) x: i32,
        pub(super) y: i32,
    }
    #[repr(C)]
    #[derive(Copy, Clone, Default)]
    pub(super) struct Size {
        pub(super) x: i32,
        pub(super) y: i32,
    }
    #[repr(C)]
    #[derive(Copy, Clone, Default)]
    pub(super) struct Rect {
        pub(super) left: i32,
        pub(super) top: i32,
        pub(super) right: i32,
        pub(super) bottom: i32,
    }
    #[repr(C)]
    #[derive(Default)]
    pub(super) struct Msg {
        pub(super) hwnd: H,
        pub(super) message: u32,
        pub(super) wparam: usize,
        pub(super) lparam: isize,
        pub(super) time: u32,
        pub(super) pt: Point,
        pub(super) lprivate: u32,
    }
    #[repr(C)]
    pub(super) struct WndClassEx {
        pub(super) size: u32,
        pub(super) style: u32,
        pub(super) proc: Option<unsafe extern "system" fn(H, u32, usize, isize) -> isize>,
        pub(super) cls_extra: i32,
        pub(super) wnd_extra: i32,
        pub(super) instance: H,
        pub(super) icon: H,
        pub(super) cursor: H,
        pub(super) background: H,
        pub(super) menu_name: *const u16,
        pub(super) class_name: *const u16,
        pub(super) icon_small: H,
    }
    #[repr(C)]
    #[derive(Default)]
    pub(super) struct PaintStruct {
        pub(super) hdc: H,
        pub(super) erase: i32,
        pub(super) rc: Rect,
        pub(super) restore: i32,
        pub(super) update: i32,
        pub(super) reserved: [u8; 32],
    }
    #[repr(C)]
    pub(super) struct ScrollInfo {
        pub(super) size: u32,
        pub(super) mask: u32,
        pub(super) min: i32,
        pub(super) max: i32,
        pub(super) page: u32,
        pub(super) pos: i32,
        pub(super) track: i32,
    }
    #[repr(C)]
    #[derive(Default)]
    pub(super) struct Guid {
        pub(super) a: u32,
        pub(super) b: u16,
        pub(super) c: u16,
        pub(super) d: [u8; 8],
    }
    #[repr(C)]
    pub(super) struct GdipStartupInput {
        pub(super) version: u32,
        pub(super) debug: *const c_void,
        pub(super) suppress_background: i32,
        pub(super) suppress_codecs: i32,
    }
    #[repr(C)]
    pub(super) struct OpenFilename {
        pub(super) size: u32,
        pub(super) owner: H,
        pub(super) instance: H,
        pub(super) filter: *const u16,
        pub(super) custom_filter: *mut u16,
        pub(super) custom_size: u32,
        pub(super) index: u32,
        pub(super) file: *mut u16,
        pub(super) max_file: u32,
        pub(super) file_title: *mut u16,
        pub(super) max_file_title: u32,
        pub(super) initial_dir: *const u16,
        pub(super) title: *const u16,
        pub(super) flags: u32,
        pub(super) file_offset: u16,
        pub(super) file_extension: u16,
        pub(super) default_ext: *const u16,
        pub(super) cust_data: isize,
        pub(super) hook: *const c_void,
        pub(super) template: *const u16,
        pub(super) reserved: *mut c_void,
        pub(super) reserved_num: u32,
        pub(super) flags_ex: u32,
    }
    #[repr(C)]
    pub(super) struct ChooseColor {
        pub(super) size: u32,
        pub(super) owner: H,
        pub(super) instance: H,
        pub(super) color: u32,
        pub(super) custom: *mut u32,
        pub(super) flags: u32,
        pub(super) cust_data: isize,
        pub(super) hook: Option<unsafe extern "system" fn(H, u32, usize, isize) -> usize>,
        pub(super) template: *const u16,
    }
    #[repr(C)]
    #[derive(Default)]
    pub(super) struct MinMaxInfo {
        pub(super) reserved: Point,
        pub(super) max_size: Point,
        pub(super) max_position: Point,
        pub(super) min_track: Point,
        pub(super) max_track: Point,
    }

    #[link(name = "user32")]
    extern "system" {
        pub(super) fn RegisterClassExW(cls: *const WndClassEx) -> u16;
        pub(super) fn CreateWindowExW(
            ex: u32,
            cls: *const u16,
            title: *const u16,
            style: u32,
            x: i32,
            y: i32,
            w: i32,
            h: i32,
            parent: H,
            id: H,
            instance: H,
            param: *mut c_void,
        ) -> H;
        pub(super) fn DefWindowProcW(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize;
        pub(super) fn DestroyWindow(hwnd: H) -> i32;
        pub(super) fn ShowWindow(hwnd: H, n: i32) -> i32;
        pub(super) fn UpdateWindow(hwnd: H) -> i32;
        pub(super) fn MoveWindow(hwnd: H, x: i32, y: i32, w: i32, h: i32, repaint: i32) -> i32;
        pub(super) fn GetClientRect(hwnd: H, out: *mut Rect) -> i32;
        pub(super) fn GetDC(hwnd: H) -> H;
        pub(super) fn ReleaseDC(hwnd: H, dc: H) -> i32;
        pub(super) fn AdjustWindowRectEx(rect: *mut Rect, style: u32, menu: i32, extended_style: u32) -> i32;
        pub(super) fn GetSystemMetrics(idx: i32) -> i32;
        pub(super) fn SystemParametersInfoW(action: u32, p: u32, output: *mut c_void, flags: u32) -> i32;
        pub(super) fn GetMessageW(out: *mut Msg, hwnd: H, min: u32, max: u32) -> i32;
        pub(super) fn TranslateMessage(msg: *const Msg) -> i32;
        pub(super) fn DispatchMessageW(msg: *const Msg) -> isize;
        pub(super) fn IsDialogMessageW(hwnd: H, msg: *mut Msg) -> i32;
        pub(super) fn GetParent(hwnd: H) -> H;
        pub(super) fn SetCursor(cursor: H) -> H;
        pub(super) fn ShowScrollBar(hwnd: H, bar: i32, show: i32) -> i32;
        pub(super) fn GetWindowLongPtrW(hwnd: H, index: i32) -> isize;
        pub(super) fn SetWindowLongPtrW(hwnd: H, index: i32, value: isize) -> isize;
        pub(super) fn PostQuitMessage(code: i32);
        pub(super) fn SendMessageW(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize;
        pub(super) fn MessageBoxW(hwnd: H, text: *const u16, title: *const u16, flags: u32) -> i32;
        pub(super) fn SetWindowTextW(hwnd: H, text: *const u16) -> i32;
        pub(super) fn OpenClipboard(hwnd: H) -> i32;
        pub(super) fn EmptyClipboard() -> i32;
        pub(super) fn SetClipboardData(format: u32, data: H) -> H;
        pub(super) fn CloseClipboard() -> i32;
        pub(super) fn GetWindowTextW(hwnd: H, buf: *mut u16, cap: i32) -> i32;
        pub(super) fn GetWindowTextLengthW(hwnd: H) -> i32;
        pub(super) fn EnableWindow(hwnd: H, enable: i32) -> i32;
        pub(super) fn IsWindow(hwnd: H) -> i32;
        pub(super) fn SetFocus(hwnd: H) -> H;
        pub(super) fn InvalidateRect(hwnd: H, rect: *const Rect, erase: i32) -> i32;
        pub(super) fn BeginPaint(hwnd: H, ps: *mut PaintStruct) -> H;
        pub(super) fn EndPaint(hwnd: H, ps: *const PaintStruct) -> i32;
        pub(super) fn LoadCursorW(instance: H, resource: *const u16) -> H;
        pub(super) fn SetCapture(hwnd: H) -> H;
        pub(super) fn GetCapture() -> H;
        pub(super) fn ReleaseCapture() -> i32;
        pub(super) fn GetKeyState(virtual_key: i32) -> i16;
        pub(super) fn GetFocus() -> H;
        pub(super) fn SetScrollInfo(hwnd: H, bar: i32, info: *const ScrollInfo, redraw: i32) -> i32;
        pub(super) fn GetScrollInfo(hwnd: H, bar: i32, info: *mut ScrollInfo) -> i32;
        pub(super) fn CreateMenu() -> H;
        pub(super) fn CreatePopupMenu() -> H;
        pub(super) fn AppendMenuW(menu: H, flags: u32, id: usize, text: *const u16) -> i32;
        pub(super) fn SetMenu(hwnd: H, menu: H) -> i32;
        pub(super) fn DrawMenuBar(hwnd: H) -> i32;
        pub(super) fn TrackPopupMenu(
            menu: H,
            flags: u32,
            x: i32,
            y: i32,
            reserved: i32,
            owner: H,
            rect: *const Rect,
        ) -> u32;
        pub(super) fn DestroyMenu(menu: H) -> i32;
        pub(super) fn ClientToScreen(hwnd: H, point: *mut Point) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        pub(super) fn GetModuleHandleW(name: *const u16) -> H;
        pub(super) fn GetLastError() -> u32;
        pub(super) fn GlobalAlloc(flags: u32, bytes: usize) -> H;
        pub(super) fn GlobalLock(memory: H) -> *mut c_void;
        pub(super) fn GlobalUnlock(memory: H) -> i32;
        pub(super) fn GlobalFree(memory: H) -> H;
    }
    #[repr(C)]
    pub(super) struct InitCommonControls {
        pub(super) size: u32,
        pub(super) classes: u32,
    }
    #[link(name = "comctl32")]
    extern "system" {
        pub(super) fn InitCommonControlsEx(controls: *const InitCommonControls) -> i32;
        pub(super) fn ImageList_Create(width: i32, height: i32, flags: u32, initial: i32, grow: i32) -> H;
        pub(super) fn ImageList_Destroy(images: H) -> i32;
        pub(super) fn SetWindowSubclass(
            hwnd: H,
            callback: Option<
                unsafe extern "system" fn(H, u32, usize, isize, usize, usize) -> isize,
            >,
            id: usize,
            data: usize,
        ) -> i32;
        pub(super) fn RemoveWindowSubclass(
            hwnd: H,
            callback: Option<
                unsafe extern "system" fn(H, u32, usize, isize, usize, usize) -> isize,
            >,
            id: usize,
        ) -> i32;
        pub(super) fn DefSubclassProc(hwnd: H, message: u32, wparam: usize, lparam: isize) -> isize;
    }
    #[link(name = "gdi32")]
    extern "system" {
        pub(super) fn CreateSolidBrush(rgb: u32) -> H;
        pub(super) fn CreatePen(style: i32, width: i32, color: u32) -> H;
        pub(super) fn SelectObject(hdc: H, obj: H) -> H;
        pub(super) fn DeleteObject(obj: H) -> i32;
        pub(super) fn Rectangle(hdc: H, x: i32, y: i32, x2: i32, y2: i32) -> i32;
        pub(super) fn Ellipse(hdc: H, x: i32, y: i32, x2: i32, y2: i32) -> i32;
        pub(super) fn MoveToEx(hdc: H, x: i32, y: i32, last: *mut Point) -> i32;
        pub(super) fn LineTo(hdc: H, x: i32, y: i32) -> i32;
        pub(super) fn TextOutW(hdc: H, x: i32, y: i32, text: *const u16, len: i32) -> i32;
        pub(super) fn GetTextExtentPoint32W(hdc: H, text: *const u16, len: i32, size: *mut Size) -> i32;
        pub(super) fn GetClipBox(hdc: H, rect: *mut Rect) -> i32;
        pub(super) fn SetTextColor(hdc: H, color: u32) -> u32;
        pub(super) fn SetBkMode(hdc: H, mode: i32) -> i32;
        pub(super) fn CreateFontW(
            height: i32,
            width: i32,
            escapement: i32,
            orientation: i32,
            weight: i32,
            italic: u32,
            underline: u32,
            strike: u32,
            charset: u32,
            output: u32,
            clip: u32,
            quality: u32,
            pitch: u32,
            face: *const u16,
        ) -> H;
        pub(super) fn CreateCompatibleDC(hdc: H) -> H;
        pub(super) fn CreateCompatibleBitmap(hdc: H, w: i32, h: i32) -> H;
        pub(super) fn DeleteDC(hdc: H) -> i32;
        pub(super) fn BitBlt(
            dest: H,
            x: i32,
            y: i32,
            w: i32,
            h: i32,
            src: H,
            sx: i32,
            sy: i32,
            op: u32,
        ) -> i32;
    }
    #[repr(C)]
    #[derive(Default)]
    pub(super) struct BitmapData {
        pub(super) width: u32,
        pub(super) height: u32,
        pub(super) stride: i32,
        pub(super) format: i32,
        pub(super) scan0: *mut c_void,
        pub(super) reserved: usize,
    }
    #[repr(C)]
    pub(super) struct BitmapRect {
        pub(super) x: i32,
        pub(super) y: i32,
        pub(super) width: i32,
        pub(super) height: i32,
    }
    #[repr(C)]
    pub(super) struct EncoderParameter {
        pub(super) guid: Guid,
        pub(super) count: u32,
        pub(super) kind: u32,
        pub(super) value: *const c_void,
    }
    #[repr(C)]
    pub(super) struct EncoderParameters {
        pub(super) count: u32,
        pub(super) parameter: EncoderParameter,
    }

    #[link(name = "gdiplus")]
    extern "system" {
        pub(super) fn GdiplusStartup(
            token: *mut usize,
            input: *const GdipStartupInput,
            output: *mut c_void,
        ) -> i32;
        pub(super) fn GdiplusShutdown(token: usize);
        pub(super) fn GdipLoadImageFromFile(file: *const u16, out: *mut *mut c_void) -> i32;
        pub(super) fn GdipDisposeImage(image: *mut c_void) -> i32;
        pub(super) fn GdipGetImageWidth(image: *mut c_void, w: *mut u32) -> i32;
        pub(super) fn GdipGetImageHeight(image: *mut c_void, h: *mut u32) -> i32;
        pub(super) fn GdipBitmapLockBits(
            image: *mut c_void,
            rect: *const BitmapRect,
            flags: u32,
            format: i32,
            data: *mut BitmapData,
        ) -> i32;
        pub(super) fn GdipBitmapUnlockBits(image: *mut c_void, data: *mut BitmapData) -> i32;
        pub(super) fn GdipCreateHBITMAPFromBitmap(image: *mut c_void, bitmap: *mut H, background: u32) -> i32;

        pub(super) fn GdipCreateFromHDC(hdc: H, out: *mut *mut c_void) -> i32;
        pub(super) fn GdipGetImageGraphicsContext(image: *mut c_void, out: *mut *mut c_void) -> i32;
        pub(super) fn GdipDeleteGraphics(graphics: *mut c_void) -> i32;
        pub(super) fn GdipSaveImageToFile(
            image: *mut c_void,
            file: *const u16,
            encoder: *const Guid,
            params: *const c_void,
        ) -> i32;
        pub(super) fn GdipCreateBitmapFromScan0(
            w: i32,
            h: i32,
            stride: i32,
            format: i32,
            data: *const u8,
            out: *mut *mut c_void,
        ) -> i32;
        pub(super) fn GdipGetDC(g: *mut c_void, dc: *mut H) -> i32;
        pub(super) fn GdipReleaseDC(g: *mut c_void, dc: H) -> i32;
        pub(super) fn GdipCreateSolidFill(color: u32, brush: *mut *mut c_void) -> i32;
        pub(super) fn GdipDeleteBrush(brush: *mut c_void) -> i32;
        pub(super) fn GdipFillPolygonI(
            graphics: *mut c_void,
            brush: *mut c_void,
            points: *const Point,
            count: i32,
            fill_mode: i32,
        ) -> i32;
        pub(super) fn GdipCreateTexture(image: *mut c_void, wrap_mode: i32, texture: *mut *mut c_void) -> i32;
    }
    #[link(name = "comdlg32")]
    extern "system" {
        pub(super) fn GetOpenFileNameW(choose: *mut OpenFilename) -> i32;
        pub(super) fn GetSaveFileNameW(choose: *mut OpenFilename) -> i32;
        pub(super) fn CommDlgExtendedError() -> u32;
        pub(super) fn ChooseColorW(choose: *mut ChooseColor) -> i32;
    }
    #[link(name = "shell32")]
    extern "system" {
        pub(super) fn ShellExecuteW(
            hwnd: H,
            verb: *const u16,
            file: *const u16,
            params: *const u16,
            dir: *const u16,
            show: i32,
        ) -> H;
    }
    #[repr(C)]
    pub(super) struct NotifyHeader {
        pub(super) window: H,
        pub(super) control_id: usize,
        pub(super) code: u32,
    }
    #[repr(C)]
    pub(super) struct TreeItem {
        pub(super) mask: u32,
        pub(super) handle: H,
        pub(super) state: u32,
        pub(super) state_mask: u32,
        pub(super) text: *mut u16,
        pub(super) text_capacity: i32,
        pub(super) image: i32,
        pub(super) selected_image: i32,
        pub(super) children: i32,
        pub(super) parameter: isize,
        pub(super) integral: i32,
        pub(super) state_ex: u32,
        pub(super) window: H,
        pub(super) expanded_image: i32,
        pub(super) reserved: i32,
    }
    #[repr(C)]
    pub(super) struct TreeInsert {
        pub(super) parent: H,
        pub(super) after: H,
        pub(super) item: TreeItem,
    }
    #[repr(C)]
    pub(super) struct SpinDelta {
        pub(super) header: NotifyHeader,
        pub(super) position: i32,
        pub(super) delta: i32,
    }
    #[repr(C)]
    pub(super) struct SpinAcceleration {
        pub(super) seconds: u32,
        pub(super) increment: u32,
    }
    #[repr(C)]
    pub(super) struct HeaderItem {
        pub(super) mask: u32,
        pub(super) width: i32,
        pub(super) text: *mut u16,
        pub(super) bitmap: H,
        pub(super) text_capacity: i32,
        pub(super) format: i32,
        pub(super) parameter: isize,
        pub(super) image: i32,
        pub(super) order: i32,
        pub(super) kind: u32,
        pub(super) filter: *mut c_void,
        pub(super) state: u32,
    }
    #[repr(C)]
    pub(super) struct CustomDraw {
        pub(super) header: NotifyHeader,
        pub(super) stage: u32,
        pub(super) dc: H,
        pub(super) rect: Rect,
        pub(super) item: usize,
        pub(super) item_state: u32,
        pub(super) item_parameter: isize,
    }
    // Only the documented prefix is accessed in the custom-draw notification.
    #[repr(C)]
    pub(super) struct ListCustomDraw {
        pub(super) draw: CustomDraw,
        pub(super) text_color: u32,
        pub(super) background_color: u32,
    }
    #[repr(C)]
    pub(super) struct ListColumn {
        pub(super) mask: u32,
        pub(super) format: i32,
        pub(super) width: i32,
        pub(super) text: *mut u16,
        pub(super) text_capacity: i32,
        pub(super) subitem: i32,
        pub(super) image: i32,
        pub(super) order: i32,
        pub(super) minimum_width: i32,
        pub(super) default_width: i32,
        pub(super) ideal_width: i32,
    }
    #[repr(C)]
    pub(super) struct ListItem {
        pub(super) mask: u32,
        pub(super) item: i32,
        pub(super) subitem: i32,
        pub(super) state: u32,
        pub(super) state_mask: u32,
        pub(super) text: *mut u16,
        pub(super) text_capacity: i32,
        pub(super) image: i32,
        pub(super) parameter: isize,
        pub(super) indent: i32,
        pub(super) group: i32,
        pub(super) column_count: u32,
        pub(super) columns: *mut u32,
        pub(super) column_formats: *mut i32,
        pub(super) group_index: i32,
    }
    pub(super) const WM_NOTIFY: u32 = 0x004e;
    pub(super) const LVM_FIRST: u32 = 0x1000;
    pub(super) const LVM_INSERTCOLUMNW: u32 = LVM_FIRST + 97;
    pub(super) const LVM_INSERTITEMW: u32 = LVM_FIRST + 77;
    pub(super) const LVM_SETITEMTEXTW: u32 = LVM_FIRST + 116;
    pub(super) const LVM_GETHEADER: u32 = LVM_FIRST + 31;
    pub(super) const LVM_SETEXTENDEDLISTVIEWSTYLE: u32 = LVM_FIRST + 54;
    pub(super) const NM_CUSTOMDRAW: u32 = (-12_i32) as u32;
    pub(super) const CDDS_PREPAINT: u32 = 1;
    pub(super) const CDDS_ITEMPREPAINT: u32 = 0x0001_0001;
    pub(super) const CDRF_NOTIFYITEMDRAW: isize = 0x20;
    #[link(name = "user32")]
    extern "system" {
        pub(super) fn FillRect(hdc: H, rect: *const Rect, brush: H) -> i32;
    }
}

#[cfg(all(windows, not(feature = "headless")))]
mod windows_gui {
    use super::*;
    use std::cell::{Cell, RefCell};
    use std::ffi::c_void;
    use std::fs;
    use std::mem::{size_of, zeroed};
    use std::ptr::{null, null_mut};
    use super::win32::*;

    const NEW: usize = 101;
    const OPEN: usize = 102;
    const SAVE: usize = 103;
    const IMPORT: usize = 104;
    const UNDO: usize = 105;
    const REDO: usize = 106;
    const SELECT: usize = 110;
    const PAN: usize = 111;
    const ZOOM: usize = 112;
    const SCALE: usize = 113;
    const GEO: usize = 114;
    const FIT: usize = 115;
    const CURVE: usize = 120;
    const POLYGON: usize = 121;
    const MEASURE: usize = 122;
    const RESULTS: usize = 123;
    const COLOR: usize = 124;
    const EXPORT: usize = 125;
    const APPLY: usize = 140;
    const COORDS: usize = 141;
    const DELETE: usize = 142;
    const ZOOM_EDIT: usize = 150;
    const ROT_EDIT: usize = 151;
    const MODEL_SELECT: usize = 152;
    const STEP_EDIT: usize = 153;
    const LIMIT_EDIT: usize = 154;
    const WIDTH_EDIT: usize = 155;
    const PROP_TITLE: usize = 170;
    const MODEL_RANGE: usize = 171;
    const STEP_L: usize = 172;
    const LIMIT_L: usize = 173;
    const WIDTH_L: usize = 174;
    const MEAS_TITLE: usize = 175;
    const OBJECT_GROUP: usize = 164;
    const OBJECT_LIST: usize = 160;
    const STATUS: usize = 161;
    const POSITION: usize = 162;
    const MEASUREMENTS: usize = 163;
    const M_SAVEAS: usize = 201;
    const M_PRINT: usize = 202;
    const M_HELP: usize = 203;
    const M_ABOUT: usize = 204;
    const M_QUIT: usize = 205;
    const M_CLOSE: usize = 206;
    const M_ORIGINAL: usize = 207;
    const M_ZOOMIN: usize = 208;
    const M_ZOOMOUT: usize = 209;
    const M_ROTLEFT: usize = 210;
    const M_ROTRIGHT: usize = 211;
    const M_DELETEVERTEX: usize = 212;
    const MODEL_LABEL: usize = 176;
    const ZOOM_SPIN: usize = 180;
    const ROT_SPIN: usize = 181;
    const WIDTH_SPIN: usize = 182;
    const CANVAS_LEFT: i32 = 395;
    const DLG_OK: usize = 801;
    const DLG_CANCEL: usize = 802;
    const DLG_COPY: usize = 803;
    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }
    fn wide_path(p: &Path) -> Vec<u16> {
        use std::os::windows::ffi::OsStrExt;
        p.as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }
    fn colorref(rgb: u32) -> u32 {
        (rgb & 0xff00) | ((rgb & 0xff) << 16) | ((rgb >> 16) & 0xff)
    }

    fn pos(l: isize) -> Pt {
        Pt::new((l as i16) as f64, ((l >> 16) as i16) as f64)
    }
    fn point(p: Pt) -> Point {
        Point {
            x: p.x
                .round_ties_even()
                .clamp(i32::MIN as f64, i32::MAX as f64) as i32,
            y: p.y
                .round_ties_even()
                .clamp(i32::MIN as f64, i32::MAX as f64) as i32,
        }
    }
    fn wh(rect: Rect) -> (i32, i32) {
        (rect.right - rect.left, rect.bottom - rect.top)
    }
    const PNG_GUID: Guid = Guid {
        a: 0x557cf406,
        b: 0x1a04,
        c: 0x11d3,
        d: [0x9a, 0x73, 0, 0, 0xf8, 0x1e, 0xf3, 0x2e],
    };
    const JPG_GUID: Guid = Guid {
        a: 0x557cf401,
        b: 0x1a04,
        c: 0x11d3,
        d: [0x9a, 0x73, 0, 0, 0xf8, 0x1e, 0xf3, 0x2e],
    };
    const TIF_GUID: Guid = Guid {
        a: 0x557cf405,
        b: 0x1a04,
        c: 0x11d3,
        d: [0x9a, 0x73, 0, 0, 0xf8, 0x1e, 0xf3, 0x2e],
    };
    fn img_error(code: i32) -> String {
        format!("GDI+ returned error status {code}")
    }
    #[derive(Debug)]
    struct ImageRef(*mut c_void);
    impl Default for ImageRef {
        fn default() -> Self {
            Self(null_mut())
        }
    }
    impl Drop for ImageRef {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    GdipDisposeImage(self.0);
                }
            }
        }
    }
    fn gdip_load(path: &Path) -> ResultT<ImageRef> {
        unsafe {
            let mut image = ImageRef::default();
            let ret = GdipLoadImageFromFile(wide_path(path).as_ptr(), &mut image.0);
            if ret != 0 || image.0.is_null() {
                return Err(format!(
                    "Cannot load image: {} ({})",
                    path.display(),
                    img_error(ret)
                ));
            }
            Ok(image)
        }
    }
    fn gdip_size(img: &ImageRef) -> ResultT<(i32, i32)> {
        unsafe {
            let (mut w, mut h) = (0u32, 0u32);
            let a = GdipGetImageWidth(img.0, &mut w);
            let b = GdipGetImageHeight(img.0, &mut h);
            if a != 0 || b != 0 || w == 0 || h == 0 || w > i32::MAX as u32 || h > i32::MAX as u32 {
                return Err("Invalid image dimensions".into());
            }
            Ok((w as i32, h as i32))
        }
    }
    fn gdip_save(image: &ImageRef, path: &Path, codec: &Guid) -> ResultT<()> {
        let value: u32;
        let parameters;
        let options = if codec.a == JPG_GUID.a {
            value = 75;
            parameters = EncoderParameters {
                count: 1,
                parameter: EncoderParameter {
                    guid: Guid {
                        a: 0x1d5be4b5,
                        b: 0xfa4a,
                        c: 0x452d,
                        d: [0x9c, 0xdd, 0x5d, 0xb3, 0x51, 0x05, 0xe7, 0xeb],
                    },
                    count: 1,
                    kind: 4,
                    value: (&value as *const u32).cast(),
                },
            };
            (&parameters as *const EncoderParameters).cast()
        } else if codec.a == TIF_GUID.a {
            value = 6; // Uncompressed RGB TIFF.
            parameters = EncoderParameters {
                count: 1,
                parameter: EncoderParameter {
                    guid: Guid {
                        a: 0xe09d739d,
                        b: 0xccd4,
                        c: 0x44ee,
                        d: [0x8e, 0xba, 0x3f, 0xbf, 0x8b, 0xe4, 0xfc, 0x58],
                    },
                    count: 1,
                    kind: 4,
                    value: (&value as *const u32).cast(),
                },
            };
            (&parameters as *const EncoderParameters).cast()
        } else {
            null()
        };
        let status =
            unsafe { GdipSaveImageToFile(image.0, wide_path(path).as_ptr(), codec, options) };
        if status != 0 {
            Err(format!("Unable to encode image ({})", img_error(status)))
        } else {
            Ok(())
        }
    }

    struct BitmapLock<'a> {
        image: &'a ImageRef,
        data: BitmapData,
        locked: bool,
    }
    impl<'a> BitmapLock<'a> {
        fn acquire(image: &'a ImageRef, format: i32, write: bool) -> ResultT<Self> {
            let (width, height) = gdip_size(image)?;
            let rect = BitmapRect {
                x: 0,
                y: 0,
                width,
                height,
            };
            let mut data = BitmapData::default();
            gdip_ok(unsafe {
                GdipBitmapLockBits(image.0, &rect, if write { 2 } else { 1 }, format, &mut data)
            })?;
            let lock = Self {
                image,
                data,
                locked: true,
            };
            let bytes_per_pixel = if format == PIXEL_FORMAT_24BPP_RGB {
                3
            } else {
                4
            };
            if lock.data.scan0.is_null()
                || lock.data.width != width as u32
                || lock.data.height != height as u32
                || u64::from(lock.data.stride.unsigned_abs())
                    < u64::from(lock.data.width) * bytes_per_pixel
            {
                return Err("The image decoder returned an invalid pixel buffer.".into());
            }
            Ok(lock)
        }
        fn release(mut self) -> ResultT<()> {
            let status = unsafe { GdipBitmapUnlockBits(self.image.0, &mut self.data) };
            if status == 0 {
                self.locked = false;
            }
            gdip_ok(status)
        }
        fn row(&self, index: usize) -> *mut u8 {
            // The decoder owns this locked buffer. A signed stride includes
            // bottom-up images; callers remain within its reported row width.
            unsafe {
                self.data
                    .scan0
                    .cast::<u8>()
                    .offset(index as isize * self.data.stride as isize)
            }
        }
    }
    impl Drop for BitmapLock<'_> {
        fn drop(&mut self) {
            if self.locked {
                unsafe {
                    GdipBitmapUnlockBits(self.image.0, &mut self.data);
                }
            }
        }
    }

    fn image_rgb(image: &ImageRef) -> ResultT<raster::Image> {
        let pixels = BitmapLock::acquire(image, PIXEL_FORMAT_32BPP_ARGB, false)?;
        let mut rgb =
            raster::Image::blank(pixels.data.width as usize, pixels.data.height as usize)?;
        for row in 0..rgb.height {
            let source = unsafe { std::slice::from_raw_parts(pixels.row(row), rgb.width * 4) };
            let destination = &mut rgb.pixels[row * rgb.width * 3..(row + 1) * rgb.width * 3];
            for (source, destination) in source
                .as_chunks::<4>()
                .0
                .iter()
                .zip(destination.as_chunks_mut::<3>().0.iter_mut())
            {
                destination.copy_from_slice(&[source[2], source[1], source[0]]);
            }
        }
        pixels.release()?;
        Ok(rgb)
    }
    fn bitmap_from_rgb(rgb: &raster::Image) -> ResultT<ImageRef> {
        let width =
            i32::try_from(rgb.width).map_err(|_| "Image width exceeds the supported range.")?;
        let height =
            i32::try_from(rgb.height).map_err(|_| "Image height exceeds the supported range.")?;
        let mut raw = null_mut();
        let status = unsafe {
            GdipCreateBitmapFromScan0(width, height, 0, PIXEL_FORMAT_24BPP_RGB, null(), &mut raw)
        };
        let image = ImageRef(raw);
        gdip_ok(status)?;
        if image.0.is_null() {
            return Err("The graphics system returned an empty image.".into());
        }
        let pixels = BitmapLock::acquire(&image, PIXEL_FORMAT_24BPP_RGB, true)?;
        for row in 0..rgb.height {
            let destination =
                unsafe { std::slice::from_raw_parts_mut(pixels.row(row), rgb.width * 3) };
            let source = &rgb.pixels[row * rgb.width * 3..(row + 1) * rgb.width * 3];
            for (source, destination) in source
                .as_chunks::<3>()
                .0
                .iter()
                .zip(destination.as_chunks_mut::<3>().0.iter_mut())
            {
                destination.copy_from_slice(&[source[2], source[1], source[0]]);
            }
        }
        pixels.release()?;
        Ok(image)
    }
    fn normalize_image_rgb(image: &ImageRef) -> ResultT<ImageRef> {
        // Keep the decoded RGB channels and discard alpha, without blending
        // against the canvas. The resulting bitmap owns its pixel allocation.
        bitmap_from_rgb(&image_rgb(image)?)
    }

    fn encoded_png(image: &ImageRef) -> ResultT<Vec<u8>> {
        let temporary = TemporaryFile::image()?;
        gdip_save(image, &temporary.path, &PNG_GUID)?;
        fs::read(&temporary.path).map_err(|error| error.to_string())
    }
    fn img_from_bytes(bytes: &[u8]) -> ResultT<ImageRef> {
        let temporary = TemporaryFile::image()?;
        fs::write(&temporary.path, bytes).map_err(|error| error.to_string())?;
        let image = gdip_load(&temporary.path)?;
        normalize_image_rgb(&image)
    }

    unsafe fn show_message(hwnd: H, title: &str, message: &str, flags: u32) -> i32 {
        MessageBoxW(hwnd, wide(message).as_ptr(), wide(title).as_ptr(), flags)
    }
    fn edit_text(hwnd: H) -> String {
        unsafe {
            if hwnd == 0 {
                return String::new();
            }
            let n = GetWindowTextLengthW(hwnd).max(0) as usize;
            let mut b = vec![0u16; n + 1];
            let len = GetWindowTextW(hwnd, b.as_mut_ptr(), b.len() as i32).max(0) as usize;
            String::from_utf16_lossy(&b[..len])
        }
    }
    unsafe fn set_text(hwnd: H, s: &str) {
        if hwnd != 0 {
            SetWindowTextW(hwnd, wide(s).as_ptr());
        }
    }
    fn parse_number(s: &str) -> ResultT<f64> {
        let text = s.trim();
        let bytes = text.as_bytes();
        if bytes.iter().enumerate().any(|(index, &byte)| {
            byte == b'_'
                && (index == 0
                    || index + 1 == bytes.len()
                    || !bytes[index - 1].is_ascii_digit()
                    || !bytes[index + 1].is_ascii_digit())
        }) {
            return Err(format!("Invalid number: {text}"));
        }
        let value = text
            .replace('_', "")
            .parse::<f64>()
            .map_err(|_| format!("Invalid number: {text}"))?;
        if !value.is_finite() {
            return Err("Numeric value must be finite".into());
        }
        Ok(value)
    }
    fn parse_integer_entry(text: &str) -> ResultT<i32> {
        let text = text.trim();
        let (negative, digits) = if let Some(digits) = text.strip_prefix('-') {
            (true, digits)
        } else {
            (false, text.strip_prefix('+').unwrap_or(text))
        };
        let radix = if digits.starts_with("0x") || digits.starts_with("0X") {
            Some(16)
        } else if digits.starts_with("0o") || digits.starts_with("0O") {
            Some(8)
        } else if digits.starts_with("0b") || digits.starts_with("0B") {
            Some(2)
        } else {
            None
        };
        if let Some(radix) = radix {
            let digits = &digits[2..];
            let cleaned = digits.replace('_', "");
            if digits.is_empty() || digits.starts_with('_') || digits.ends_with('_') {
                return Err("Enter a valid integer.".into());
            }
            let value =
                i64::from_str_radix(&cleaned, radix).map_err(|_| "Enter a valid integer.")?;
            let value = if negative { -value } else { value };
            return i32::try_from(value)
                .map_err(|_| "The integer is outside the supported range.".into());
        }
        if !digits.is_empty()
            && !digits.starts_with('_')
            && !digits.ends_with('_')
            && digits
                .bytes()
                .all(|byte| byte.is_ascii_digit() || byte == b'_')
        {
            let value = digits
                .replace('_', "")
                .parse::<i64>()
                .map_err(|_| "The integer is outside the supported range.")?;
            let value = if negative { -value } else { value };
            return i32::try_from(value)
                .map_err(|_| "The integer is outside the supported range.".into());
        }
        let bytes = text.as_bytes();
        let mut index = 0;
        while index < bytes.len() {
            if bytes[index] == b'_' {
                if index == 0 || !bytes[index - 1].is_ascii_digit() {
                    return Err("Enter a valid integer.".into());
                }
                while index < bytes.len() && bytes[index] == b'_' {
                    index += 1;
                }
                if index == bytes.len() || !bytes[index].is_ascii_digit() {
                    return Err("Enter a valid integer.".into());
                }
            }
            index += 1;
        }
        let value = parse_number(&text.replace('_', ""))?.trunc();
        if value < f64::from(i32::MIN) || value > f64::from(i32::MAX) {
            return Err("The integer is outside the supported range.".into());
        }
        Ok(value as i32)
    }
    unsafe fn control(
        parent: H,
        class: &str,
        text: &str,
        style: u32,
        id: usize,
        bounds: (i32, i32, i32, i32),
        font: H,
    ) -> H {
        let (x, y, w, h) = bounds;
        let style = style | if class == "STATIC" { 0x80 } else { 0 }; // SS_NOPREFIX.
        let hwnd = CreateWindowExW(
            0,
            wide(class).as_ptr(),
            wide(text).as_ptr(),
            WS_CHILD | WS_VISIBLE | style,
            x,
            y,
            w,
            h,
            parent,
            id as H,
            GetModuleHandleW(null()),
            null_mut(),
        );
        if hwnd != 0 && font != 0 {
            SendMessageW(hwnd, WM_SETFONT, font as usize, 1);
        }
        hwnd
    }
    /// Native child controls sharing one parent and font. Styles remain explicit.
    #[derive(Copy, Clone)]
    struct Controls {
        parent: H,
        font: H,
    }
    impl Controls {
        fn new(parent: H, font: H) -> Self {
            Self { parent, font }
        }
        unsafe fn create(self, class: &str, text: &str, style: u32, id: usize, bounds: (i32, i32, i32, i32)) -> H {
            control(self.parent, class, text, style, id, bounds, self.font)
        }
        unsafe fn label(self, id: usize, text: &str, bounds: (i32, i32, i32, i32)) -> H {
            self.create("STATIC", text, 0, id, bounds)
        }
        unsafe fn button(self, id: usize, text: &str, bounds: (i32, i32, i32, i32)) -> H {
            self.create("BUTTON", text, WS_TABSTOP, id, bounds)
        }
        unsafe fn group(self, id: usize, text: &str, bounds: (i32, i32, i32, i32)) -> H {
            self.create("BUTTON", text, BS_GROUPBOX, id, bounds)
        }
        unsafe fn entry(self, id: usize, text: &str, bounds: (i32, i32, i32, i32)) -> H {
            self.create("EDIT", text, WS_BORDER | ES_AUTOHSCROLL | WS_TABSTOP, id, bounds)
        }
    }

    unsafe fn menu_item(menu: H, id: usize, label: &str) {
        AppendMenuW(menu, MF_STRING, id, wide(label).as_ptr());
    }
    unsafe fn font_line_height(window: H, font: H) -> i32 {
        font_metrics(window, font, "Mg").map_or(18, |size| size.y.max(1))
    }
    unsafe fn font_text_width(window: H, font: H, text: &str) -> i32 {
        font_metrics(window, font, text)
            .map_or_else(|| (text.chars().count() as i32).saturating_mul(8), |size| size.x.max(1))
    }
    unsafe fn font_metrics(window: H, font: H, text: &str) -> Option<Size> {
        let dc = WindowDc { window, dc: GetDC(window) };
        if dc.dc == 0 {
            return None;
        }
        let _selection = GdiSelection::select(dc.dc, font).ok()?;
        let mut size = Size::default();
        let text = wide(text);
        (GetTextExtentPoint32W(dc.dc, text.as_ptr(), (text.len() - 1) as i32, &mut size) != 0).then_some(size)
    }
    unsafe fn spin_control(
        parent: H,
        buddy: H,
        id: usize,
        bounds: (i32, i32, i32, i32),
        limits: (i32, i32, u32, i32),
    ) -> H {
        let spin = control(
            parent,
            "msctls_updown32",
            "",
            0x0020 | 0x0080,
            id,
            bounds,
            0,
        );
        if spin != 0 {
            let (minimum, maximum, increment, value) = limits;
            let acceleration = SpinAcceleration {
                seconds: 0,
                increment,
            };
            SendMessageW(spin, UDM_SETBUDDY, buddy as usize, 0);
            SendMessageW(spin, UDM_SETRANGE32, minimum as usize, maximum as isize);
            SendMessageW(spin, UDM_SETACCEL, 1, &acceleration as *const _ as isize);
            SendMessageW(spin, UDM_SETPOS32, 0, value as isize);
        }
        spin
    }
    struct WorkingDirectoryGuard(Option<PathBuf>);
    impl WorkingDirectoryGuard {
        fn preserve() -> Self {
            Self(std::env::current_dir().ok())
        }
    }
    impl Drop for WorkingDirectoryGuard {
        fn drop(&mut self) {
            if let Some(directory) = &self.0 {
                let _ = std::env::set_current_dir(directory);
            }
        }
    }
    #[derive(Copy, Clone)]
    enum FileDialog {
        OpenProject,
        SaveProject,
        ImportImage,
        ExportImage,
    }
    impl FileDialog {
        fn choose(self, owner: H) -> Option<PathBuf> {
            use std::os::windows::ffi::OsStringExt;
            let (title, filter, extension, save) = match self {
                Self::OpenProject => ("Open Baycraft Project", "Baycraft Project\0*.bay\0JSON\0*.json\0All files\0*.*\0\0", "bay", false),
                Self::SaveProject => ("Save Baycraft Project", "Baycraft Project\0*.bay\0\0", "bay", true),
                Self::ImportImage => ("Import Image File", "Images\0*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.gif\0All files\0*.*\0\0", "", false),
                Self::ExportImage => ("Export Image", "PNG\0*.png\0TIFF\0*.tif;*.tiff\0JPEG\0*.jpg;*.jpeg\0\0", "png", true),
            };
            let _directory = WorkingDirectoryGuard::preserve();
            let filter: Vec<u16> = filter.encode_utf16().collect();
            let native_title = wide(title);
            let extension = wide(extension);
            let mut file = [0u16; 32768];
            unsafe {
                let mut dialog: OpenFilename = zeroed();
                dialog.size = size_of::<OpenFilename>() as u32;
                dialog.owner = owner;
                dialog.filter = filter.as_ptr();
                dialog.file = file.as_mut_ptr();
                dialog.max_file = file.len() as u32;
                dialog.title = native_title.as_ptr();
                // Import deliberately has no default extension.
                dialog.default_ext = if matches!(self, Self::ImportImage) { null() } else { extension.as_ptr() };
                dialog.flags = OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
                    | if save { OFN_OVERWRITEPROMPT } else { OFN_FILEMUSTEXIST };
                let accepted = if save { GetSaveFileNameW(&mut dialog) } else { GetOpenFileNameW(&mut dialog) };
                if accepted == 0 {
                    let error = CommDlgExtendedError();
                    if error != 0 {
                        show_message(owner, title, &format!("The file dialog failed (Windows error {error})."), MB_ICONERROR);
                    }
                    return None;
                }
            }
            let length = file.iter().position(|&c| c == 0).unwrap_or(file.len());
            Some(PathBuf::from(std::ffi::OsString::from_wide(&file[..length])))
        }
    }

    // -------------------------- MODAL WINDOWS --------------------------------
    #[derive(Default)]
    struct FormState {
        edits: Vec<H>,
        values: Option<Vec<f64>>,
        coordinate_rows: Vec<CoordinateRow>,
        coordinate_values: Vec<[String; 2]>,
        coordinate_labels: Vec<String>,
        coordinate_headers: Vec<H>,
        coordinate_viewport: H,
        coordinate_row_height: i32,
        coordinate_header_height: i32,
        coordinate_label_width: i32,
        coordinate_entry_width: i32,
        coordinate_content_width: i32,
        row_offset: i32,
        row_max_offset: i32,
        visible_rows_height: i32,
        column_offset: i32,
        column_max_offset: i32,
        visible_columns_width: i32,
        buttons: Vec<H>,
        coordinate_validation: bool,
        positive_first: bool,
    }
    struct CoordinateRow {
        label: H,
        x_edit: H,
        y_edit: H,
        index: Option<usize>,
    }
    thread_local! {
        static FORM:RefCell<FormState>=RefCell::new(FormState::default());
    }
    struct ClipboardSession;
    impl Drop for ClipboardSession {
        fn drop(&mut self) {
            unsafe {
                CloseClipboard();
            }
        }
    }
    struct ClipboardMemory(H);
    impl Drop for ClipboardMemory {
        fn drop(&mut self) {
            if self.0 != 0 {
                unsafe {
                    GlobalFree(self.0);
                }
            }
        }
    }
    struct LockedClipboardMemory<'a>(&'a ClipboardMemory);
    impl Drop for LockedClipboardMemory<'_> {
        fn drop(&mut self) {
            unsafe {
                GlobalUnlock(self.0 .0);
            }
        }
    }
    fn copy_to_clipboard(owner: H, text: &str) -> ResultT<()> {
        unsafe {
            let normalized = text
                .replace("\r\n", "\n")
                .replace('\r', "\n")
                .replace('\n', "\r\n");
            let buffer = wide(&normalized);
            let bytes = buffer
                .len()
                .checked_mul(std::mem::size_of::<u16>())
                .ok_or("The clipboard text is too large.")?;
            // Prepare replacement data before changing the existing clipboard.
            let mut memory = ClipboardMemory(GlobalAlloc(GMEM_MOVEABLE, bytes));
            if memory.0 == 0 {
                return Err("Cannot allocate clipboard memory".into());
            }
            {
                let pointer = GlobalLock(memory.0).cast::<u16>();
                if pointer.is_null() {
                    return Err("Cannot lock clipboard memory".into());
                }
                let _lock = LockedClipboardMemory(&memory);
                std::ptr::copy_nonoverlapping(buffer.as_ptr(), pointer, buffer.len());
            }
            if OpenClipboard(owner) == 0 {
                return Err(format!(
                    "Cannot open clipboard: {}",
                    std::io::Error::last_os_error()
                ));
            }
            let _clipboard = ClipboardSession;
            if EmptyClipboard() == 0 {
                return Err("Cannot clear the clipboard".into());
            }
            if SetClipboardData(CF_UNICODETEXT, memory.0) == 0 {
                return Err("Cannot place text on clipboard".into());
            }
            // The operating system owns the allocation only after success.
            memory.0 = 0;
            Ok(())
        }
    }
    fn window_belongs_to(mut window: H, ancestor: H) -> bool {
        while window != 0 {
            if window == ancestor {
                return true;
            }
            window = unsafe { GetParent(window) };
        }
        false
    }

    unsafe fn submit_form(hwnd: H) {
        let (values, coordinates, positive_first) = FORM.with(|slot| {
            let mut state = slot.borrow_mut();
            flush_coordinate_rows(&mut state);
            let values = if state.coordinate_validation {
                state.coordinate_values.iter().flat_map(|pair| pair.iter().cloned()).collect()
            } else {
                state.edits.iter().copied().map(edit_text).collect::<Vec<_>>()
            };
            (values, state.coordinate_validation, state.positive_first)
        });
        let numbers = match values.iter().map(|value| parse_number(value)).collect::<ResultT<Vec<_>>>() {
            Ok(numbers) => numbers,
            Err(_) => {
                show_message(hwnd, "Invalid values", "Enter finite numerical values for every field.", MB_ICONERROR);
                return;
            }
        };
        let error = if positive_first && numbers.first().is_some_and(|&value| value < 1e-12) {
            Some("Distance must be a finite positive number.")
        } else if coordinates && !APP.with(|slot| {
            let ui = slot.borrow();
            numbers.chunks_exact(2).all(|pair| {
                let point = ui.project.source(Pt::new(pair[0], pair[1]));
                point.finite() && point.x.abs() <= MAX_PIXEL && point.y.abs() <= MAX_PIXEL
            })
        }) {
            Some("Coordinates exceed the supported image-coordinate range.")
        } else {
            None
        };
        if let Some(error) = error {
            show_message(hwnd, "Invalid values", error, MB_ICONERROR);
            return;
        }
        FORM.with(|slot| slot.borrow_mut().values = Some(numbers));
        DestroyWindow(hwnd);
    }

    unsafe extern "system" fn form_proc(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        dispatch_gui_callback(hwnd, msg, wparam, lparam, form_proc_impl)
    }

    unsafe fn form_proc_impl(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        match msg {
            WM_COMMAND => match wparam & 0xffff {
                DLG_OK => {
                    submit_form(hwnd);
                    0
                }
                DLG_CANCEL => {
                    DestroyWindow(hwnd);
                    0
                }
                _ => DefWindowProcW(hwnd, msg, wparam, lparam),
            },
            WM_VSCROLL | WM_HSCROLL => {
                let horizontal = msg == WM_HSCROLL;
                let (viewport, current, maximum, page) = FORM.with(|slot| {
                    let state = slot.borrow();
                    if horizontal {
                        (
                            state.coordinate_viewport,
                            state.column_offset,
                            state.column_max_offset,
                            state.visible_columns_width,
                        )
                    } else {
                        (
                            state.coordinate_viewport,
                            state.row_offset,
                            state.row_max_offset,
                            state.visible_rows_height,
                        )
                    }
                });
                if maximum > 0 {
                    let unit = (page / 10).max(1);
                    let page_step = (i64::from(page) * 9 / 10) as i32;
                    let next = match (wparam & 0xffff) as u32 {
                        0 => current.saturating_sub(unit),
                        1 => current.saturating_add(unit),
                        2 => current.saturating_sub(page_step),
                        3 => current.saturating_add(page_step),
                        4 | 5 => {
                            let mut info = ScrollInfo {
                                size: size_of::<ScrollInfo>() as u32,
                                mask: SIF_ALL,
                                min: 0,
                                max: 0,
                                page: 0,
                                pos: 0,
                                track: 0,
                            };
                            GetScrollInfo(
                                viewport,
                                if horizontal { SB_HORZ } else { SB_VERT },
                                &mut info,
                            );
                            info.track
                        }
                        6 => 0,
                        7 => maximum,
                        _ => current,
                    };
                    if horizontal {
                        FORM.with(|slot| slot.borrow_mut().column_offset = next.clamp(0, maximum));
                        let offset = FORM.with(|slot| slot.borrow().row_offset);
                        scroll_coordinate_rows(offset);
                    } else {
                        scroll_coordinate_rows(next);
                    }
                }
                0
            }
            WM_MOUSEWHEEL => {
                let delta = ((wparam >> 16) as u16) as i16 as i32;
                let (current, unit) = FORM.with(|slot| {
                    let state = slot.borrow();
                    (state.row_offset, (state.visible_rows_height / 10).max(1))
                });
                scroll_coordinate_rows(
                    current.saturating_sub((delta / 120).saturating_mul(unit)),
                );
                0
            }
            WM_CLOSE => {
                DestroyWindow(hwnd);
                0
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }

    unsafe fn form_tab(backward: bool) {
        let focus = GetFocus();
        let target = FORM.with(|slot| {
            let state = slot.borrow();
            if !state.coordinate_validation {
                let order = state
                    .edits
                    .iter()
                    .chain(state.buttons.iter())
                    .copied()
                    .collect::<Vec<_>>();
                if order.is_empty() {
                    return None;
                }
                let current = order
                    .iter()
                    .position(|&handle| handle == focus)
                    .unwrap_or(0);
                let next = if backward {
                    (current + order.len() - 1) % order.len()
                } else {
                    (current + 1) % order.len()
                };
                return Some((order[next], None));
            }
            let edit_count = state.coordinate_values.len() * 2;
            let count = edit_count + state.buttons.len();
            if count == 0 {
                return None;
            }
            let current = state
                .coordinate_rows
                .iter()
                .find_map(|row| {
                    row.index.and_then(|index| {
                        if row.x_edit == focus {
                            Some(index * 2)
                        } else if row.y_edit == focus {
                            Some(index * 2 + 1)
                        } else {
                            None
                        }
                    })
                })
                .or_else(|| {
                    state
                        .buttons
                        .iter()
                        .position(|&button| button == focus)
                        .map(|index| edit_count + index)
                })
                .unwrap_or(0);
            let next = if backward {
                (current + count - 1) % count
            } else {
                (current + 1) % count
            };
            if next < edit_count {
                Some((0, Some(next)))
            } else {
                Some((state.buttons[next - edit_count], None))
            }
        });
        if let Some((handle, coordinate)) = target {
            if let Some(index) = coordinate {
                let offset = FORM.with(|slot| {
                    let state = slot.borrow();
                    let top = state
                        .coordinate_header_height
                        .saturating_add((index / 2) as i32 * state.coordinate_row_height);
                    let bottom = top.saturating_add(state.coordinate_row_height);
                    if top < state.row_offset {
                        top
                    } else if bottom > state.row_offset.saturating_add(state.visible_rows_height) {
                        bottom.saturating_sub(state.visible_rows_height)
                    } else {
                        state.row_offset
                    }
                });
                scroll_coordinate_rows(offset);
                let next = FORM.with(|slot| {
                    slot.borrow().coordinate_rows.iter().find_map(|row| {
                        (row.index == Some(index / 2)).then_some(if index.is_multiple_of(2) {
                            row.x_edit
                        } else {
                            row.y_edit
                        })
                    })
                });
                if let Some(next) = next {
                    SetFocus(next);
                }
            } else {
                SetFocus(handle);
            }
        }
    }

    unsafe fn modal_loop(owner: H, window: H) -> Option<Vec<f64>> {
        EnableWindow(owner, 0);
        ShowWindow(window, 1);
        UpdateWindow(window);
        let first = FORM.with(|slot| slot.borrow().edits.first().copied());
        if let Some(first) = first {
            SetFocus(first);
        }
        let mut message = Msg::default();
        while IsWindow(window) != 0 && !gui_failed() {
            match GetMessageW(&mut message, 0, 0, 0) {
                -1 => {
                    let error = GetLastError();
                    DestroyWindow(window);
                    show_message(
                        owner,
                        "Input dialog",
                        &format!("The dialog message loop failed (Windows error {error})."),
                        MB_ICONERROR,
                    );
                    break;
                }
                0 => {
                    DestroyWindow(window);
                    PostQuitMessage(message.wparam as i32);
                    break;
                }
                _ => {}
            }
            if window_belongs_to(message.hwnd, window)
                && message.message == WM_MOUSEWHEEL
                && FORM.with(|slot| slot.borrow().coordinate_validation)
            {
                SendMessageW(window, WM_MOUSEWHEEL, message.wparam, message.lparam);
                continue;
            }
            if window_belongs_to(message.hwnd, window) && message.message == WM_KEYDOWN {
                match message.wparam {
                    0x0d => {
                        submit_form(window);
                        continue;
                    }
                    0x1b => {
                        DestroyWindow(window);
                        continue;
                    }
                    0x09 => {
                        form_tab(GetKeyState(0x10) < 0);
                        continue;
                    }
                    _ => {}
                }
            }
            if IsDialogMessageW(window, &mut message) == 0 {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
        if gui_failed() {
            if IsWindow(window) != 0 {
                DestroyWindow(window);
            }
            FORM.with(|slot| *slot.borrow_mut() = FormState::default());
            return None;
        }
        if IsWindow(owner) != 0 {
            EnableWindow(owner, 1);
            SetFocus(owner);
        }
        FORM.with(|slot| std::mem::take(&mut *slot.borrow_mut()).values)
    }

    fn form(
        owner: H,
        title: &str,
        fields: &[(&str, String)],
        introduction: &[String],
    ) -> Option<Vec<f64>> {
        unsafe {
            let single = fields.len() == 1;
            FORM.with(|slot| {
                *slot.borrow_mut() = FormState {
                    positive_first: single,
                    ..FormState::default()
                };
            });
            let font = APP.with(|slot| slot.borrow().font);
            let line_height = font_line_height(owner, font);
            let entry_height = line_height + 6;
            let button_height = line_height + 12;
            let label_width = fields
                .iter()
                .map(|(label, _)| font_text_width(owner, font, label))
                .max()
                .unwrap_or(0);
            let entry_width = font_text_width(
                owner,
                font,
                if single {
                    "00000000000000000000"
                } else {
                    "00000000000000000000000"
                },
            ) + 6;
            let intro_width = introduction
                .iter()
                .map(|text| font_text_width(owner, font, text))
                .max()
                .unwrap_or(0);
            let width = if single {
                (label_width.max(entry_width) + 20).max(224)
            } else {
                (intro_width.max(label_width + 9 + entry_width) + 32).max(256)
            };
            let intro_height = introduction.len() as i32 * (line_height + 9);
            let field_top = if single {
                10 + line_height + 5
            } else {
                16 + intro_height
            };
            let fields_bottom = if single {
                field_top + entry_height
            } else {
                field_top + fields.len() as i32 * (entry_height + 8)
            };
            let height = fields_bottom + 12 + button_height + 12;
            let bounds = centered_bounds(owner, width, height);
            let window = create_popup(owner, "BaycraftForm", title, bounds, true);
            if window == 0 {
                show_message(
                    owner,
                    title,
                    "Cannot create the input dialog.",
                    MB_ICONERROR,
                );
                FORM.with(|slot| *slot.borrow_mut() = FormState::default());
                return None;
            }
            let widgets = Controls::new(window, font);
            let mut ready = true;
            for (index, text) in introduction.iter().enumerate() {
                ready &= widgets.label(
                    0,
                    text,
                    (  16,  16 + index as i32 * (line_height + 9),  width - 32,  line_height,  ),
                ) != 0;
            }
            for (index, (label, initial)) in fields.iter().enumerate() {
                let y = field_top + index as i32 * (entry_height + 8);
                let label_bounds = if single {
                    (10, 10, width - 20, line_height)
                } else {
                    (16, y + 3, label_width, line_height)
                };
                ready &= widgets.label(0, label, label_bounds) != 0;
                let edit_bounds = if single {
                    (10, y, width - 20, entry_height)
                } else {
                    (width - 16 - entry_width, y, entry_width, entry_height)
                };
                let edit = widgets.entry(940 + index, initial, edit_bounds);
                ready &= edit != 0;
                FORM.with(|slot| slot.borrow_mut().edits.push(edit));
            }
            let button_x = if single {
                (width - 200) / 2
            } else {
                width - 216
            };
            let apply = widgets.create(
                "BUTTON",
                if single { "OK" } else { "Apply" },
                WS_TABSTOP | 1,
                DLG_OK,
                (button_x, height - 12 - button_height, 96, button_height),
            );
            let cancel = widgets.button(
                DLG_CANCEL,
                "Cancel",
                (  button_x + 104,  height - 12 - button_height,  96,  button_height,  ),
            );
            if !ready || apply == 0 || cancel == 0 {
                DestroyWindow(window);
                show_message(
                    owner,
                    title,
                    "Cannot create the input dialog controls.",
                    MB_ICONERROR,
                );
                FORM.with(|slot| *slot.borrow_mut() = FormState::default());
                return None;
            }
            FORM.with(|slot| slot.borrow_mut().buttons = vec![apply, cancel]);
            modal_loop(owner, window)
        }
    }
    fn flush_coordinate_rows(state: &mut FormState) {
        for row in &state.coordinate_rows {
            if let Some(values) = row
                .index
                .and_then(|index| state.coordinate_values.get_mut(index))
            {
                *values = [edit_text(row.x_edit), edit_text(row.y_edit)];
            }
        }
    }

    unsafe extern "system" fn coordinate_viewport_proc(
        window: H,
        message: u32,
        wparam: usize,
        lparam: isize,
        subclass_id: usize,
        _reference: usize,
    ) -> isize {
        if gui_failed() {
            return DefSubclassProc(window, message, wparam, lparam);
        }
        guarded_gui_call(0, || {
            if matches!(message, WM_HSCROLL | WM_VSCROLL | WM_MOUSEWHEEL) {
                return SendMessageW(GetParent(window), message, wparam, lparam);
            }
            if message == 0x0082 {
                RemoveWindowSubclass(window, Some(coordinate_viewport_proc), subclass_id);
            }
            DefSubclassProc(window, message, wparam, lparam)
        })
    }

    // A bounded pool of entry controls keeps large polygons editable without
    // allocating a native window for every coordinate. The focused row remains
    // bound to its coordinate even when it scrolls outside the viewport.
    unsafe fn scroll_coordinate_rows(requested: i32) {
        let focus = GetFocus();
        let _guard = InitializationGuard::begin();
        FORM.with(|slot| {
            let mut state = slot.borrow_mut();
            if state.coordinate_rows.is_empty() {
                return;
            }
            flush_coordinate_rows(&mut state);
            state.row_offset = requested.clamp(0, state.row_max_offset);
            let offset = state.row_offset;
            let page = state.visible_rows_height;
            let row_height = state.coordinate_row_height;
            let header_height = state.coordinate_header_height;
            let first = (offset.saturating_sub(header_height).max(0) / row_height) as usize;
            let last = ((offset
                .saturating_add(page)
                .saturating_sub(header_height)
                .max(0)
                / row_height) as usize
                + 1)
            .min(state.coordinate_values.len());
            for row in &mut state.coordinate_rows {
                let pinned = row.x_edit == focus || row.y_edit == focus;
                if !pinned
                    && row
                        .index
                        .is_some_and(|index| index < first || index >= last)
                {
                    row.index = None;
                }
            }
            for index in first..last {
                if state
                    .coordinate_rows
                    .iter()
                    .any(|row| row.index == Some(index))
                {
                    continue;
                }
                if let Some(row) = state
                    .coordinate_rows
                    .iter_mut()
                    .find(|row| row.index.is_none())
                {
                    row.index = Some(index);
                }
            }
            let left = -state.column_offset;
            let label_width = state.coordinate_label_width;
            let entry_width = state.coordinate_entry_width;
            for (index, &header) in state.coordinate_headers.iter().enumerate() {
                let (x, width) = if index == 0 {
                    (left, label_width)
                } else {
                    (
                        left + label_width + (index as i32 - 1) * (entry_width + 8) + 4,
                        entry_width,
                    )
                };
                MoveWindow(header, x, -offset, width, header_height, 0);
            }
            for row in &state.coordinate_rows {
                if let Some(index) = row.index {
                    let y = header_height
                        .saturating_add((index as i32).saturating_mul(row_height))
                        .saturating_sub(offset);
                    set_text(row.label, &state.coordinate_labels[index]);
                    let values = &state.coordinate_values[index];
                    if edit_text(row.x_edit) != values[0] {
                        set_text(row.x_edit, &values[0]);
                    }
                    if edit_text(row.y_edit) != values[1] {
                        set_text(row.y_edit, &values[1]);
                    }
                    MoveWindow(
                        row.label,
                        left + 8,
                        y + 6,
                        (label_width - 16).max(1),
                        row_height - 6,
                        0,
                    );
                    MoveWindow(
                        row.x_edit,
                        left + label_width + 4,
                        y + 3,
                        entry_width,
                        row_height - 6,
                        0,
                    );
                    MoveWindow(
                        row.y_edit,
                        left + label_width + entry_width + 12,
                        y + 3,
                        entry_width,
                        row_height - 6,
                        0,
                    );
                    ShowWindow(row.label, 1);
                    ShowWindow(row.x_edit, 1);
                    ShowWindow(row.y_edit, 1);
                } else {
                    ShowWindow(row.label, 0);
                    ShowWindow(row.x_edit, 0);
                    ShowWindow(row.y_edit, 0);
                }
            }
            for (bar, total, page, offset) in [
                (
                    SB_VERT,
                    state
                        .row_max_offset
                        .saturating_add(state.visible_rows_height),
                    state.visible_rows_height,
                    state.row_offset,
                ),
                (
                    SB_HORZ,
                    state.coordinate_content_width,
                    state.visible_columns_width,
                    state.column_offset,
                ),
            ] {
                let info = ScrollInfo {
                    size: size_of::<ScrollInfo>() as u32,
                    mask: SIF_ALL | 8,
                    min: 0,
                    max: total.saturating_sub(1).max(0),
                    page: page.max(1) as u32,
                    pos: offset,
                    track: 0,
                };
                SetScrollInfo(state.coordinate_viewport, bar, &info, 1);
            }
            InvalidateRect(state.coordinate_viewport, null(), 1);
        });
    }

    fn coordinate_form(
        owner: H,
        coordinates: &[(String, Pt)],
        georeferenced: bool,
    ) -> Option<Vec<f64>> {
        unsafe {
            let font = APP.with(|slot| slot.borrow().font);
            let line_height = font_line_height(owner, font);
            let row_height = line_height + 12;
            let header_height = line_height + 4;
            let entry_width = font_text_width(owner, font, "0000000000000000000") + 6;
            let label_width = coordinates
                .iter()
                .map(|(label, _)| font_text_width(owner, font, label))
                .max()
                .unwrap_or(0)
                .max(font_text_width(owner, font, "Point"))
                + 16;
            let content_width = label_width + (entry_width + 8) * 2;
            let count = i32::try_from(coordinates.len()).ok()?;
            let content_height = header_height.checked_add(count.checked_mul(row_height)?)?;
            let visible_width = content_width.min(GetSystemMetrics(0).saturating_sub(120).max(160));
            let visible_height =
                content_height.min(GetSystemMetrics(1).saturating_sub(240).max(90));
            let vertical_width = GetSystemMetrics(2).max(1);
            let horizontal_height = GetSystemMetrics(3).max(1);
            let viewport_top = 12 + line_height + 10;
            let button_height = line_height + 12;
            let width = 24 + visible_width + vertical_width;
            let height =
                viewport_top + visible_height + horizontal_height + 10 + button_height + 12;
            FORM.with(|slot| {
                *slot.borrow_mut() = FormState {
                    coordinate_validation: true,
                    coordinate_values: coordinates
                        .iter()
                        .map(|(_, point)| [format_coordinate(point.x), format_coordinate(point.y)])
                        .collect(),
                    coordinate_labels: coordinates.iter().map(|(label, _)| label.clone()).collect(),
                    coordinate_row_height: row_height,
                    coordinate_header_height: header_height,
                    coordinate_label_width: label_width,
                    coordinate_entry_width: entry_width,
                    coordinate_content_width: content_width,
                    row_max_offset: content_height.saturating_sub(visible_height).max(0),
                    visible_rows_height: visible_height,
                    column_max_offset: content_width.saturating_sub(visible_width).max(0),
                    visible_columns_width: visible_width,
                    ..FormState::default()
                };
            });
            let bounds = centered_bounds(owner, width, height);
            let window = create_popup(owner, "BaycraftForm", "Edit Point Coordinates", bounds, true);
            if window == 0 {
                show_message(
                    owner,
                    "Edit Point Coordinates",
                    "Cannot create the coordinate editor.",
                    MB_ICONERROR,
                );
                FORM.with(|slot| *slot.borrow_mut() = FormState::default());
                return None;
            }
            let widgets = Controls::new(window, font);
            let headline = if georeferenced {
                "Georeferenced XY (m)"
            } else {
                "Local image XY (m)"
            };
            let title = widgets.label(0, headline, (12, 12, width - 24, line_height));
            let viewport = widgets.create(
                "STATIC",
                "",
                WS_CLIPCHILDREN | WS_VSCROLL | WS_HSCROLL,
                930,
                (  12,  viewport_top,  visible_width + vertical_width,  visible_height + horizontal_height,  ),
            );
            let cells = Controls::new(viewport, font);
            let mut ready = title != 0 && viewport != 0;
            if viewport != 0 {
                ready &= SetWindowSubclass(viewport, Some(coordinate_viewport_proc), 1, 0) != 0;
            }
            FORM.with(|slot| slot.borrow_mut().coordinate_viewport = viewport);
            if ready {
                for text in ["Point", "X (m)", "Y (m)"] {
                    let header = cells.create("STATIC", text, 1, 0, (0, 0, 1, header_height));
                    ready &= header != 0;
                    FORM.with(|slot| slot.borrow_mut().coordinate_headers.push(header));
                }
                let pool_size = ((visible_height / row_height) as usize + 3).min(coordinates.len());
                for index in 0..pool_size {
                    let label = cells.create("STATIC", "", 1, 0, (0, 0, label_width, line_height));
                    let x_edit = cells.entry(950 + index * 2, "", (0, 0, entry_width, row_height - 6));
                    let y_edit = cells.entry(951 + index * 2, "", (0, 0, entry_width, row_height - 6));
                    ready &= label != 0 && x_edit != 0 && y_edit != 0;
                    FORM.with(|slot| {
                        let mut state = slot.borrow_mut();
                        state.edits.extend([x_edit, y_edit]);
                        state.coordinate_rows.push(CoordinateRow {
                            label,
                            x_edit,
                            y_edit,
                            index: None,
                        });
                    });
                    if !ready {
                        break;
                    }
                }
            }
            let button_y = height - 12 - button_height;
            let apply = widgets.create(
                "BUTTON",
                "Apply",
                WS_TABSTOP | 1,
                DLG_OK,
                (width - 212, button_y, 96, button_height),
            );
            let cancel = widgets.button(DLG_CANCEL, "Cancel", (width - 108, button_y, 96, button_height));
            ready &= apply != 0 && cancel != 0;
            if !ready {
                DestroyWindow(window);
                show_message(
                    owner,
                    "Edit Point Coordinates",
                    "Cannot create the coordinate editor controls.",
                    MB_ICONERROR,
                );
                FORM.with(|slot| *slot.borrow_mut() = FormState::default());
                return None;
            }
            FORM.with(|slot| slot.borrow_mut().buttons = vec![apply, cancel]);
            scroll_coordinate_rows(0);
            modal_loop(owner, window)
        }
    }
    fn entry_number(value: f64) -> String {
        if value.fract() == 0.0 {
            format!("{value:.1}")
        } else {
            value.to_string()
        }
    }
    fn format_coordinate(value: f64) -> String {
        let text = format!("{value:.12}");
        let trimmed = text.trim_end_matches('0').trim_end_matches('.');
        if trimmed.is_empty() {
            "0".to_string()
        } else {
            trimmed.to_string()
        }
    }

    struct ResultWindow {
        clipboard: Option<String>,
    }
    struct ResultTable {
        headings: Vec<&'static str>,
        widths: Vec<i32>,
        rows: Vec<Vec<String>>,
        clipboard: String,
    }
    struct SelectedResults {
        title: String,
        width: i32,
        height: i32,
        summary_title: String,
        summary: Vec<Vec<String>>,
        table_title: &'static str,
        table: Option<ResultTable>,
        footer: String,
    }
    thread_local! {
        static RESULT_WINDOWS: RefCell<std::collections::BTreeMap<H, ResultWindow>> = const { RefCell::new(std::collections::BTreeMap::new()) };
    }
    const RESULT_TABLE: usize = 810;
    unsafe fn popup_bounds(owner: H, requested_width: i32, requested_height: i32) -> Rect {
        let width = requested_width.min(GetSystemMetrics(0).saturating_sub(80).max(540));
        let height = requested_height.min(GetSystemMetrics(1).saturating_sub(110).max(440));
        centered_bounds(owner, width, height)
    }

    unsafe fn centered_bounds(owner: H, width: i32, height: i32) -> Rect {
        let mut frame = Rect {
            left: 0,
            top: 0,
            right: width,
            bottom: height,
        };
        AdjustWindowRectEx(&mut frame, WS_POPUP | WS_CAPTION | WS_SYSMENU, 0, 0);
        let mut parent = Rect::default();
        GetClientRect(owner, &mut parent);
        let mut origin = Point::default();
        ClientToScreen(owner, &mut origin);
        let left = (origin.x.saturating_add((parent.right - width) / 2)).max(0);
        let top = (origin.y.saturating_add((parent.bottom - height) / 2)).max(0);
        let (outer_width, outer_height) = wh(frame);
        Rect {
            left,
            top,
            right: left.saturating_add(outer_width),
            bottom: top.saturating_add(outer_height),
        }
    }

    unsafe fn create_popup(owner: H, class: &str, title: &str, bounds: Rect, clip_children: bool) -> H {
        CreateWindowExW(
            0, wide(class).as_ptr(), wide(title).as_ptr(),
            WS_POPUP | WS_CAPTION | WS_SYSMENU | if clip_children { WS_CLIPCHILDREN } else { 0 },
            bounds.left, bounds.top, bounds.right - bounds.left, bounds.bottom - bounds.top,
            owner, 0, GetModuleHandleW(null()), null_mut(),
        )
    }

    unsafe fn result_window(
        owner: H,
        title: &str,
        width: i32,
        height: i32,
        clipboard: Option<String>,
    ) -> H {
        let bounds = popup_bounds(owner, width, height);
        let window = create_popup(owner, "BaycraftResults", title, bounds, false);
        if gui_failed() {
            if window != 0 {
                DestroyWindow(window);
            }
            return 0;
        }
        if window == 0 {
            show_message(
                owner,
                "Results",
                "Cannot create the results window.",
                MB_ICONERROR,
            );
        } else {
            RESULT_WINDOWS.with(|windows| {
                windows
                    .borrow_mut()
                    .insert(window, ResultWindow { clipboard })
            });
        }
        window
    }

    unsafe extern "system" fn results_proc(
        hwnd: H,
        message: u32,
        wparam: usize,
        lparam: isize,
    ) -> isize {
        dispatch_gui_callback(hwnd, message, wparam, lparam, results_proc_impl)
    }

    unsafe fn results_proc_impl(hwnd: H, message: u32, wparam: usize, lparam: isize) -> isize {
        match message {
            WM_COMMAND => match wparam & 0xffff {
                DLG_CANCEL => {
                    DestroyWindow(hwnd);
                    0
                }
                DLG_COPY => {
                    let text = RESULT_WINDOWS.with(|windows| {
                        windows
                            .borrow()
                            .get(&hwnd)
                            .and_then(|window| window.clipboard.clone())
                    });
                    if let Some(text) = text {
                        if let Err(error) = copy_to_clipboard(hwnd, &text) {
                            show_message(hwnd, "Copy results", &error, MB_ICONERROR);
                        }
                    }
                    0
                }
                _ => DefWindowProcW(hwnd, message, wparam, lparam),
            },
            WM_NOTIFY if lparam != 0 => {
                let header = &*(lparam as *const NotifyHeader);
                if header.control_id == RESULT_TABLE && header.code == NM_CUSTOMDRAW {
                    let draw = &mut *(lparam as *mut ListCustomDraw);
                    match draw.draw.stage {
                        CDDS_PREPAINT => CDRF_NOTIFYITEMDRAW,
                        CDDS_ITEMPREPAINT => {
                            draw.text_color = colorref(0x232323);
                            draw.background_color = colorref(if draw.draw.item.is_multiple_of(2) {
                                0xeef2f6
                            } else {
                                0xffffff
                            });
                            0
                        }
                        _ => 0,
                    }
                } else {
                    DefWindowProcW(hwnd, message, wparam, lparam)
                }
            }
            WM_CLOSE => {
                DestroyWindow(hwnd);
                0
            }
            WM_DESTROY => {
                RESULT_WINDOWS.with(|windows| windows.borrow_mut().remove(&hwnd));
                0
            }
            _ => DefWindowProcW(hwnd, message, wparam, lparam),
        }
    }

    unsafe extern "system" fn fixed_table_proc(
        window: H,
        message: u32,
        wparam: usize,
        lparam: isize,
        subclass_id: usize,
        reference: usize,
    ) -> isize {
        if gui_failed() {
            return DefSubclassProc(window, message, wparam, lparam);
        }
        guarded_gui_call(0, || {
            if message == WM_NOTIFY && lparam != 0 {
                let header = &*(lparam as *const NotifyHeader);
                // Works with both ANSI/Unicode headers and comctl32 v5/v6.
                if [-306_i32, -326, -305, -325]
                    .iter()
                    .any(|&code| header.code == code as u32)
                {
                    return 1;
                }
            }
            if message == 0x0082 {
                RemoveWindowSubclass(window, Some(fixed_table_proc), subclass_id);
                let result = DefSubclassProc(window, message, wparam, lparam);
                if reference != 0 {
                    ImageList_Destroy(reference as H);
                }
                return result;
            }
            DefSubclassProc(window, message, wparam, lparam)
        })
    }

    unsafe fn create_result_table(
        parent: H,
        data: &ResultTable,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        font: H,
    ) {
        let table = control(
            parent,
            "SysListView32",
            "",
            WS_BORDER | WS_TABSTOP | 1 | 4 | 8 | 0x0040,
            RESULT_TABLE,
            (x, y, width, height),
            font,
        );
        if table == 0 || gui_failed() {
            return;
        }
        let row_height = (font_line_height(table, font) + 12).max(29);
        let row_images = ImageList_Create(1, row_height.saturating_sub(2), 0x0020, 1, 1);
        if row_images == 0
            || SetWindowSubclass(table, Some(fixed_table_proc), 1, row_images as usize) == 0
        {
            DestroyWindow(table);
            if row_images != 0 {
                ImageList_Destroy(row_images);
            }
            show_message(
                parent,
                "Results",
                "Cannot create a fixed-column results table.",
                MB_ICONERROR,
            );
            return;
        }
        SendMessageW(table, LVM_FIRST + 3, 1, row_images);
        SendMessageW(table, LVM_SETEXTENDEDLISTVIEWSTYLE, 0, 0x0001_0020);
        // Windows forces the first column left-aligned. A zero-width leading
        // column permits the first visible numeric column to be centered.
        let mut empty = wide("");
        let mut leading: ListColumn = zeroed();
        leading.mask = 0x0007;
        leading.text = empty.as_mut_ptr();
        SendMessageW(table, LVM_INSERTCOLUMNW, 0, &leading as *const _ as isize);
        for (index, (&heading, &width)) in data.headings.iter().zip(&data.widths).enumerate() {
            let mut text = wide(heading);
            let mut column: ListColumn = zeroed();
            column.mask = 0x000f;
            column.format = if index == 0 { 2 } else { 1 };
            column.width = width;
            column.text = text.as_mut_ptr();
            column.subitem = index as i32 + 1;
            SendMessageW(
                table,
                LVM_INSERTCOLUMNW,
                index + 1,
                &column as *const _ as isize,
            );
        }
        let header = SendMessageW(table, LVM_GETHEADER, 0, 0);
        if header != 0 {
            let bold = APP.with(|slot| slot.borrow().bold);
            SendMessageW(header, WM_SETFONT, bold as usize, 1);
            let style = GetWindowLongPtrW(header, -16);
            SetWindowLongPtrW(header, -16, style | 0x0800); // HDS_NOSIZING.
            for index in 1..=data.headings.len() {
                let mut item: HeaderItem = zeroed();
                item.mask = 4;
                SendMessageW(header, 0x1200 + 11, index, &mut item as *mut _ as isize);
                item.format = (item.format & !3) | 2;
                SendMessageW(header, 0x1200 + 12, index, &item as *const _ as isize);
            }
        }
        SendMessageW(table, WM_SETREDRAW, 0, 0);
        for (index, row) in data.rows.iter().enumerate() {
            let mut item: ListItem = zeroed();
            item.mask = 1;
            item.item = index as i32;
            item.text = empty.as_mut_ptr();
            SendMessageW(table, LVM_INSERTITEMW, 0, &item as *const _ as isize);
            for (column, text) in row.iter().enumerate() {
                let mut text = wide(text);
                item.subitem = column as i32 + 1;
                item.text = text.as_mut_ptr();
                SendMessageW(table, LVM_SETITEMTEXTW, index, &item as *const _ as isize);
            }
        }
        SendMessageW(table, WM_SETREDRAW, 1, 0);
        ShowScrollBar(table, 3, 1);
        InvalidateRect(table, null(), 1);
    }

    fn show_selected_results(owner: H, result: SelectedResults) {
        unsafe {
            let clipboard = result.table.as_ref().map(|table| table.clipboard.clone());
            let window =
                result_window(owner, &result.title, result.width, result.height, clipboard);
            if window == 0 {
                return;
            }
            let font = APP.with(|slot| slot.borrow().font);
            let widgets = Controls::new(window, font);
            let mut rect = Rect::default();
            GetClientRect(window, &mut rect);
            let (width, height) = wh(rect);
            let summary_height = 43 + result.summary.len() as i32 * 26;
            widgets.group(0, &result.summary_title, (16, 14, width - 32, summary_height));
            for (row, values) in result.summary.iter().enumerate() {
                let column_width = (width - 64) / values.len().max(1) as i32;
                for (column, text) in values.iter().enumerate() {
                    widgets.label(
                        0,
                        text,
                        (  30 + column as i32 * column_width,  43 + row as i32 * 26,  column_width,  24,  ),
                    );
                }
            }
            if let Some(table) = &result.table {
                let top = 14 + summary_height + 8;
                let table_height = (height - top - 66).max(90);
                widgets.group(0, result.table_title, (16, top, width - 32, table_height));
                create_result_table(
                    window,
                    table,
                    27,
                    top + 28,
                    width - 54,
                    table_height - 40,
                    font,
                );
                widgets.label(0, &result.footer, (18, height - 42, width - 310, 25));
                widgets.button(DLG_COPY, "Copy Table", (width - 254, height - 46, 120, 32));
            } else {
                widgets.label(0, &result.footer, (22, summary_height + 40, width - 44, 45));
            }
            widgets.button(DLG_CANCEL, "Close", (width - 122, height - 46, 104, 32));
            ShowWindow(window, 1);
            UpdateWindow(window);
        }
    }

    fn show_text_window(owner: H, text: &str, report_file: Option<&Path>, model: Model) {
        unsafe {
            let window = result_window(
                owner,
                "Baycraft Results — Project",
                980,
                690,
                Some(text.to_owned()),
            );
            if window == 0 {
                return;
            }
            let (font, mono) = APP.with(|slot| {
                let ui = slot.borrow();
                (ui.font, ui.mono)
            });
            let widgets = Controls::new(window, font);
            let mut rect = Rect::default();
            GetClientRect(window, &mut rect);
            let (width, height) = wh(rect);
            widgets.label(
                0,
                &format!("Complete Baycraft technical report — {}", model.text()),
                (14, 12, width - 28, 25),
            );
            let editor = Controls::new(window, mono).create(
                "EDIT",
                "",
                WS_BORDER  | WS_TABSTOP  | ES_MULTILINE  | ES_AUTOVSCROLL  | ES_AUTOHSCROLL  | ES_READONLY  | WS_VSCROLL  | WS_HSCROLL,
                0,
                (12, 42, width - 24, height - 102),
            );
            SendMessageW(editor, EM_LIMITTEXT, 0, 0);
            let display = text
                .replace("\r\n", "\n")
                .replace('\r', "\n")
                .replace('\n', "\r\n");
            set_text(editor, &display);
            let location = report_file
                .map(|path| format!("output.txt: {}", path.display()))
                .unwrap_or_else(|| "output.txt was not saved".into());
            widgets.label(0, &location, (14, height - 45, width - 285, 32));
            widgets.button(DLG_COPY, "Copy Report", (width - 254, height - 46, 120, 32));
            widgets.button(DLG_CANCEL, "Close", (width - 122, height - 46, 104, 32));
            ShowWindow(window, 1);
            UpdateWindow(window);
        }
    }

    // -------------------------- APPLICATION DATA -----------------------------
    #[derive(Copy, Clone, PartialEq, Eq, Debug)]
    enum Mode {
        Select,
        Pan,
        Zoom,
        Scale,
        Georeference,
        Curve,
        Polygon,
        Measure,
    }
    struct Drag {
        vertex: usize,
        before: Project,
    }
    #[derive(Clone, Copy, PartialEq, Eq)]
    struct CurveKey {
        points: [[u64; 2]; 3],
        increment: u64,
        limit: u64,
        model: Model,
    }
    struct CachedCurve {
        key: CurveKey,
        value: ResultT<std::rc::Rc<Curve>>,
    }
    #[derive(Default)]
    struct CurveCache {
        entries: std::collections::VecDeque<CachedCurve>,
        samples: usize,
    }
    impl CurveCache {
        fn get(&mut self, tool: &Tool, model: Model) -> ResultT<std::rc::Rc<Curve>> {
            let points: [Pt; 3] = tool
                .points
                .as_slice()
                .try_into()
                .map_err(|_| "A parabola requires exactly three control points.".to_owned())?;
            // Bitwise keys preserve signed-zero distinctions in floating-point geometry.
            let key = CurveKey {
                points: points.map(|point| [point.x.to_bits(), point.y.to_bits()]),
                increment: tool.increment.to_bits(),
                limit: tool.limit.to_bits(),
                model,
            };
            if let Some(index) = self.entries.iter().position(|entry| entry.key == key) {
                if let Some(entry) = self.entries.remove(index) {
                    let result = entry.value.clone();
                    self.entries.push_back(entry);
                    return result;
                }
            }
            let value = tool.curve(model).map(std::rc::Rc::new);
            let samples = value.as_ref().map_or(0, |curve| curve.points.len());
            // Bound both sampled geometry and cached validation failures.
            while self.entries.len() >= 16 || self.samples + samples > 4 * MAX_SAMPLES {
                let Some(entry) = self.entries.pop_front() else {
                    break;
                };
                self.samples -= entry.value.as_ref().map_or(0, |curve| curve.points.len());
            }
            self.samples += samples;
            self.entries.push_back(CachedCurve {
                key,
                value: value.clone(),
            });
            value
        }
    }
    struct ObjectItem {
        kind: Kind,
        number: u32,
        handle: H,
    }
    struct UI {
        hwnd: H,
        canvas: H,
        controls: std::collections::BTreeMap<usize, H>,
        object_items: Vec<ObjectItem>,
        font: H,
        mono: H,
        bold: H,
        control_font: H,
        text_line_height: i32,
        control_line_height: i32,
        project: Project,
        image: ImageRef,
        raster_cache: RefCell<Option<DisplayRaster>>,
        curve_cache: RefCell<CurveCache>,
        mode: Mode,
        pending: Vec<Pt>,
        preview: Option<Pt>,
        selected: Option<usize>,
        drag: Option<Drag>,
        history: Vec<Project>,
        future: Vec<Project>,
        dirty: bool,
        scroll: Pt,
        pan_start: Option<(Pt, Pt)>,
        status: String,
        canvas_w: i32,
        canvas_h: i32,
        context_point: Option<Pt>,
    }
    impl Default for UI {
        fn default() -> Self {
            Self {
                hwnd: 0,
                canvas: 0,
                controls: Default::default(),
                object_items: Vec::new(),
                font: 0,
                mono: 0,
                bold: 0,
                control_font: 0,
                text_line_height: 18,
                control_line_height: 28,
                project: Project::default(),
                image: ImageRef::default(),
                raster_cache: RefCell::new(None),
                curve_cache: RefCell::new(CurveCache::default()),
                mode: Mode::Select,
                pending: Vec::new(),
                preview: None,
                selected: None,
                drag: None,
                history: Vec::new(),
                future: Vec::new(),
                dirty: false,
                scroll: Pt::new(0.0, 0.0),
                pan_start: None,
                status: "Import an image, then choose Parabola and click H, E, W.".into(),
                canvas_w: 800,
                canvas_h: 600,
                context_point: None,
            }
        }
    }
    impl UI {
        fn curve(&self, tool: &Tool) -> ResultT<std::rc::Rc<Curve>> {
            self.curve_cache.borrow_mut().get(tool, self.project.model)
        }
        fn ctl(&self, id: usize) -> H {
            *self.controls.get(&id).unwrap_or(&0)
        }
        fn add(&mut self, id: usize, h: H) {
            self.controls.insert(id, h);
        }
        fn status(&mut self, s: impl Into<String>) {
            // Win32 may synchronously send child notifications while the UI is borrowed.
            let _guard = InitializationGuard::begin();
            self.status = s.into();
            unsafe {
                set_text(self.ctl(STATUS), &self.status);
            }
        }
        fn title(&self) -> String {
            let filename = if self.project.filename.is_empty() {
                "Untitled".into()
            } else {
                Path::new(&self.project.filename)
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_else(|| "Untitled".into())
            };
            format!(
                "{}Baycraft — {}",
                if self.dirty { "● " } else { "" },
                filename
            )
        }
        fn image_view(&self, p: Pt) -> Pt {
            p.rotated(self.project.rotation as f64, self.project.center)
                .scale(self.project.zoom as f64 / 100.0)
        }
        fn source_view(&self, p: Pt) -> Pt {
            Pt::new(
                p.x * 100.0 / f64::from(self.project.zoom),
                p.y * 100.0 / f64::from(self.project.zoom),
            )
            .rotated(-(self.project.rotation as f64), self.project.center)
        }
        fn canvas_to_source(&self, p: Pt) -> Pt {
            self.source_view(Pt::new(
                (p.x + self.scroll.x).round_ties_even(),
                (p.y + self.scroll.y).round_ties_even(),
            ))
        }

        fn to_canvas_tool(&self, t: &Tool, p: Pt) -> Pt {
            let q = t.display_point(p);
            Pt::new(q.x - self.scroll.x, q.y - self.scroll.y)
        }
        fn canvas_to_tool_source(&self, t: &Tool, p: Pt) -> Pt {
            let display = Pt::new(
                (p.x + self.scroll.x).round_ties_even(),
                (p.y + self.scroll.y).round_ties_even(),
            );
            Pt::new(
                display.x * 100.0 / f64::from(t.scale),
                display.y * 100.0 / f64::from(t.scale),
            )
            .rotated(-(t.angle as f64), t.anchor)
        }
        fn refresh(&mut self) {
            let _guard = InitializationGuard::begin();
            unsafe {
                set_text(self.hwnd, &self.title());
                let list = self.ctl(OBJECT_LIST);
                if list != 0 {
                    let rebuild = self.object_items.len() != self.project.tools.len()
                        || self.object_items.iter().zip(&self.project.tools).any(|(item, tool)| {
                            item.kind != tool.kind || item.number != tool.number || item.handle == 0
                        });
                    if rebuild {
                        let visible = SendMessageW(list, TVM_GETNEXTITEM, TVGN_FIRSTVISIBLE, 0);
                        let top = self.object_items.iter().position(|item| item.handle == visible).unwrap_or(0);
                        let fraction = top as f64 / self.object_items.len().max(1) as f64;
                        SendMessageW(list, WM_SETREDRAW, 0, 0);
                        SendMessageW(list, TVM_DELETEITEM, 0, TVI_ROOT);
                        self.object_items.clear();
                        for tool in &self.project.tools {
                            let mut label = wide(&tool.identifier());
                            let mut insert: TreeInsert = zeroed();
                            insert.parent = TVI_ROOT;
                            insert.after = TVI_LAST;
                            insert.item.mask = 1;
                            insert.item.text = label.as_mut_ptr();
                            let handle = SendMessageW(list, TVM_INSERTITEMW, 0, &insert as *const _ as isize);
                            self.object_items.push(ObjectItem { kind: tool.kind, number: tool.number, handle });
                        }
                        if let Some(item) = self.object_items.get((fraction * self.object_items.len() as f64) as usize) {
                            SendMessageW(list, TVM_SELECTITEM, TVGN_FIRSTVISIBLE, item.handle);
                        }
                        SendMessageW(list, WM_SETREDRAW, 1, 0);
                        InvalidateRect(list, null(), 1);
                    }
                    let selected = self.selected.and_then(|index| self.object_items.get(index))
                        .map_or(0, |item| item.handle);
                    SendMessageW(list, TVM_SELECTITEM, TVGN_CARET, selected);
                    if selected != 0 {
                        SendMessageW(list, TVM_ENSUREVISIBLE, 0, selected);
                    }
                    ShowScrollBar(list, SB_VERT, 1);
                }
                let model_index = Model::ALL
                    .iter()
                    .position(|&model| model == self.project.model)
                    .unwrap_or(0);
                SendMessageW(self.ctl(MODEL_SELECT), CB_SETCURSEL, model_index, 0);
                let (low, high) = self.project.model.beta_range();
                set_text(
                    self.ctl(MODEL_RANGE),
                    &format!("β: {}–{}°", fmt_general(low, 6), fmt_general(high, 6)),
                );
                set_text(self.ctl(ZOOM_EDIT), &self.project.zoom.to_string());
                set_text(self.ctl(ROT_EDIT), &self.project.rotation.to_string());
                SendMessageW(
                    self.ctl(ZOOM_SPIN),
                    UDM_SETPOS32,
                    0,
                    self.project.zoom as isize,
                );
                SendMessageW(
                    self.ctl(ROT_SPIN),
                    UDM_SETPOS32,
                    0,
                    self.project.rotation as isize,
                );
                self.update_properties();
                self.update_buttons();
                self.scroll_update();
                InvalidateRect(self.canvas, null(), 0);
            }
        }
        fn update_buttons(&self) {
            unsafe {
                for (id, mode) in [
                    (SELECT, Mode::Select),
                    (PAN, Mode::Pan),
                    (ZOOM, Mode::Zoom),
                    (SCALE, Mode::Scale),
                    (GEO, Mode::Georeference),
                    (CURVE, Mode::Curve),
                    (POLYGON, Mode::Polygon),
                    (MEASURE, Mode::Measure),
                ] {
                    SendMessageW(self.ctl(id), BM_SETCHECK, usize::from(self.mode == mode), 0);
                }
            }
        }
        fn finish_drag(&mut self) -> bool {
            let Some(drag) = self.drag.take() else {
                return false;
            };
            if let Some(index) = self.selected {
                if drag.before.tools.get(index).map(|tool| &tool.points)
                    != self.project.tools.get(index).map(|tool| &tool.points)
                {
                    self.history.push(drag.before);
                    if self.history.len() > 100 {
                        self.history.remove(0);
                    }
                    self.future.clear();
                    self.dirty = true;
                }
            }
            true
        }
        fn checkpoint(&mut self) {
            self.finish_drag();
            self.history.push(self.project.clone());
            if self.history.len() > 100 {
                self.history.remove(0);
            }
            self.future.clear();
            self.dirty = true;
        }
        fn finish_tool(&mut self, kind: Kind) {
            self.checkpoint();
            let number = self.project.new_number(kind);
            let points = self.pending.iter().map(|&point| self.source_view(point)).collect();
            self.project.tools.push(Tool::new(
                kind, points, number, self.project.zoom, self.project.rotation, self.project.center,
            ));
            self.selected = Some(self.project.tools.len() - 1);
            self.pending.clear();
            self.mode = Mode::Select;
            self.status("Drag the red handles to adjust the object. Numeric Results shows the curve values.");
            self.refresh();
        }
        fn selected_tool(&self) -> Option<&Tool> {
            self.selected.and_then(|i| self.project.tools.get(i))
        }
        fn update_properties(&self) {
            let _guard = InitializationGuard::begin();
            unsafe {
                let tool = self.selected_tool();
                set_text(
                    self.ctl(STEP_EDIT),
                    &entry_number(tool.map(|t| t.increment).unwrap_or(DEFAULT_INCREMENT)),
                );
                set_text(
                    self.ctl(LIMIT_EDIT),
                    &entry_number(tool.map(|t| t.limit).unwrap_or(DEFAULT_LIMIT)),
                );
                set_text(
                    self.ctl(WIDTH_EDIT),
                    &tool.map(|t| t.width).unwrap_or(DEFAULT_WIDTH).to_string(),
                );
                SendMessageW(
                    self.ctl(WIDTH_SPIN),
                    UDM_SETPOS32,
                    0,
                    tool.map(|t| t.width).unwrap_or(DEFAULT_WIDTH) as isize,
                );
            }
            self.update_info();
        }
        fn update_info(&self) {
            let _guard = InitializationGuard::begin();
            let tool = self.selected_tool();
            let units = "Lengths: m  ·  Areas: m²";
            let text = match tool {
                None => format!(
                    "Select an object to view its properties.\r\n{}\r\n\r\n{units}",
                    if self.project.georeferenced() {
                        "Georeferenced X/Y (metres)"
                    } else {
                        "XY georeference not defined"
                    }
                ),
                Some(tool) if tool.kind == Kind::Curve => {
                    match self.curve(tool) {
                        Ok(curve) => format!(
                            "Model: {}\r\nβ = {}°  ·  Rb = {} m\r\nWave from: {} (north-up image)\r\nC0 = {}\r\nC1 = {}\r\nC2 = {}\r\nSamples: {}",
                            self.project.model.text(), fmt_display(curve.beta,2), fmt_display(curve.rb * self.project.pixel_size,2),
                            fmt_bearing(curve.direction), fmt_general(curve.coeff[0], 9),
                            fmt_general(curve.coeff[1], 9), fmt_general(curve.coeff[2], 9), curve.angles.len()),
                        Err(error) => error,
                    }
                }
                Some(tool) if tool.kind == Kind::Measure => format!(
                    "Distance: {} m\r\n\r\n{units}",
                    fmt_display(tool.length_m(self.project.pixel_size), 2)
                ),
                Some(tool) => format!(
                    "Area: {} m²\r\nVertices: {}\r\n\r\n{units}",
                    fmt_display(tool.area_m2(self.project.pixel_size), 2),
                    tool.points.len()
                ),
            };
            unsafe {
                set_text(self.ctl(MEASUREMENTS), &text);
            }
        }
        fn select(&mut self, i: Option<usize>) {
            self.finish_drag();
            self.selected = i.filter(|i| *i < self.project.tools.len());
            self.update_properties();
            unsafe {
                InvalidateRect(self.canvas, null(), 0);
            }
        }
        fn mode(&mut self, mode: Mode) -> ResultT<()> {
            let _guard = InitializationGuard::begin();
            self.finish_drag();
            self.pan_start = None;
            unsafe {
                ReleaseCapture();
            }
            if mode == Mode::Georeference && !self.project.scale_defined {
                return Err(
                    "Set the image scale before assigning reference X/Y coordinates.".into(),
                );
            }
            if mode == Mode::Georeference && self.project.image_png.is_empty() {
                return Err("Import an image before georeferencing.".into());
            }
            self.mode = mode;
            self.pending.clear();
            self.preview = None;
            self.status(match mode {
                Mode::Curve => "Click the wave diffraction point (H).",
                Mode::Polygon => "Click polygon vertices; double-click or Enter to finish.",
                Mode::Measure => "Click the first measurement point.",
                Mode::Scale => "Click the first end of a known distance.",
                Mode::Georeference => {
                    "Click a known point in the image and enter X (Easting), Y (Northing)."
                }
                Mode::Select => "Select an object or drag its red control handles.",
                Mode::Pan => "Drag to pan the image.",
                Mode::Zoom => "Click to zoom in. Shift-click to zoom out.",
            });
            self.update_buttons();
            unsafe {
                InvalidateRect(self.canvas, null(), 0);
            }
            Ok(())
        }
        fn set_view(&mut self, zoom: Option<i32>, rotation: Option<i32>) {
            let zoom = zoom.map(|value| value.clamp(10, 500));
            if zoom.is_none_or(|value| value == self.project.zoom)
                && rotation.is_none_or(|value| value == self.project.rotation)
            {
                return;
            }
            self.checkpoint();
            if let Some(rotation) = rotation {
                self.project.set_rotation(rotation);
            }
            if let Some(zoom) = zoom {
                self.project.set_zoom(zoom);
            }
            self.pending.clear();
            self.refresh();
        }
        fn set_image(&mut self, image: ImageRef, bytes: Vec<u8>) -> ResultT<()> {
            let (w, h) = gdip_size(&image)?;
            self.image = image;
            self.raster_cache.replace(None);
            self.project.image_png = bytes.into();
            self.project.width = w;
            self.project.height = h;
            self.project.center = Pt::new((w / 2) as f64, (h / 2) as f64);
            self.project.pixel_size = 1.0;
            self.project.scale_defined = false;
            self.project.ref_pixel = None;
            self.project.ref_xy = None;
            let rotation = self.project.rotation;
            self.project.set_rotation(rotation);
            self.refresh();
            self.scroll_to_start();
            Ok(())
        }
        fn install_project(&mut self, mut project: Project) -> ResultT<()> {
            let same_image = std::sync::Arc::ptr_eq(&project.image_png, &self.project.image_png)
                && !self.image.0.is_null();
            if !same_image {
                let image = if project.image_png.is_empty() {
                    ImageRef::default()
                } else {
                    let image = img_from_bytes(&project.image_png)?;
                    let (width, height) = gdip_size(&image)?;
                    let encoded = encoded_png(&image)?;
                    if project.image_png.as_ref() != encoded.as_slice() {
                        project.image_png = encoded.into();
                    }
                    project.width = width;
                    project.height = height;
                    image
                };
                // Decode successfully before replacing any live application state.
                self.raster_cache.replace(None);
                self.image = image;
            }
            self.project = project;
            self.selected = None;
            self.pending.clear();
            self.preview = None;
            self.drag = None;
            self.pan_start = None;
            self.mode = Mode::Select;
            Ok(())
        }
        fn image_extent(&self) -> (Pt, Pt) {
            let p = &self.project;
            if self.image.0.is_null() {
                return (
                    Pt::new(0.0, 0.0),
                    Pt::new(
                        (f64::from(p.width) * f64::from(p.zoom) / 100.0).max(1000.0),
                        (f64::from(p.height) * f64::from(p.zoom) / 100.0).max(700.0),
                    ),
                );
            }
            let corners = [
                Pt::new(0.0, 0.0),
                Pt::new(p.width as f64, 0.0),
                Pt::new(0.0, p.height as f64),
                Pt::new(p.width as f64, p.height as f64),
            ];
            let mut min = Pt::new(0.0, 0.0);
            let mut max = Pt::new(1000.0, 700.0);
            if p.width > 0 && p.height > 0 {
                min = Pt::new(f64::INFINITY, f64::INFINITY);
                max = Pt::new(f64::NEG_INFINITY, f64::NEG_INFINITY);
                for corner in corners {
                    let v = self.image_view(corner);
                    min.x = min.x.min(v.x);
                    min.y = min.y.min(v.y);
                    max.x = max.x.max(v.x);
                    max.y = max.y.max(v.y);
                }
            }
            (min, max)
        }
        fn scene_extent(&self) -> (Pt, Pt) {
            let mut bounds = SceneBounds::new(self);
            let metric_y = -f64::from(self.text_line_height);
            let control_y = -10.0 - f64::from(self.control_line_height);
            for tool in self.project.tools.iter().filter(|tool| tool.visible) {
                let points = tool.display_points();
                for &point in &points {
                    bounds.point(point, tool.width as f64 / 2.0 + 4.0);
                }
                let label = metric_label(tool, self.project.pixel_size);
                match tool.kind {
                    Kind::Curve => {
                        let (head, end, wave) = (points[0], points[1], points[2]);
                        bounds.point(Pt::new(head.x + end.x - wave.x, head.y + end.y - wave.y), tool.width as f64 / 2.0 + 2.0);
                        let curve = self.curve(tool).ok();
                        if let Some(curve) = &curve {
                            for &point in &curve.points {
                                bounds.point(tool.display_point(point), tool.width as f64 + 2.0);
                            }
                        }
                        bounds.label(Pt::new(head.x + 10.0, head.y + 12.0), &curve_label(tool, curve.as_deref()), self.font);
                        bounds.label(Pt::new((head.x + end.x) / 2.0, (head.y + end.y) / 2.0 + metric_y), &label, self.font);
                        for (text, point) in CONTROL_LABELS.iter().zip(&points) {
                            bounds.label(Pt::new(point.x + 10.0, point.y + control_y), text, self.control_font);
                        }
                    }
                    Kind::Measure => {
                        let middle = Pt::new((points[0].x + points[1].x) / 2.0, (points[0].y + points[1].y) / 2.0 + metric_y);
                        bounds.label(middle, &label, self.font);
                    }
                    Kind::Polygon => {
                        let center = tool.display_point(polygon_center(&tool.points));
                        bounds.label(Pt::new(center.x, center.y + metric_y), &label, self.font);
                    }
                }
            }
            for (index, &point) in self.pending.iter().enumerate() {
                bounds.point(point, 5.0);
                if self.mode == Mode::Curve {
                    bounds.label(Pt::new(point.x + 10.0, point.y + control_y), CONTROL_LABELS[index.min(2)], self.control_font);
                }
            }
            if let Some(preview) = self.preview.filter(|_| !self.pending.is_empty()) {
                bounds.point(preview, 4.0);
            }
            if let Some(reference) = self.project.ref_pixel.filter(|_| self.project.georeferenced()) {
                let point = reference.transformed(self.project.rotation, self.project.zoom, self.project.center);
                bounds.point(point, 5.0);
                bounds.label(Pt::new(point.x + 10.0, point.y + control_y), "G", self.control_font);
            }
            bounds.padded()
        }
        fn scroll_to_start(&mut self) {
            let (minimum, _) = self.scene_extent();
            self.scroll = Pt::new(minimum.x.floor(), minimum.y.floor());
            self.scroll_update();
            unsafe {
                InvalidateRect(self.canvas, null(), 0);
            }
        }
        fn scroll_update(&mut self) {
            let _guard = InitializationGuard::begin();
            unsafe {
                if self.canvas == 0 {
                    return;
                }
                let (min, max) = self.scene_extent();
                let view = [
                    (SB_HORZ, min.x, max.x, self.canvas_w, &mut self.scroll.x),
                    (SB_VERT, min.y, max.y, self.canvas_h, &mut self.scroll.y),
                ];
                for (bar, a, b, page, value) in view {
                    let lo = a.floor() as i32;
                    let hi = b.ceil() as i32;
                    let limit = hi.saturating_sub(page).saturating_add(1).max(lo);
                    *value = (*value).clamp(lo as f64, limit as f64);
                    let info = ScrollInfo {
                        size: size_of::<ScrollInfo>() as u32,
                        mask: SIF_ALL,
                        min: lo,
                        max: hi.max(lo.saturating_add(page)),
                        page: page.max(1) as u32,
                        pos: *value as i32,
                        track: 0,
                    };
                    SetScrollInfo(self.canvas, bar, &info, 1);
                }
            }
        }
    }
    struct WindowDc {
        window: H,
        dc: H,
    }
    impl Drop for WindowDc {
        fn drop(&mut self) {
            if self.dc != 0 {
                unsafe {
                    ReleaseDC(self.window, self.dc);
                }
            }
        }
    }
    fn curve_label(tool: &Tool, curve: Option<&Curve>) -> String {
        curve.map_or_else(|| tool.identifier(), |curve| {
            format!("{}  β = {}°", tool.identifier(), fmt_display(curve.beta, 2))
        })
    }
    fn metric_label(tool: &Tool, pixel_size: f64) -> String {
        match tool.kind {
            Kind::Curve => format!("{} m", fmt_display(tool.length_m(pixel_size), 2)),
            Kind::Measure => format!("{}: {} m", tool.identifier(), fmt_display(tool.length_m(pixel_size), 2)),
            Kind::Polygon => format!("{}: {} m²", tool.identifier(), fmt_display(tool.area_m2(pixel_size), 2)),
        }
    }
    /// Bounds use the same geometry and label strings as the overlay renderer.
    struct SceneBounds {
        minimum: Pt,
        maximum: Pt,
        dc: WindowDc,
    }
    impl SceneBounds {
        fn new(ui: &UI) -> Self {
            let (minimum, maximum) = ui.image_extent();
            Self {
                minimum: Pt::new(minimum.x.floor(), minimum.y.floor()),
                maximum: Pt::new(maximum.x.ceil(), maximum.y.ceil()),
                dc: WindowDc { window: ui.canvas, dc: unsafe { GetDC(ui.canvas) } },
            }
        }
        fn point(&mut self, point: Pt, margin: f64) {
            extend_extent(&mut self.minimum, &mut self.maximum, point, margin);
        }
        fn label(&mut self, point: Pt, text: &str, font: H) {
            extend_label(&mut self.minimum, &mut self.maximum, point, text, font, self.dc.dc);
        }
        fn padded(&self) -> (Pt, Pt) {
            (Pt::new(self.minimum.x - 10.0, self.minimum.y - 10.0),
             Pt::new(self.maximum.x + 30.0, self.maximum.y + 30.0))
        }
    }
    fn extend_extent(minimum: &mut Pt, maximum: &mut Pt, point: Pt, margin: f64) {
        if !point.finite() {
            return;
        }
        minimum.x = minimum.x.min(point.x - margin);
        minimum.y = minimum.y.min(point.y - margin);
        maximum.x = maximum.x.max(point.x + margin);
        maximum.y = maximum.y.max(point.y + margin);
    }
    fn extend_label(minimum: &mut Pt, maximum: &mut Pt, point: Pt, text: &str, font: H, dc: H) {
        let mut size = Size {
            x: (text.chars().count() as i32).saturating_mul(10),
            y: 24,
        };
        if dc != 0 {
            let encoded = wide(text);
            let _font = GdiSelection::select(dc, font).ok();
            unsafe {
                GetTextExtentPoint32W(dc, encoded.as_ptr(), (encoded.len() - 1) as i32, &mut size);
            }
        }
        extend_extent(minimum, maximum, point, 1.0);
        extend_extent(
            minimum,
            maximum,
            Pt::new(point.x + size.x as f64, point.y + size.y as f64),
            1.0,
        );
    }
    impl Drop for UI {
        fn drop(&mut self) {
            for font in [
                &mut self.font,
                &mut self.mono,
                &mut self.bold,
                &mut self.control_font,
            ] {
                if *font != 0 {
                    unsafe {
                        DeleteObject(*font);
                    }
                    *font = 0;
                }
            }
            self.raster_cache.replace(None);
            if !self.image.0.is_null() {
                unsafe {
                    GdipDisposeImage(self.image.0);
                }
                self.image.0 = null_mut();
            }
        }
    }
    thread_local! {
        static APP: RefCell<UI> = RefCell::new(UI::default());
        // Child creation, SetMenu, MoveWindow, and SetWindowText can dispatch
        // synchronous messages, including WM_SIZE, WM_PAINT, and WM_COMMAND.
        // Those messages must not borrow APP while initialization owns it.
        static INITIALIZING: Cell<bool> = const { Cell::new(false) };
    }

    fn during_initialization() -> bool {
        INITIALIZING.with(Cell::get)
    }

    struct InitializationGuard {
        previous: bool,
    }
    impl InitializationGuard {
        fn begin() -> Self {
            let previous = INITIALIZING.with(|flag| flag.replace(true));
            Self { previous }
        }
    }
    impl Drop for InitializationGuard {
        fn drop(&mut self) {
            INITIALIZING.with(|flag| flag.set(self.previous));
        }
    }

    thread_local! {
        static GUI_FAILED: Cell<bool> = const { Cell::new(false) };
        static GUI_FAILURE: RefCell<Option<String>> = const { RefCell::new(None) };
    }

    fn gui_failed() -> bool {
        GUI_FAILED.with(Cell::get)
    }

    fn take_gui_failure() -> Option<String> {
        GUI_FAILURE.with(|failure| failure.borrow_mut().take())
    }

    fn panic_message(payload: Box<dyn std::any::Any + Send>) -> String {
        match payload.downcast::<String>() {
            Ok(message) => *message,
            Err(payload) => match payload.downcast::<&str>() {
                Ok(message) => (*message).to_owned(),
                Err(payload) => {
                    // An arbitrary panic payload can itself panic in Drop.
                    // The GUI is terminating, so retain that unknown payload
                    // rather than risk a second unwind at the native boundary.
                    std::mem::forget(payload);
                    "An unexpected GUI operation failed.".to_owned()
                }
            },
        }
    }

    fn guarded_gui_call<T: Copy>(fallback: T, operation: impl FnOnce() -> T) -> T {
        if gui_failed() {
            return fallback;
        }
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(operation)) {
            Ok(value) if !gui_failed() => value,
            Ok(_) => fallback,
            Err(payload) => {
                GUI_FAILED.with(|failed| failed.set(true));
                let message = panic_message(payload);
                GUI_FAILURE.with(|failure| {
                    if let Ok(mut failure) = failure.try_borrow_mut() {
                        if failure.is_none() {
                            *failure = Some(message);
                        }
                    }
                });
                // No further application events may use partially updated
                // state. The outer loop owns cleanup and the final dialog.
                unsafe {
                    PostQuitMessage(1);
                }
                fallback
            }
        }
    }

    unsafe fn failed_callback(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        match msg {
            0x0081 => 0, // WM_NCCREATE: reject creation after a fatal callback.
            WM_CREATE => -1,
            WM_PAINT => {
                // Validate the update region without borrowing GUI state.
                let mut paint = PaintStruct::default();
                if BeginPaint(hwnd, &mut paint) != 0 {
                    EndPaint(hwnd, &paint);
                }
                0
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }

    unsafe fn dispatch_gui_callback(
        hwnd: H,
        msg: u32,
        wparam: usize,
        lparam: isize,
        implementation: unsafe fn(H, u32, usize, isize) -> isize,
    ) -> isize {
        if gui_failed() {
            return failed_callback(hwnd, msg, wparam, lparam);
        }
        let fallback = if msg == WM_CREATE { -1 } else { 0 };
        guarded_gui_call(fallback, || implementation(hwnd, msg, wparam, lparam))
    }

    // ----------------------------- GDI DRAWING -------------------------------
    fn win32_error(operation: &str) -> String {
        format!("{operation} failed (Win32 error {})", unsafe {
            GetLastError()
        })
    }
    struct GdiObject(H);
    impl GdiObject {
        fn checked(handle: H, operation: &str) -> ResultT<Self> {
            if handle == 0 || handle == -1 {
                Err(win32_error(operation))
            } else {
                Ok(Self(handle))
            }
        }
    }
    impl Drop for GdiObject {
        fn drop(&mut self) {
            unsafe {
                DeleteObject(self.0);
            }
        }
    }
    struct GdiSelection {
        dc: H,
        previous: H,
    }
    impl GdiSelection {
        fn select(dc: H, object: H) -> ResultT<Self> {
            let previous = unsafe { SelectObject(dc, object) };
            if previous == 0 || previous == -1 {
                Err(win32_error("SelectObject"))
            } else {
                Ok(Self { dc, previous })
            }
        }
    }
    impl Drop for GdiSelection {
        fn drop(&mut self) {
            unsafe {
                SelectObject(self.dc, self.previous);
            }
        }
    }
    struct MemoryDc(H);
    impl Drop for MemoryDc {
        fn drop(&mut self) {
            unsafe {
                DeleteDC(self.0);
            }
        }
    }
    struct PaintSession {
        window: H,
        paint: PaintStruct,
    }
    impl PaintSession {
        fn begin(window: H) -> Self {
            let mut paint = PaintStruct::default();
            unsafe {
                BeginPaint(window, &mut paint);
            }
            Self { window, paint }
        }
    }
    impl Drop for PaintSession {
        fn drop(&mut self) {
            unsafe {
                EndPaint(self.window, &self.paint);
            }
        }
    }
    struct GraphicsRef(*mut c_void);
    impl GraphicsRef {
        fn from_dc(dc: H) -> ResultT<Self> {
            let mut graphics = Self(null_mut());
            let status = unsafe { GdipCreateFromHDC(dc, &mut graphics.0) };
            if status != 0 || graphics.0.is_null() {
                Err(img_error(status))
            } else {
                Ok(graphics)
            }
        }
        fn for_image(image: &ImageRef) -> ResultT<Self> {
            let mut graphics = Self(null_mut());
            let status = unsafe { GdipGetImageGraphicsContext(image.0, &mut graphics.0) };
            if status != 0 || graphics.0.is_null() {
                Err(img_error(status))
            } else {
                Ok(graphics)
            }
        }
    }
    impl Drop for GraphicsRef {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    GdipDeleteGraphics(self.0);
                }
            }
        }
    }
    struct GdipBrush(*mut c_void);
    impl Drop for GdipBrush {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    GdipDeleteBrush(self.0);
                }
            }
        }
    }
    struct GraphicsDc<'a> {
        graphics: &'a GraphicsRef,
        dc: H,
    }
    impl<'a> GraphicsDc<'a> {
        fn acquire(graphics: &'a GraphicsRef) -> ResultT<Self> {
            let mut context = Self { graphics, dc: 0 };
            let status = unsafe { GdipGetDC(graphics.0, &mut context.dc) };
            if status != 0 || context.dc == 0 {
                Err(img_error(status))
            } else {
                Ok(context)
            }
        }
        fn release(mut self) -> ResultT<()> {
            let status = unsafe { GdipReleaseDC(self.graphics.0, self.dc) };
            if status == 0 {
                self.dc = 0;
            }
            gdip_ok(status)
        }
    }
    impl Drop for GraphicsDc<'_> {
        fn drop(&mut self) {
            if self.dc != 0 {
                unsafe {
                    GdipReleaseDC(self.graphics.0, self.dc);
                }
            }
        }
    }
    fn gdip_ok(status: i32) -> ResultT<()> {
        if status == 0 {
            Ok(())
        } else {
            Err(img_error(status))
        }
    }
    fn draw_text(hdc: H, position: Pt, text: &str, color: u32) -> ResultT<()> {
        unsafe {
            let position = point(position);
            let encoded = wide(text);
            SetTextColor(hdc, colorref(color));
            SetBkMode(hdc, TRANSPARENT);
            if TextOutW(
                hdc,
                position.x,
                position.y,
                encoded.as_ptr(),
                (encoded.len() - 1) as i32,
            ) == 0
            {
                return Err(win32_error("TextOutW"));
            }
            Ok(())
        }
    }
    fn stroke(hdc: H, points: &[Pt], color: u32, width: i32, closed: bool) -> ResultT<()> {
        unsafe {
            if points.len() < 2 {
                return Ok(());
            }
            let pen = GdiObject::checked(
                CreatePen(PS_SOLID, width.max(1), colorref(color)),
                "CreatePen",
            )?;
            let _selection = GdiSelection::select(hdc, pen.0)?;
            let first = point(points[0]);
            if MoveToEx(hdc, first.x, first.y, null_mut()) == 0 {
                return Err(win32_error("MoveToEx"));
            }
            for &position in &points[1..] {
                let p = point(position);
                if LineTo(hdc, p.x, p.y) == 0 {
                    return Err(win32_error("LineTo"));
                }
            }
            if closed && LineTo(hdc, first.x, first.y) == 0 {
                return Err(win32_error("LineTo"));
            }
            Ok(())
        }
    }
    fn visible_segment(a: Pt, b: Pt, clip: Rect) -> Option<(f64, f64)> {
        let (dx, dy) = (b.x - a.x, b.y - a.y);
        let (mut first, mut last) = (0.0_f64, 1.0_f64);
        for (p, q) in [
            (-dx, a.x - f64::from(clip.left)),
            (dx, f64::from(clip.right) - a.x),
            (-dy, a.y - f64::from(clip.top)),
            (dy, f64::from(clip.bottom) - a.y),
        ] {
            if p == 0.0 {
                if q < 0.0 {
                    return None;
                }
                continue;
            }
            let ratio = q / p;
            if p < 0.0 {
                first = first.max(ratio);
            } else {
                last = last.min(ratio);
            }
            if first > last {
                return None;
            }
        }
        Some((first, last))
    }
    fn dot_line(hdc: H, points: &[Pt], width: i32, color: u32) -> ResultT<()> {
        unsafe {
            if points.len() < 2 {
                return Ok(());
            }
            // PS_DOT is silently solid for wide GDI pens. Draw the actual 3/3
            // pattern, clipping its iteration range so distant controls stay fast.
            let pen = GdiObject::checked(
                CreatePen(PS_SOLID, width.max(1), colorref(color)),
                "CreatePen",
            )?;
            let _selection = GdiSelection::select(hdc, pen.0)?;
            let mut clip = Rect::default();
            if GetClipBox(hdc, &mut clip) == 0 {
                return Err(win32_error("GetClipBox"));
            }
            clip.left = clip.left.saturating_sub(width);
            clip.top = clip.top.saturating_sub(width);
            clip.right = clip.right.saturating_add(width);
            clip.bottom = clip.bottom.saturating_add(width);
            for segment in points.windows(2) {
                let (a, b) = (segment[0], segment[1]);
                let length = a.distance(b);
                if length == 0.0 {
                    continue;
                }
                let Some((first, last)) = visible_segment(a, b, clip) else {
                    continue;
                };
                let mut step = ((first * length / 6.0).floor() * 6.0).max(0.0);
                let end = last * length;
                while step <= end {
                    let (start, finish) = (step / length, (step + 3.0).min(length) / length);
                    let p = point(Pt::new(
                        a.x + start * (b.x - a.x),
                        a.y + start * (b.y - a.y),
                    ));
                    let q = point(Pt::new(
                        a.x + finish * (b.x - a.x),
                        a.y + finish * (b.y - a.y),
                    ));
                    if MoveToEx(hdc, p.x, p.y, null_mut()) == 0 {
                        return Err(win32_error("MoveToEx"));
                    }
                    if LineTo(hdc, q.x, q.y) == 0 {
                        return Err(win32_error("LineTo"));
                    }
                    step += 6.0;
                }
            }
            Ok(())
        }
    }
    fn markers(hdc: H, positions: impl IntoIterator<Item = Pt>, radius: i32, color: u32, oval: bool) -> ResultT<()> {
        let mut positions = positions.into_iter().peekable();
        if positions.peek().is_none() {
            return Ok(());
        }
        unsafe {
            let brush = GdiObject::checked(CreateSolidBrush(colorref(color)), "CreateSolidBrush")?;
            let pen = GdiObject::checked(CreatePen(PS_SOLID, 1, colorref(color)), "CreatePen")?;
            let _brush_selection = GdiSelection::select(hdc, brush.0)?;
            let _pen_selection = GdiSelection::select(hdc, pen.0)?;
            for position in positions {
                let p = point(position);
                let rect = Rect {
                    left: p.x.saturating_sub(radius),
                    top: p.y.saturating_sub(radius),
                    right: p.x.saturating_add(radius).saturating_add(1),
                    bottom: p.y.saturating_add(radius).saturating_add(1),
                };
                let success = if oval {
                    Ellipse(hdc, rect.left, rect.top, rect.right, rect.bottom)
                } else {
                    Rectangle(hdc, rect.left, rect.top, rect.right, rect.bottom)
                };
                if success == 0 {
                    return Err(win32_error("Draw marker"));
                }
            }
            Ok(())
        }
    }
    fn marker(hdc: H, position: Pt, radius: i32, color: u32, oval: bool) -> ResultT<()> {
        markers(hdc, std::iter::once(position), radius, color, oval)
    }
    fn polygon_fill(hdc: H, points: &[Pt], export: bool) -> ResultT<()> {
        unsafe {
            if points.len() < 3 {
                return Ok(());
            }
            let graphics = GraphicsRef::from_dc(hdc)?;
            // The gray12 stipple contains eight white pixels in an 8x8 tile.
            let mut pixels = [0_u32; 64];
            let mut texture = ImageRef::default();
            let mut brush = GdipBrush(null_mut());
            for row in (0..8).step_by(2) {
                for column in [
                    if row % 4 == 0 { 0 } else { 2 },
                    if row % 4 == 0 { 4 } else { 6 },
                ] {
                    pixels[row * 8 + column] = 0xffff_ffff;
                }
            }
            if export {
                gdip_ok(GdipCreateSolidFill(0x32ff_ffff, &mut brush.0))?;
            } else {
                gdip_ok(GdipCreateBitmapFromScan0(
                    8,
                    8,
                    32,
                    PIXEL_FORMAT_32BPP_ARGB,
                    pixels.as_ptr().cast(),
                    &mut texture.0,
                ))?;
                gdip_ok(GdipCreateTexture(texture.0, 0, &mut brush.0))?;
            }
            let vertices = points.iter().copied().map(point).collect::<Vec<_>>();
            gdip_ok(GdipFillPolygonI(
                graphics.0,
                brush.0,
                vertices.as_ptr(),
                vertices.len() as i32,
                0,
            ))
        }
    }
    #[derive(Copy, Clone, PartialEq)]
    struct RasterKey {
        source: *mut c_void,
        zoom: i32,
        rotation: i32,
        anchor: Pt,
    }
    struct DisplayRaster {
        key: RasterKey,
        transformed: raster::Transformed,
        bitmap: GdiObject,
    }
    fn display_raster(ui: &UI) -> ResultT<std::cell::Ref<'_, DisplayRaster>> {
        let key = RasterKey {
            source: ui.image.0,
            zoom: ui.project.zoom,
            rotation: ui.project.rotation,
            anchor: ui.project.center,
        };
        let reusable = ui
            .raster_cache
            .borrow()
            .as_ref()
            .is_some_and(|cached| cached.key == key);
        if !reusable {
            let source = image_rgb(&ui.image)?;
            let transformed =
                source.transformed(key.zoom, key.rotation, (key.anchor.x, key.anchor.y))?;
            let image = bitmap_from_rgb(&transformed.image)?;
            let mut handle = 0;
            let status = unsafe { GdipCreateHBITMAPFromBitmap(image.0, &mut handle, 0xff3a3a3a) };
            let bitmap = GdiObject::checked(handle, "Create image display bitmap");
            gdip_ok(status)?;
            let bitmap = bitmap?;
            *ui.raster_cache.borrow_mut() = Some(DisplayRaster {
                key,
                transformed,
                bitmap,
            });
        }
        std::cell::Ref::filter_map(ui.raster_cache.borrow(), Option::as_ref)
            .map_err(|_| "The rendered image is unavailable.".to_owned())
    }
    fn draw_image_scene(hdc: H, ui: &UI, origin: Pt) -> ResultT<()> {
        if ui.image.0.is_null() {
            return Ok(());
        }
        let cached = display_raster(ui)?;
        let image = &cached.transformed.image;
        let position = Pt::new(
            cached.transformed.origin.0 - origin.x,
            cached.transformed.origin.1 - origin.y,
        );
        unsafe {
            let mut clip = Rect::default();
            if GetClipBox(hdc, &mut clip) == 0 {
                return Err(win32_error("GetClipBox"));
            }
            if position.x >= f64::from(clip.right)
                || position.y >= f64::from(clip.bottom)
                || position.x + image.width as f64 <= f64::from(clip.left)
                || position.y + image.height as f64 <= f64::from(clip.top)
            {
                return Ok(());
            }
            let handle = CreateCompatibleDC(hdc);
            if handle == 0 {
                return Err(win32_error("CreateCompatibleDC"));
            }
            let memory = MemoryDc(handle);
            let _selection = GdiSelection::select(memory.0, cached.bitmap.0)?;
            let position = point(position);
            if BitBlt(
                hdc,
                position.x,
                position.y,
                image.width as i32,
                image.height as i32,
                memory.0,
                0,
                0,
                SRCCOPY,
            ) == 0
            {
                return Err(win32_error("Draw background image"));
            }
        }
        Ok(())
    }
    unsafe fn create_font(face: &str, height: i32, weight: i32, quality: u32) -> H {
        CreateFontW(height, 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, quality, 0, wide(face).as_ptr())
    }
    fn drawing_font(height: i32, weight: i32) -> ResultT<GdiObject> {
        unsafe {
            GdiObject::checked(
                create_font("Arial", -height, weight, 4),
                "CreateFontW",
            )
        }
    }
    fn draw_overlays(hdc: H, ui: &UI, origin: Pt, export: bool) -> ResultT<()> {
        let export_font = if export {
            Some(drawing_font(16, 400)?)
        } else {
            None
        };
        let export_control_font = if export {
            Some(drawing_font(22, 700)?)
        } else {
            None
        };
        let regular_font = export_font.as_ref().map_or(ui.font, |font| font.0);
        let control_font = export_control_font
            .as_ref()
            .map_or(ui.control_font, |font| font.0);
        let metric_label_y = -f64::from(ui.text_line_height);
        let control_label_y = if export {
            -30.0
        } else {
            -10.0 - f64::from(ui.control_line_height)
        };
        let _font = GdiSelection::select(hdc, regular_font)?;
        let offset_drawing_point = |point: Pt| -> ResultT<Pt> {
            Ok(Pt::new(
                f64::from(pixel_int(point.x)?) - origin.x,
                f64::from(pixel_int(point.y)?) - origin.y,
            ))
        };
        let text_at = |p: Pt, x: f64, y: f64, text: &str, color: u32| {
            draw_text(hdc, Pt::new(p.x + x, p.y + y), text, color)
        };
        for (index, tool) in ui.project.tools.iter().enumerate() {
            if !tool.visible {
                continue;
            }
            let map_tool = |point: Pt| offset_drawing_point(tool.display_point(point));
            let controls = tool
                .points
                .iter()
                .copied()
                .map(map_tool)
                .collect::<ResultT<Vec<_>>>()?;
            match tool.kind {
                Kind::Curve => {
                    let (h, e, w) = (controls[0], controls[1], controls[2]);
                    dot_line(hdc, &[h, e, w], tool.width, 0)?;
                    dot_line(
                        hdc,
                        &[h, Pt::new(h.x + e.x - w.x, h.y + e.y - w.y)],
                        tool.width,
                        0,
                    )?;
                    let curve = ui.curve(tool).ok();
                    if let Some(curve) = &curve {
                        let vertices = curve
                            .points
                            .iter()
                            .copied()
                            .map(map_tool)
                            .collect::<ResultT<Vec<_>>>()?;
                        stroke(hdc, &vertices, tool.color.rgb(), tool.width, false)?;
                        if vertices.len() <= 2000 {
                            markers(hdc, vertices, tool.width, tool.color.rgb(), true)?;
                        }
                    }
                    let label = curve_label(tool, curve.as_deref());
                    text_at(h, 10.0, 12.0, &label, 0)?;
                    let middle = Pt::new((h.x + e.x) / 2.0, (h.y + e.y) / 2.0);
                    text_at(
                        middle,
                        0.0,
                        if export { -20.0 } else { metric_label_y },
                        &metric_label(tool, ui.project.pixel_size),
                        0,
                    )?;
                    let _bold = GdiSelection::select(hdc, control_font)?;
                    for (label, position) in CONTROL_LABELS.iter().zip(&controls) {
                        text_at(*position, 10.0, control_label_y, label, 0xb40000)?;
                    }
                }
                Kind::Measure => {
                    stroke(hdc, &controls, tool.color.rgb(), tool.width, false)?;
                    let middle = Pt::new(
                        (controls[0].x + controls[1].x) / 2.0,
                        (controls[0].y + controls[1].y) / 2.0,
                    );
                    text_at(
                        middle,
                        0.0,
                        if export { 0.0 } else { metric_label_y },
                        &metric_label(tool, ui.project.pixel_size),
                        tool.color.rgb(),
                    )?;
                }
                Kind::Polygon => {
                    polygon_fill(hdc, &controls, export)?;
                    stroke(hdc, &controls, tool.color.rgb(), tool.width, true)?;
                    let center = polygon_center(&tool.points);
                    text_at(
                        map_tool(center)?,
                        0.0,
                        if export { 0.0 } else { metric_label_y },
                        &metric_label(tool, ui.project.pixel_size),
                        tool.color.rgb(),
                    )?;
                }
            }
            if !export && ui.selected == Some(index) {
                markers(hdc, controls, 4, 0xff0000, false)?;
            }
        }
        if !export && !ui.pending.is_empty() {
            let offset = |p: Pt| Pt::new(p.x - origin.x, p.y - origin.y);
            let mut points = ui.pending.iter().copied().map(offset).collect::<Vec<_>>();
            if let Some(preview) = ui.preview {
                points.push(offset(preview));
            }
            dot_line(hdc, &points, DEFAULT_WIDTH, 0x007000)?;
            let _bold = GdiSelection::select(hdc, control_font)?;
            for (index, position) in ui.pending.iter().copied().map(offset).enumerate() {
                marker(hdc, position, 4, 0xff0000, false)?;
                if ui.mode == Mode::Curve {
                    text_at(
                        position,
                        10.0,
                        control_label_y,
                        CONTROL_LABELS[index.min(2)],
                        0xb40000,
                    )?;
                }
            }
        }
        if let Some(reference) = ui.project.ref_pixel.filter(|_| ui.project.georeferenced()) {
            let position = offset_drawing_point(reference.transformed(
                ui.project.rotation,
                ui.project.zoom,
                ui.project.center,
            ))?;
            marker(hdc, position, 4, 0xff0000, false)?;
            let _bold = GdiSelection::select(hdc, control_font)?;
            text_at(position, 10.0, control_label_y, "G", 0xb40000)?;
        }
        Ok(())
    }
    fn paint_canvas(hwnd: H) {
        let paint = PaintSession::begin(hwnd);
        let destination = paint.paint.hdc;
        if destination == 0 {
            return;
        }
        let mut image_error = None;
        let result = (|| -> ResultT<()> {
            unsafe {
                let mut rect = Rect::default();
                if GetClientRect(hwnd, &mut rect) == 0 {
                    return Err(win32_error("GetClientRect"));
                }
                let (width, height) = wh(rect);
                if width < 1 || height < 1 {
                    return Ok(());
                }
                let dc = CreateCompatibleDC(destination);
                if dc == 0 {
                    return Err(win32_error("CreateCompatibleDC"));
                }
                let memory = MemoryDc(dc);
                let bitmap = GdiObject::checked(
                    CreateCompatibleBitmap(destination, width, height),
                    "CreateCompatibleBitmap",
                )?;
                let _bitmap = GdiSelection::select(memory.0, bitmap.0)?;
                let brush =
                    GdiObject::checked(CreateSolidBrush(colorref(0x3a3a3a)), "CreateSolidBrush")?;
                if FillRect(memory.0, &rect, brush.0) == 0 {
                    return Err(win32_error("FillRect"));
                }
                APP.with(|app| -> ResultT<()> {
                    let ui = app.borrow();
                    if let Err(error) = draw_image_scene(memory.0, &ui, ui.scroll) {
                        image_error = Some(error);
                    }
                    if let Err(error) = draw_overlays(memory.0, &ui, ui.scroll, false) {
                        image_error = Some(error);
                    }
                    Ok(())
                })?;
                if BitBlt(destination, 0, 0, width, height, memory.0, 0, 0, SRCCOPY) == 0 {
                    return Err(win32_error("BitBlt"));
                }
                Ok(())
            }
        })();
        if let Some(error) = result.err().or(image_error) {
            APP.with(|app| {
                if let Ok(mut ui) = app.try_borrow_mut() {
                    ui.status(error);
                }
            });
        }
    }

    fn export_bitmap(ui: &UI, path: &Path) -> ResultT<()> {
        if ui.image.0.is_null() {
            return Err("Import an image before exporting".into());
        }
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let codec = match extension.as_str() {
            "png" => &PNG_GUID,
            "jpg" | "jpeg" => &JPG_GUID,
            "tif" | "tiff" => &TIF_GUID,
            _ => {
                return Err(format!(
                    "Unsupported image extension: .{extension}. Choose PNG, TIFF or JPEG."
                ))
            }
        };
        let cached = display_raster(ui)?;
        let image = bitmap_from_rgb(&cached.transformed.image)?;
        {
            let graphics = GraphicsRef::for_image(&image)?;
            let dc = GraphicsDc::acquire(&graphics)?;
            let origin = Pt::new(cached.transformed.origin.0, cached.transformed.origin.1);
            draw_overlays(dc.dc, ui, origin, true)?;
            dc.release()?;
        }
        gdip_save(&image, path, codec)
    }

    // ------------------------------ TOOL ACTIONS -----------------------------
    fn save_current(owner: H, save_as: bool) -> bool {
        on_canvas_up();
        let old = APP.with(|a| a.borrow().project.filename.clone());
        let path = if save_as || old.is_empty() {
            match FileDialog::SaveProject.choose(owner) {
                Some(p) => p,
                None => return false,
            }
        } else {
            PathBuf::from(old)
        };
        let mut project = APP.with(|a| a.borrow().project.clone());
        project.filename = path.to_string_lossy().to_string();
        project.name = path
            .file_stem()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "Untitled".into());
        match save_project(&project, &path) {
            Ok(()) => {
                APP.with(|a| {
                    let mut u = a.borrow_mut();
                    u.project.filename = project.filename;
                    u.project.name = project.name;
                    u.dirty = false;
                    u.status(format!("Saved {}", path.display()));
                    u.refresh();
                });
                true
            }
            Err(e) => {
                unsafe {
                    show_message(owner, "Cannot save project", &e, MB_ICONERROR);
                }
                false
            }
        }
    }
    fn confirm_save(owner: H) -> bool {
        on_canvas_up();
        let dirty = APP.with(|a| a.borrow().dirty);
        if !dirty {
            return true;
        }
        let choice = unsafe {
            show_message(
                owner,
                "Baycraft",
                "Do you want to save changes to Document?",
                MB_YESNOCANCEL | MB_ICONQUESTION,
            )
        };
        match choice {
            IDYES => save_current(owner, false),
            IDNO => true,
            _ => false,
        }
    }
    fn new_project(owner: H) {
        if !confirm_save(owner) {
            return;
        }
        APP.with(|a| {
            let mut u = a.borrow_mut();
            let _ = u.install_project(Project::default());
            u.history.clear();
            u.future.clear();
            u.dirty = false;
            u.status("Select an object or drag its red control handles.");
            u.refresh();
        });
    }
    fn load_named(owner: H, path: &Path) {
        match load_project(path) {
            Ok(p) => {
                let result = APP.with(|a| {
                    let mut u = a.borrow_mut();
                    let r = u.install_project(p);
                    if r.is_ok() {
                        u.history.clear();
                        u.future.clear();
                        u.dirty = false;
                        u.refresh();
                        u.status(format!("Opened {}", path.display()));
                    }
                    r
                });
                if let Err(e) = result {
                    unsafe {
                        show_message(owner, "Cannot open project", &e, MB_ICONERROR);
                    }
                }
            }
            Err(e) => unsafe {
                show_message(owner, "Cannot open project", &e, MB_ICONERROR);
            },
        }
    }
    fn open_project_action(owner: H) {
        if !confirm_save(owner) {
            return;
        }
        if let Some(p) = FileDialog::OpenProject.choose(owner) {
            load_named(owner, &p);
        }
    }
    fn import_image_action(owner: H) {
        let Some(path) = FileDialog::ImportImage.choose(owner) else {
            return;
        };
        let loaded = (|| -> ResultT<(ImageRef, Vec<u8>)> {
            let original = gdip_load(&path)?;
            let image = normalize_image_rgb(&original)?;
            let bytes = encoded_png(&image)?;
            Ok((image, bytes))
        })();
        match loaded {
            Ok((image, bytes)) => {
                let result = APP.with(|slot| {
                    let mut ui = slot.borrow_mut();
                    ui.checkpoint();
                    ui.set_image(image, bytes)?;
                    ui.status(
                        "Image imported. Select Parabola, then click the diffraction point H.",
                    );
                    Ok::<(), String>(())
                });
                if let Err(error) = result {
                    unsafe {
                        show_message(owner, "Import failed", &error, MB_ICONERROR);
                    }
                }
            }
            Err(error) => unsafe {
                show_message(owner, "Import failed", &error, MB_ICONERROR);
            },
        }
    }
    fn undo_action(owner: H, redo: bool) {
        on_canvas_up();
        let result = APP.with(|slot| -> ResultT<()> {
            let mut ui = slot.borrow_mut();
            let next = if redo {
                ui.future.last()
            } else {
                ui.history.last()
            }
            .cloned();
            let Some(next) = next else {
                return Ok(());
            };
            let current = ui.project.clone();
            let scroll = ui.scroll;
            // Decode and validate the snapshot before consuming either stack.
            ui.install_project(next)?;
            if redo {
                ui.future.pop();
                ui.history.push(current);
            } else {
                ui.history.pop();
                ui.future.push(current);
            }
            ui.scroll = scroll;
            ui.dirty = true;
            ui.status("Select an object or drag its red control handles.");
            ui.refresh();
            Ok(())
        });
        if let Err(error) = result {
            unsafe {
                show_message(owner, "Undo / Redo", &error, MB_ICONERROR);
            }
        }
    }
    fn export_action(owner: H) {
        let has_image = APP.with(|a| !a.borrow().project.image_png.is_empty());
        if !has_image {
            return;
        }
        let Some(path) = FileDialog::ExportImage.choose(owner) else {
            return;
        };
        let result = APP.with(|a| export_bitmap(&a.borrow(), &path));
        match result {
            Ok(()) => APP.with(|a| {
                a.borrow_mut()
                    .status(format!("Image exported: {}", path.display()))
            }),
            Err(e) => unsafe {
                show_message(owner, "Cannot export image", &e, MB_ICONERROR);
            },
        }
    }
    fn print_action(owner: H) {
        if !APP.with(|app| !app.borrow().project.image_png.is_empty()) {
            return;
        }
        let prepared = (|| -> ResultT<TemporaryFile> {
            let temporary = TemporaryFile::image()?;
            APP.with(|app| export_bitmap(&app.borrow(), &temporary.path))?;
            Ok(temporary)
        })();
        match prepared {
            Ok(temporary) => {
                let result = unsafe {
                    ShellExecuteW(
                        owner,
                        wide("print").as_ptr(),
                        wide_path(&temporary.path).as_ptr(),
                        null(),
                        null(),
                        1,
                    )
                };
                if result <= 32 {
                    unsafe {
                        show_message(
                            owner,
                            "Print",
                            "Windows could not open an image print handler.",
                            MB_ICONERROR,
                        );
                    }
                } else {
                    // The external print handler opens this file asynchronously.
                    let path = temporary.persist();
                    APP.with(|app| {
                        app.borrow_mut()
                            .status(format!("Print image prepared: {}", path.display()))
                    });
                }
            }
            Err(error) => unsafe {
                show_message(owner, "Print", &error, MB_ICONERROR);
            },
        }
    }
    fn set_mode_action(owner: H, mode: Mode) {
        let result = APP.with(|a| a.borrow_mut().mode(mode));
        if let Err(error) = result {
            let title = if error.starts_with("Import") {
                "Image required"
            } else {
                "Image scale required"
            };
            unsafe {
                show_message(owner, title, &error, MB_ICONWARNING);
            }
        }
    }
    fn cancel_action() {
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            ui.finish_drag();
            ui.selected = None;
            let _ = ui.mode(Mode::Select);
            ui.refresh();
        });
    }
    fn zoom_action(delta: i32) {
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            let next = ui.project.zoom.saturating_add(delta);
            ui.set_view(Some(next), None);
        });
    }
    fn wheel_action(canvas: H, wparam: usize) {
        let detent = ((wparam >> 16) as u16) as i16 as i32;
        if detent == 0 {
            return;
        }
        let steps = detent.abs() / 120;
        let direction = if detent > 0 { 1 } else { -1 };
        let ctrl = (wparam & 0x0008) != 0 || unsafe { GetKeyState(0x11) < 0 };
        if ctrl {
            zoom_action(direction * 10);
        } else {
            if steps == 0 {
                return;
            }
            let command = if direction > 0 { 0 } else { 1 };
            for _ in 0..(steps * 3) {
                on_scroll(canvas, SB_VERT, command);
            }
        }
    }
    fn start_middle_pan(at: Pt) {
        APP.with(|slot| {
            let _guard = InitializationGuard::begin();
            let mut ui = slot.borrow_mut();
            ui.pan_start = Some((at, ui.scroll));
            unsafe {
                SetCapture(ui.canvas);
            }
        });
    }
    fn fit_action() {
        APP.with(|a| {
            let mut u = a.borrow_mut();
            if u.project.width <= 0 || u.project.height <= 0 {
                return;
            }
            let zoom = (100.0
                * ((u.canvas_w - 30) as f64 / u.project.width as f64)
                    .min((u.canvas_h - 30) as f64 / u.project.height as f64))
            .trunc() as i32;
            u.set_view(Some(zoom), Some(0));
            u.scroll_to_start();
        });
    }
    fn apply_view() {
        let values = APP.with(|a| {
            let u = a.borrow();
            (edit_text(u.ctl(ZOOM_EDIT)), edit_text(u.ctl(ROT_EDIT)))
        });
        let parsed = (
            parse_integer_entry(&values.0),
            parse_integer_entry(&values.1),
        );
        if let (Ok(z), Ok(r)) = parsed {
            APP.with(|a| a.borrow_mut().set_view(Some(z), Some(r)));
        } else {
            APP.with(|slot| {
                slot.borrow_mut()
                    .status("Enter a valid zoom percentage and rotation angle.")
            });
        }
    }
    fn spin_value(text: &str, increment: i32, minimum: i32, maximum: i32) -> i32 {
        let text = text.trim_start();
        let bytes = text.as_bytes();
        let signed = usize::from(matches!(bytes.first(), Some(b'+' | b'-')));
        let value = if bytes
            .get(signed..signed + 3)
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case(b"inf"))
        {
            Some(if bytes.first() == Some(&b'-') {
                f64::NEG_INFINITY
            } else {
                f64::INFINITY
            })
        } else {
            let mut end = signed;
            let mut digits = 0;
            while bytes.get(end).is_some_and(u8::is_ascii_digit) {
                end += 1;
                digits += 1;
            }
            if bytes.get(end) == Some(&b'.') {
                end += 1;
                while bytes.get(end).is_some_and(u8::is_ascii_digit) {
                    end += 1;
                    digits += 1;
                }
            }
            if digits == 0 {
                None
            } else {
                if matches!(bytes.get(end), Some(b'e' | b'E')) {
                    let mut exponent = end + 1;
                    if matches!(bytes.get(exponent), Some(b'+' | b'-')) {
                        exponent += 1;
                    }
                    let first_digit = exponent;
                    while bytes.get(exponent).is_some_and(u8::is_ascii_digit) {
                        exponent += 1;
                    }
                    if exponent > first_digit {
                        end = exponent;
                    }
                }
                text[..end].parse::<f64>().ok()
            }
        };
        value
            .map(|number| number + f64::from(increment))
            .unwrap_or(f64::from(minimum))
            .clamp(f64::from(minimum), f64::from(maximum))
            .round_ties_even() as i32
    }
    fn adjust_spin_input(id: usize, increment: i32) {
        let buddy = APP.with(|slot| {
            let ui = slot.borrow();
            let (edit, minimum, maximum) = match id {
                ZOOM_SPIN => (ZOOM_EDIT, 10, 500),
                ROT_SPIN => (ROT_EDIT, -360, 360),
                WIDTH_SPIN => (WIDTH_EDIT, 1, 20),
                _ => return None,
            };
            let buddy = ui.ctl(edit);
            let value = spin_value(&edit_text(buddy), increment, minimum, maximum);
            let _guard = InitializationGuard::begin();
            unsafe {
                set_text(buddy, &value.to_string());
                SendMessageW(ui.ctl(id), UDM_SETPOS32, 0, value as isize);
            }
            Some(buddy)
        });
        if matches!(id, ZOOM_SPIN | ROT_SPIN) {
            apply_view();
        }
        if let Some(buddy) = buddy {
            let _guard = InitializationGuard::begin();
            unsafe {
                SetFocus(buddy);
                SendMessageW(buddy, 0x00b1, 0, -1); // EM_SETSEL.
            }
        }
    }
    unsafe extern "system" fn color_dialog_hook(
        window: H,
        message: u32,
        _wparam: usize,
        _lparam: isize,
    ) -> usize {
        guarded_gui_call(0, || {
            if message == 0x0110 {
                set_text(window, "Line Color");
            }
            0
        })
    }
    thread_local! {
        static COLOR_PALETTE: Cell<[u32; 16]> = const { Cell::new([0; 16]) };
    }
    fn color_action(owner: H) {
        let color = APP.with(|a| a.borrow().selected_tool().map(|t| t.color.rgb()));
        let Some(color) = color else {
            return;
        };
        let mut palette = COLOR_PALETTE.with(Cell::get);
        let mut data = ChooseColor {
            size: size_of::<ChooseColor>() as u32,
            owner,
            instance: 0,
            color: colorref(color),
            custom: palette.as_mut_ptr(),
            flags: CC_RGBINIT | CC_FULLOPEN | 0x0010,
            cust_data: 0,
            hook: Some(color_dialog_hook),
            template: null(),
        };
        let chosen = unsafe { ChooseColorW(&mut data) };
        COLOR_PALETTE.with(|stored| stored.set(palette));
        if chosen != 0 {
            APP.with(|a| {
                let mut u = a.borrow_mut();
                if let Some(i) = u.selected.filter(|&index| index < u.project.tools.len()) {
                    let color = Color::from_rgb(colorref(data.color));
                    if u.project.tools[i].color == color {
                        return;
                    }
                    u.checkpoint();
                    u.project.tools[i].color = color;
                    u.refresh();
                }
            });
        } else {
            let error = unsafe { CommDlgExtendedError() };
            if error != 0 {
                unsafe {
                    show_message(
                        owner,
                        "Line Color",
                        &format!("The color dialog failed (Windows error {error})."),
                        MB_ICONERROR,
                    );
                }
            }
        }
    }
    fn change_model() {
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            let selected = unsafe { SendMessageW(ui.ctl(MODEL_SELECT), CB_GETCURSEL, 0, 0) };
            let Some(&model) = usize::try_from(selected)
                .ok()
                .and_then(|index| Model::ALL.get(index))
            else {
                return;
            };
            if model == ui.project.model {
                return;
            }
            ui.checkpoint();
            ui.project.model = model;
            ui.status(format!(
                "{} selected for all planform curves.",
                model.text()
            ));
            ui.refresh();
        });
    }
    fn apply_properties(owner: H) {
        let values = APP.with(|slot| {
            let ui = slot.borrow();
            (
                ui.selected,
                edit_text(ui.ctl(STEP_EDIT)),
                edit_text(ui.ctl(LIMIT_EDIT)),
                edit_text(ui.ctl(WIDTH_EDIT)),
            )
        });
        let Some(index) = values.0 else {
            return;
        };
        let parsed = (
            parse_number(&values.1),
            parse_number(&values.2),
            parse_integer_entry(&values.3),
        );
        let (Ok(increment), Ok(limit), Ok(width)) = parsed else {
            unsafe {
                show_message(
                    owner,
                    "Invalid properties",
                    "Enter valid numerical properties.",
                    MB_ICONERROR,
                );
            }
            return;
        };
        if increment < 1e-12
            || !(1..=20).contains(&width)
            || limit.max(0.0) / increment > MAX_SAMPLES as f64
        {
            unsafe {
                show_message(owner, "Invalid properties", "Angle step must be at least 1e-12, width must be 1..20 and samples must not exceed 100,000.", MB_ICONERROR);
            }
            return;
        }
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            if ui.project.tools.get(index).is_some_and(|tool| {
                tool.increment != increment || tool.limit != limit || tool.width != width
            }) {
                ui.checkpoint();
                let tool = &mut ui.project.tools[index];
                tool.increment = increment;
                tool.limit = limit;
                tool.width = width;
                ui.refresh();
            }
        });
    }
    fn edit_coordinates(owner: H) {
        let data = APP.with(|slot| {
            let ui = slot.borrow();
            ui.selected_tool().map(|tool| {
                let rows = tool
                    .points
                    .iter()
                    .enumerate()
                    .map(|(index, &pixel)| {
                        let name = if tool.kind == Kind::Curve {
                            CONTROL_LABELS.get(index).unwrap_or(&"P").to_string()
                        } else {
                            (index + 1).to_string()
                        };
                        (name, ui.project.world(pixel))
                    })
                    .collect::<Vec<_>>();
                (rows, ui.project.georeferenced())
            })
        });
        let Some((rows, referenced)) = data else {
            return;
        };
        let Some(values) = coordinate_form(owner, &rows, referenced) else {
            return;
        };
        if values.len() != rows.len() * 2 {
            unsafe {
                show_message(
                    owner,
                    "Coordinates",
                    "Incomplete coordinate data.",
                    MB_ICONERROR,
                );
            }
            return;
        }
        // The modal form validated every number and its source-image range.
        let points: Vec<Pt> = APP.with(|slot| {
            let ui = slot.borrow();
            values.chunks_exact(2).map(|pair| ui.project.source(Pt::new(pair[0], pair[1]))).collect()
        });
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            if let Some(index) = ui.selected {
                if ui.project.tools.get(index).map(|tool| tool.points.len()) == Some(points.len())
                    && ui.project.tools[index].points != points
                {
                    ui.checkpoint();
                    ui.project.tools[index].points = points;
                    ui.refresh();
                }
            }
        });
    }
    fn delete_selected() {
        APP.with(|a| {
            let mut u = a.borrow_mut();
            if let Some(i) = u.selected {
                u.checkpoint();
                u.project.tools.remove(i);
                u.selected = None;
                u.refresh();
            }
        });
    }
    fn delete_vertex() {
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            let Some(index) = ui.selected else {
                return;
            };
            let Some(tool) = ui.project.tools.get(index) else {
                return;
            };
            if tool.kind != Kind::Polygon || tool.points.len() <= 3 {
                return;
            }
            let points = tool
                .points
                .iter()
                .copied()
                .map(|point| tool.display_point(point))
                .collect::<Vec<_>>();
            let target = ui.context_point.unwrap_or(points[0]);
            let vertex = (0..points.len())
                .min_by(|&a, &b| {
                    points[a]
                        .distance(target)
                        .total_cmp(&points[b].distance(target))
                })
                .unwrap_or(0);
            ui.checkpoint();
            ui.project.tools[index].points.remove(vertex);
            ui.refresh();
        });
    }
    fn selected_results(project: &Project, index: usize) -> ResultT<SelectedResults> {
        let tool = project
            .tools
            .get(index)
            .ok_or_else(|| "Selected object not found".to_owned())?;
        let mut result = SelectedResults {
            title: format!("Baycraft Results — {}", tool.identifier()),
            width: 770,
            height: 550,
            summary_title: tool.identifier(),
            summary: Vec::new(),
            table_title: "",
            table: None,
            footer: String::new(),
        };
        match tool.kind {
            Kind::Measure => {
                let first = project.world(tool.points[0]);
                let second = project.world(tool.points[1]);
                result.width = 610;
                result.height = 300;
                result.summary = vec![
                    vec![format!(
                        "Measured distance: {:.2} m",
                        tool.length_m(project.pixel_size)
                    )],
                    vec![format!("P1: X = {:.2} m,  Y = {:.2} m", first.x, first.y)],
                    vec![format!("P2: X = {:.2} m,  Y = {:.2} m", second.x, second.y)],
                ];
                result.footer = "Measure objects are not included in output.txt.".into();
            }
            Kind::Polygon => {
                result.summary = vec![
                    vec![format!(
                        "Enclosed area: {:.2} m²",
                        tool.area_m2(project.pixel_size)
                    )],
                    vec![format!(
                        "Perimeter: {:.2} m",
                        polygon_perimeter(&tool.points) * project.pixel_size
                    )],
                    vec![format!("Vertices: {}", tool.points.len())],
                ];
                result.table_title = "Polygon vertex coordinates";
                let rows = tool
                    .points
                    .iter()
                    .enumerate()
                    .map(|(index, &point)| {
                        let world = project.world(point);
                        vec![
                            (index + 1).to_string(),
                            format!("{:.2}", world.x),
                            format!("{:.2}", world.y),
                        ]
                    })
                    .collect::<Vec<_>>();
                let clipboard = table_text("Vertex\tX (m)\tY (m)", &rows);
                result.table = Some(ResultTable {
                    headings: vec!["Vertex", "X (m)", "Y (m)"],
                    widths: vec![90, 265, 265],
                    rows,
                    clipboard,
                });
            }
            Kind::Curve => {
                let curve = tool.curve(project.model)?;
                let ratio =
                    planform_ratio(curve.beta, curve.beta, project.model, Some(curve.coeff))?;
                result.width = 980;
                result.height = 650;
                result.summary_title = "Planform analysis".into();
                result.summary = vec![
                    vec![
                        format!("Model: {}", project.model.text()),
                        format!("Reference angle β: {:.2}°", curve.beta),
                    ],
                    vec![
                        format!(
                            "Reference radius Rb: {:.2} m",
                            tool.length_m(project.pixel_size)
                        ),
                        format!("Angular increment: {:.2}°", tool.increment),
                    ],
                    vec![
                        format!("R(β)/Rb: {ratio:.4}"),
                        format!("Number of samples: {}", curve.angles.len()),
                    ],
                    vec![
                        format!("Wave direction (from): {}", fmt_bearing(curve.direction)),
                        "Clockwise from N · north-up source image assumed".into(),
                    ],
                    vec![format!(
                        "C0 = {:.6}   C1 = {:.6}   C2 = {:.6}",
                        curve.coeff[0], curve.coeff[1], curve.coeff[2]
                    )],
                ];
                result.table_title = "Sampled equilibrium planform";
                let rows = curve
                    .angles
                    .iter()
                    .zip(&curve.radii)
                    .zip(&curve.points)
                    .enumerate()
                    .map(|(index, ((&theta, &radius), &point))| {
                        let world = project.world(point);
                        vec![
                            (index + 1).to_string(),
                            format!("{theta:.2}"),
                            format!("{:.2}", radius * project.pixel_size),
                            format!("{:.2}", world.x),
                            format!("{:.2}", world.y),
                        ]
                    })
                    .collect::<Vec<_>>();
                result.footer = format!("{} rows · length in metres", rows.len());
                let clipboard = table_text("No.\tTheta (deg)\tRn (m)\tX (m)\tY (m)", &rows);
                result.table = Some(ResultTable {
                    headings: vec!["No.", "θ (degrees)", "Rn (m)", "X (m)", "Y (m)"],
                    widths: vec![65, 130, 130, 220, 220],
                    rows,
                    clipboard,
                });
            }
        }
        Ok(result)
    }

    fn table_text(header: &str, rows: &[Vec<String>]) -> String {
        let mut text = header.to_owned();
        for row in rows {
            text.push('\n');
            text.push_str(&row.join("\t"));
        }
        text
    }

    fn show_results(owner: H) {
        let state = APP.with(|slot| {
            let ui = slot.borrow();
            (
                ui.project.clone(),
                ui.selected.filter(|&index| index < ui.project.tools.len()),
            )
        });
        let (project, index) = state;
        if !project.scale_defined {
            APP.with(|slot| {
                slot.borrow_mut()
                    .status("Define image scale first using the Scale tool.")
            });
            unsafe {
                show_message(owner,"Image scale required","Define the image scale before viewing results.\n\nSelect Scale, click two points a known distance apart, and enter that distance in metres.",MB_ICONWARNING);
            }
            return;
        }
        let text = report(&project, index);
        let report_location = match save_report_with_fallback(&project, &text) {
            Ok((path, warning)) => {
                APP.with(|slot| {
                    slot.borrow_mut()
                        .status(format!("Results report saved: {}", path.display()))
                });
                if let Some(message) = warning {
                    unsafe {
                        show_message(
                            owner,
                            "Report saved to alternate location",
                            &message,
                            MB_ICONWARNING,
                        );
                    }
                }
                Some(path)
            }
            Err(message) => {
                APP.with(|slot| {
                    slot.borrow_mut()
                        .status("Cannot save output.txt; results remain available.")
                });
                unsafe {
                    show_message(owner, "Cannot save output.txt", &message, MB_ICONERROR);
                }
                None
            }
        };
        if let Some(index) = index {
            match selected_results(&project, index) {
                Ok(results) => {
                    show_selected_results(owner, results);
                    return;
                }
                Err(error) => {
                    APP.with(|slot| {
                        slot.borrow_mut()
                            .status(format!("Curve calculation: {error}"))
                    });
                }
            }
        }
        show_text_window(owner, &text, report_location.as_deref(), project.model);
    }
    fn help_action(owner: H) {
        unsafe {
            show_message(owner, "Baycraft Help", "1. Import a map or aerial/satellite image.\n2. Select Oliveira2010 (default) or Hsu1989 in the Model list. The selected model applies to every planform curve in the project.\n3. Choose Parabola, then click H (diffraction point), E (downcoast control), and W (wave-crest tangent endpoint). Drag the handles to adjust these points.\n4. Both models use sixth-degree C0, C1, C2 coefficient polynomials. Oliveira2010 covers beta = 22.19 to 88.29 degrees; Hsu1989 covers beta = 10 to 80 degrees. Out-of-range curves retain their control points for editing, but their shorelines are not calculated.\n5. Use Apply under Properties to set the selected object's angle increment, angle limit, and line width. Control lines and labels are always shown. The selected model applies to all curves, including their image exports and numeric results.\n6. Define image scale before opening Results. Results works even without a selected object; only planform curves and polygons are included in output.txt. The planform table can be copied.\n7. Scale: click the endpoints of a known distance and enter its length in metres. Lengths use metres and areas square metres.\n8. Georeference: after setting scale, select Georeference, click one known position in the source image, and enter X Easting and Y Northing in metres. North is assumed up. The reference is stored in .bay files; all reported XY then use that coordinate system (its EPSG code is not inferred).\n9. Wave direction is reported as a FROM bearing clockwise from north (N=0, E=90, S=180, W=270). The E-W crest normal facing toward H is taken as offshore. The source image must be north-up for a geographic bearing; view rotation is ignored.\n10. Polygon: click vertices, then double-click or press Enter. Measure: click two endpoints.\n11. Save/Open uses .bay projects with embedded images, styles, calibration, georeference, and the selected model. Export defaults to PNG.\n\nEsc cancels. Delete removes selection. Ctrl+Z/Y undo/redo. Application windows, panels, and result columns have fixed sizes. The main window fills the available screen and may be moved by its title bar. Object numbers are independent by type.", 0);
        }
    }

    // -------------------------- CANVAS INTERACTION ---------------------------
    fn segment_distance(p: Pt, a: Pt, b: Pt) -> f64 {
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let len = dx * dx + dy * dy;
        let u = if len > 0.0 {
            (((p.x - a.x) * dx + (p.y - a.y) * dy) / len).clamp(0.0, 1.0)
        } else {
            0.0
        };
        p.distance(Pt::new(a.x + u * dx, a.y + u * dy))
    }
    fn hit_test(ui: &UI, at: Pt) -> Option<usize> {
        for (index, tool) in ui.project.tools.iter().enumerate().rev() {
            if !tool.visible {
                continue;
            }
            let mapped = |point: Pt| ui.to_canvas_tool(tool, point);
            if tool.points.iter().any(|&point| mapped(point).distance(at) < 10.0) {
                return Some(index);
            }
            let curve = if tool.kind == Kind::Curve {
                ui.curve(tool).ok()
            } else {
                None
            };
            let path = curve
                .as_ref()
                .map_or(tool.points.as_slice(), |curve| curve.points.as_slice());
            let mut previous = None;
            for &point in path {
                let point = mapped(point);
                if previous.is_some_and(|last| segment_distance(at, last, point) < 8.0) {
                    return Some(index);
                }
                previous = Some(point);
            }
            if tool.kind == Kind::Polygon && path.len() > 2
                && segment_distance(at, mapped(path[path.len() - 1]), mapped(path[0])) < 8.0
            {
                return Some(index);
            }
        }
        None
    }
    enum ClickEvent {
        None,
        Scale(Pt, Pt),
        Geo(Pt),
    }
    fn on_canvas_down(owner: H, at: Pt, flags: usize) {
        let event = APP.with(|app| {
            let _guard = InitializationGuard::begin();
            let mut ui = app.borrow_mut();
            let display = Pt::new(
                (at.x + ui.scroll.x).round_ties_even(),
                (at.y + ui.scroll.y).round_ties_even(),
            );
            let source = ui.source_view(display);
            match ui.mode {
                Mode::Pan => {
                    ui.pan_start = Some((at, ui.scroll));
                    unsafe {
                        SetCapture(ui.canvas);
                    }
                    ClickEvent::None
                }
                Mode::Zoom => {
                    let delta = if flags & 4 != 0 { -10 } else { 10 };
                    let zoom = ui.project.zoom.saturating_add(delta);
                    ui.set_view(Some(zoom), None);
                    ClickEvent::None
                }
                Mode::Georeference => {
                    if source.x < 0.0
                        || source.y < 0.0
                        || source.x >= f64::from(ui.project.width)
                        || source.y >= f64::from(ui.project.height)
                    {
                        ui.status("Choose a reference point inside the image.");
                        ClickEvent::None
                    } else {
                        ClickEvent::Geo(source)
                    }
                }
                Mode::Scale | Mode::Curve | Mode::Measure | Mode::Polygon => {
                    if ui.pending.last().is_some_and(|&point| point == display) {
                        return ClickEvent::None;
                    }
                    ui.pending.push(display);
                    let count = ui.pending.len();
                    let event = if ui.mode == Mode::Scale && count >= 2 {
                        ClickEvent::Scale(ui.pending[0], ui.pending[1])
                    } else {
                        ClickEvent::None
                    };
                    if ui.mode == Mode::Curve && count == 3
                        || ui.mode == Mode::Measure && count == 2
                    {
                        let kind = if ui.mode == Mode::Curve {
                            Kind::Curve
                        } else {
                            Kind::Measure
                        };
                        ui.finish_tool(kind);
                    } else if ui.mode == Mode::Curve {
                        let prompt = match count {
                            1 => "Click the downcoast beach control point (E).",
                            _ => "Click the wave-crest tangent endpoint (W).",
                        };
                        ui.status(prompt);
                    } else if ui.mode == Mode::Scale && count == 1 {
                        ui.status("Click the other end of the known distance.");
                    }
                    unsafe {
                        InvalidateRect(ui.canvas, null(), 0);
                    }
                    event
                }
                Mode::Select => {
                    if let Some(index) = ui.selected {
                        let vertex = ui.project.tools[index].points.iter().position(|&point| {
                            let displayed = ui.to_canvas_tool(&ui.project.tools[index], point);
                            (displayed.x - at.x).abs() <= 6.0 && (displayed.y - at.y).abs() <= 6.0
                        });
                        if let Some(vertex) = vertex {
                            ui.drag = Some(Drag {
                                vertex,
                                before: ui.project.clone(),
                            });
                            unsafe {
                                SetCapture(ui.canvas);
                            }
                            return ClickEvent::None;
                        }
                    }
                    let selection = hit_test(&ui, at);
                    ui.select(selection);
                    ui.refresh();
                    ClickEvent::None
                }
            }
        });
        match event {
            ClickEvent::None => {}
            ClickEvent::Scale(p0, p1) => {
                let input = form(
                    owner,
                    "Scale",
                    &[("Known distance in meters:", String::new())],
                    &[],
                );
                if let Some(values) = input {
                    let meters = values[0];
                    let result = APP.with(|slot| -> ResultT<()> {
                        let mut ui = slot.borrow_mut();
                        let mut calibrated = ui.project.clone();
                        calibrated.calibrated(p0.distance(p1), meters)?;
                        ui.checkpoint();
                        ui.project = calibrated;
                        ui.status(format!("Scale calibrated: {} m between the selected points.", fmt_display(meters, 2)));
                        Ok(())
                    });
                    if let Err(error) = result {
                        unsafe { show_message(owner, "Scale", &error, MB_ICONERROR); }
                    }
                }
                APP.with(|a| {
                    let mut u = a.borrow_mut();
                    u.pending.clear();
                    u.mode = Mode::Select;
                    u.refresh();
                });
            }
            ClickEvent::Geo(source) => {
                let defaults = APP.with(|a| {
                    let u = a.borrow();
                    if u.project.georeferenced() {
                        let p = u.project.world(source);
                        (format!("{:.6}", p.x), format!("{:.6}", p.y))
                    } else {
                        (String::new(), String::new())
                    }
                });
                let introduction = [
                    format!(
                        "Reference point on north-up image: pixel ({:.2}, {:.2})",
                        source.x, source.y
                    ),
                    "Enter coordinates in a projected metric system (metres).".to_owned(),
                ];
                let prompt = form(
                    owner,
                    "Georeference image",
                    &[
                        ("X (Easting, m)", defaults.0),
                        ("Y (Northing, m)", defaults.1),
                    ],
                    &introduction,
                );
                if let Some(values) = prompt {
                    let (x, y) = (values[0], values[1]);
                    let result = APP.with(|slot| {
                        let mut ui = slot.borrow_mut();
                        ui.checkpoint();
                        ui.project.georeference(source, Pt::new(x, y))?;
                        ui.status(format!("Image georeferenced: X={x:.3} m, Y={y:.3} m."));
                        ui.mode = Mode::Select;
                        ui.refresh();
                        Ok::<(), String>(())
                    });
                    if let Err(error) = result {
                        unsafe { show_message(owner, "Invalid coordinates", &error, MB_ICONERROR); }
                    }
                }
            }
        }
    }
    fn finish_polygon() {
        APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            if ui.mode == Mode::Polygon && ui.pending.len() >= 3 {
                ui.finish_tool(Kind::Polygon);
            }
        });
    }
    fn insert_polygon_vertex(at: Pt) -> bool {
        APP.with(|a| {
            let mut u = a.borrow_mut();
            if u.mode != Mode::Select {
                return false;
            }
            let Some(index) = u.selected else {
                return false;
            };
            let Some(tool) = u.project.tools.get(index) else {
                return false;
            };
            if tool.kind != Kind::Polygon || tool.points.len() < 3 {
                return false;
            }
            let display = tool
                .points
                .iter()
                .copied()
                .map(|p| u.to_canvas_tool(tool, p))
                .collect::<Vec<_>>();
            let best = (0..display.len())
                .map(|j| {
                    (
                        segment_distance(at, display[j], display[(j + 1) % display.len()]),
                        j,
                    )
                })
                .min_by(|a, b| a.0.total_cmp(&b.0));
            let Some((distance, edge)) = best else {
                return false;
            };
            if distance >= 10.0 {
                return false;
            }
            let source = u.canvas_to_tool_source(tool, at);
            u.checkpoint();
            u.project.tools[index].points.insert(edge + 1, source);
            u.refresh();
            true
        })
    }
    fn on_canvas_move(at: Pt) {
        APP.with(|a| {
            let mut u = a.borrow_mut();
            if let Some((start, scroll)) = u.pan_start {
                u.scroll = Pt::new(scroll.x + start.x - at.x, scroll.y + start.y - at.y);
                u.scroll_update();
                unsafe {
                    InvalidateRect(u.canvas, null(), 0);
                }
                return;
            }
            let pt = u.canvas_to_source(at);
            if let Some(vertex) = u.drag.as_ref().map(|drag| drag.vertex) {
                if let Some(i) = u.selected {
                    let moved = u
                        .project
                        .tools
                        .get(i)
                        .map(|t| u.canvas_to_tool_source(t, at));
                    if let (Some(source), Some(point)) = (
                        moved,
                        u.project
                            .tools
                            .get_mut(i)
                            .and_then(|t| t.points.get_mut(vertex)),
                    ) {
                        *point = source;
                        u.update_info();
                        u.scroll_update();
                        unsafe {
                            InvalidateRect(u.canvas, null(), 0);
                        }
                    }
                }
            } else if !u.pending.is_empty() {
                u.preview = Some(Pt::new(
                    (at.x + u.scroll.x).round_ties_even(),
                    (at.y + u.scroll.y).round_ties_even(),
                ));
                u.scroll_update();
                unsafe {
                    InvalidateRect(u.canvas, null(), 0);
                }
            }
            let w = u.project.world(pt);
            unsafe {
                set_text(
                    u.ctl(POSITION),
                    &format!("X: {:.2} m   Y: {:.2} m", w.x, w.y),
                );
            }
        });
    }
    fn on_canvas_up() {
        let canvas = APP.with(|slot| {
            let mut ui = slot.borrow_mut();
            let had_drag = ui.finish_drag();
            ui.pan_start = None;
            if had_drag {
                ui.refresh();
            }
            ui.canvas
        });
        // ReleaseCapture sends WM_CAPTURECHANGED synchronously: no APP borrow
        // may remain alive when the native notification is dispatched.
        unsafe {
            if GetCapture() == canvas {
                ReleaseCapture();
            }
        }
    }
    fn on_scroll(hwnd: H, bar: i32, command: u32) {
        APP.with(|a| {
            let mut u = a.borrow_mut();
            unsafe {
                let mut info = ScrollInfo {
                    size: size_of::<ScrollInfo>() as u32,
                    mask: SIF_ALL,
                    min: 0,
                    max: 0,
                    page: 0,
                    pos: 0,
                    track: 0,
                };
                GetScrollInfo(hwnd, bar, &mut info);
                let old = info.pos;
                let page = i32::try_from(info.page).unwrap_or(i32::MAX);
                let unit = (page / 10).max(1);
                let page_step = (page as i64 * 9 / 10) as i32;
                let new = match command {
                    0 => old.saturating_sub(unit),
                    1 => old.saturating_add(unit),
                    2 => old.saturating_sub(page_step),
                    3 => old.saturating_add(page_step),
                    4 | 5 => info.track,
                    6 => info.min,
                    7 => info.max,
                    _ => old,
                };
                let max = info
                    .max
                    .saturating_sub(page)
                    .saturating_add(1)
                    .max(info.min);
                let new = new.clamp(info.min, max);
                if bar == SB_HORZ {
                    u.scroll.x = new as f64;
                } else {
                    u.scroll.y = new as f64;
                }
                u.scroll_update();
                InvalidateRect(hwnd, null(), 0);
            }
        });
    }

    // --------------------------- WINDOW LAYOUT -------------------------------
    unsafe fn create_controls(u: &mut UI) {
        let hwnd = u.hwnd;
        // Eleven-point text at the application's fixed 96-DPI coordinate scale.
        u.font = create_font("Segoe UI", -15, 400, 0);
        u.mono = create_font("Consolas", -14, 400, 0);
        u.bold = create_font("Segoe UI", -15, 700, 0);
        // Control-point letters remain larger than panel text.
        u.control_font = create_font("Segoe UI", -21, 700, 0);
        let widgets = Controls::new(hwnd, u.font);
        u.text_line_height = font_line_height(hwnd, u.font);
        u.control_line_height = font_line_height(hwnd, u.control_font);
        let row = [
            (NEW, "New", 65),
            (OPEN, "Open", 66),
            (SAVE, "Save", 65),
            (IMPORT, "Import", 76),
            (UNDO, "Undo", 70),
            (REDO, "Redo", 70),
            (SELECT, "Select", 77),
            (PAN, "Pan", 65),
            (ZOOM, "Zoom", 70),
            (SCALE, "Scale", 76),
            (GEO, "Georeference", 128),
        ];
        let mut x = 7;
        for (id, label, width) in row {
            let style = WS_TABSTOP
                | if [SELECT, PAN, ZOOM, SCALE, GEO].contains(&id) {
                    BS_RADIOBUTTON
                } else {
                    0
                };
            let handle = widgets.create("BUTTON", label, style, id, (x, 7, width, 34));
            u.add(id, handle);
            x += width + 4;
            if matches!(id, REDO | GEO) {
                Controls::new(hwnd, 0).create("STATIC", "", 0x0011, 0, (x + 7, 7, 2, 34));
                x += 18;
            }
        }
        widgets.label(0, "Zoom %", (x + 4, 13, 67, 27));
        x += 72;
        let handle = widgets.create("EDIT", "100", WS_BORDER | WS_TABSTOP, ZOOM_EDIT, (x, 10, 54, 30));
        u.add(ZOOM_EDIT, handle);
        let spin = spin_control(
            hwnd,
            handle,
            ZOOM_SPIN,
            (x + 53, 10, 17, 30),
            (10, 500, 10, 100),
        );
        u.add(ZOOM_SPIN, spin);
        x += 75;
        widgets.label(0, "Rotate °", (x + 3, 13, 78, 27));
        x += 80;
        let handle = widgets.create("EDIT", "0", WS_BORDER | WS_TABSTOP, ROT_EDIT, (x, 10, 54, 30));
        u.add(ROT_EDIT, handle);
        let spin = spin_control(
            hwnd,
            handle,
            ROT_SPIN,
            (x + 53, 10, 17, 30),
            (-360, 360, 5, 0),
        );
        u.add(ROT_SPIN, spin);
        x += 75;
        let handle = widgets.button(FIT, "Fit", (x, 7, 55, 34));
        u.add(FIT, handle);

        let label = widgets.label(MODEL_LABEL, "Model", (9, 58, 45, 24));
        u.add(MODEL_LABEL, label);
        let selector = widgets.create("COMBOBOX", "", WS_TABSTOP | WS_VSCROLL | 3, MODEL_SELECT, (56, 53, 141, 200));
        u.add(MODEL_SELECT, selector);
        for model in Model::ALL {
            let text = wide(model.text());
            SendMessageW(selector, CB_ADDSTRING, 0, text.as_ptr() as isize);
        }
        let label = widgets.label(MODEL_RANGE, "", (204, 58, 176, 24));
        u.add(MODEL_RANGE, label);
        Controls::new(hwnd, 0).create("STATIC", "", 0x0011, 0, (CANVAS_LEFT - 14, 48, 2, 36));
        // Drawing modes share the canvas's immutable west edge. Model text
        // changes only inside its own fixed rectangle and never affects layout.
        x = CANVAS_LEFT;
        for (id, label, width) in [
            (CURVE, "Parabola", 100),
            (POLYGON, "Polygon", 95),
            (MEASURE, "Measure", 94),
            (RESULTS, "Results", 91),
            (COLOR, "Color", 80),
            (EXPORT, "Export", 90),
        ] {
            let style = WS_TABSTOP
                | if [CURVE, POLYGON, MEASURE].contains(&id) {
                    BS_RADIOBUTTON
                } else {
                    0
                };
            let handle = widgets.create("BUTTON", label, style, id, (x, 48, width, 36));
            u.add(id, handle);
            x += width + 6;
            if id == MEASURE {
                Controls::new(hwnd, 0).create("STATIC", "", 0x0011, 0, (x + 5, 48, 2, 36));
                x += 22;
            }
        }
        widgets.label(0, "H → E → W", (x + 6, 57, 125, 27));
        u.canvas = CreateWindowExW(
            0,
            wide("BaycraftCanvas").as_ptr(),
            wide("").as_ptr(),
            WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_HSCROLL,
            CANVAS_LEFT,
            93,
            800,
            600,
            hwnd,
            900,
            GetModuleHandleW(null()),
            null_mut(),
        );
        let group = widgets.group(OBJECT_GROUP, "Project objects", (5, 93, 384, 175));
        u.add(OBJECT_GROUP, group);
        let list = widgets.create(
            "SysTreeView32",
            "",
            WS_BORDER | WS_TABSTOP | 0x0020,
            OBJECT_LIST,
            (13, 124, 360, 135),
        );
        u.add(OBJECT_LIST, list);
        SendMessageW(list, TVM_SETINDENT, 0, 0);
        SendMessageW(
            list,
            TVM_SETITEMHEIGHT,
            (font_line_height(hwnd, u.font) + 6) as usize,
            0,
        );
        let group = widgets.group(PROP_TITLE, "Properties", (5, 274, 384, 391));
        u.add(PROP_TITLE, group);
        for (id, label_id, label, text, y) in [
            (STEP_EDIT, STEP_L, "Angle step (°)", "5.0", 306),
            (LIMIT_EDIT, LIMIT_L, "Angle limit (°)", "150.0", 337),
            (WIDTH_EDIT, WIDTH_L, "Line width", "5", 368),
        ] {
            let label_handle = widgets.label(label_id, label, (13, y + 2, 111, 25));
            u.add(label_id, label_handle);
            let edit = widgets.entry(id, text, (134, y, if id == WIDTH_EDIT { 230 } else { 247 }, 29));
            u.add(id, edit);
            if id == WIDTH_EDIT {
                let spin = spin_control(
                    hwnd,
                    edit,
                    WIDTH_SPIN,
                    (364, y, 17, 29),
                    (1, 20, 1, DEFAULT_WIDTH),
                );
                u.add(WIDTH_SPIN, spin);
            }
        }
        for (id, label, x, width) in [
            (APPLY, "Apply", 13, 103),
            (COORDS, "Coordinates", 119, 153),
            (DELETE, "Delete", 276, 105),
        ] {
            let handle = widgets.button(id, label, (x, 396, width, 32));
            u.add(id, handle);
        }
        let group = widgets.group(MEAS_TITLE, "Measurements", (13, 433, 368, 224));
        u.add(MEAS_TITLE, group);
        let handle = widgets.label(MEASUREMENTS, "", (21, 464, 352, 180));
        u.add(MEASUREMENTS, handle);
        let handle = widgets.label(STATUS, "", (7, 780, 870, 25));
        u.add(STATUS, handle);
        let handle = widgets.label(POSITION, "", (880, 780, 450, 25));
        u.add(POSITION, handle);
        let menu = CreateMenu();
        let file = CreatePopupMenu();
        let edit = CreatePopupMenu();
        let view = CreatePopupMenu();
        let help = CreatePopupMenu();
        for (id, label) in [
            (NEW, "New\tCtrl+N"),
            (OPEN, "Open…\tCtrl+O"),
            (IMPORT, "Import Image…\tCtrl+I"),
            (SAVE, "Save\tCtrl+S"),
            (M_SAVEAS, "Save As…\tCtrl+Shift+S"),
        ] {
            menu_item(file, id, label);
        }
        AppendMenuW(file, MF_SEPARATOR, 0, null());
        for (id, label) in [
            (EXPORT, "Export Image…"),
            (M_PRINT, "Print…\tCtrl+P"),
            (M_CLOSE, "Close"),
            (M_QUIT, "Exit"),
        ] {
            if id == M_CLOSE {
                AppendMenuW(file, MF_SEPARATOR, 0, null());
            }
            menu_item(file, id, label);
        }
        for (id, label) in [
            (UNDO, "Undo\tCtrl+Z"),
            (REDO, "Redo\tCtrl+Y"),
            (DELETE, "Delete\tDel"),
            (COLOR, "Edit Color…"),
            (RESULTS, "Numeric Results"),
        ] {
            if id == DELETE {
                AppendMenuW(edit, MF_SEPARATOR, 0, null());
            }
            menu_item(edit, id, label);
        }
        for (id, label) in [
            (M_ZOOMIN, "Zoom in"),
            (M_ZOOMOUT, "Zoom out"),
            (M_ORIGINAL, "Original size"),
            (FIT, "Fit Image"),
            (M_ROTRIGHT, "Rotate +90°"),
            (M_ROTLEFT, "Rotate −90°"),
        ] {
            if id == M_ROTRIGHT {
                AppendMenuW(view, MF_SEPARATOR, 0, null());
            }
            menu_item(view, id, label);
        }
        menu_item(help, M_HELP, "Help");
        menu_item(help, M_ABOUT, "About");
        for (h, label) in [
            (file, "File"),
            (edit, "Edit"),
            (view, "View"),
            (help, "Help"),
        ] {
            AppendMenuW(menu, MF_POPUP, h as usize, wide(label).as_ptr());
        }
        SetMenu(hwnd, menu);
        DrawMenuBar(hwnd);
        layout(u);
        u.refresh();
        let current_status = u.status.clone();
        u.status(current_status);
    }
    fn layout(u: &mut UI) {
        let _guard = InitializationGuard::begin();
        unsafe {
            if u.hwnd == 0 || u.canvas == 0 {
                return;
            }
            let mut rect = Rect::default();
            GetClientRect(u.hwnd, &mut rect);
            let (w, h) = wh(rect);
            // The sidebar and canvas retain fixed horizontal alignment.
            let side_top = 93i32;
            let canvas_x = CANVAS_LEFT;
            let bottom = 32i32;
            u.canvas_w = (w - canvas_x - 8).max(220);
            u.canvas_h = (h - side_top - bottom).max(170);
            MoveWindow(u.canvas, canvas_x, side_top, u.canvas_w, u.canvas_h, 1);

            // A short, fixed-ratio Project objects area keeps the Properties and
            // Measurements visible even on a 768-pixel-high laptop screen.
            let objects_height =
                ((GetSystemMetrics(1) as f64 * 0.22).round_ties_even() as i32).clamp(146, 200);
            let properties_top = side_top + objects_height + 6;
            let sidebar_bottom = h - 35;
            MoveWindow(u.ctl(OBJECT_GROUP), 5, side_top, 384, objects_height, 1);
            MoveWindow(
                u.ctl(OBJECT_LIST),
                13,
                side_top + 31,
                360,
                (objects_height - 40).max(96),
                1,
            );
            MoveWindow(
                u.ctl(PROP_TITLE),
                5,
                properties_top,
                384,
                (sidebar_bottom - properties_top).max(250),
                1,
            );

            // Property rows remain aligned beneath their section heading.
            for (id, x, dy, width, height) in [
                (STEP_L, 13, 34, 111, 25),
                (STEP_EDIT, 134, 32, 247, 29),
                (LIMIT_L, 13, 65, 111, 25),
                (LIMIT_EDIT, 134, 63, 247, 29),
                (WIDTH_L, 13, 96, 111, 25),
                (WIDTH_EDIT, 134, 94, 230, 29),
                (WIDTH_SPIN, 364, 94, 17, 29),
                (APPLY, 13, 122, 103, 34),
                (COORDS, 119, 122, 153, 34),
                (DELETE, 276, 122, 105, 34),
            ] {
                MoveWindow(u.ctl(id), x, properties_top + dy, width, height, 1);
            }
            let measurement_top = properties_top + 159;
            let measurement_height = (sidebar_bottom - measurement_top - 8).max(76);
            MoveWindow(
                u.ctl(MEAS_TITLE),
                13,
                measurement_top,
                368,
                measurement_height,
                1,
            );
            MoveWindow(
                u.ctl(MEASUREMENTS),
                21,
                measurement_top + 31,
                352,
                (measurement_height - 43).max(40),
                1,
            );

            MoveWindow(u.ctl(STATUS), 7, h - 29, (w - 455).max(200), 25, 1);
            MoveWindow(u.ctl(POSITION), (w - 440).max(450), h - 29, 430, 25, 1);
            u.scroll_update();
            InvalidateRect(u.canvas, null(), 1);
        }
    }
    fn command(owner: H, id: usize, notification: usize) {
        match id {
            NEW | M_CLOSE => new_project(owner),
            OPEN => open_project_action(owner),
            SAVE => {
                save_current(owner, false);
            }
            M_SAVEAS => {
                save_current(owner, true);
            }
            IMPORT => import_image_action(owner),
            UNDO => undo_action(owner, false),
            REDO => undo_action(owner, true),
            SELECT => set_mode_action(owner, Mode::Select),
            PAN => set_mode_action(owner, Mode::Pan),
            ZOOM => set_mode_action(owner, Mode::Zoom),
            SCALE => set_mode_action(owner, Mode::Scale),
            GEO => set_mode_action(owner, Mode::Georeference),
            CURVE => set_mode_action(owner, Mode::Curve),
            POLYGON => set_mode_action(owner, Mode::Polygon),
            MEASURE => set_mode_action(owner, Mode::Measure),
            RESULTS => show_results(owner),
            COLOR => color_action(owner),
            EXPORT => export_action(owner),
            FIT => fit_action(),
            APPLY => apply_properties(owner),
            COORDS => edit_coordinates(owner),
            DELETE => delete_selected(),
            M_DELETEVERTEX => delete_vertex(),
            M_PRINT => print_action(owner),
            M_HELP => help_action(owner),
            M_ABOUT => unsafe {
                show_message(owner, "About Baycraft", "Baycraft: interactive bay-planform analysis with selectable coefficient models.\n\nModels: Oliveira2010 (default) and Hsu1989, using sixth-degree coefficient fits in the parabolic shoreline equation.\n\nProjects store the model, geometry, scale, georeference, styles, and an embedded PNG.\n\nRun baycraft.exe [project.bay] to open a project, or use --calculate JSON for calculations without opening a window.", 0);
            },
            M_QUIT => unsafe {
                SendMessageW(owner, WM_CLOSE, 0, 0);
            },
            M_ORIGINAL => APP.with(|a| {
                let mut u = a.borrow_mut();
                u.set_view(Some(100), None);
            }),
            M_ZOOMIN => zoom_action(10),
            M_ZOOMOUT => zoom_action(-10),
            M_ROTRIGHT => APP.with(|a| {
                let mut u = a.borrow_mut();
                let r = u.project.rotation.saturating_add(90);
                u.set_view(None, Some(r));
            }),
            M_ROTLEFT => APP.with(|a| {
                let mut u = a.borrow_mut();
                let r = u.project.rotation.saturating_sub(90);
                u.set_view(None, Some(r));
            }),
            MODEL_SELECT if notification == CBN_SELCHANGE => change_model(),
            _ => {}
        }
    }
    unsafe extern "system" fn canvas_proc(
        hwnd: H,
        msg: u32,
        wparam: usize,
        lparam: isize,
    ) -> isize {
        dispatch_gui_callback(hwnd, msg, wparam, lparam, canvas_proc_impl)
    }

    unsafe fn canvas_proc_impl(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        if during_initialization() {
            if msg == WM_PAINT {
                let mut ps = PaintStruct::default();
                if BeginPaint(hwnd, &mut ps) != 0 {
                    EndPaint(hwnd, &ps);
                }
                return 0;
            }
            return DefWindowProcW(hwnd, msg, wparam, lparam);
        }
        match msg {
            WM_SETCURSOR if (lparam as usize & 0xffff) == 1 => {
                let cursor = APP.with(|slot| match slot.borrow().mode {
                    Mode::Select => IDC_ARROW,
                    Mode::Pan => IDC_SIZEALL,
                    _ => IDC_CROSS,
                });
                SetCursor(LoadCursorW(0, cursor as *const u16));
                1
            }
            WM_PAINT => {
                paint_canvas(hwnd);
                0
            }
            WM_ERASEBKGND => 1,
            WM_LBUTTONDOWN => {
                SetFocus(hwnd);
                let owner = APP.with(|a| a.borrow().hwnd);
                on_canvas_down(owner, pos(lparam), wparam);
                0
            }
            WM_LBUTTONDBLCLK => {
                let mode = APP.with(|a| a.borrow().mode);
                match mode {
                    Mode::Polygon => finish_polygon(),
                    Mode::Select => {
                        insert_polygon_vertex(pos(lparam));
                    }
                    _ => {
                        let owner = APP.with(|a| a.borrow().hwnd);
                        on_canvas_down(owner, pos(lparam), wparam);
                    }
                }
                0
            }
            WM_MOUSEMOVE => {
                on_canvas_move(pos(lparam));
                0
            }
            WM_MBUTTONDOWN => {
                SetFocus(hwnd);
                start_middle_pan(pos(lparam));
                0
            }
            WM_MBUTTONUP | WM_LBUTTONUP | WM_CANCELMODE | WM_CAPTURECHANGED => {
                on_canvas_up();
                0
            }
            WM_RBUTTONUP => {
                let at = pos(lparam);
                let owner = APP.with(|slot| {
                    let mut ui = slot.borrow_mut();
                    ui.context_point = Some(Pt::new(
                        (at.x + ui.scroll.x).round_ties_even(),
                        (at.y + ui.scroll.y).round_ties_even(),
                    ));
                    if let Some(index) = hit_test(&ui, at) {
                        ui.select(Some(index));
                        ui.refresh();
                    }
                    ui.hwnd
                });
                let menu = CreatePopupMenu();
                if menu == 0 {
                    return 0;
                }
                menu_item(menu, RESULTS, "Numeric Results");
                menu_item(menu, COLOR, "Edit Color…");
                menu_item(menu, M_DELETEVERTEX, "Delete Vertex");
                AppendMenuW(menu, MF_SEPARATOR, 0, null());
                menu_item(menu, DELETE, "Delete Object");
                let mut location = point(at);
                ClientToScreen(hwnd, &mut location);
                let choice =
                    TrackPopupMenu(menu, 0x100 | 0x2, location.x, location.y, 0, owner, null());
                DestroyMenu(menu);
                if choice != 0 {
                    command(owner, choice as usize, 0);
                }
                0
            }
            WM_MOUSEWHEEL => {
                wheel_action(hwnd, wparam);
                0
            }
            WM_HSCROLL => {
                on_scroll(hwnd, SB_HORZ, (wparam & 0xffff) as u32);
                0
            }
            WM_VSCROLL => {
                on_scroll(hwnd, SB_VERT, (wparam & 0xffff) as u32);
                0
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
    unsafe extern "system" fn main_proc(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        dispatch_gui_callback(hwnd, msg, wparam, lparam, main_proc_impl)
    }

    unsafe fn main_proc_impl(hwnd: H, msg: u32, wparam: usize, lparam: isize) -> isize {
        match msg {
            // WM_CREATE must return promptly. Child controls are constructed
            // after CreateWindowExW returns to the top-level run() function.
            // Constructing them here causes nested WM_SIZE/WM_PAINT reentrancy
            // while APP is mutably borrowed, terminating a Windows GUI process.
            WM_CREATE => {
                APP.with(|a| a.borrow_mut().hwnd = hwnd);
                0
            }
            WM_SIZE => {
                if !during_initialization() {
                    APP.with(|a| layout(&mut a.borrow_mut()));
                }
                0
            }
            WM_MOUSEWHEEL => {
                if !during_initialization() {
                    let canvas = APP.with(|slot| slot.borrow().canvas);
                    if canvas != 0 {
                        wheel_action(canvas, wparam);
                    }
                }
                0
            }
            WM_COMMAND => {
                if !during_initialization() {
                    let id = wparam & 0xffff;
                    let notify = (wparam >> 16) & 0xffff;
                    command(hwnd, id, notify);
                }
                0
            }
            WM_NOTIFY if lparam != 0 && !during_initialization() => {
                let header = &*(lparam as *const NotifyHeader);
                match header.control_id {
                    OBJECT_LIST
                        if [(-402_i32) as u32, (-451_i32) as u32].contains(&header.code) =>
                    {
                        APP.with(|slot| {
                            let mut ui = slot.borrow_mut();
                            let selected =
                                SendMessageW(ui.ctl(OBJECT_LIST), TVM_GETNEXTITEM, TVGN_CARET, 0);
                            let index = ui.object_items.iter().position(|item| item.handle == selected);
                            ui.select(index);
                        });
                        0
                    }
                    OBJECT_LIST if header.code == (-3_i32) as u32 => {
                        show_results(hwnd);
                        0
                    }
                    ZOOM_SPIN | ROT_SPIN | WIDTH_SPIN if header.code == UDN_DELTAPOS => {
                        let delta = &*(lparam as *const SpinDelta);
                        adjust_spin_input(header.control_id, delta.delta);
                        1
                    }
                    _ => DefWindowProcW(hwnd, msg, wparam, lparam),
                }
            }
            WM_GETMINMAXINFO => {
                if lparam != 0 {
                    let rect = &mut *(lparam as *mut MinMaxInfo);
                    let mut screen = Rect::default();
                    if SystemParametersInfoW(0x30, 0, &mut screen as *mut _ as *mut c_void, 0) == 0
                    {
                        screen = Rect {
                            left: 0,
                            top: 0,
                            right: GetSystemMetrics(0),
                            bottom: GetSystemMetrics(1).saturating_sub(45),
                        };
                    }
                    let (w, h) = wh(screen);
                    if w > 0 && h > 0 {
                        rect.max_position = Point {
                            x: screen.left,
                            y: screen.top,
                        };
                        rect.max_size = Point { x: w, y: h };
                        rect.max_track = Point { x: w, y: h };
                    }
                }
                0
            }
            WM_CLOSE => {
                if confirm_save(hwnd) {
                    DestroyWindow(hwnd);
                }
                0
            }
            WM_DESTROY => {
                PostQuitMessage(0);
                0
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
    unsafe fn register(
        name: &str,
        proc: unsafe extern "system" fn(H, u32, usize, isize) -> isize,
    ) -> ResultT<()> {
        let name_w = wide(name);
        let cls = WndClassEx {
            size: size_of::<WndClassEx>() as u32,
            style: 8,
            proc: Some(proc),
            cls_extra: 0,
            wnd_extra: 0,
            instance: GetModuleHandleW(null()),
            icon: 0,
            cursor: LoadCursorW(0, IDC_ARROW as *const u16),
            background: COLOR_WINDOW + 1,
            menu_name: null(),
            class_name: name_w.as_ptr(),
            icon_small: 0,
        };
        if RegisterClassExW(&cls) == 0 {
            return Err(format!(
                "RegisterClassExW({name}) failed (Win32 error {})",
                GetLastError()
            ));
        }
        Ok(())
    }
    fn dispatch_shortcut(owner: H, message: &Msg) -> bool {
        if gui_failed() || message.message != WM_KEYDOWN {
            return false;
        }
        let result_windows =
            RESULT_WINDOWS.with(|windows| windows.borrow().keys().copied().collect::<Vec<_>>());
        if let Some(window) = result_windows
            .into_iter()
            .find(|&window| window_belongs_to(message.hwnd, window))
        {
            if message.wparam == 0x1b {
                unsafe {
                    DestroyWindow(window);
                }
                return true;
            }
            if message.wparam == 0x09 {
                return dialog_navigation(window, message);
            }
            return false;
        }
        if !window_belongs_to(message.hwnd, owner) {
            return false;
        }
        let control = unsafe { GetKeyState(0x11) < 0 };
        if control {
            let id = match message.wparam {
                0x4e => NEW,
                0x4f => OPEN,
                0x49 => IMPORT,
                0x53 => {
                    if unsafe { GetKeyState(0x10) < 0 } {
                        M_SAVEAS
                    } else {
                        SAVE
                    }
                }
                0x5a => UNDO,
                0x59 => REDO,
                0x50 => M_PRINT,
                _ => return false,
            };
            command(owner, id, 0);
            return true;
        }
        let focus = unsafe { GetFocus() };
        match message.wparam {
            0x09 => return dialog_navigation(owner, message),
            0x1b => {
                cancel_action();
                return true;
            }
            0x2e => {
                let editing = APP.with(|slot| {
                    let ui = slot.borrow();
                    [
                        ZOOM_EDIT,
                        ROT_EDIT,
                        STEP_EDIT,
                        LIMIT_EDIT,
                        WIDTH_EDIT,
                        MODEL_SELECT,
                    ]
                    .iter()
                    .any(|&id| window_belongs_to(focus, ui.ctl(id)))
                });
                if !editing {
                    delete_selected();
                    return true;
                }
            }
            0x0d => {
                let (view, polygon) = APP.with(|slot| {
                    let ui = slot.borrow();
                    (
                        [ZOOM_EDIT, ROT_EDIT].iter().any(|&id| ui.ctl(id) == focus),
                        ui.mode == Mode::Polygon && focus == ui.canvas,
                    )
                });
                if view {
                    apply_view();
                    return true;
                }
                if polygon {
                    finish_polygon();
                    return true;
                }
            }
            _ => {}
        }
        false
    }

    fn dialog_navigation(window: H, message: &Msg) -> bool {
        let mut local = Msg {
            hwnd: message.hwnd,
            message: message.message,
            wparam: message.wparam,
            lparam: message.lparam,
            time: message.time,
            pt: message.pt,
            lprivate: message.lprivate,
        };
        unsafe { IsDialogMessageW(window, &mut local) != 0 }
    }

    fn cleanup_results() {
        let windows = RESULT_WINDOWS.with(|state| std::mem::take(&mut *state.borrow_mut()));
        for (window, _) in windows {
            unsafe {
                if IsWindow(window) != 0 {
                    DestroyWindow(window);
                }
            }
        }
    }
    fn show_startup_error(phase: &str, message: &str) {
        let details = format!("Baycraft startup failure ({phase}): {message}\n");
        // The normal executable runs in the Windows GUI subsystem. Without a
        // dialog and log, startup errors look like a double-click doing nothing.
        let log_path = std::env::temp_dir().join("baycraft_startup.log");
        let _ = std::fs::write(&log_path, &details);
        let _ = std::io::Write::write_all(
            &mut std::io::stderr().lock(),
            format!("{details}Log: {}\n", log_path.display()).as_bytes(),
        );
        unsafe {
            MessageBoxW(
                0,
                wide(&format!(
                    "{details}\nDiagnostic log: {}",
                    log_path.display()
                ))
                .as_ptr(),
                wide("Baycraft - Startup Error").as_ptr(),
                MB_ICONERROR,
            );
        }
    }

    fn install_panic_diagnostics() {
        std::panic::set_hook(Box::new(|info| {
            let details = format!("Baycraft runtime panic: {info}\n");
            let path = std::env::temp_dir().join("baycraft_startup.log");
            let _ = std::fs::write(&path, &details);
            let diagnostic = format!("{details}Diagnostic log: {}\n", path.display());
            let _ = std::io::Write::write_all(&mut std::io::stderr().lock(), diagnostic.as_bytes());
            // A panic hook runs before borrowed application state unwinds.
            // Showing a native dialog here would dispatch nested callbacks
            // while those borrows are still held. The event loop reports the
            // captured failure only after it has stopped and cleaned up.
        }));
    }

    struct GdiSession(usize);
    impl GdiSession {
        fn start() -> ResultT<Self> {
            unsafe {
                let mut token = 0;
                let input = GdipStartupInput {
                    version: 1,
                    debug: null(),
                    suppress_background: 0,
                    suppress_codecs: 0,
                };
                gdip_ok(GdiplusStartup(&mut token, &input, null_mut()))?;
                Ok(Self(token))
            }
        }
    }
    impl Drop for GdiSession {
        fn drop(&mut self) {
            unsafe {
                GdiplusShutdown(self.0);
            }
        }
    }
    struct GuiSession;
    impl Drop for GuiSession {
        fn drop(&mut self) {
            // Windows must release child controls before their fonts, while GDI+
            // must outlive every image. This also runs after a caught callback panic.
            cleanup_results();
            let window = APP.with(|app| app.borrow().hwnd);
            if window != 0 && unsafe { IsWindow(window) } != 0 {
                unsafe {
                    DestroyWindow(window);
                }
            }
            APP.with(|app| *app.borrow_mut() = UI::default());
        }
    }
    fn run_application(project_path: Option<&str>) -> ResultT<u8> {
        unsafe {
            let _gdi = GdiSession::start()?;
            let _gui = GuiSession;
            let controls = InitCommonControls {
                size: size_of::<InitCommonControls>() as u32,
                classes: 0x0001 | 0x0002 | 0x0010, // List views, tree views and up-down controls.
            };
            if InitCommonControlsEx(&controls) == 0 {
                return Err(win32_error("Initialize common controls"));
            }
            for (name, procedure) in [
                (
                    "BaycraftMain",
                    main_proc as unsafe extern "system" fn(H, u32, usize, isize) -> isize,
                ),
                (
                    "BaycraftCanvas",
                    canvas_proc as unsafe extern "system" fn(H, u32, usize, isize) -> isize,
                ),
                (
                    "BaycraftForm",
                    form_proc as unsafe extern "system" fn(H, u32, usize, isize) -> isize,
                ),
                (
                    "BaycraftResults",
                    results_proc as unsafe extern "system" fn(H, u32, usize, isize) -> isize,
                ),
            ] {
                register(name, procedure)?;
            }
            let mut area = Rect::default();
            if SystemParametersInfoW(0x30, 0, &mut area as *mut _ as *mut c_void, 0) == 0 {
                area = Rect {
                    left: 0,
                    top: 0,
                    right: GetSystemMetrics(0),
                    bottom: GetSystemMetrics(1).saturating_sub(45),
                };
            }
            let (width, height) = wh(area);
            if width <= 0 || height <= 0 {
                return Err("Windows returned an invalid desktop work area.".into());
            }
            let window = CreateWindowExW(
                0,
                wide("BaycraftMain").as_ptr(),
                wide("Baycraft").as_ptr(),
                WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN,
                area.left,
                area.top,
                width,
                height,
                0,
                0,
                GetModuleHandleW(null()),
                null_mut(),
            );
            if window == 0 {
                return Err(win32_error("Create main window"));
            }
            if gui_failed() {
                return Err("Main window initialization failed.".into());
            }
            let initialized = {
                // Control creation, menus and MoveWindow may synchronously dispatch
                // callbacks. Suppress their state access until this borrow ends.
                let _guard = InitializationGuard::begin();
                APP.with(|app| {
                    let mut ui = app.borrow_mut();
                    create_controls(&mut ui);
                    ui.canvas != 0
                        && !ui.controls.is_empty()
                        && ui.controls.values().all(|&control| control != 0)
                        && [ui.font, ui.mono, ui.bold, ui.control_font]
                            .iter()
                            .all(|font| *font != 0)
                })
            };
            if !initialized || gui_failed() {
                return Err(
                    "One or more essential interface controls failed to initialize.".into(),
                );
            }
            // Build the entire fixed layout before the first visible frame.
            APP.with(|app| {
                let mut ui = app.borrow_mut();
                layout(&mut ui);
                InvalidateRect(ui.canvas, null(), 1);
            });
            ShowWindow(window, 1);
            UpdateWindow(window);
            if let Some(path) = project_path {
                load_named(window, Path::new(path));
            }
            let mut message = Msg::default();
            while !gui_failed() {
                let status = GetMessageW(&mut message, 0, 0, 0);
                if status == 0 {
                    return Ok(u8::try_from(message.wparam).unwrap_or(1));
                }
                if status < 0 {
                    return Err(win32_error("Read Windows message queue"));
                }
                let handled = guarded_gui_call(false, || dispatch_shortcut(window, &message));
                if gui_failed() {
                    break;
                }
                if handled {
                    continue;
                }
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
            Ok(1)
        }
    }
    pub fn run(project_path: Option<&str>) -> u8 {
        install_panic_diagnostics();
        let mut outcome = Err("The graphical application stopped during startup.".into());
        guarded_gui_call((), || {
            outcome = run_application(project_path);
        });
        if let Some(problem) = take_gui_failure() {
            show_startup_error("runtime", &problem);
            return 1;
        }
        match outcome {
            Ok(status) => status,
            Err(problem) => {
                show_startup_error("application", &problem);
                1
            }
        }
    }
}

// ============================================================================
// NATIVE ENTRY POINT / HEADLESS CALCULATION INTERFACE
// ============================================================================
enum CommandLine {
    Run {
        filename: Option<String>,
        calculation: Option<String>,
        model: Option<Model>,
    },
    Help,
}

fn command_option(argument: &str) -> ResultT<Option<&'static str>> {
    let name = argument.split_once('=').map_or(argument, |(name, _)| name);
    if name.starts_with("--") {
        let mut matches = ["--calculate", "--model", "--help"]
            .into_iter()
            .filter(|option| option.starts_with(name));
        let option = matches.next();
        if matches.next().is_none() {
            Ok(option)
        } else {
            Err(format!("Ambiguous option: {argument}"))
        }
    } else if name.starts_with("-h") {
        Ok(Some("--help"))
    } else {
        Ok(None)
    }
}

fn is_command_option(argument: &str) -> bool {
    if argument == "--" || !matches!(command_option(argument), Ok(None)) {
        return true;
    }
    let negative_number = argument.strip_prefix('-').is_some_and(|number| {
        let digits = |text: &str| !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit());
        number.split_once('.').map_or_else(
            || digits(number),
            |(integer, fraction)| (integer.is_empty() || digits(integer)) && digits(fraction),
        )
    });
    argument.starts_with('-') && argument.len() > 1 && !negative_number && !argument.contains(' ')
}

fn parse_command_line(arguments: impl IntoIterator<Item = String>) -> ResultT<CommandLine> {
    let mut arguments = arguments.into_iter().peekable();
    let mut filename = None;
    let mut calculation = None;
    let mut model = None;
    let mut options = true;
    let mut option_after_filename = false;
    let mut unknown = Vec::new();
    while let Some(argument) = arguments.next() {
        if options && argument == "--" {
            if option_after_filename {
                unknown.push(argument);
            }
            options = false;
            continue;
        }
        if !options || !is_command_option(&argument) {
            if filename.is_none() {
                filename = Some(argument);
            } else {
                unknown.push(argument);
            }
            continue;
        }
        option_after_filename |= filename.is_some();
        let Some(option) = command_option(&argument)? else {
            unknown.push(argument);
            continue;
        };
        let (name, explicit) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        if option == "--help" {
            if (explicit.is_some() && (name == "-h" || name.starts_with("--")))
                || argument.starts_with("-h-")
            {
                return Err("The help option does not accept an argument.".into());
            }
            return Ok(CommandLine::Help);
        }
        let value = match explicit {
            Some(value) => value.to_owned(),
            None => {
                if arguments.peek().is_none_or(|next| is_command_option(next)) {
                    return Err(format!("{option} requires one argument."));
                }
                arguments
                    .next()
                    .ok_or_else(|| format!("{option} requires one argument."))?
            }
        };
        match option {
            "--calculate" => calculation = Some(value),
            "--model" => {
                model = Some(Model::parse(&value).map_err(|_| {
                    format!(
                        "--model must be {}.",
                        Model::ALL.map(Model::text).join(" or ")
                    )
                })?);
            }
            _ => return Err(format!("Unknown argument: {argument}")),
        }
    }
    if !unknown.is_empty() {
        return Err(format!("Unknown arguments: {}", unknown.join(" ")));
    }
    Ok(CommandLine::Run {
        filename,
        calculation,
        model,
    })
}

fn main() -> std::process::ExitCode {
    use std::process::ExitCode;
    let (filename, calculation, model) = match parse_command_line(std::env::args().skip(1)) {
        Ok(CommandLine::Run {
            filename,
            calculation,
            model,
        }) => (filename, calculation, model),
        Ok(CommandLine::Help) => {
            println!("Baycraft — Oliveira2010 and Hsu1989 bay-planform models\n\nUsage:\n  baycraft [project.bay]\n  baycraft --calculate JSON [--model Oliveira2010|Hsu1989]\n\nDefault model: Oliveira2010. --model overrides the model in JSON.\nFor georeferenced XY, also supply pixel_size (m/pixel), reference_pixel\nand reference_xy together.\n\nExample:\n  baycraft --calculate '{{\"h\":[100,100],\"e\":[200,100],\"w\":[150,186.602540378],\"increment\":5,\"limit\":150}}'");
            return ExitCode::SUCCESS;
        }
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    if let Some(src) = calculation {
        match calculate_arg(&src, model) {
            Ok(text) => println!("{text}"),
            Err(e) => {
                eprintln!("Baycraft calculation: {e}");
                return ExitCode::from(2);
            }
        }
        return ExitCode::SUCCESS;
    }
    #[cfg(all(windows, not(feature = "headless")))]
    {
        ExitCode::from(windows_gui::run(filename.as_deref()))
    }
    #[cfg(any(not(windows), feature = "headless"))]
    {
        if let Some(path) = filename {
            match load_project(Path::new(&path)) {
                Ok(p) => print!("{}", report(&p, None)),
                Err(e) => {
                    eprintln!("Cannot open project: {e}");
                    return ExitCode::from(2);
                }
            }
        } else {
            eprintln!("Use --calculate JSON [--model MODEL] for the headless engine. The full GUI is supported on Windows only.");
        }
        ExitCode::SUCCESS
    }
}
