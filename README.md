# Baycraft: headland-bay beach planform analysis

## Abstract

Baycraft calculator constructs and measures equilibrium-planform overlays on coastal imagery using the parabolic bay-shape framework of Hsu and Evans (1989). Two coefficient parameterizations are available: **Oliveira2010, the default**, and **Hsu1989**. The former represents the coefficient observations associated with the Portuguese applications of Oliveira and Barreiro (2010); the latter represents the original coefficient table of Hsu and Evans (1989). Both use three independent sixth-degree numerical regressions within the same quadratic relationship between normalized shoreline radius and angular ratio. The sixth-degree functions are software representations of coefficient data, rather than additional physical equations published by either paper. This document presents their provenance, complete polynomial parameters, fitting diagnostics, geometric construction, field interpretation, and reproducible software use.

A deterministic comparison calculated here, with methods in Section 8, covers the common reference-angle range $22.19^{\circ}\leq\beta\leq80^{\circ}$. It gives a root-mean-square radial difference of $0.00519081R_b$ on a grid extending to $\theta=270^{\circ}$. Approximately 93.98% of retained grid points differ by no more than $0.01R_b$. The largest separation found by the specified extrema check is $0.04659859R_b$ at $\beta=\theta=80^{\circ}$, where neither coefficient set satisfies exact endpoint closure. These are differences between numerical parameterizations, not errors against surveyed shorelines.

The Portuguese examples demonstrate that dynamically exchanging beaches can closely resemble a static-equilibrium planform during particular seasonal conditions. Geometric agreement therefore requires interpretation alongside sediment budgets, representative wave conditions, coastal controls, and the shoreline observation itself. Oliveira and Barreiro (2010); Hsu and Evans (1989).

**Keywords:** headland-bay beach; static equilibrium; dynamic equilibrium; parabolic bay-shape equation; coastal imagery; coefficient regression; shoreline geometry; sediment budget.

## 1. Scope, evidence, and notation

### 1.1 Scientific and computational scope

Baycraft is an image-based geometric analysis program. It places a candidate static-equilibrium shoreline relative to a diffraction point, a downcoast control point, and a representative wave-crest alignment. It also measures distances and polygon areas, retains the analytical geometry in a project file, and exports numerical and visual results. The scientific interpretation follows the empirical bay-shape literature, including the distinction between a limiting static planform and a beach maintained by continuing sediment exchange. Hsu and Evans (1989); Oliveira and Barreiro (2010).

Three levels of evidence are distinguished throughout this document. **Published theory and field observations** come from the cited literature. **Coefficient regressions and inter-model statistics** are numerical calculations on the stated tabular data and implemented arrays. **Interface, file-format, and command-line behavior** describe the accompanying baycraft.py and baycraft.rs source files. A coefficient-fit statistic is not a field-validation statistic, and a software default is not a finding of scientific superiority. This distinction follows directly from the different purposes of the coefficient tables and field applications in Hsu and Evans (1989) and Oliveira and Barreiro (2010).

The implemented models are listed in their interface order:

| Property | Oliveira2010 | Hsu1989 |
|---|---|---|
| Selection | Default | Alternative |
| Coefficient observations | 48 rows | 15 rows |
| Accepted $\beta$ range | 22.19°–88.29° | 10°–80° |
| Coefficient degree | Six | Six |
| Regression weighting | Equal per row | Equal per row |
| Exact endpoint constraint | None | None |

The model is a **project-wide selection**. Selecting it recalculates all planform curves in the project. A curve whose reference angle falls outside the selected coefficient range retains its editable controls but has no valid result for that selection. The ranges identify the supported coefficient data, rather than independently established physical validity limits for every beach. Hsu and Evans (1989); Oliveira and Barreiro (2010).

### 1.2 Symbols and units

The same coefficient notation, $C_0,C_1,C_2$, appears in the original equations of both principal papers and in the software. A comparison report may label these terms $C_1,C_2,C_3$; that display convention maps respectively to the constant, linear-ratio, and quadratic-ratio terms below. It does not introduce a cubic term. Hsu and Evans (1989, Eq. 1); Oliveira and Barreiro (2010, Eq. 2).

| Symbol | Meaning |
|---|---|
| $H$ | Upcoast diffraction/control point |
| $E$ | Downcoast reference/control point |
| $W$ | Point defining the directed crest line from $E$ |
| $R_b$ | Nominal control radius, distance from $H$ to $E$ |
| $R_0$ | Published reference radius, equal to $R_b$ |
| $\beta$ | Reference-line obliquity, in degrees |
| $\theta$ | Shoreline-ray angle, in degrees |
| $q$ | Angular ratio $\beta/\theta$ |
| $r$ | Normalized radius $R/R_b$ |
| $C_i$ | Dimensionless coefficient, $i=0,1,2$ |
| $a_{i,k}$ | Coefficient of $\beta^k$ in the fit for $C_i$ |
| $p$ | Calibrated metres per source-image pixel |

The reference radius is also sometimes written $R_\beta$ because its ideal geometrical direction is $\theta=\beta$. This notation identifies the control-line length; it does not force an unconstrained fitted polynomial to pass exactly through $E$. The source-image coordinate system has $x$ increasing rightward and $y$ increasing downward. Mathematical angles used in trigonometric library calls are converted to radians, while the coefficient functions take the numerical value of $\beta$ in **degrees**. Hsu and Evans (1989); direct application of their dimensionless construction.

## 2. Physical theory of headland-bay beaches

### 2.1 Coastal controls and sediment cells

A headland-bay beach is a sedimentary shoreline whose planform is influenced by rocky promontories, islands, reefs, or engineered structures. The sheltered upcoast portion is usually strongly curved, while the more exposed downcoast reach tends toward a straighter alignment. The distance that the controls project into the active coastal zone, their spacing, and the predominant incident-wave direction influence the available equilibrium shape. The effective diffraction point can lie on a natural headland, an offshore island, a breaking reef, or a coastal structure; selecting it is a physical interpretation of the site. Hsu and Evans (1989); Oliveira and Barreiro (2010).

The visible bay is not automatically a closed sediment cell. Sand can enter from rivers, eroding cliffs, neighboring beaches, or nourishment and can leave through bypassing, dredging, offshore losses, or transport around a control. If the active transport zone extends seaward of a headland or jetty, sediment exchange can continue despite the apparent enclosure of the waterline. The Portuguese examples explicitly associate such bypassing with dynamic equilibrium. Oliveira and Barreiro (2010); Hsu, Uda, and Silvester (1993).

A schematic one-line balance illustrates why shoreline geometry alone cannot determine sediment-system behavior. Let $s$ be alongshore distance, $n$ the seaward-positive shoreline displacement, $D$ a fixed effective active-profile height, $Q_s$ the alongshore bulk-sediment-volume flux, and $q_{\mathrm{ext}}$ the compatible bulk-volume supply per unit shoreline length. For one translating active profile and this stated sign convention, volume conservation takes the form below. It is a simplified background balance consistent with the transport-gradient reasoning of Hurst et al. (2015), rather than a verbatim equation from that paper or an equation integrated by Baycraft.

$$ D\frac{\partial n}{\partial t}=-\frac{\partial Q_s}{\partial s}+q_{\mathrm{ext}} $$

A spatially constant, nonzero transport flux can leave the shoreline stationary if the external terms balance. Conversely, a transport gradient can produce erosion or accretion without an immediate change in the large-scale diffraction geometry. A static planform overlay therefore cannot substitute for measurements or modeling of sediment sources, sinks, bypassing, and profile exchange. Hsu and Evans (1989); Oliveira and Barreiro (2010); Hurst et al. (2015).

### 2.2 Refraction, diffraction, and representative waves

Wave diffraction around the upcoast control redistributes the wave field into the sheltered bay. Refraction over the nearshore bathymetry changes the crest orientation as waves approach the shoreline. In the static-equilibrium interpretation, the dominant waves break approximately normally to the local shoreline, reducing the alongshore component of wave forcing and the associated net littoral transport. Hsu and Evans (1989) motivate the resulting geometry by approximately equal travel times and nearly simultaneous breaking around the bay. This is the physical rationale for an empirical shape relationship, rather than a numerical solution of the wave equations. Hsu and Evans (1989, pp. 559–563).

The relevant angular reference is the **wave-crest alignment**. The wave propagation direction, or orthogonal, is perpendicular to that alignment. In the ideal downcoast geometry, the crest is approximately parallel to the straight beach tangent. A bearing for waves coming *from* offshore, a bearing for their direction of travel, and the orientation of a crest differ by sign or by a right angle. Interchanging them changes the inferred reference angle and can place a curve outside the supported coefficient range. Hsu and Evans (1989); Oliveira and Barreiro (2010).

A single representative crest direction compresses a distribution of wave heights, periods, and directions into one geometric assumption. The annual or seasonal mean direction need not reproduce a shoreline responding to a broad or bimodal directional climate. Directional spreading, wave energy, bay size, and response time require additional analysis when they influence the question being asked. Hurst et al. (2015); El-Shinnawy, Medina, and González (2017).

### 2.3 Static, dynamic, and evolving states

**Static equilibrium** is the limiting conceptual state with negligible net alongshore transport and no sustained sediment exchange through the cell boundaries under the assumed predominant conditions. **Dynamic equilibrium** can retain an approximately stationary planform while sediment passes through the system, provided input and output remain balanced. An **evolving state** has a sediment imbalance that changes the shoreline through erosion or accretion. These categories concern processes and budgets as well as shape. Hsu and Evans (1989); Oliveira and Barreiro (2010).

If the static-equilibrium curve lies landward of a beach whose position is maintained by continuing supply, it can indicate additional indentation that may become possible after that supply is reduced. Dredged channels, river regulation, dams, and coastal structures can alter the supply. The geometric curve supplies neither an erosion rate nor the time needed to reach the limiting shape, and it does not establish that the supply reduction will occur. Hsu and Evans (1989, pp. 557–558, 561).

Storms can transfer sediment from the berm and dunes to offshore bars, followed by partial recovery under lower-energy waves. A shoreline close to a static planform can still experience substantial cross-shore storm erosion. The static-equilibrium curve is consequently not a maximum storm-erosion line or a complete basis for a setback. The required storm allowance, profile response, and sediment volume lie outside the planform equation. Hsu and Evans (1989, pp. 557–558, 568–569).

### 2.4 Engineering applications and their physical limits

Hsu and Evans (1989) use the static-bay concept to examine how natural or artificial headlands can subdivide an eroding coast. A reference curve between the original upcoast and downcoast controls establishes an approximate equilibrium alignment. An intermediate control defines a sub-bay, and the wave orthogonal normal to the reference curve provides a local directional assumption. Repeating the construction gives a conceptual sequence of sub-bays. Offshore projection and alongshore spacing determine their indentation and intersections with the existing shoreline. Hsu and Evans (1989, pp. 564–568).

Moving a control seaward or altering its spacing can shift the predicted balance of local erosion and accretion. The same procedure can be considered on initially straight or convex coasts, with the local obliquity changing along the reach. Wave height does not appear explicitly in the empirical planform equation; wave period and bathymetry can still influence the wave transformation used to select an effective control and direction. Structural stability, overtopping, foundation depth, costs, and environmental impacts require their own analyses. Hsu and Evans (1989, pp. 566–568).

Accretion around a control requires sediment. Nourishment or reclamation can supply that volume, whereas natural filling can temporarily intercept transport and reduce supply to neighboring beaches. A projected equilibrium shoreline therefore needs to be assessed with the sediment volumes, active profiles, transition period, and downdrift impacts. Those quantities cannot be inferred from a planform polygon alone. Hsu and Evans (1989, pp. 568–569); González, Medina, and Losada (2010).

## 3. Empirical planform theory and the Portuguese application

### 3.1 The common parabolic bay-shape equation

The governing geometric relationship is the parabolic bay-shape equation:

$$ \frac{R(\theta)}{R_b}=C_0(\beta)+C_1(\beta)\left(\frac{\beta}{\theta}\right)+C_2(\beta)\left(\frac{\beta}{\theta}\right)^2 $$

With $q=\beta/\theta$, the same expression is a quadratic function of $q$:

$$ r=f(\beta,q)=C_0(\beta)+C_1(\beta)q+C_2(\beta)q^2,\qquad R=R_bf(\beta,q) $$

The term *parabolic* refers to this quadratic dependence of normalized radius on angular ratio. The resulting shoreline in Cartesian coordinates is generally not a conic parabola. The coefficients are dimensionless functions of reference obliquity, so the equation represents a family of normalized shapes. At fixed angles and coefficient selection, multiplying $R_b$ by a factor multiplies every radius by that factor. Hsu and Evans (1989, Eq. 1); Oliveira and Barreiro (2010, Eq. 2).

Both angles in the ratio must use the same unit. The ordinary-power coefficient functions documented here specifically require degrees. Changing the polynomial input to radians while leaving its constants unchanged defines a different and incorrect numerical function. The parabolic relationship can be dimensionless even though its fitted coefficients of successive powers carry inverse powers of the chosen angle unit. This is a consequence of applying the published equation with the degree-based tables of Hsu and Evans (1989) and Oliveira and Barreiro (2010).

