HSU (1989) FIGURE 4 — DIGITIZED MODEL POINTS AND PRINTED CURVES
=================================================================

This package preserves all records from the accepted Figure 4 extraction and
includes the user-specified additions from 6 November 2026.

CONTENTS
--------
241 total records, of which 233 have numeric data:
  127 model experimental-symbol readings (accepted source-figure assignments);
   45 prototype symbol readings (original figure does not identify their theta);
   11 defined origins (beta=0, R/R0=0), one for each model theta;
   50 requested fitted-curve readings at beta=5,10,15,75,80 degrees
      (42 numeric, 5 outside the plotted range, 3 unreadable merged ink);
    8 additional non-origin points explicitly supplied by the user.

NEW USER-SUPPLIED COORDINATES
-----------------------------
theta = 30 degrees (new model series, no source-figure experimental symbol):
    beta_deg      r_ratio
        0.00        0.000  (defined origin)
        7.25        0.250
       11.00        0.400
       15.00        0.525
       18.00        0.650

Additional model points (all at beta=70 degrees):
    theta=180: R/R0=0.310
    theta=210: R/R0=0.225
    theta=240: R/R0=0.170
    theta=270: R/R0=0.160

New values appear with point_type=user_supplied in Models, in the separate
User_added worksheet, in the CSV/JSON exports and on the plot as filled
coloured diamond markers. Defined origins appear as unfilled stars.
New data are not misrepresented as points digitized from printed symbols.

PREVIOUS DATA
-------------
The original 232 points are retained unchanged, with their IDs, coordinates,
statuses and notes. In particular, M150-12, M210-03 and M210-04 retain
status=user_confirmed. The earlier user acceptance of all flagged symbol
mappings is preserved.

The 50 requested fitted-curve records remain at beta=5,10,15,75,80 for the
original ten theta models. There are no inferred samples at those beta values
for the new theta=30 series: the five theta=30 points are precisely the
coordinates supplied by the user.

UNAVAILABLE CURVE REQUESTS
--------------------------
Outside the figure (R/R0 > 1): theta 45 at beta 75/80; theta 60 at beta
75/80; theta 75 at beta 80. Unresolved in merged origin-area strokes:
theta 210/240/270 at beta 5. These retain blank ratios and are not plotted.
No values have been extrapolated or invented.

FILES
-----
hsu1989_digitized.xls          Genuine Excel 97–2003 workbook.
hsu1989_digitized.xlsx         Modern Excel workbook, same numeric data.
plot_hsu1989.py                Portable plotting script with original JPEG,
                               calibration and dataset embedded.
hsu1989_overlay.png            Combined original-figure verification plot.
hsu1989_user_additions.png     User additions and all 11 origins only.
hsu1989_curve_samples.png      Origins and fitted-curve samples.
hsu1989_theta_*.png            11 individual model overlays, including θ=30.
hsu1989_points.csv             All 241 records, including unavailable requests.
hsu1989_curve_samples.csv      11 origins + 50 requested fitted-curve samples.
hsu1989_user_additions.csv     Nine new user-supplied values, including origin.
hsu1989_digitized.json         Canonical records, grid calibration, provenance.
hsu1989_figure4.jpg           Original unchanged image (731x566 pixels).
source/                       Reproducible scripts and retained audits.

WORKBOOK
--------
Models:          all 196 model records, sorted by theta/beta.
Prototypes:      45 distinct prototype symbols, theta undefined.
User_added:      nine new values, labelled by origin / user_supplied.
Curve_samples:   linked summary of the previous printed-curve requests.
Calibration:     per-theta counts and the fitted grid-line calibration.

PLOTTING
--------
Install Python packages:
    python -m pip install matplotlib numpy Pillow xlrd

From the unzipped package:
    python plot_hsu1989.py --workbook hsu1989_digitized.xlsx --no-show --per-series

For legacy XLS input (needs xlrd):
    python plot_hsu1989.py --workbook hsu1989_digitized.xls --no-show --per-series

Interactive display:
    python plot_hsu1989.py

Useful filters:
    python plot_hsu1989.py --theta 30,180,210,240,270 --no-show
    python plot_hsu1989.py --point-types user_supplied,origin --no-show
    python plot_hsu1989.py --labels --no-show

The script positions points from beta_deg and r_ratio, not from pixel columns;
stored pixel coordinates provide a round-trip calibration verification. The
source image is not warped. The overlay is a visual audit, not proof that
uncertain source symbols were identified with experimental-level accuracy.

REBUILDING
----------
See source/README.txt and the provided Python builders. The new series is
assembled by source/add_user_points.py from the retained 232-record JSON.
The Excel workbooks are generated from the same canonical dataset; the
portable plotting script embeds that same JSON and original figure.