The curved branch uses $\theta\geq\beta$. For the finite straight continuation, Moreno and Kraus (1999) describe:

$$ \frac{R}{R_b}=\frac{\sin\beta}{\sin\theta},\qquad 0<\theta\leq\beta $$

That expression represents the straight downcoast alignment for the stated angular convention. Baycraft samples the curved branch and does not append this straight continuation. The ideal meeting point of the two branches has unit normalized radius; the fitted coefficient arrays and their actual endpoint residuals are discussed separately in Section 7. Moreno and Kraus (1999).

### 3.2 Oliveira and Barreiro: study design and model ancestry

Oliveira and Barreiro (2010) apply empirical planform equations to **42 beaches** on the Portuguese west and south Atlantic coasts. Natural headlands or coastal structures provide one or two principal controls. Observed waterlines come from rectified aerial photographs acquired in October, near the transition between maritime seasons. The procedure consists of data preparation, local parameter selection, analytical curve construction, and comparison with the photographed waterlines. The study compares three mathematical families: the parabolic model, the logarithmic spiral, and the hyperbolic tangent. Oliveira and Barreiro (2010, pp. 124–127).

The Portuguese paper uses the parabolic equation developed by Hsu and Evans. It attributes the coefficient relationships to regressions on 27 prototype and model bays in static equilibrium and describes fourth-order coefficient polynomials from Silvester and Hsu (1993). Its Table 1 records the parameters used for the Portuguese applications. It does not publish the sixth-degree Oliveira2010 equations implemented in Baycraft. Those equations represent a separate numerical regression of the recorded coefficient observations. Oliveira and Barreiro (2010, p. 125, Table 1); Silvester and Hsu (1993), as reviewed there.

The study locations are reproduced in their original **Figure 4 numbering** below. This is a catalogue of the 42 beaches, not 42 statistically independent coefficient observations: some locations have two fitted parabolic branches (2010, Fig. 4, Table 1).

| No. | Portuguese beach | No. | Portuguese beach |
|---:|---|---:|---|
| 01 | Cabedelo | 23 | Sesimbra |
| 02 | Ofir | 24 | Creiro |
| 03 | Lagoa | 25 | Galapinhos |
| 04 | Salgueira | 26 | Lagosteiros |
| 05 | Caxinas | 27 | Cavalo |
| 06 | Árvore | 28 | Grande |
| 07 | Angeiras | 29 | Amoreira |
| 08 | Matosinhos | 30 | Murração |
| 09 | Espinho | 31 | Ponta Ruiva |
| 10 | Furadouro | 32 | Belixe |
| 11 | Figueira da Foz | 33 | Mareta |
| 12 | Nazaré | 34 | Martinhal |
| 13 | São Martinho do Porto | 35 | Ingrina |
| 14 | Baleal | 36 | Zavial |
| 15 | São Bernardino | 37 | Alvor |
| 16 | Porto Novo | 38 | Alemão |
| 17 | Pedra do Guincho | 39 | Rocha |
| 18 | Baleia | 40 | Albufeira |
| 19 | Ursa | 41 | St.ª Eulália |
| 20 | Arneira | 42 | Quarteira |
| 21 | São Pedro do Estoril |  |  |
| 22 | Caxias |  |  |

Some beaches require two analytical curves associated with the two ends of the bay. Six Table 1 rows contain paired parabolic parameter sets, giving 48 numeric records when each complete set is counted separately. The minimum reference angle is 22.19° and the maximum is 88.29°. These are coverage limits of that application table. They should not be interpreted as a new, independently validated range for every combination of wave climate, headland geometry, and sediment regime. Oliveira and Barreiro (2010, Table 1).

### 3.3 Logarithmic-spiral theory

The logarithmic spiral is expressed in polar coordinates as:

$$ R=R_0\exp(\theta\cot\alpha) $$

Here $R_0$ is the radius at the chosen reference direction, $\theta$ is the angular separation from that direction, and $\alpha$ is the constant angle between a radius and the spiral tangent. The ordinary exponential formula uses the radian measure of $\theta$. This spiral reference radius is a parameter of the spiral fit and should not be confused with the parabolic control radius. The spiral origin is selected geometrically and generally does not coincide with the physical wave-diffraction point. Oliveira and Barreiro (2010, Eq. 1), reviewing the logarithmic-spiral literature.

A spiral can approximate the strongly curved, sheltered part of a bay. Its practical limitations are the ambiguity of its origin, the absence of an explicit incident-wave direction, and exponential radial growth that poorly represents the distant, nearly straight reach. Spiral-like shapes can also occur outside static equilibrium, so a good spiral fit alone does not establish beach stability. Hsu and Evans (1989, p. 559); Oliveira and Barreiro (2010, pp. 125, 127–129); LeBlond (1979).

In the Portuguese applications, most fitted spiral angles were approximately 25°–65°, and most spiral reference radii were below 250 m. Double-curvature examples included Sesimbra, Mareta, Martinhal, and Albufeira. The fitted origins usually differed from the diffraction controls. The spiral described the sheltered curved zone well but did not adequately describe the almost straight part of the same beach. These are findings about the spiral family, not a comparison between Baycraft's two coefficient selections. Oliveira and Barreiro (2010, pp. 127–129).

### 3.4 Hyperbolic-tangent theory

For alongshore coordinate $x$ and cross-shore coordinate $y$, the hyperbolic-tangent model is:

$$ y=\pm a[\tanh(bx)]^m $$

Its equivalent exponential form is:

$$ y=\pm a\left(\frac{e^{bx}-e^{-bx}}{e^{bx}+e^{-bx}}\right)^m $$

The parameter $a$ is a length controlling the asymptotic cross-shore displacement, $b$ has inverse-length units and controls horizontal scaling, and $m$ is dimensionless and controls curvature. The origin is chosen where the shoreline tangent is perpendicular to the general shoreline trend; the $x$ axis follows that trend and $y$ points onshore. The intended branch and coordinate orientation must be retained when evaluating noninteger powers. Oliveira and Barreiro (2010, Eqs. 5–6), reviewing Moreno and Kraus (1999).

$$ \frac{dy}{dx}=\pm abm[\tanh(bx)]^{m-1}[1-\tanh^2(bx)] $$

The derivative above applies to the positive-side branch. As $x$ approaches zero from that side, the slope magnitude tends to infinity for $0<m<1$, equals $ab$ for $m=1$, and tends to zero for $m>1$. For increasing positive $x$, the curve tends to the asymptote $y=\pm a$. Values of $m$ above one tend to produce a more rectangular planform, while smaller positive values produce a rounded approach near the control. These properties explain the roles of the empirical parameters; they do not supply an independent equilibrium criterion. Oliveira and Barreiro (2010); direct differentiation of their stated equation.

The Moreno–Kraus examples reviewed in the Portuguese paper comprised 46 beaches, approximately half in northeast Spain and the remainder in western North America. Typical fits had $m\approx0.5$ and mean $ab\approx1.2$. Many Portuguese examples also had $m\approx0.5$, but their mean product was approximately 0.87; Figure 6 gives 0.8736. The logarithmic spiral generally fitted the part of strongest curvature more closely than the hyperbolic tangent, and the latter's parameters were less intuitive to calibrate because they do not explicitly specify the incident-wave conditions. Oliveira and Barreiro (2010, pp. 126–130).

The paper reports the following empirical parameter correlations, first for the Moreno–Kraus dataset and then for the Portuguese fits:

$$ a^{0.9124}b=0.606,\qquad R^2=0.8696 $$

$$ a^{0.9271}b=1.877,\qquad R^2=0.7906 $$

The second relationship is reproduced **as printed** in Equation 8 and Figure 6c. Its stated constant appears inconsistent with the plotted relationship involving $1/b$ and the reported mean $ab$. It is therefore not treated here as a transferable calibration rule or silently rearranged into a different fitted equation. Both correlations also depend on the units used for $a$ and $b$. Baycraft does not implement the hyperbolic-tangent model or either parameter correlation. Oliveira and Barreiro (2010, Eqs. 7–8, Fig. 6).

### 3.5 Reference-point selection and the González method

The start of the nearly straight downcoast reach is often difficult to identify. Oliveira and Barreiro (2010) review a method relating the reference angle and control geometry to wave-field information through a limiting angle $\alpha_{\min}$. Their Equations 3–4 print:

$$ \beta=90^{\circ}-\alpha_{\min},\qquad R_0=\frac{Y}{\tan\alpha_{\min}} $$

There is a source-notation discrepancy in that printed radius relation. For the radial control length and perpendicular offset $Y$, Equation 16 of González and Medina (2001) gives the consistent relationship below; their Equation 19 independently gives $Y=R_0\cos\alpha_{\min}$. A tangent denominator appears in their Figure 8 and in Oliveira's Equation 4. The two expressions must not be treated as interchangeable radial formulas. The cosine relation is therefore used when interpreting the radial geometry, while the preceding equation records Oliveira's printed expression explicitly. González and Medina (2001); Oliveira and Barreiro (2010).

$$ R_0=\frac{Y}{\cos\alpha_{\min}}=\frac{Y}{\sin\beta} $$

The limiting angle is related to the ratio $Y/L$, where $Y$ is the distance from the diffraction point to the straight downcoast alignment and $L$ is local wavelength. The reviewed construction uses:

$$ L=cT,\qquad c=\sqrt{gd} $$

Here $T$ is wave period, $g$ is gravitational acceleration, and $d$ is the water depth at the diffraction point. The celerity expression is the shallow-water approximation. The development considered 26 Spanish bays with negligible longshore transport. The Portuguese paper does not provide a general closed-form expression for $\alpha_{\min}(Y/L)$, so these equations alone do not define a complete automated reference-point procedure. Oliveira and Barreiro (2010, pp. 125–126); González and Medina (2001).

This approach clarifies the physical information that can guide control placement: bathymetry, local wavelength, and diffraction geometry. Baycraft accepts the analyst's $H$, $E$, and $W$ coordinates; it does not solve wave propagation, infer the bathymetry, compute $\alpha_{\min}$, or automatically locate the straight-to-curved transition. The distinction between a control-selection method and a curve-drawing method is central to reproducible interpretation. González and Medina (2001); Oliveira and Barreiro (2010).

### 3.6 Portuguese field results and the Espinho example

Most studied Portuguese beaches were interpreted as being in **dynamic equilibrium**. On the west coast, an energetic maritime winter extends approximately from October to March, with substantial seasonal changes in wave height, period, and direction. The paper reports a closure depth of about 10–12 m below mean sea level. For many studied controls, the active transport zone extends beyond the headland or jetty, allowing bypassing and exchange with neighboring reaches. Oliveira and Barreiro (2010, pp. 130–131).

Nevertheless, the parabolic static-equilibrium curves closely matched many photographed planforms. The authors interpret this through rapid seasonal adjustment and the end-of-summer timing of the October imagery. Summer beaches were generally wider and more reflective in profile, while winter beaches tended to be more dissipative. A photographed waterline can therefore resemble the static limiting shape while belonging to an open, dynamically exchanging sediment system. The paper does not report a shoreline RMSE or MAE for all 42 beaches that could be substituted for this qualified interpretation. Oliveira and Barreiro (2010, pp. 130–131).

Espinho illustrates the distinction. The paper describes a northern groin approximately 380 m long, a southern groin approximately 440 m long, and a shorter intermediate groin. Sediment bypassing remains possible because the active zone extends beyond the groin heads. The authors cite an estimated net southward littoral transport of roughly **one million cubic metres per year** and explain the persistent planform through balanced input and output. A deficit would alter that geometry. The example supports sediment-budget reasoning rather than an inference of zero transport from the curve fit. Oliveira and Barreiro (2010, discussing Oliveira et al., 2000).

Table 1 and Figure 7 use different printed parameter sets for Espinho. Table 1 gives $\beta=58.63^{\circ}$, $R_0=370$ m, and coefficients $C_0=-0.20577$, $C_1=1.88805$, and $C_2=-0.68329$. Figure 7 gives $\beta=42^{\circ}$ and $R_0=524$ m, with $C_0=-0.011062$, $C_1=1.350184$, and $C_2=-0.362030$. The coefficient dataset documented in Section 5 follows **Table 1**. Mixing its angle with Figure 7's coefficients would create a parameter combination stated in neither place. Oliveira and Barreiro (2010, Table 1, Fig. 7).

### 3.7 Original Hsu–Evans evidence and construction

Hsu and Evans (1989) developed the normalized relationship from model tests and observations of natural bays. Natural examples were selected as approximately static where islands or promontories lacked rivers or evident continuing sediment supply. Their observed reference angles were approximately 22°–72°; the graphical ratio curves were extrapolated over 0°–80°; and the published coefficient table covers 10°–80°. These three ranges describe different parts of the evidence and should remain distinct. Hsu and Evans (1989, pp. 561–563).

A single universal linear relationship between normalized radius and angular ratio did not adequately represent the dependence on $\beta$. Computer fitting led to the quadratic form with smoothly varying coefficients. Figure 4 includes ray-angle curves through 210°, 240°, and 270°, although a subsequent practical construction example lists rays only through 180°. That example does not establish 180° as an absolute validity cutoff. Physical presence of a sandy beach, geology, and the suitability of the control geometry still limit interpretation of a mathematical continuation. Hsu and Evans (1989, Figs. 3–5, pp. 560–563).

The natural-bay observations listed in Table 1 of the original paper are retained below. They describe the published evidence, not an independent validation dataset for the software regressions. Hsu and Evans (1989, Table 1).

| Location | Region | $\beta$ |
|---|---|---:|
| Magnetic Island | Queensland | 22.5° |
| Mission Island | Queensland | 35.0° |
| Philip Island | Victoria | 38.0° |
| Magnetic Island | Queensland | 39.0° |
| Wilson Promontory | Victoria | 43.0° |
| Keppel Island | Queensland | 43.0° |
| Wilson Promontory | Victoria | 52.0° |
| Dongara | Western Australia | 52.0° |
| Freycinet Peninsula | Tasmania | 55.5° |
| Philip Island | Victoria | 57.0° |
| Jurien Bay | Western Australia | 61.0° |
| Kangaroo Island | South Australia | 61.0° |
| Freycinet Peninsula | Tasmania | 71.5° |
| Port Arthur Peninsula | Tasmania | 72.0° |

The construction identifies the diffraction point and downcoast limit, measures $\beta$ and $R_0$, obtains coefficients, and plots the calculated radius on each chosen ray. The authors discuss a possible small adjustment of the measured reference angle for a beach not already static, suggested as no more than about one degree. Baycraft does not apply that empirical adjustment automatically. Near the upcoast control, rough rock can attenuate waves and preserve sand deposited by storms, producing departures from the idealized curve. Hsu and Evans (1989, pp. 563–564).

## 4. Numerical coefficient methods

### 4.1 Regression objective and polynomial representation

Each parameterization supplies three independent polynomials:

$$ C_i(\beta)=\sum_{k=0}^{6}a_{i,k}\beta^k,\qquad i=0,1,2 $$

For coefficient observations $c_{i,j}$ at angles $\beta_j$, the fitted parameters minimize:

$$ \sum_{j=1}^{n}\left[\sum_{k=0}^{6}a_{i,k}\beta_j^k-c_{i,j}\right]^2 $$

Every row receives equal weight. The three fits do not impose joint normalization, an artificial observation at zero degrees, an endpoint condition, or a monotonicity constraint. The Oliveira dataset retains its repeated coefficient record, so that observation contributes twice to the objective. The underlying values come from Oliveira and Barreiro (2010, Table 1) and Hsu and Evans (1989, Table 2); the degree-six least-squares representation is the numerical method used by the application.

Working directly with high powers of degree-valued angles produces a poorly scaled regression matrix. A scaled fitting coordinate is therefore useful:

$$ x=\frac{\beta-\mu}{h} $$

For Oliveira, the midpoint and half-range are $\mu=55.24^{\circ}$ and $h=33.05^{\circ}$. The source records an 80-digit QR solution in a scaled Chebyshev basis, followed by conversion to ordinary powers of $\beta$. For Hsu, the corresponding coordinate is $x=(\beta-45)/35$, and a scaled polynomial least-squares fit can be reproduced with NumPy's Polynomial fitting interface before conversion to ordinary powers. These basis choices improve numerical conditioning; they do not change the equal-weight least-squares objective. The application stores the final ordinary-power arrays and does not require a numerical-fitting package at runtime.

### 4.2 Runtime evaluation and reproducible precision

Horner's method evaluates each stored polynomial:

$$ b_6=a_{i,6},\qquad b_k=a_{i,k}+\beta b_{k+1}\quad(k=5,\ldots,0),\qquad C_i=b_0 $$

The full-precision parameter tables in Sections 5 and 6 preserve the decimal literals used for binary64 evaluation. The expanded display equations use eleven significant digits for readability; calculations intended to reproduce the source should use the full tables. Neither 80-digit fitting arithmetic nor seventeen-digit parameter storage makes the empirical observations equally precise. The source tables contain rounded coefficients, and the field interpretation has additional geometric and environmental uncertainty. Hsu and Evans (1989); Oliveira and Barreiro (2010).

### 4.3 Residual statistics and influence diagnostics

This document defines signed residuals as **fitted minus observed**:

$$ e_{i,j}=\widehat{c}_{i,j}-c_{i,j},\qquad \overline{c}_i=\frac{1}{n}\sum_{j=1}^{n}c_{i,j} $$

$$ \mathrm{SSE}_i=\sum_{j=1}^{n}e_{i,j}^2,\qquad \mathrm{SST}_i=\sum_{j=1}^{n}(c_{i,j}-\overline{c}_i)^2 $$

Here SSE is the sum of squared errors and SST is the total sum of squares. The reported fit measures are:

$$ R_i^2=1-\frac{\mathrm{SSE}_i}{\mathrm{SST}_i},\qquad \mathrm{RMSE}_i=\sqrt{\frac{\mathrm{SSE}_i}{n}} $$

$$ \mathrm{MAE}_i=\frac{1}{n}\sum_{j=1}^{n}|e_{i,j}|,\qquad E_{\max,i}=\max_j|e_{i,j}| $$

RMSE here uses $n$ in its denominator. The residual variance for regression diagnostics instead uses $n-p_f$, with $p_f=7$ fitted parameters per coefficient. Residual degrees of freedom are therefore 41 for Oliveira and 8 for Hsu. If $h_j$ is the diagonal leverage obtained from the scaled design matrix, the standardized residual, Cook's distance, and leave-one-out residual are:

$$ s_i^2=\frac{\mathrm{SSE}_i}{n-p_f},\qquad t_{i,j}=\frac{e_{i,j}}{s_i\sqrt{1-h_j}} $$

$$ D_{i,j}=\frac{e_{i,j}^2h_j}{p_fs_i^2(1-h_j)^2},\qquad e_{i,j}^{\mathrm{LOO}}=\frac{e_{i,j}}{1-h_j} $$

These diagnostics describe the sensitivity of a coefficient-table regression to individual rows. Leave-one-out prediction concerns a withheld coefficient observation, not a withheld surveyed shoreline. Rounded table values, a small sample, repeated observations, and common empirical ancestry prevent treating these diagnostics as a calibrated distribution of coastal prediction error. A quantile plot or a very high $R^2$ does not establish normal field errors or justify a shoreline confidence band. Hsu and Evans (1989); Oliveira and Barreiro (2010), interpreted through the stated regression design.

## 5. Oliveira2010 coefficient parameterization

### 5.1 Source data, observations, and model domain

**Oliveira2010 is the default coefficient selection.** Its 48 regression observations are the numeric rows of the **coeffs** in Table 1. These rows cover 42 beaches and 47 distinct reference angles. Six beaches have two complete parabolic parameter sets: São Martinho do Porto (13), São Bernardino (15), Pedra do Guincho (17), Ponta Ruiva (31), Martinhal (34), and Albufeira (40). The accepted interval is $22.19^{\circ}\leq\beta\leq88.29^{\circ}$. The original observations are attributed to Oliveira and Barreiro (2010, Table 1, p. 127).

Two provenance details are essential to reproducing this dataset. **Ofir (02)** has one complete angle/reference-radius record but two printed alternatives for $C_2$, namely $-0.3051$ and $-0.10908$. The numeric regression uses **only $-0.3051$**. The second printed alternative is not an additional fitted observation, although both alternatives appear in the raw table transcription. Also, São Bernardino's second branch and Albufeira's first branch have the same $\beta,C_0,C_1,C_2$ tuple at $\beta=25.38^{\circ}$; both rows remain in the equal-weight fit. This states the actual numerical selection without treating the paper's Ofir ambiguity as resolved by the authors. Oliveira and Barreiro (2010, Table 1).

**Model summary (Oliveira2010).**

| Property | Value |
|---|---|
| Published observation source | Oliveira and Barreiro (2010), Table 1 |
| Source beach locations | 42, numbered according to Figure 4 |
| Fitted coefficient observations | 48 triples, six additional branches |
| Accepted reference-angle interval | $22.19^{\circ}\leq\beta\leq88.29^{\circ}$ |
| Polynomial representation | Three independent sixth-degree functions in degrees |
| Regression weighting | Equal weight for each of the 48 rows |
| Endpoint-closure constraint | None |

The following table lists every fitted coefficient observation, with the **Portuguese beach names corresponding to Figure 4**. The first column identifies the paper's beach number and the branch within that row; suffix `.2` means a second parabolic parameter set, not a separate beach. Reference lengths do not enter this dimensionless coefficient regression. Oliveira's editable ray angle is written $\alpha$ there; it corresponds to the software's $\theta$ and is not a fourth regression input.

| ID | Portuguese beach | $\beta$ (deg) | $C_0$ | $C_1$ | $C_2$ |
|---|---|---:|---:|---:|---:|
| 01.1 | Cabedelo | 37.04 | 0.02028 | 1.25732 | -0.28112 |
| 02.1 | Ofir | 38.57 | 0.01158 | 1.28983 | -0.3051 |
| 03.1 | Lagoa | 55.01 | -0.15211 | 1.76327 | -0.61216 |
| 04.1 | Salgueira | 42.82 | -0.01756 | 1.39132 | -0.37676 |
| 05.1 | Caxinas | 39.43 | 0.00642 | 1.30918 | -0.31888 |
| 06.1 | Árvore | 47.05 | -0.05603 | 1.50898 | -0.45495 |
| 07.1 | Angeiras | 38.66 | 0.01104 | 1.29185 | -0.30656 |
| 08.1 | Matosinhos | 45.18 | -0.03762 | 1.45504 | -0.41983 |
| 09.1 | Espinho | 58.63 | -0.20577 | 1.88805 | -0.68329 |
| 10.1 | Furadouro | 30.71 | 0.04423 | 1.14665 | -0.19452 |
| 11.1 | Figueira da Foz | 30.14 | 0.04565 | 1.13812 | -0.18769 |
| 12.1 | Nazaré | 63.94 | -0.29386 | 2.07373 | -0.77986 |
| 13.1 | São Martinho do Porto | 88.29 | -0.75039 | 2.76693 | -0.79021 |
| 13.2 | São Martinho do Porto | 87.35 | -0.7346 | 2.74769 | -0.8131 |
| 14.1 | Baleal | 61.74 | -0.25571 | 1.9969 | -0.74132 |
| 15.1 | São Bernardino | 45.32 | -0.03888 | 1.45896 | -0.42242 |
| 15.2 | São Bernardino | 25.38 | 0.05262 | 1.08211 | -0.13811 |
| 16.1 | Porto Novo | 52.33 | -0.11629 | 1.67306 | -0.5586 |
| 17.1 | Pedra do Guincho | 53.13 | -0.12669 | 1.69985 | -0.5746 |
| 17.2 | Pedra do Guincho | 55.4 | -0.1576 | 1.7766 | -0.62 |
| 18.1 | Baleia | 53.71 | -0.13423 | 1.71929 | -0.5862 |
| 19.1 | Ursa | 66.71 | -0.34414 | 2.16879 | -0.8233 |
| 20.1 | Arneira | 22.19 | 0.054 | 1.05452 | -0.11052 |
| 21.1 | São Pedro do Estoril | 71.57 | -0.43552 | 2.32295 | -0.88343 |
| 22.1 | Caxias | 45.83 | -0.04347 | 1.47324 | -0.43186 |
| 23.1 | Sesimbra | 48.16 | -0.06776 | 1.54188 | -0.47612 |
| 24.1 | Creiro | 50.08 | -0.08896 | 1.60056 | -0.5136 |
| 25.1 | Galapinhos | 39.96 | 0.00318 | 1.32133 | -0.32752 |
| 26.1 | Lagosteiros | 61.48 | -0.25142 | 1.9878 | -0.73664 |
| 27.1 | Cavalo | 52.07 | -0.11291 | 1.66435 | -0.5534 |
| 28.1 | Grande | 47.11 | -0.05666 | 1.51075 | -0.45609 |
| 29.1 | Amoreira | 35.54 | 0.02785 | 1.22745 | -0.25853 |
| 30.1 | Murração | 34.56 | 0.03176 | 1.20936 | -0.24484 |
| 31.1 | Ponta Ruiva | 49.05 | -0.07755 | 1.56903 | -0.49348 |
| 31.2 | Ponta Ruiva | 61.19 | -0.24662 | 1.97762 | -0.7314 |
| 32.1 | Belixe | 41.91 | -0.01037 | 1.36784 | -0.36047 |
| 33.1 | Mareta | 43.9 | -0.0262 | 1.4194 | -0.3962 |
| 34.1 | Martinhal | 33.39 | 0.03614 | 1.18894 | -0.22877 |
| 34.2 | Martinhal | 22.62 | 0.054 | 1.05796 | -0.11396 |
| 35.1 | Ingrina | 83.87 | -0.673 | 2.6685 | -0.876 |
| 36.1 | Zavial | 34.57 | 0.03172 | 1.20955 | -0.24498 |
| 37.1 | Alvor | 36.87 | 0.02122 | 1.25383 | -0.27848 |
| 38.1 | Alemão | 56.22 | -0.1693 | 1.80459 | -0.63629 |
| 39.1 | Rocha | 25.77 | 0.05223 | 1.08581 | -0.14181 |
| 40.1 | Albufeira | 25.38 | 0.05262 | 1.08211 | -0.13811 |
| 40.2 | Albufeira | 36.03 | 0.02585 | 1.23656 | -0.26542 |
| 41.1 | St.ª Eulália | 28.88 | 0.04824 | 1.12114 | -0.17368 |
| 42.1 | Quarteira | 26.97 | 0.05103 | 1.09867 | -0.1537 |

### 5.2 Full-precision sixth-degree polynomial coefficients

**Full-precision polynomial coefficients (Oliveira2010).** The tables use the common format $a_{i,k}$ for powers $\beta^k$ ($k=0,\ldots,6$) and are in ascending power order. Each of the three series is shown separately to prevent wide tables in a portrait PDF. Keep all digits when reproducing the computation. The equal-weight, scaled-QR fit of the 48 observations reproduces all 21 stored binary64 coefficient literals. Oliveira and Barreiro (2010, Table 1) provide the source observations, not these degree-six equations.

| Power $k$ for $C_0$ | $a_{0,k}$ |
|---:|---:|
| 0 | 8.9379927134888931e-02 |
| 1 | -7.4010747230969986e-03 |
| 2 | 5.0128072495406347e-04 |
| 3 | -1.3097394953416148e-05 |
| 4 | 1.1423122564951566e-07 |
| 5 | -5.2045195736435901e-10 |
| 6 | 1.6282762116787805e-12 |

| Power $k$ for $C_1$ | $a_{1,k}$ |
|---:|---:|
| 0 | 8.8162348805414326e-01 |
| 1 | 1.5146321651759101e-02 |
| 2 | -6.9703159306350117e-04 |
| 3 | 1.6757848070587428e-05 |
| 4 | 4.1151569864693824e-08 |
| 5 | -2.8320953879636758e-09 |
| 6 | 1.5079413405730286e-11 |

| Power $k$ for $C_2$ | $a_{2,k}$ |
|---:|---:|
| 0 | 1.8740249891403760e-02 |
| 1 | -7.3238336183188302e-03 |
| 2 | 2.6842398440550411e-04 |
| 3 | -1.0866508661427859e-05 |
| 4 | 7.9276852802049855e-08 |
| 5 | 9.9295446608229346e-11 |
| 6 | -2.6583961939866272e-13 |

### 5.3 Expanded sixth-degree coefficient equations

The following expressions are the same polynomials, displayed to eleven significant digits. Use the full-precision tables for numerical reproduction and input $\beta$ in degrees. These expanded expressions are the Baycraft regression of the data associated with Oliveira and Barreiro (2010), rather than equations printed in that paper.

$$ \begin{aligned} C_0(\beta)\approx{}&0.089379927135-0.0074010747231\beta \\ &+0.00050128072495\beta^2-1.3097394953\times10^{-5}\beta^3 \\ &+1.1423122565\times10^{-7}\beta^4-5.2045195736\times10^{-10}\beta^5 \\ &+1.6282762117\times10^{-12}\beta^6\end{aligned} $$

$$ \begin{aligned} C_1(\beta)\approx{}&0.88162348805+0.015146321652\beta \\ &-0.00069703159306\beta^2+1.6757848071\times10^{-5}\beta^3 \\ &+4.1151569865\times10^{-8}\beta^4-2.8320953880\times10^{-9}\beta^5 \\ &+1.5079413406\times10^{-11}\beta^6\end{aligned} $$

$$ \begin{aligned} C_2(\beta)\approx{}&0.018740249891-0.0073238336183\beta \\ &+0.00026842398441\beta^2-1.0866508661\times10^{-5}\beta^3 \\ &+7.9276852802\times10^{-8}\beta^4+9.9295446608\times10^{-11}\beta^5 \\ &-2.6583961940\times10^{-13}\beta^6\end{aligned} $$

### 5.4 Regression diagnostics and domain limitations

The following diagnostics are computed from the 48 documented numeric rows and the implemented coefficients. RMSE divides SSE by 48. LOO RMSE uses one-row-at-a-time deletion from the seven-parameter fit. The reported residuals do not include either the excluded Ofir alternative or the different Espinho parameter set in Figure 7. The observation source is Oliveira and Barreiro (2010, Table 1).

| Metric | $C_0$ | $C_1$ | $C_2$ |
|---|---:|---:|---:|
| $R^2$ | 0.999998926818 | 0.999996793023 | 0.999999569897 |
| RMSE | 0.000203811057 | 0.000788150777 | 0.000149234393 |
| MAE | 0.000145951454 | 0.000514790418 | 0.000110980583 |
| Max. abs. | 0.000523591929 | 0.003901640958 | 0.000469733963 |
| SSE | 0.000001993869 | 0.000029816719 | 0.000001069003 |
| LOO RMSE | 0.000243813097 | 0.001650468150 | 0.000167115796 |


The largest absolute coefficient residuals occur at Ursa (19) for $C_0$, São Pedro do Estoril (21) for $C_1$, and Albufeira's second branch (40.2) for $C_2$. The small residuals show that the sixth-degree functions closely reproduce the selected table values. Because the data include paired branches and a repeated tuple, row-wise leave-one-out diagnostics are not leave-one-beach-out validation and do not establish spatial independence. They also do not measure waterline or sediment-budget error. Oliveira and Barreiro (2010), with the coefficient-regression diagnostics defined in Section 4.

The accepted upper range requires particular attention to geometric closure. At $\beta=88.29^{\circ}$, the implemented coefficients sum to approximately **1.2275**, so the first radius is about 22.75% larger than the nominal $R_b$. The source row itself sums to 1.22633. Most of this endpoint discrepancy is therefore inherited from the tabulated parameter combination, rather than introduced by the small sixth-degree fitting residual. It is outside the common range of the two models used in Section 8. A supported coefficient input is not a guarantee that the resulting curve satisfies every ideal geometric constraint. Oliveira and Barreiro (2010, Table 1); direct evaluation of the documented data and polynomials.

## 6. Hsu1989 coefficient parameterization

### 6.1 Source data, observations, and model domain

Hsu and Evans (1989) publish 15 coefficient rows at five-degree increments and explicitly recommend **linear interpolation** between them. For $\beta_j\leq\beta\leq\beta_{j+1}$, their recommendation can be expressed as:

$$ t=\frac{\beta-\beta_j}{5},\qquad C_i^{\mathrm{linear}}(\beta)=(1-t)C_{i,j}+tC_{i,j+1} $$

Baycraft's Hsu1989 selection evaluates degree-six regressions of those 15 rows. The distinction concerns the numerical representation of the published data; the underlying parabolic equation and coefficient provenance remain those of Hsu and Evans (1989). The accepted interval is $10^{\circ}\leq\beta\leq80^{\circ}$, and there is no artificial zero-degree observation.

**Model summary (Hsu1989).**

| Property | Value |
|---|---|
| Published observation source | Hsu and Evans (1989), Table 2 |
| Source beach locations | 14 natural-bay observations in Table 1, not regression inputs |
| Fitted coefficient observations | 15 triples at five-degree intervals |
| Accepted reference-angle interval | $10^{\circ}\leq\beta\leq80^{\circ}$ |
| Polynomial representation | Three independent sixth-degree functions in degrees |
| Regression weighting | Equal weight for each of the 15 rows |
| Endpoint-closure constraint | None |

**Fitted coefficient observations (Hsu1989).** Hsu and Evans (1989, Table 2).

| $\beta$ (deg) | $C_0$ | $C_1$ | $C_2$ |
|---:|---:|---:|---:|
| 10 | 0.036 | 1.011 | -0.047 |
| 15 | 0.050 | 0.998 | -0.049 |
| 20 | 0.055 | 1.029 | -0.088 |
| 25 | 0.054 | 1.083 | -0.142 |
| 30 | 0.045 | 1.146 | -0.194 |
| 35 | 0.029 | 1.220 | -0.253 |
| 40 | 0.000 | 1.326 | -0.332 |
| 45 | -0.039 | 1.446 | -0.412 |
| 50 | -0.088 | 1.588 | -0.507 |
| 55 | -0.151 | 1.756 | -0.611 |
| 60 | -0.227 | 1.930 | -0.706 |
| 65 | -0.315 | 2.113 | -0.800 |
| 70 | -0.409 | 2.284 | -0.873 |
| 75 | -0.505 | 2.422 | -0.909 |
| 80 | -0.600 | 2.520 | -0.906 |

The entry at $\beta=40^{\circ}$ is printed as negative zero and is numerically zero. The three-decimal precision of the table should be retained when judging the meaning of much more precise polynomial parameters. The Hsu table is distinct from coefficient tables and polynomial representations attributed to other publications, including Silvester and Hsu (1993). Hsu and Evans (1989, Table 2); Oliveira and Barreiro (2010, p. 125).

For completeness, the scaled least-squares construction for this dataset is:

$$ x_j=\frac{\beta_j-45}{35},\qquad \widehat{\mathbf b}_i=\underset{\mathbf b_i}{\arg\min}\sum_{j=1}^{15}\left[c_{i,j}-\sum_{k=0}^{6}b_{i,k}x_j^k\right]^2 $$

The fitted polynomial is converted back to ordinary degree powers before storage. All 15 rows have equal weight, and each coefficient series has eight residual degrees of freedom. No endpoint normalization is imposed. This specifies the numerical fit of the table in Hsu and Evans (1989), whose own intermediate-angle recommendation remains linear interpolation.

### 6.2 Full-precision sixth-degree polynomial coefficients

**Full-precision polynomial coefficients (Hsu1989).** The tables use the common format $a_{i,k}$ for powers $\beta^k$ ($k=0,\ldots,6$) and are in ascending power order. Each of the three series is shown separately to prevent wide tables in a portrait PDF. Keep all digits when reproducing the computation; even the small high-order terms contribute at degree-valued $\beta$. Hsu and Evans (1989, Table 2) provide the source observations, not these degree-six equations.

| Power $k$ for $C_0$ | $a_{0,k}$ |
|---:|---:|
| 0 | -2.5948717948720286e-02 |
| 1 | 9.4371469397480281e-03 |
| 2 | -4.0811322978137366e-04 |
| 3 | 1.0108930697786255e-05 |
| 4 | -1.7860566448803580e-07 |
| 5 | 1.1488449630866086e-09 |
| 6 | -1.3026029125105853e-12 |

| Power $k$ for $C_1$ | $a_{1,k}$ |
|---:|---:|
| 0 | 1.3292717948718358e00 |
| 1 | -6.5720015956185304e-02 |
| 2 | 4.6454080433615905e-03 |
| 3 | -1.5110565213940694e-04 |
| 4 | 2.7247346369948383e-06 |
| 5 | -2.3730284988490486e-08 |
| 6 | 7.7202155716091587e-11 |

| Power $k$ for $C_2$ | $a_{2,k}$ |
|---:|---:|
| 0 | -2.9170512820513572e-01 |
| 1 | 5.4566218941018596e-02 |
| 2 | -4.1688146498725922e-03 |
| 3 | 1.4006101055807072e-04 |
| 4 | -2.5540727510077560e-06 |
| 5 | 2.2867190600936895e-08 |
| 6 | -7.7541566334136543e-11 |

### 6.3 Expanded sixth-degree coefficient equations

The expanded equations are displayed to eleven significant digits. They describe the same stored polynomial functions; use the complete tables for numerical reproduction. They are application-side regressions of the source coefficient table, rather than sixth-degree equations published by Hsu and Evans (1989).

$$ \begin{aligned} C_0(\beta)\approx{}&-0.025948717949+0.0094371469397\beta \\ &-0.00040811322978\beta^2+1.0108930698\times10^{-5}\beta^3 \\ &-1.7860566449\times10^{-7}\beta^4+1.1488449631\times10^{-9}\beta^5 \\ &-1.3026029125\times10^{-12}\beta^6\end{aligned} $$

$$ \begin{aligned} C_1(\beta)\approx{}&1.3292717949-0.065720015956\beta \\ &+0.0046454080434\beta^2-0.00015110565214\beta^3 \\ &+2.7247346370\times10^{-6}\beta^4-2.3730284988\times10^{-8}\beta^5 \\ &+7.7202155716\times10^{-11}\beta^6\end{aligned} $$

$$ \begin{aligned} C_2(\beta)\approx{}&-0.29170512821+0.054566218941\beta \\ &-0.0041688146499\beta^2+0.00014006101056\beta^3 \\ &-2.5540727510\times10^{-6}\beta^4+2.2867190601\times10^{-8}\beta^5 \\ &-7.7541566334\times10^{-11}\beta^6\end{aligned} $$

### 6.4 Regression diagnostics and domain limitations

The following descriptive diagnostics use the 15 published coefficient rows. RMSE divides SSE by 15, while the regression residual variance uses eight residual degrees of freedom. These distinctions are the same as for Oliveira. The values characterize a numerical approximation of Hsu and Evans (1989, Table 2).

| Metric | $C_0$ | $C_1$ | $C_2$ |
|---|---:|---:|---:|
| $R^2$ | 0.9999902925770000 | 0.9999848472820000 | 0.9999470790680000 |
| RMSE | 0.0006699048134300 | 0.0020443783763000 | 0.0022875106866000 |
| MAE | 0.0005500346643400 | 0.0015375502104000 | 0.0017437940250000 |
| Max. abs. | 0.0012527585933000 | 0.0054051758355000 | 0.0047892752243000 |
| SSE | 0.0000067315868858 | 0.0000626922441850 | 0.0000784905771220 |
| LOO RMSE | 0.0024806208797000 | 0.0056975422245000 | 0.0082280860054000 |

The high $R^2$ values establish close reproduction of the rounded source coefficients on the fitted interval. They provide no independent estimate of the accuracy of the diffraction point, selected wave direction, image georeferencing, or surveyed shoreline. The comparatively larger row-wise LOO errors also show why residuals at the fitted observations alone are an incomplete description of a seven-parameter fit to 15 rows. None of these coefficient diagnostics supplies coastal prediction intervals. Hsu and Evans (1989); Lausman, Klein, and Stive (2010a).

Hsu and Evans (1989) give graphical and natural-bay examples over ranges that differ from Table 2, as documented in Section 3.7. The application range follows the actual table. A curve can be mathematically evaluated at a long ray angle within the sampling rules, but local geology, headland sheltering, or a lack of sandy shoreline can make part of that continuation physically irrelevant. Hsu and Evans (1989, pp. 560–564).

## 7. Geometric closure and sensitivity

### 7.1 The nominal control point and the first curve sample

At the reference ray, $q=1$. Direct substitution into the common equation gives:

$$ R(\beta)=R_b´C_0(\beta)+C_1(\beta)+C_2(\beta)] $$

Exact passage through $E$ would require the three coefficients to sum to one. Define the signed normalized endpoint defect and its dimensional magnitude as:

$$ \varepsilon_E=C_0+C_1+C_2-1,\qquad d_E=R_b|\varepsilon_E| $$

Both parameterizations fit the coefficient series independently and preserve their resulting sums. Baycraft does not normalize the coefficients or snap the first sample to $E$. Thus $E$ fixes the nominal reference length and direction, while the first calculated shoreline point may lie elsewhere on that ray. This is an algebraic property of the implemented representation of Hsu and Evans (1989) and Oliveira and Barreiro (2010), rather than a georeferencing error.

The following values are direct evaluations of the full-precision arrays. A dash denotes an angle outside the Hsu1989 coefficient range.

| $\beta$ | Oliveira $R(\beta)/R_b$ | Hsu $R(\beta)/R_b$ |
|---:|---:|---:|
| 30° | 0.996234772008 | 0.995798650472 |
| 45° | 0.997682529253 | 0.994294038263 |
| 60° | 0.998715004049 | 0.995672477574 |
| 80° | 1.060599934731 | 1.014001341589 |
| 88.29° | 1.227542230835 | — |

Within the common range through 80°, the extrema check gives Oliveira endpoint defects from approximately $-0.00397573$ at $\beta=33.752^{\circ}$ to $+0.06059993$ at 80°. The corresponding Hsu range is approximately $-0.00598708$ at 50.22785° to $+0.01400134$ at 80°. These ranges belong to that comparison interval; they do not describe Oliveira's extension to 88.29°. The relevant coefficients originate in Oliveira and Barreiro (2010) and Hsu and Evans (1989); the defects are calculations from the stored arrays.

### 7.2 Angular and coefficient sensitivity

At fixed $\beta$ and $R_b$, differentiation with respect to the ray angle gives:

$$ \frac{\partial R}{\partial\theta}=-R_b\frac{\beta}{\theta^2}\left(C_1+2C_2\frac{\beta}{\theta}\right) $$

At fixed $\theta$ and $R_b$, reference-angle sensitivity is:

$$ \frac{\partial R}{\partial\beta}=R_b\left[C_0'+C_1'q+C_2'q^2+\frac{C_1+2C_2q}{\theta}\right] $$

The coefficient derivatives are obtained from the stored polynomials:

$$ C_i'(\beta)=\sum_{k=1}^{6}k\,a_{i,k}\beta^{k-1} $$

These derivatives use degrees consistently, so their angular sensitivities are per degree. They describe local changes in the equation, not the complete effect of moving a control point, which may also alter $R_b$, the polar orientation, and the chosen side of the bay. They are direct analytical derivatives of the relationship of Hsu and Evans (1989), also used by Oliveira and Barreiro (2010).

At fixed angles and scale, a perturbation of the three coefficients gives:

$$ \delta R=R_b(\delta C_0+q\,\delta C_1+q^2\delta C_2) $$

The coefficients can partially compensate in the combined radius. Consequently, a large change in an individual coefficient need not produce an equally large change in the curve. Conversely, near $q=1$, their sum directly controls closure. Relative coefficient errors are also unstable where a coefficient passes through zero. Radial differences, endpoint defects, and application-specific shoreline offsets are more interpretable than isolated percentage changes in such coefficients. Hsu and Evans (1989); Oliveira and Barreiro (2010), through the stated equation.

## 8. Model comparison: methods, results, and conclusions

### 8.1 Comparison design

The comparison evaluates the stored coefficient functions without refitting, normalizing, or adjusting the control points. Both models use the same $R_b$, $\beta$, ray angles, and Cartesian orientation. Their shared reference-angle interval is 22.19°–80°. With identical controls, the normalized radial difference is:

$$ \Delta r=r_{\mathrm O}-r_{\mathrm H}=\Delta C_0+q\,\Delta C_1+q^2\Delta C_2 $$

The dimensional separation along a common ray is:

$$ \Delta R=R_b\Delta r $$

This signed difference uses Oliveira minus Hsu. It is a comparison between two implementations of the same empirical family, with related data ancestry. It does not use either model as a ground truth and does not compare a calculated curve with a surveyed beach. The physical framework and source tables are those of Oliveira and Barreiro (2010) and Hsu and Evans (1989); the statistics below are deterministic software calculations.

The principal grid has **401 uniformly spaced reference angles** from 22.19° to 80° and **481 uniformly spaced ray angles** from 22.19° to 270°. Retaining only $\theta\geq\beta$ leaves **170,233 pairs**. Each retained pair has equal weight. This design specifies the reported distribution: it is neither uniform in shoreline arclength nor a random sample of field beaches. The 270° extent is a comparison setting; the graphical application's default limit is 150°.

For an optional dimensionless percentage comparison, the symmetric denominator is:

$$ P_{\mathrm{sym}}=\frac{200\Delta r}{|r_{\mathrm O}|+|r_{\mathrm H}|} $$

Percentage values are omitted where the denominator is below 0.02. This prevents unstable ratios near small radii, but it does not convert the difference into prediction error. Percentages stated as fractions of $R_b$ below use the nominal control radius, not the local radius. A radial separation is not generally the perpendicular or nearest-point distance between two shorelines.

### 8.2 Principal radial results

The following statistics reproduce the comparison on the specified 270° grid.

| Statistic | Normalized radial difference |
|---|---:|
| Mean signed difference | 0.002529499840 |
| Root-mean-square difference | 0.005190810776 |
| Mean absolute difference | 0.002883158160 |
| Median signed difference | 0.001614509685 |
| 95th percentile of absolute difference | 0.011622073198 |
| Maximum sampled absolute difference | 0.046591950497 |

| Agreement threshold | Retained grid points |
|---|---:|
| $\lvert\Delta r\rvert\leq0.01$ | 93.9771% |
| $\lvert\Delta r\rvert\leq0.02$ | 98.4233% |

The positive mean indicates a slightly larger Oliveira radius on average under this grid weighting. The RMS difference is approximately **0.5191% of $R_b$**. For an illustrative $R_b=100$ m, it corresponds to 0.5191 m, and the mean absolute difference corresponds to 0.2883 m. These dimensional examples rescale the numerical comparison; they are not measured shoreline errors or accuracy guarantees. The models share the framework described by Hsu and Evans (1989) and Oliveira and Barreiro (2010).

A separate extrema check evaluates 20,001 reference angles. For each fixed angle, it checks the interval endpoints in $q$ and the internal stationary point of the quadratic difference where that point lies within the interval:

$$ q_*=-\frac{\Delta C_1}{2\Delta C_2},\qquad \Delta C_2\ne0 $$

The relevant interval is $\beta/270\leq q\leq1$. This produces a checked minimum $\Delta r\approx-0.001495555329$ near $\beta=28.696516^{\circ}$, $\theta=58.595713^{\circ}$, and a checked maximum $\Delta r\approx0.046598593141$ at $\beta=\theta=80^{\circ}$. The latter corresponds to **4.6599 m for $R_b=100$ m**. Because $\beta$ remains sampled, this procedure is not a certified continuous two-dimensional global optimization.

### 8.3 Coefficient differences and endpoint effects

**Full-precision coefficient comparison.** The following tables place the source-code polynomial coefficients side by side at equal powers of $\beta$ (degrees). They are intended for traceability; direct subtraction of coefficients is not equivalent to comparing predicted radii, because the radius includes $q$ and $q^2$ weights. The numerical observation sets and the supported angle intervals differ between the two fits. Oliveira and Barreiro (2010); Hsu and Evans (1989).

**Polynomial $C_0(\beta)$ — stored coefficients.**

| Power $k$ | Oliveira2010 $a_{0,k}$ | Hsu1989 $a_{0,k}$ |
|---:|---:|---:|
| 0 | 8.9379927134888931e-02 | -2.5948717948720286e-02 |
| 1 | -7.4010747230969986e-03 | 9.4371469397480281e-03 |
| 2 | 5.0128072495406347e-04 | -4.0811322978137366e-04 |
| 3 | -1.3097394953416148e-05 | 1.0108930697786255e-05 |
| 4 | 1.1423122564951566e-07 | -1.7860566448803580e-07 |
| 5 | -5.2045195736435901e-10 | 1.1488449630866086e-09 |
| 6 | 1.6282762116787805e-12 | -1.3026029125105853e-12 |

**Polynomial $C_1(\beta)$ — stored coefficients.**

| Power $k$ | Oliveira2010 $a_{1,k}$ | Hsu1989 $a_{1,k}$ |
|---:|---:|---:|
| 0 | 8.8162348805414326e-01 | 1.3292717948718358e00 |
| 1 | 1.5146321651759101e-02 | -6.5720015956185304e-02 |
| 2 | -6.9703159306350117e-04 | 4.6454080433615905e-03 |
| 3 | 1.6757848070587428e-05 | -1.5110565213940694e-04 |
| 4 | 4.1151569864693824e-08 | 2.7247346369948383e-06 |
| 5 | -2.8320953879636758e-09 | -2.3730284988490486e-08 |
| 6 | 1.5079413405730286e-11 | 7.7202155716091587e-11 |

**Polynomial $C_2(\beta)$ — stored coefficients.**

| Power $k$ | Oliveira2010 $a_{2,k}$ | Hsu1989 $a_{2,k}$ |
|---:|---:|---:|
| 0 | 1.8740249891403760e-02 | -2.9170512820513572e-01 |
| 1 | -7.3238336183188302e-03 | 5.4566218941018596e-02 |
| 2 | 2.6842398440550411e-04 | -4.1688146498725922e-03 |
| 3 | -1.0866508661427859e-05 | 1.4006101055807072e-04 |
| 4 | 7.9276852802049855e-08 | -2.5540727510077560e-06 |
| 5 | 9.9295446608229346e-11 | 2.2867190600936895e-08 |
| 6 | -2.6583961939866272e-13 | -7.7541566334136543e-11 |

On the 401 reference-angle nodes, the coefficient differences are:

| Metric | $C_0$ | $C_1$ | $C_2$ |
|---|---:|---:|---:|
| Mean difference | 0.0012738055426 | 0.0024151876475 | 0.0011102429114 |
| RMS difference | 0.0018517239012 | 0.010855007036 | 0.0045800166186 |
| Max. abs. dif. | 0.0036729105071 | 0.050678229363 | 0.0084715450272 |

The linear-ratio coefficient has the largest absolute inter-model variation, but the actual shoreline radius depends on all three weighted terms. At $\beta=\theta=80^{\circ}$, the endpoint ratios are approximately 1.06060 for Oliveira and 1.01400 for Hsu, accounting for the largest checked separation. The nominal $E$ point remains identical in this comparison. Moving $E$, renormalizing coefficients, or snapping endpoints would answer a different numerical question. Data ancestry: Oliveira and Barreiro (2010); Hsu and Evans (1989).

On the retained 270° grid, the raw normalized radii range from approximately 0.08175055 to 1.06048421 for Oliveira and 0.06735498 to 1.01389226 for Hsu. Neither produces a negative radius on those sampled nodes; 400 Oliveira nodes and 136 Hsu nodes exceed one. Those maxima differ slightly from the exact $\theta=\beta=80^{\circ}$ evaluations because the rectangular grid does not include every reference ray. A negative $C_0$ alone does not imply a negative complete radius. At sufficiently extended ray angles, however, finite negative radii can occur, and Baycraft retains them in the Cartesian calculation.

### 8.4 Comparison at the default angular extent

A second calculation uses the same 401 reference angles with 481 ray-angle nodes from 22.19° to **150°**, retaining 149,150 pairs. It samples the angular domain associated with the default limit, rather than using the GUI's five-degree sampling step. It is a separately defined comparison and should not be combined with the 270° statistics.

| Statistic | 150° domain | 270° domain |
|---|---:|---:|
| Retained pairs | 149,150 | 170,233 |
| Mean signed difference | 0.002759673383 | 0.002529499840 |
| RMS difference | 0.006102828300 | 0.005190810776 |
| Mean absolute difference | 0.003220847945 | 0.002883158160 |
| 95th percentile abs. dif. | 0.013436891179 | 0.011622073198 |
| Maximum sampled abs. dif. | 0.046471250377 | 0.046591950497 |
| Within $0.01R_b$ | 93.6071% | 93.9771% |
| Within $0.02R_b$ | 97.0332% | 98.4233% |

The 150° RMS is approximately **0.6103% of $R_b$**. The difference between the two aggregate RMS values reflects both the angular extent and the distribution of retained nodes. A larger comparison domain can lower the average difference when it adds many rays with smaller separation. Neither statistic describes all possible choices of angles or a site's actual distribution of shoreline positions.

### 8.5 Scientific conclusions from the comparison

**Overall agreement is close on the specified common domain, with localized differences reaching about 4.66% of the control radius.** Most sampled radii agree within one or two percent of that radius, while the largest checked separation occurs near the high-angle reference ray. A mean or RMS value alone would conceal that endpoint effect. These conclusions follow from the defined numerical experiment, whose empirical source material is Oliveira and Barreiro (2010) and Hsu and Evans (1989).

**Oliveira's smaller coefficient-fit residuals do not establish better shoreline prediction.** Its fit uses a different table, more observations, different angular coverage, and differently rounded inputs. Both parameterizations share the parabolic equation and related empirical ancestry. Their agreement is useful for sensitivity analysis, but is not independent validation against coastlines. The default identifies the application's initial selection, rather than a universal scientific ranking. Oliveira and Barreiro (2010); Hsu and Evans (1989).

**The comparison applies only where both coefficient sets are defined.** Hsu alone covers $10^{\circ}\leq\beta<22.19^{\circ}$, while Oliveira alone covers $80^{\circ}<\beta\leq88.29^{\circ}$. No direct two-model statistics are asserted on those nonoverlapping intervals. In particular, the larger Oliveira endpoint defect near 88.29° remains important even though it is absent from the shared-domain comparison. Oliveira and Barreiro (2010, Table 1); Hsu and Evans (1989, Table 2).

**Field assessment requires a separate observation-based comparison.** The analyst must evaluate representative wave conditions, control placement, sediment exchange, shoreline datum, and seasonal state. Published studies identify substantial sensitivity to these choices, but the present numerical comparison does not quantify their uncertainty relative to the coefficient differences. A claim that one uncertainty source dominates another would require a site-specific calculation. Lausman, Klein, and Stive (2010a, 2010b); Jackson and Cooper (2010); Oliveira and Barreiro (2010).

## 9. Image geometry, sampling, and wave bearing

### 9.1 Three-control construction

The graphical construction uses three source-image points: $H$ at the effective diffraction origin, $E$ at the downcoast reference point, and $W$ to define the directed wave-crest line from $E$. Coordinates are finite pixel coordinates with positive $x$ rightward and positive $y$ downward. These controls encode the polar geometry underlying the parabolic equation. Hsu and Evans (1989); Oliveira and Barreiro (2010).

Define:

$$ \mathbf u=E-H,\qquad \mathbf v=W-E,\qquad R_b=\sqrt{u_x^2+u_y^2} $$

The implemented reference angle is:

$$ \beta=\frac{180}{\pi}\,\mathrm{atan2}\left(|u_xv_y-u_yv_x|,-\mathbf u\cdot\mathbf v\right) $$

The directed crest convention matters. Placing $W$ on the opposite side of $E$ can replace $\beta$ by its supplementary angle, even though the undirected line appears unchanged. The application requires distinct $H$ and $E$, distinct $E$ and $W$, finite inputs, and a reference angle within the selected model's coefficient interval. The interval check permits a numerical tolerance of $10^{-9}$ degree at a boundary. This is an implementation of the crest-based geometry of Hsu and Evans (1989), rather than a mechanism for inferring wave conditions from an image.

### 9.2 Ray sampling and Cartesian coordinates

Let the control-line orientation in source-image coordinates be $\phi$, and let $s$ select the side of the construction:

$$ \phi=\mathrm{atan2}(u_y,u_x),\qquad s=\mathrm{sign}(u_xv_y-u_yv_x) $$

For increment $\Delta\theta$ and maximum angle $\theta_{\max}$, the sampled angles and Cartesian ray orientations are:

$$ \theta_k=\beta+k\Delta\theta,\qquad \psi_k=\phi+s(\theta_k-\beta)\frac{\pi}{180} $$

The corresponding source point is:

$$ P_k=H+R(\theta_k)(\cos\psi_k,\sin\psi_k) $$

The sample index runs from zero to:

$$ K=\max\left(0,\left\lfloor\frac{\theta_{\max}-\beta}{\Delta\theta}+10^{-12}\right\rfloor\right) $$

The implementation retains at least the initial sample after its boundary-tolerance checks. The default increment is **5 degrees** and the default limit is **150 degrees**. The increment must be positive and finite, and the limit must be finite and no smaller than $\beta$ within a $10^{-10}$-degree comparison tolerance. The maximum count is 100,000 samples. A sample is not appended merely to force the final angle to equal the limit.

The application preserves full-precision source points and radii before rounding drawing coordinates to integer pixels. Drawing uses nearest-integer, ties-to-even rounding and checks coordinate bounds. Numerical comparisons should use the full-precision source points rather than the displayed pixels. Reducing the increment samples the same mathematical curve more densely; it does not improve the empirical coefficient data or the selected coastal controls. Hsu and Evans (1989); Oliveira and Barreiro (2010), as implemented by the stated sampling rule.

The angular limit controls mathematical continuation. The program does not infer a maximum physically sandy sector, append the straight branch, suppress a negative finite radius, or classify a long-angle result as physically plausible. A negative radius reverses the Cartesian direction of the corresponding polar point. Any such continuation must be interpreted with the actual headland and shoreline setting. Hsu and Evans (1989, Fig. 3, pp. 563–564).

### 9.3 Wave FROM bearing

The crest direction is $\mathbf v$. A perpendicular in source-image coordinates is:

$$ \mathbf n=(-v_y,v_x) $$

The software reverses $\mathbf n$ if its dot product with $H-E$ is negative, selecting the normal toward the diffraction-point side. It then reports the wave **FROM** bearing:

$$ B=\left[\frac{180}{\pi}\,\mathrm{atan2}(n_x,-n_y)\right]\bmod360^{\circ} $$

This convention gives north as 0°, east as 90°, south as 180°, and west as 270°. The bearing is undefined when $E=W$, or when $H$ lies on or numerically too close to the crest line for its side to be determined. The convention assumes the original source image is north-up. Rotating the display changes the view, not the source coordinate frame or reported bearing. A north-up requirement for this software's bearing calculation should not be generalized to all coastal imagery, which can instead be analyzed with an explicitly transformed coordinate system. The physical distinction between crest and wave orthogonal follows Hsu and Evans (1989).

## 10. Calibration, coordinates, and measurements

### 10.1 Scale calibration

A two-point calibration assigns a known distance $L$ in metres to a displayed separation $d_{\mathrm{screen}}$ at zoom $z$ percent:

$$ p=\frac{L}{d_{\mathrm{screen}}}\frac{z}{100} $$

The resulting $p$ is metres per **source-image pixel**, not metres per current display pixel. Changing the zoom therefore does not change stored metric distances. Calibration requires a finite positive scale, with the implementation accepting $p\geq10^{-12}$ m per pixel. Accurate image scale and geometric rectification remain analytical inputs: a precise pixel measurement cannot compensate for a distorted photograph. The importance of reliable observed geometry follows the field applications of Oliveira and Barreiro (2010) and Jackson and Cooper (2010).

### 10.2 Local metric coordinates and one-point georeferencing

With calibration but no geographic anchor, metric coordinates are local image coordinates:

$$ X=px,\qquad Y=py $$

Their positive $Y$ direction is downward. They have metre units but are not automatically eastings and northings. If one source pixel $(x_0,y_0)$ is assigned metric map coordinates $(X_0,Y_0)$, the application uses:

$$ X=X_0+p(x-x_0),\qquad Y=Y_0-p(y-y_0) $$

The inverse mapping used for coordinate entry is:

$$ x=x_0+\frac{X-X_0}{p},\qquad y=y_0-\frac{Y-Y_0}{p} $$

This is a north-up, uniform-scale mapping with one known anchor. It does not determine a coordinate reference system, infer an EPSG identifier, transform a datum, convert latitude and longitude, estimate skew, fit an affine transformation, or orthorectify the image. The analyst supplies appropriate projected metric coordinates and an already suitable image. These implementation limits preserve the distinction between a geometric overlay and the preparation of geospatial observations needed for field analysis. Oliveira and Barreiro (2010).

### 10.3 Polygon and distance measurements

For a closed polygon with $N$ source-image vertices and cyclic indices, the area is computed by the shoelace formula:

$$ A=\frac{p^2}{2}\left|\sum_{j=0}^{N-1}(x_jy_{j+1}-x_{j+1}y_j)\right| $$

Its perimeter is:

$$ P=p\sum_{j=0}^{N-1}\sqrt{(x_{j+1}-x_j)^2+(y_{j+1}-y_j)^2} $$

For a two-point Measure object:

$$ d=p\sqrt{(x_B-x_A)^2+(y_B-y_A)^2} $$

These are planar measurements in the supplied image scale. A polygon between two shoreline traces can represent a planform area for the analyst's chosen construction, but it does not provide an erosion or nourishment volume. Volume requires additional profile and bathymetric information, and its time evolution requires a sediment budget. Hsu and Evans (1989); González, Medina, and Losada (2010).

## 11. Installation and execution

### 11.1 Python application

`baycraft.py` requires **Python 3.10 or newer**, Tkinter, and Pillow for the graphical image workflow. Tkinter is normally included with standard Windows Python distributions; some Linux distributions provide it through a separate `python3-tk` package. Pillow is the application's only nonstandard Python package. NumPy and SciPy are not runtime requirements. The numerical coefficient arrays are already stored in the program.

From the source directory in PowerShell:

```powershell
python --version
python -m tkinter
python -m pip install Pillow
python .\baycraft.py
```

The Tkinter command opens a small diagnostic window. The final command starts the Baycraft interface. To open an existing project directly:

```powershell
python .\baycraft.py .\my_bay.bay
```

If only a small Tk diagnostic window appears, check that the command being executed is the application command above. Tkinter's diagnostic and the Baycraft program are separate entry points. For a missing module or startup exception, run the application from a terminal so its actual error message remains visible.

### 11.2 Windowless numerical calculation

The calculation interface accepts one JSON argument. The following JSON examples use **PowerShell 7.3 or newer**, with Standard or Windows native-argument passing, so embedded quotation marks reach the executable correctly. Windows PowerShell 5.1 and Legacy argument passing require different escaping; the Bash examples in Section 11.5 provide an alternative. See Microsoft's [native-argument parsing documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing). The here-string uses the default model explicitly:

```powershell
$case = @'
{
  "h": [0, 0],
  "e": [100, 0],
  "w": [0, 100],
  "increment": 10,
  "limit": 150,
  "model": "Oliveira2010"
}
'@
python .\baycraft.py --calculate $case
```

To evaluate the same controls with the alternative parameterization:

```powershell
python .\baycraft.py --calculate $case --model Hsu1989
```

An explicit `--model` overrides the model in the JSON. The accepted identifiers are `Oliveira2010` and `Hsu1989`, and omission of both selections uses Oliveira2010. The coordinate pairs `h`, `e`, and `w` are required and must contain finite numbers. The optional `increment` defaults to 5 and `limit` to 150. Run `python .\baycraft.py --help` for the command-line options. Windowless calculation creates no GUI window, but Tkinter must still be importable because the module imports it at startup.

The core JSON output has the following meanings:

| Field | Meaning and unit |
|---|---|
| `beta` | Reference angle in degrees |
| `rb` | Nominal control radius in source pixels |
| `orientation_deg` | Control-line image orientation in degrees |
| `model` | Selected coefficient identifier |
| `coefficients` | Evaluated $C_0,C_1,C_2$ |
| `wave_direction_deg` | North-up wave FROM bearing in degrees |
| `theta` | Sampled ray angles in degrees |
| `radii` | Sampled radii in source pixels |
| `source_points` | Full-precision source pixel coordinates |
| `points` | Drawing pixels or georeferenced metres |

Metric point output requires **all three** fields `pixel_size`, `reference_pixel`, and `reference_xy`. A partial triplet is rejected. For example:

```powershell
$geo = @'
{
  "h": [0, 0],
  "e": [100, 0],
  "w": [0, 100],
  "pixel_size": 1,
  "reference_pixel": [0, 0],
  "reference_xy": [500000, 4600000]
}
'@
python .\baycraft.py --calculate $geo
```

With that triplet, `points` contains full-precision metric coordinate pairs and the result adds `coordinate_system` and `points_unit` metadata. **The fields `rb` and `radii` remain in source-image pixels**, and `source_points` remain full-precision pixel coordinates. Multiply a pixel radius by `pixel_size` to obtain metres. Without the triplet, `points` are rounded drawing pixels; use `source_points` for numerical analysis.

### 11.3 Rust application and toolchain

`baycraft.rs` is a single-file Rust 2021 program using the standard library and native Windows DLLs. No external crates or Cargo manifest are required. The graphical interface uses Win32 controls, GDI/GDI+, and native common dialogs. The intended native GUI platform is **Windows 10/11 x64**, built in the **MSYS2 UCRT64** environment with the GNU Windows target. Non-Windows builds provide the numerical command-line interface.

Use a suitable current stable Rust compiler. Edition 2021 alone does not specify the availability of every standard-library method used by the source: for example, [slice.as_chunks](https://doc.rust-lang.org/std/primitive.slice.html#method.as_chunks) is available from Rust 1.88.0. The [MSYS2 environment documentation](https://www.msys2.org/docs/environments/) identifies UCRT64's compiler prefix and runtime environment. Use the UCRT64 compiler and linker consistently.

Install [MSYS2](https://www.msys2.org/), open **MSYS2 UCRT64**, and run:

```bash
pacman -Syu
pacman -S --needed base-devel \
  mingw-w64-ucrt-x86_64-toolchain \
  mingw-w64-ucrt-x86_64-rust
echo "$MSYSTEM"
command -v rustc
command -v gcc
rustc -vV
```

Reopen the UCRT64 terminal and complete the update if the package manager requests it. Expect `UCRT64`, compiler paths under `/ucrt64/bin`, and Rust host `x86_64-pc-windows-gnu`. Change to the directory containing the source; for example, Windows `C:\baycraft` is `/c/baycraft` in this shell.

### 11.4 Windows build commands

For a portable x86-64 CPU baseline:

```bash
rustc --edition=2021 --target x86_64-pc-windows-gnu \
  -C linker=gcc -C opt-level=3 -C target-cpu=x86-64 \
  -C prefer-dynamic=no baycraft.rs -o baycraft.exe
./baycraft.exe
```

For a CPU-specific optimized build:

```bash
rustc --edition=2021 --target x86_64-pc-windows-gnu \
  -C linker=gcc -C opt-level=3 -C codegen-units=1 \
  -C lto=fat -C target-cpu=native -C prefer-dynamic=no \
  -C panic=unwind -C strip=symbols \
  baycraft.rs -o baycraft.exe
```

The native CPU target can use instructions unavailable on other machines. The portable target is therefore appropriate when distributing to a broader x64 audience. The `prefer-dynamic=no` option does not guarantee static linkage of every MinGW support library. Inspect the resulting executable's imports:

```bash
objdump -p baycraft.exe | grep -i 'DLL Name'
```

Normal Windows system libraries such as USER32, GDI32, GDIPLUS, and COMDLG32 are provided by the operating system. Resolve any additional deployment dependencies revealed by the import inspection.

For a diagnostic build with a console:

```bash
rustc --edition=2021 --target x86_64-pc-windows-gnu \
  --cfg 'feature="debug_console"' -C linker=gcc \
  -C debuginfo=1 -C opt-level=0 \
  baycraft.rs -o baycraft_debug.exe
./baycraft_debug.exe
```

Startup diagnostics are also recorded in `%TEMP%\baycraft_startup.log`. The normal GUI executable uses the Windows subsystem and does not provide a regular terminal window.

### 11.5 Rust numerical interface

For a Windows console program with no image GUI:

```bash
rustc --edition=2021 --target x86_64-pc-windows-gnu \
  --cfg 'feature="headless"' -C linker=gcc -C opt-level=3 \
  baycraft.rs -o baycraft_cli.exe
case_json='{
  "h": [0, 0],
  "e": [100, 0],
  "w": [0, 100],
  "increment": 10,
  "limit": 150,
  "model": "Oliveira2010"
}'
./baycraft_cli.exe --calculate "$case_json"
./baycraft_cli.exe --calculate "$case_json" --model Hsu1989
```

The regular Windows GUI build also accepts `--calculate JSON`. Use a headless or diagnostic console build for terminal JSON workflows. On a non-Windows host:

```bash
rustc --edition=2021 -C opt-level=3 baycraft.rs -o baycraft
./baycraft --calculate "$case_json"
```

Both numerical interfaces use the coordinate fields and unit conventions described in Section 11.2, including the complete georeference triplet and source-pixel radii. Their scientific model selection and numerical outputs are separate from the platform-specific graphical rendering.

## 12. Graphical workflow and analytical outputs

### 12.1 Project setup and curve construction

The main window is sized to the available work area at startup and is nonresizable. Toolbars, the object list, and property panels use fixed layout dimensions. Model selection changes the numerical interpretation of curves without requiring the analyst to reposition the interface. Image zoom, panning, and display rotation remain view operations.

1. Import a suitable map, orthophoto, or satellite image. Use a rectified, uniformly scaled, north-up source when relying on the application's map-coordinate and bearing conventions.
2. Select **Scale**, click two points with known separation, and enter that distance in metres.
3. If map coordinates are required, select **Georeference**, click a known image position, and enter its projected metric coordinates.
4. Choose **Oliveira2010** or **Hsu1989**. Oliveira2010 is the default model.
5. Select **Parabola** and click **H**, **E**, then **W**. Refine the three controls by dragging their handles or entering coordinates.
6. Use the curve's angular increment, angular limit, and line-width fields, then **Apply**. The default line width is 5 pixels. Use **Color** for its line color.
7. Add **Polygon** or **Measure** objects as needed, inspect **Results**, and save the project.

Object labels are generated from separate Parabola, Polygon, and Measure counters. Visible curves show their control geometry and the H, E, and W labels. A visible georeference anchor is labeled G. Curves whose angles fall outside a selected model's range require an appropriate model or revised control geometry before numerical results can be produced.

The workflow supplies a geometric overlay. Choosing controls to closely trace one waterline is not a substitute for documenting why those points represent the diffraction and wave conditions. Field studies emphasize control ambiguity, geological confinement, and sediment-budget context. Jackson and Cooper (2010); Lausman, Klein, and Stive (2010a); Oliveira and Barreiro (2010).

### 12.2 Editing and navigation

Polygon entry finishes with a double-click or Enter. A Measure object takes two clicks. Selected objects show red handles for editing. Double-clicking near a selected polygon edge inserts a vertex, and the context menu permits appropriate vertex actions while retaining at least three vertices. Coordinate dialogs accept finite values in the applicable local or map system, and large vertex tables scroll.

Pan with the Pan tool and left drag, or with a middle-button drag. Ctrl plus the mouse wheel adjusts zoom in ten-percentage-point steps within the supported range of 10–500%. The Zoom tool zooms in on click and out on Shift-click. The wheel scrolls vertically. **Fit** adjusts the image view and resets display rotation to zero. Escape cancels pending drawing and drag actions, clears selection, and returns to Select.

| Shortcut | Action |
|---|---|
| Ctrl+N | New project |
| Ctrl+O | Open project |
| Ctrl+I | Import image |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+P | Print |
| Escape | Cancel pending action and return to Select |
| Delete | Delete selected object when not editing text |
| Enter | Finish polygon entry |

Undo and redo retain up to 100 history states. Display zoom and rotation do not modify the source geometry, calibrated distances, or wave bearing. Importing another image retains the objects but resets calibration and georeferencing, so their suitability for the new source must be reassessed.

### 12.3 Project persistence

The **.bay** project is self-contained JSON with format identifier **4**. It stores model selection, source geometry, styles, visibility, object numbering, source-pixel scale, optional geographic anchor, view settings, and an embedded RGB PNG image. Project name metadata follows the save filename. Saving writes through a temporary file and atomically replaces the destination after flushing the data.

Save the project to preserve the analytical state and background image together. A raster export records a view, while the project retains editable controls and full numerical geometry. These products serve different parts of a reproducible analysis. The general need to preserve assumptions alongside overlays is consistent with the software-assessment framework of Klein et al. (2003) and Raabe et al. (2010).

### 12.4 Results and the technical report

**Results requires a defined scale.** It attempts to write a UTF-8 `output.txt` technical report whether or not an object is selected. A selected valid curve opens its summary and sampled-coordinate table; a selected polygon shows area, perimeter, and vertices; a selected Measure shows its distance and endpoints. With no selection, or when a selected curve has no valid model result, the complete report window is available.

The complete text report includes curve and polygon objects, including hidden objects. Measure objects have their graphical result dialogs but are not sections in that complete report. It contains model and fit provenance, evaluated curve coefficients, control coordinates, reference angles and radii, wave FROM bearings, sampled radii and coordinates, and polygon measurements. The complete global polynomial arrays and regression statistics are documented in this README rather than repeated for every object.

The preferred destination is the saved project's directory, or the working directory for an unsaved project. Fallback locations include the working directory, the script or executable directory, and a temporary directory. An alternate destination is reported, and the GUI report remains available if writing fails. **Copy Table** and **Copy Report** place the displayed text on the clipboard. Displayed tables commonly use two decimal places; the underlying numerical arrays retain full precision.

### 12.5 Image export and printing

Image import supports JPG/JPEG, PNG, BMP, TIF/TIFF, and GIF through the corresponding image stack. Export supports PNG, JPEG, and TIFF, with PNG as the default. It requires an imported image and otherwise performs no export. The raster includes visible objects and their control labels, omits selection handles, and follows the current display zoom and rotation. The output is RGB, with a maximum rendered size of 100 million pixels.

The print workflow uses a prepared image. Windows hands that image to the native printing workflow; the non-Windows Python path provides the prepared image location. A raster export is not a GIS vector dataset and does not replace the .bay project or numerical coordinates. Document the shoreline source, map frame, and export scale when using the image in a scientific or engineering report. Oliveira and Barreiro (2010); Klein et al. (2003).

## 14. Interpretation, uncertainty, and reporting

### 14.1 Observed shoreline and representative conditions

A modeled line should be compared with an observed shoreline whose definition is explicit: instantaneous waterline, a tidal datum, vegetation edge, berm feature, or another mapped indicator. Image date, tide, wave run-up, seasonal beach state, and shoreline extraction method affect the comparison. The October timing of the Portuguese imagery is part of the explanation for its reported agreement and cannot be detached from the field conclusion. Oliveira and Barreiro (2010).

Wave direction should be justified from the conditions relevant to the intended time scale and active coastal geometry. Where a broad or changing directional climate is important, alternative crest orientations and more complete wave-climate methods are appropriate. A single-direction static overlay does not determine the response to every wave event or the time needed for planform adjustment. Hurst et al. (2015); El-Shinnawy, Medina, and González (2017).

The diffraction control may be ambiguous around irregular rock, islands, reefs, structures, or a reach with limited sand. A model mismatch can reflect those controls, sediment scarcity or excess, inappropriate wave orientation, or an unsuitable equilibrium assumption. A close fit can also arise from flexible control placement. Both outcomes should be treated as hypotheses requiring independent coastal evidence. Jackson and Cooper (2010); Lausman, Klein, and Stive (2010a).

### 14.2 Three distinct meanings of accuracy

**Numerical reproduction** concerns whether a calculation evaluates the specified polynomial and geometry consistently. Retaining the full arrays, degree convention, sampling rule, and source-point precision makes that question reproducible. **Coefficient approximation** concerns how closely the fitted functions reproduce their selected table values. **Physical predictive skill** concerns agreement with independent coastal observations under justified conditions. The tables in Sections 5 and 6 address coefficient approximation; Section 8 addresses sensitivity between parameterizations; neither provides a site-specific physical error distribution. Hsu and Evans (1989); Oliveira and Barreiro (2010).

The large number of stored digits is useful for reproducibility, including cancellation between polynomial terms. It should not be reported as an equally fine shoreline accuracy. Source rounding, high-angle endpoint nonclosure, image uncertainty, scale error, wave assumptions, and control placement remain separate components of the analysis. In particular, tighter polynomial regression residuals cannot remove a closure discrepancy already present in a source parameter set. Oliveira and Barreiro (2010, Table 1); Hsu and Evans (1989, Table 2).

### 14.3 Practical sensitivity analysis

Repeat the construction for plausible diffraction points, downcoast references, and wave-crest orientations. Record each control set and the physical reason for choosing its range. Where both models are defined, compare their curves using identical controls before changing the geometry. Report both local departures and aggregate statistics, since a small average can coexist with a substantial endpoint difference. Control-placement studies demonstrate the importance of this procedure but do not supply a universal uncertainty band for a new site. Lausman, Klein, and Stive (2010a, 2010b).

For an observed-to-modeled comparison, choose and describe the distance measure. Radial distance along rays from $H$, offsets along fixed cross-shore transects, and nearest-point distances answer different questions. State the sign convention, the observed segment used, whether rocky or nonsandy sectors are excluded, and how points are weighted. Avoid interpreting an aggregate value outside its stated spatial and angular domain. The practical ambiguity of applying ideal planforms to natural bays is documented by Jackson and Cooper (2010) and Oliveira and Barreiro (2010).

Baycraft draws and reports geometry. It does not automatically delineate an observed shoreline, calculate observed-to-modeled offset statistics, propagate uncertainty, classify beach stability, solve the sediment budget, compute erosion rates, or predict nourishment volume. If those quantities are needed, combine the exported geometry with the appropriate observations and coastal-process analysis. Hsu et al. (2010); Raabe et al. (2010); González, Medina, and Losada (2010).

### 14.4 Equilibrium interpretation and temporal evidence

A geometrically static-looking bay can be in dynamic equilibrium, with continuing sediment throughput. Conversely, a departure from the ideal curve does not uniquely establish an unstable beach: local geology, sediment availability, an unrepresentative image, or a natural adjustment to changed controls may explain it. Silveira, Klein, and Tessler (2010) distinguish static, dynamic, unstable, and natural-reshaping states and explicitly identify the limitation of a single image set for assigning an instability class. Oliveira and Barreiro (2010) demonstrate why sediment exchange and seasonal timing matter.

The static curve describes a limiting planform under its assumptions. It is not a trajectory, an erosion deadline, a probability of failure, or a maximum storm-recession envelope. For coastal works, combine it with sediment budgets, cross-shore profiles, wave transformation, extreme-event assessment, and neighboring-shore impacts. Hsu and Evans (1989); Hsu et al. (2008, 2010); González, Medina, and Losada (2010).

### 14.5 Minimum reproducibility record

A scientific report using a Baycraft construction should retain the following information so that the numerical result and its physical interpretation can be assessed independently. These reporting elements follow the control-selection and uncertainty issues discussed by González and Medina (2001), Lausman, Klein, and Stive (2010a, 2010b), and Jackson and Cooper (2010).

- **Observation:** image source, acquisition date, resolution, rectification accuracy, shoreline indicator, extraction method, and relevant tidal or seasonal conditions.
- **Coordinate system:** calibration distance and points, metres per source pixel, supplied projected reference system, geographic anchor if used, and the north-up assumption for bearings.
- **Physical hypothesis:** diffraction control, downcoast reference, representative wave conditions, evidence about sediment supply and bypassing, and relevant geological confinement.
- **Numerical settings:** model identifier, all H/E/W coordinates, $\beta$, $R_b$, evaluated coefficients, endpoint defect, angular increment, and angular limit.
- **Comparison definition:** observed segment, offset convention, spatial weighting, exclusion rules, summary statistic, local extrema, and results for plausible alternative controls.
- **Retained outputs:** the .bay project, technical report, full-precision coordinate result when needed, and the visual overlay used in the interpretation.

## 15. Conclusions

Baycraft implements two reproducible coefficient parameterizations within a common parabolic bay-shape framework. **Oliveira2010 is the default model**, with all 48 fitted observations, its complete degree-six coefficients, expanded equations, and diagnostics. Hsu1989 provides the corresponding representation of the 15-row original table. The governing empirical equation and static-equilibrium interpretation originate with Hsu and Evans (1989); the Portuguese application and its parameter observations are documented by Oliveira and Barreiro (2010).

The degree-six regressions closely reproduce their selected coefficient data. The documented inter-model comparison also shows close average radial agreement over the shared reference-angle interval, together with a larger localized separation near $\beta=\theta=80^{\circ}$. Exact endpoint closure is absent from both numerical parameterizations, and Oliveira's full upper range contains substantially larger source-inherited closure departures. The relevant practical conclusions are therefore the domain of use, the actual curve geometry, and the endpoint residual as well as the regression statistics. These are numerical findings from the explicitly stated data and methods, rather than additional field results attributed to either source paper.

The field interpretation remains conditional on the coastal system. The Portuguese examples show that a dynamically exchanging beach can resemble a static-equilibrium shape at a particular seasonal stage. The original Hsu–Evans construction provides a limiting geometrical hypothesis whose engineering application requires sediment-volume, storm-response, and neighboring-coast considerations. A complete use of Baycraft couples reproducible geometry with evidence about those processes. Oliveira and Barreiro (2010); Hsu and Evans (1989).

## References and further reading

The first two references are the principal sources of the implemented coefficient data and shared planform framework. The remaining works support the physical context, alternatives, control selection, uncertainty, field applications, and wider engineering interpretation. Software fitting and comparison results in this document are identified as calculations on the stated datasets rather than as results published in these papers.

1. **Oliveira, F. S. B. F., and Barreiro, O. M. (2010).** Application of empirical models to bay-shaped beaches in Portugal. *Coastal Engineering*, **57**(2), 124–131. [DOI](https://doi.org/10.1016/j.coastaleng.2009.09.008). Primary source for the 42 Portuguese sites, Table 1 parameters, three-family planform comparison, and seasonal/dynamic-equilibrium interpretation.

2. **Hsu, J. R. C., and Evans, C. (1989).** Parabolic bay shapes and applications. *Proceedings of the Institution of Civil Engineers*, Part 2, **87**(4), 557–570. [DOI](https://doi.org/10.1680/iicep.1989.3778). Primary source for the parabolic equation, 15-row coefficient Table 2, crest-based geometry, and headland-control applications. It recommends linear interpolation between tabulated coefficient values.

3. **Hsu, J. R. C., Silvester, R., and Xia, Y.-M. (1989).** Static equilibrium bays: New relationships. *Journal of Waterway, Port, Coastal, and Ocean Engineering*, **115**(3), 285–298. [Publisher](https://ascelibrary.org/doi/10.1061/%28ASCE%290733-950X%281989%29115%3A3%28285%29). Related development of empirical static-bay relationships.

4. **LeBlond, P. H. (1979).** An explanation of the logarithmic spiral plan shape of headland-bay beaches. *Journal of Sedimentary Petrology*, **49**(4), 1093–1100. [DOI](https://doi.org/10.1306/212F78BA-2B24-11D7-8648000102C1865D). Physical background to logarithmic-spiral descriptions.

5. **Silvester, R. (1985).** Natural headland control of beaches. *Continental Shelf Research*, **4**(5), 581–596. [DOI](https://doi.org/10.1016/0278-4343(85)90013-5). Headland sheltering and limiting-indentation concepts.

6. **Hsu, J. R. C., Uda, T., and Silvester, R. (1993).** Beaches downcoast of harbours in bays. *Coastal Engineering*, **19**(1–2), 163–181. [DOI](https://doi.org/10.1016/0378-3839(93)90023-2). Harbour-control applications and adjacent shoreline response.

7. **Silvester, R., and Hsu, J. R. C. (1993).** *Coastal Stabilization: Innovative Concepts*. Prentice-Hall, Englewood Cliffs, New Jersey, 578 pp. Source attributed by Oliveira and Barreiro (2010) for fourth-order parabolic coefficient functions; distinct from Baycraft's sixth-degree regressions.

8. **Moreno, L. J., and Kraus, N. C. (1999).** Equilibrium shape of headland-bay beaches for engineering design. In *Proceedings of Coastal Sediments '99*, vol. 1, 860–875. American Society of Civil Engineers. [USACE publication catalogue](https://cirp.usace.army.mil/pubs/index.php). [Preserved original equation page](https://coastalinlets.tpub.com/cs99-moreno/cs99-moreno0006.htm). Includes the curved and straight branches and the hyperbolic-tangent approach.

9. **González, M., and Medina, R. (2001).** On the application of static equilibrium bay formulations to natural and man-made beaches. *Coastal Engineering*, **43**(3–4), 209–225. [DOI](https://doi.org/10.1016/S0378-3839(01)00014-X). [Author-institution manuscript compilation](https://smc.ihcantabria.es/SMC25/wp-content/uploads/2017/11/Documento-de-referencia_Volumen5.Apendices.pdf). Physical selection of the downcoast limit. The archived manuscript's Equations 16 and 19 clarify the radial relation discussed in Section 3.5.

10. **Klein, A. H. F., Vargas, A., Raabe, A. L. A., and Hsu, J. R. C. (2003).** Visual assessment of bayed beach stability with computer software. *Computers & Geosciences*, **29**(10), 1249–1257. [DOI](https://doi.org/10.1016/j.cageo.2003.08.002). Image-overlay assessment and its practical scope.

11. **Hsu, J. R. C., Benedet, L., Klein, A. H. F., Raabe, A. L. A., Tsai, C.-P., and Hsu, T.-W. (2008).** Appreciation of static bay beach concept for coastal management and protection. *Journal of Coastal Research*, **24**(1), 198–215. [DOI](https://doi.org/10.2112/05-0579.1). Coastal-management interpretation of limiting static shapes.

12. **Hsu, J. R. C., Yu, M. M.-J., Lee, F.-C., and Silvester, R. (2009).** Headland-bay beaches for recreation and shore protection. In Y. C. Kim (ed.), *Handbook of Coastal and Ocean Engineering*, chapter 29, 825–842. World Scientific. Applied headland-bay concepts for protection and recreational beach design.

13. **Hsu, J. R. C., Yu, M.-J., Lee, F.-C., and Benedet, L. (2010).** Static bay beach concept for scientists and engineers: A review. *Coastal Engineering*, **57**(2), 76–91. [DOI](https://doi.org/10.1016/j.coastaleng.2009.09.004). Review of physical scope and planform methods.

14. **Jackson, D. W. T., and Cooper, J. A. G. (2010).** Application of the equilibrium planform concept to natural beaches in Northern Ireland. *Coastal Engineering*, **57**(2), 112–123. [DOI](https://doi.org/10.1016/j.coastaleng.2009.09.007). Natural-control ambiguity, geological effects, and sediment scarcity or excess in nine embayments.

15. **Lausman, R., Klein, A. H. F., and Stive, M. J. F. (2010a).** Uncertainty in the application of the Parabolic Bay Shape Equation: Part 1. *Coastal Engineering*, **57**(2), 132–141. [DOI](https://doi.org/10.1016/j.coastaleng.2009.09.009). Empirical assessment of variation in placement of the three controls.

16. **Lausman, R., Klein, A. H. F., and Stive, M. J. F. (2010b).** Uncertainty in the application of the parabolic bay shape equation: Part 2. *Coastal Engineering*, **57**(2), 142–151. [DOI](https://doi.org/10.1016/j.coastaleng.2009.10.001). Companion treatment of application uncertainty.

17. **Silveira, L. F., Klein, A. H. F., and Tessler, M. G. (2010).** Headland-bay beach planform stability of Santa Catarina State and of the Northern Coast of São Paulo State. *Brazilian Journal of Oceanography*, **58**(2), 101–122. [DOI](https://doi.org/10.1590/S1679-87592010000200003). Regional planform assessment and the limitation of a single image set for instability classification.

18. **Raabe, A. L. A., Klein, A. H. F., González, M., and Medina, R. (2010).** MEPBAY and SMC: Software tools to support different operational levels of headland-bay beach in coastal engineering projects. *Coastal Engineering*, **57**(2), 213–226. [DOI](https://doi.org/10.1016/j.coastaleng.2009.10.008). Different roles of visual predesign tools and broader engineering analysis.

19. **González, M., Medina, R., and Losada, M. A. (2010).** On the design of beach nourishment projects using static equilibrium concepts: Application to the Spanish coast. *Coastal Engineering*, **57**(2), 227–240. [DOI](https://doi.org/10.1016/j.coastaleng.2009.10.009). Planform and profile considerations in nourishment design.

20. **Hurst, M. D., Barkwith, A., Ellis, M. A., Thomas, C. W., and Murray, A. B. (2015).** Exploring the sensitivities of crenulate bay shorelines to wave climates using a new vector-based one-line model. *Journal of Geophysical Research: Earth Surface*, **120**(12), 2586–2608. [DOI](https://doi.org/10.1002/2015JF003704). Directional wave climate, bay size, and response-time sensitivity in an evolving shoreline model.

21. **El-Shinnawy, A., Medina, R., and González, M. (2017).** Equilibrium planform of headland bay beaches: Effect of directional wave climate. *Coastal Dynamics 2017*, paper 020. [Conference PDF](https://coastaldynamics2017.dk/onewebmedia/020_Elshinnawy_Ahmed.pdf). Directional-wave-climate effects on equilibrium planform interpretation.