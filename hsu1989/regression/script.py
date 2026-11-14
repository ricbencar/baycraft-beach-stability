#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compact four-coefficient regression to ORIGINAL IMAGE-DIGITIZED CURVES ONLY.

Default selected equation (theta and beta in numerical DEGREES):
    r_ratio = A*beta / (theta**(4/5) *
              (1 + B*beta + (beta/C)**4*(1-exp(-(theta/D)**9))))
Four positive/nonnegative fitted coefficients: A, B, C and D.
The powers 4/5, 4 and 9 are structural constants, selected from finite candidate
sets, not additional continuously fitted coefficients. No anchoring at theta=beta.

Only the 152 original curve-stroke Y-pixel readings embedded below enter fitting.
Their coordinates and four-corner calibration are unchanged. No origin anchors,
interpolated reference curves, synthetic Hsu values, or data.txt are used.
This program reuses the stored digitization; it does not retrace image pixels.
The original JPG is used to check image geometry and render the calibrated overlay.

By default, test 288 four-parameter model forms: two damping functions, four
fixed theta powers, four beta powers and nine integer transition powers. Fit each
by bounded multistart nonlinear least squares and refine the best candidate.
This is a finite model-form search, not a proof over all possible equations.
--quick fits only the default selected form, retaining multistart refinement.
A leave-one-original-theta-profile-out check refits the four coefficients; the
selected form remains fixed. This is not nested model-selection validation.

Prediction grid: theta=30..270 step 10; beta=0..80 step 5 (425 combinations).
Reference entries exist ONLY at exact original digitized positions. Other grid
positions have predictions but blank references and residuals. No values are
clipped to improve errors. R(theta,0)=0 is a model identity, not a fitted anchor.

Install: python -m pip install numpy scipy matplotlib
Run:     python script_final.py
         python script_final.py --quick
         python script_final.py --figure4-image "hsu1989_figure 4.jpg"
         python script_final.py --output EXISTING_DIRECTORY --no-plots

All outputs are flat files in the script directory or an EXISTING --output path:
  output.txt, coefficients.json, predictions.tsv, search_coverage.tsv,
  profile_statistics.tsv, generated_reference.tsv, digitized_profiles.tsv,
  source_predictions.tsv, cross_validation.tsv, r_ratio_model.py,
  fit_results.png, fit_profiles.png, fit_error_analysis.png,
  fit_coefficient_sensitivity.png, fit_hsu1989_figure4_overlay.png.
No subdirectories are created. Image reading uncertainty limits the physical
meaning of small residuals; these are approximations to drawn curves, not an
independent validation with measured beaches.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

MODEL_LABEL = 'Four-coefficient image-curve approximation'
DEFAULT_THETA_MIN, DEFAULT_THETA_MAX, DEFAULT_THETA_STEP = 30., 270., 10.
DEFAULT_BETA_MIN, DEFAULT_BETA_MAX, DEFAULT_BETA_STEP = 0., 80., 5.
DEFAULT_SHAPE = ('stretched_exp', 0.2, 4, 9)
PARAMETER_NAMES = ('A', 'B', 'C', 'D')
LOWER_NORMALIZED = np.array([0.1, 0.0, 0.001, 0.3])
UPPER_NORMALIZED = np.array([5.0, 5.0, 30.0, 4.0])
START_NORMALIZED = np.array([1.43, 0.34, 3.0, 1.85])

FIGURE4_REFERENCE_SIZE = (731.0, 566.0)

FIGURE4_CORNERS = (
    (51.0, 463.5),   # beta=0,  R/R0=0
    (710.5, 464.0),  # beta=80, R/R0=0
    (49.5, 8.5),     # beta=0,  R/R0=1
    (710.0, 9.5),    # beta=80, R/R0=1
)

FIGURE4_X_RANGE = (0.0, 80.0)

FIGURE4_Y_RANGE = (0.0, 1.0)

FIGURE4_DIGITIZED_PIXEL_Y = {
  30: {5: 380, 10: 299, 15: 223, 20: 146, 25: 77, 30: 12},
  45: {5: 402, 10: 345, 15: 289, 20: 223, 25: 174, 30: 121, 35: 92, 40: 47},
  60: {5: 415, 10: 370, 15: 327, 20: 286, 25: 244, 30: 205, 35: 169, 40: 126, 45: 91, 50: 67, 55: 36, 60: 11},
  75: {5: 425, 10: 386, 15: 350, 20: 315, 25: 279, 30: 245, 35: 212, 40: 182, 45: 152, 50: 123, 55: 96, 60: 70, 65: 46, 70: 26},
  90: {5: 429, 10: 396, 15: 366, 20: 336, 25: 305, 30: 280, 35: 250, 40: 224, 45: 198, 50: 173, 55: 148, 60: 123, 65: 100, 70: 79, 75: 57, 80: 32},
  120: {5: 433, 10: 409, 15: 384, 20: 360, 25: 336, 30: 315, 35: 293, 40: 272, 45: 262, 50: 235, 55: 218, 60: 200, 65: 183, 70: 165, 75: 147, 80: 132},
  150: {5: 440, 10: 420, 15: 397, 20: 377, 25: 359, 30: 341, 35: 324, 40: 307, 45: 294, 50: 282, 55: 271, 60: 261, 65: 255, 70: 248, 75: 242, 80: 237},
  180: {5: 442, 10: 421, 15: 404, 20: 386, 25: 374, 30: 364, 35: 346, 40: 336, 45: 322, 50: 325, 55: 322, 60: 318, 65: 322, 70: 328, 75: 334, 80: 341},
  210: {5: 445, 10: 427, 15: 411, 20: 398, 25: 384, 30: 374, 35: 366, 40: 350, 45: 351, 50: 353, 55: 353, 60: 364, 65: 374, 70: 381, 75: 390, 80: 384},
  240: {5: 448, 10: 431, 15: 417, 20: 404, 25: 393, 30: 385, 35: 378, 40: 368, 45: 364, 50: 365, 55: 367, 60: 374, 65: 380, 70: 387, 75: 391, 80: 399},
  270: {5: 448, 10: 435, 15: 420, 20: 408, 25: 399, 30: 393, 35: 385, 40: 379, 45: 375, 50: 374, 55: 375, 60: 379, 65: 386, 70: 394, 75: 398, 80: 406},
}

def samples(lo,hi,step):
    if not np.isfinite([lo,hi,step]).all() or step<=0 or lo>hi:
        raise ValueError('Sample ranges must be finite, increasing and have positive steps.')
    count=int(np.floor((hi-lo)/step+1e-10))+1
    return lo+step*np.arange(count,dtype=float)

def validate(theta,beta,observed):
    if len(theta)!=len(beta) or len(theta)!=len(observed) or len(theta)<10:
        raise ValueError('Need at least ten observations and equal-length input columns.')
    if not all(np.isfinite(a).all() for a in (theta,beta,observed)):
        raise ValueError('Non-finite input or reference values.')
    if (theta<=0).any() or (beta<0).any():
        raise ValueError('Require theta>0, beta>=0 (angles are numerical degrees).')
    if np.unique(beta).size<4 or np.unique(theta).size<4:
        raise ValueError('Need at least four distinct theta and four beta angles.')

def stats(y,predicted):
    e=np.asarray(predicted,dtype=float)-np.asarray(y,dtype=float)
    sse=float(np.dot(e,e))
    sst=float(np.sum((y-np.mean(y))**2))
    return dict(SSE=sse,RMSE=float(np.sqrt(np.mean(e*e))),
                MAE=float(np.mean(np.abs(e))),MaxAE=float(np.max(np.abs(e))),
                R2=1-sse/sst if sst>0 else None)

def extra_statistics(y,predicted):
    e=np.asarray(predicted)-np.asarray(y)
    ae=np.abs(e)
    return dict(Bias=float(np.mean(e)),MedianAE=float(np.median(ae)),
                P90AE=float(np.percentile(ae,90)),P95AE=float(np.percentile(ae,95)),
                ResidualSD=float(np.std(e,ddof=1)),
                PositiveResiduals=int(np.sum(e>0)),NegativeResiduals=int(np.sum(e<0)),
                ZeroResiduals=int(np.sum(e==0)))

def profile_statistics(theta,beta,y,pred):
    rows=[]
    for angle in np.unique(theta):
        sel=np.isclose(theta,angle,atol=1e-10,rtol=0)
        e=pred[sel]-y[sel]
        s=stats(y[sel],pred[sel])
        rows.append(dict(theta=float(angle),N=int(sel.sum()),
                         RMSE=s['RMSE'],MAE=s['MAE'],MaxAE=s['MaxAE'],
                         Bias=float(np.mean(e)),MedianAE=float(np.median(abs(e))),
                         SSE=s['SSE']))
    return rows

def save_tsv(path,names,columns):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t');writer.writerow(names)
        for row in zip(*columns):
            writer.writerow([('' if isinstance(x,float) and not np.isfinite(x)
                              else f'{x:.15f}' if isinstance(x,(float,np.floating))
                              else x) for x in row])

def find_figure4_image(filename,base):
    if filename is not None:
        filename=Path(filename).expanduser().resolve()
        if not filename.is_file():
            raise FileNotFoundError(f'Hsu (1989) Figure 4 not found: {filename}')
        return filename
    for name in ('hsu1989_figure 4.jpg','hsu1989_figure4.jpg',
                 'hsu1989_figure 4(1).jpg','hsu1989_figure 4(2).jpg',
                 'hsu1989_figure4.png',
                 'hsu1989_figure 4.png'):
        path=base/name
        if path.is_file():return path.resolve()
    return None

def figure4_pixel_coordinates(beta,ratio,width,height):
    """Bilinear registration to the four actual corners of the scanned chart."""
    beta,ratio=np.asarray(beta,dtype=float),np.asarray(ratio,dtype=float)
    u=(beta-FIGURE4_X_RANGE[0])/(FIGURE4_X_RANGE[1]-FIGURE4_X_RANGE[0])
    v=(ratio-FIGURE4_Y_RANGE[0])/(FIGURE4_Y_RANGE[1]-FIGURE4_Y_RANGE[0])
    scale=np.array([width/FIGURE4_REFERENCE_SIZE[0],
                    height/FIGURE4_REFERENCE_SIZE[1]],dtype=float)
    bl,br,tl,tr=[np.asarray(c)*scale for c in FIGURE4_CORNERS]
    xx=((1-u)*(1-v)*bl[0]+u*(1-v)*br[0]+(1-u)*v*tl[0]+u*v*tr[0])
    yy=((1-u)*(1-v)*bl[1]+u*(1-v)*br[1]+(1-u)*v*tl[1]+u*v*tr[1])
    return xx,yy

def digitized_plot_samples(image_path):
    """Convert stored original curve-stroke pixel readings with the fixed calibration."""
    if image_path is None:
        raise FileNotFoundError('Figure 4 JPG required for digitized-plot regression.')
    from matplotlib.image import imread
    im=imread(str(image_path))
    height,width=im.shape[:2]
    # Scaling is permitted only for the identical scan resized uniformly.
    # A different scan or crop would require new corner calibration.
    if not np.isclose(width/height,731/566,rtol=.012):
        raise ValueError('Figure 4 aspect ratio differs from the calibrated 731x566 scan.')
    theta=[]; beta=[]; obs=[]; pixel_y=[]; method=[]
    for angle, readings in FIGURE4_DIGITIZED_PIXEL_Y.items():
        for b,y0 in [(0., None)]+sorted(readings.items()):
            if y0 is None:
                val=0.0
                yc=FIGURE4_CORNERS[0][1]
                status='common_graph_origin'
            else:
                # The original scanned chart has slightly skewed horizontal axes.
                # Invert the Y coordinate of its calibrated four-corner mapping.
                u=float(b)/80
                bottom=(1-u)*FIGURE4_CORNERS[0][1]+u*FIGURE4_CORNERS[1][1]
                top=(1-u)*FIGURE4_CORNERS[2][1]+u*FIGURE4_CORNERS[3][1]
                val=(bottom-float(y0))/(bottom-top)
                yc=float(y0)
                status='digitized_figure4_stroke'
            theta.append(float(angle));beta.append(float(b));obs.append(val)
            pixel_y.append(yc*height/566);method.append(status)
    theta,beta,obs=np.array(theta),np.array(beta),np.array(obs)
    validate(theta,beta,obs)
    return theta,beta,obs,np.array(pixel_y),method,(width,height)

def figure4_grid(theta_original,beta_original,observed,args):
    """Prediction grid; only EXACT image-digitized original pixels are references.

    Every unmatched theta/beta pair has a missing reference, never interpolated.
    The grid remains 25x17 by default for complete predictions and plotting.
    """
    th=samples(args.theta_min,args.theta_max,args.theta_step)
    be=samples(args.beta_min,args.beta_max,args.beta_step)
    if len(th)*len(be)>250_000:
        raise ValueError('Requested grid is too large.')
    t,b=np.meshgrid(th,be,indexing='ij');ts=t.ravel();bs=b.ravel()
    refs=np.full(len(ts),np.nan)
    status=np.full(len(ts),'prediction_only_no_original_image_point',dtype=object)
    for j,(angle,beta_value) in enumerate(zip(ts,bs)):
        match=np.flatnonzero((np.abs(theta_original-angle)<1e-9)&
                              (np.abs(beta_original-beta_value)<1e-9))
        if match.size:
            refs[j]=observed[match[0]]
            status[j]='directly_digitized'
    return ts,bs,refs,status

def normalized_prediction(theta, beta, parameters, shape):
    """Stable fitted-family evaluation in scaled coordinates, no observations added."""
    family, alpha, m, n = shape
    theta, beta = np.broadcast_arrays(np.asarray(theta, float), np.asarray(beta, float))
    if not np.isfinite(theta).all() or not np.isfinite(beta).all():
        raise ValueError('Angles must be finite.')
    if (theta <= 0).any() or (beta < 0).any():
        raise ValueError('Require theta > 0 and beta >= 0 (degrees).')
    a, b, c, d = np.asarray(parameters, float)
    t, u = theta / 100.0, beta / 80.0
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        if family == 'stretched_exp':
            gate = -np.expm1(-np.power(t / d, n))
        elif family == 'rational':
            # exp(log(t/d)*n) in logistic form avoids an overflowing (d/t)**n.
            log_ratio = n * np.log(t / d)
            gate = np.exp(-np.logaddexp(0.0, -log_ratio))
        else:
            raise ValueError(f'Unknown damping family: {family}')
        answer = a * (beta / theta) * t**alpha / (1.0 + b*u + c*u**m*gate)
    if not np.isfinite(answer).all():
        raise ValueError('Non-finite prediction; angles exceed a safe numeric range.')
    return answer


def to_raw(parameters, shape):
    """Convert normalized coefficients to four constants in the degree-valued formula."""
    _, alpha, m, _ = shape
    a, b, c, d = np.asarray(parameters, float)
    return np.array([a / 100.0**alpha, b / 80.0, 80.0 / c**(1.0/m), 100.0*d])


def to_normalized(parameters, shape):
    _, alpha, m, _ = shape
    a, b, c, d = np.asarray(parameters, float)
    return np.array([a * 100.0**alpha, b * 80.0, (80.0/c)**m, d/100.0])


def model(theta, beta, fit):
    shape = (fit['family'], fit['alpha'], fit['beta_power'], fit['transition_power'])
    return normalized_prediction(theta, beta, to_normalized(fit['selected_coefficients'], shape), shape)


def formula(fit, precision=12):
    a,b,c,d = fit['selected_coefficients']
    pp=1.0-fit['alpha'];m=fit['beta_power'];n=fit['transition_power']
    if fit['family']=='stretched_exp':
        gate=f'(1 - exp(-(theta/{d:.{precision}g})**{n}))'
    else:
        gate=f'(1/(1 + ({d:.{precision}g}/theta)**{n}))'
    return (f'r_ratio(theta,beta) = {a:.{precision}g}*beta / '
            f'(theta**{pp:.12g} * (1 + {b:.{precision}g}*beta + '
            f'(beta/{c:.{precision}g})**{m} * {gate}))')


def fit_form(theta, beta, observed, shape, starts=2, seed=17429, initial=None):
    """Bounded, reproducible multistart least squares; local optima only are claimed."""
    rng=np.random.default_rng(seed)
    center=START_NORMALIZED.copy() if initial is None else np.asarray(initial,float).copy()
    best=None; attempts=[]
    for index in range(starts):
        p=center.copy()
        if index:
            p+=rng.normal(size=4)*(UPPER_NORMALIZED-LOWER_NORMALIZED)*0.12
        p=np.clip(p,LOWER_NORMALIZED+1e-9,UPPER_NORMALIZED-1e-9)
        opt=least_squares(lambda a: normalized_prediction(theta,beta,a,shape)-observed,
                          p,bounds=(LOWER_NORMALIZED,UPPER_NORMALIZED),
                          max_nfev=1200,ftol=1e-12,xtol=1e-12,gtol=1e-12,x_scale='jac')
        error=normalized_prediction(theta,beta,opt.x,shape)-observed
        sse=float(error@error)
        attempts.append({'start':index+1,'SSE':sse,'success':bool(opt.success),
                         'nfev':int(opt.nfev),'message':str(opt.message)})
        if best is None or sse<best[0]:
            best=(sse,opt)
    if best is None:
        raise RuntimeError('No finite optimization result.')
    _,opt=best
    return opt,attempts


def fit_model(theta,beta,observed,quick=False,starts=12,progress=True):
    shapes=[DEFAULT_SHAPE] if quick else [
        (family,alpha,m,n)
        for family in ('rational','stretched_exp')
        for alpha in (1/8,1/6,1/5,1/4)
        for m in (2,3,4,5)
        for n in range(6,15)]
    rows=[]; best=None
    for index,shape in enumerate(shapes):
        opt,attempts=fit_form(theta,beta,observed,shape,starts=2)
        values=normalized_prediction(theta,beta,opt.x,shape)
        st=stats(observed,values)
        row=dict(family=shape[0],alpha=float(shape[1]),beta_power=shape[2],
                 transition_power=shape[3],term_count=4,
                 parameters_normalized=opt.x.tolist(),parameters_raw=to_raw(opt.x,shape).tolist(),
                 starts=len(attempts),successful_starts=sum(a['success'] for a in attempts),**st)
        rows.append(row)
        if best is None or row['SSE']<best['SSE']:
            best=row
        if progress and ((index+1)%48==0 or index+1==len(shapes)):
            print(f'Model forms {index+1}/{len(shapes)} | best RMSE={best["RMSE"]:.9f}',flush=True)
    shape=(best['family'],best['alpha'],best['beta_power'],best['transition_power'])
    opt,attempts=fit_form(theta,beta,observed,shape,starts=starts,
                          initial=best['parameters_normalized'])
    raw=to_raw(opt.x,shape)
    fit=dict(name=MODEL_LABEL,family=shape[0],alpha=float(shape[1]),
             theta_power=1.0-shape[1],beta_power=shape[2],transition_power=shape[3],
             selected_terms=list(PARAMETER_NAMES),selected_coefficients=raw.tolist(),
             normalized_coefficients=opt.x.tolist(),term_count=4,
             normalization={'theta_scale':100.0,'beta_scale':80.0},
             coefficient_bounds_normalized={'lower':LOWER_NORMALIZED.tolist(),'upper':UPPER_NORMALIZED.tolist()},
             candidate_forms=len(rows),refinement_starts=attempts,
             matrix_rank=int(np.linalg.matrix_rank(opt.jac)),
             jacobian_condition_number=float(np.linalg.cond(opt.jac)),
             optimizer_success=bool(opt.success),optimizer_message=str(opt.message),
             global_optimality_proven=False,
             structure_selection='lowest sampled SSE among tested bounded multistart models')
    return fit,rows


def coefficient_diagnostics(theta,beta,observed,fit):
    predicted=model(theta,beta,fit);base=stats(observed,predicted)['SSE']
    parameters=np.array(fit['selected_coefficients'])
    result=[]
    for j,(term,value) in enumerate(zip(PARAMETER_NAMES,parameters)):
        minus=dict(fit);plus=dict(fit)
        pm=parameters.copy();pp=parameters.copy();pm[j]*=.99;pp[j]*=1.01
        minus['selected_coefficients']=pm.tolist();plus['selected_coefficients']=pp.tolist()
        ym=model(theta,beta,minus);yp=model(theta,beta,plus)
        ssem=stats(observed,ym)['SSE'];ssep=stats(observed,yp)['SSE']
        result.append(dict(term=term,value=float(value),
            RMS_elastic_sensitivity=float(np.sqrt(np.mean(((yp-ym)/.02)**2))),
            SSE_minus_1pct=ssem,SSE_plus_1pct=ssep,
            delta_SSE_minus_1pct=ssem-base,delta_SSE_plus_1pct=ssep-base))
    return result


def cross_validate(theta,beta,observed,fit):
    """Omit complete original theta profiles; keep the selected equation structure fixed."""
    shape=(fit['family'],fit['alpha'],fit['beta_power'],fit['transition_power'])
    predictions=np.empty_like(observed);folds=[]
    for angle in np.unique(theta):
        hold=theta==angle;train=~hold
        opt,_=fit_form(theta[train],beta[train],observed[train],shape,starts=3,
                       initial=fit['normalized_coefficients'])
        predictions[hold]=normalized_prediction(theta[hold],beta[hold],opt.x,shape)
        folds.append(dict(theta_deg=float(angle),N=int(hold.sum()),
                          parameters_raw=to_raw(opt.x,shape).tolist(),
                          **stats(observed[hold],predictions[hold])))
    return dict(method='leave-one-original-theta-profile-out; selected form fixed',
                nested_model_selection=False,independent_field_validation=False,
                folds=folds,statistics=stats(observed,predictions)),predictions


def export_evaluator(path,fit):
    """A standalone standard-library evaluator; does not import the fitting script."""
    a,b,c,d=fit['selected_coefficients'];alpha=fit['alpha'];m=fit['beta_power'];n=fit['transition_power']
    gate=(f'power = (theta / D) ** {n} if theta / D < 2.0 else float("inf")\n'
          '    gate = -math.expm1(-power)') if fit['family']=='stretched_exp' else (
          f'log_ratio = {n} * math.log(theta / D)\n'
          '    gate = (1.0/(1.0+math.exp(-log_ratio)) if log_ratio >= 0\n'
          '            else math.exp(log_ratio)/(1.0+math.exp(log_ratio)))')
    text=f'''"""Four-coefficient fit to 152 stored original Figure 4 curve readings.
Angles are numerical degrees. No interpolation or origin anchors were fitted.
{formula(fit,17)}
"""
import math
A = {a!r}
B = {b!r}
C = {c!r}
D = {d!r}

def r_ratio(theta: float, beta: float) -> float:
    if not (math.isfinite(theta) and math.isfinite(beta)):
        raise ValueError("Angles must be finite.")
    if theta <= 0 or beta < 0:
        raise ValueError("Require theta > 0 and beta >= 0 degrees.")
    {gate}
    value = A*beta / (theta**{1.0-alpha!r} * (1.0+B*beta+(beta/C)**{m}*gate))
    if not math.isfinite(value):
        raise ValueError("Non-finite model prediction.")
    return value
'''
    path.write_text(text,encoding='utf-8')


def plot_hsu_figure4_overlay(output,image_path,theta,beta,observed,fit):
    """Overlay unchanged original digitized readings and fitted model predictions."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    image=plt.imread(str(image_path))
    height,width=image.shape[:2]
    scale=.0100
    img_w,img_h=width*scale,height*scale
    leg_w=4.65
    fig=plt.figure(figsize=(img_w+leg_w,img_h+.4),facecolor='white')
    ax=fig.add_axes([.07/(img_w+leg_w),.17/(img_h+.4),
                     img_w/(img_w+leg_w),img_h/(img_h+.4)])
    ax.imshow(image,origin='upper',extent=(-.5,width-.5,height-.5,-.5),
              interpolation='nearest',zorder=0)
    ax.set_xlim(-.5,width-.5);ax.set_ylim(height-.5,-.5)
    ax.set_aspect('equal',adjustable='box');ax.axis('off')
    uniq=np.unique(theta)
    colors=plt.get_cmap('turbo')(np.linspace(.05,.94,len(uniq)))
    markers=['o','s','^','D','v','P','X','<','>','h','*','d']
    legends=[]
    shown=0; clipped=0; extrapolated_shown=0
    beta_line=np.linspace(0,80,1601)
    for ang in np.arange(30,271,10):
        yy=model(np.full_like(beta_line,ang),beta_line,fit)
        yy=np.where((yy>=0)&(yy<=1),yy,np.nan)
        px,py=figure4_pixel_coordinates(beta_line,yy,width,height)
        ax.plot(px,py,color='0.65',lw=.45,alpha=.45,zorder=1)
    for idx,angle in enumerate(uniq):
        color=colors[idx];marker=markers[idx%len(markers)]
        sel=np.isclose(theta,angle,atol=1e-10,rtol=0)
        yy=observed[sel];bb=beta[sel]
        inside=(bb>=0)&(bb<=80)&(yy>=0)&(yy<=1)
        physical=inside & (bb<=angle+1e-10)
        extrap=inside & (~physical)
        shown+=int(np.sum(inside));clipped+=int(np.sum(~inside))
        extrapolated_shown+=int(np.sum(extrap))
        px,py=figure4_pixel_coordinates(bb[physical],yy[physical],width,height)
        ax.scatter(px,py,s=20,marker=marker,facecolors=[color],edgecolors='white',
                   linewidths=.3,alpha=.94,zorder=4)
        if np.any(extrap):
            ex,ey=figure4_pixel_coordinates(bb[extrap],yy[extrap],width,height)
            ax.scatter(ex,ey,s=16,marker='x',color=color,linewidths=.55,
                       alpha=.63,zorder=4)
        prediction=model(np.full_like(beta_line,angle),beta_line,fit)
        prediction=np.where((prediction>=0)&(prediction<=1),prediction,np.nan)
        x_line,y_line=figure4_pixel_coordinates(beta_line,prediction,width,height)
        in_branch=beta_line<=angle+1e-10
        ax.plot(np.where(in_branch,x_line,np.nan),
                np.where(in_branch,y_line,np.nan),color=color,lw=1.30,
                alpha=.88,zorder=3)
        # No extrapolated theta<beta branch is drawn over the published graph.
        legends.append(Line2D([0],[0],color=color,lw=1.5,marker=marker,
                              markersize=4.5,markeredgecolor='white',
                              label=f'θ={angle:g}°'))
    # The original paper figure stays the same size: legends never alter its XY
    # registration, and graph features outside [0,80]x[0,1] are not drawn.
    sidebar=fig.add_axes([(img_w+.24)/(img_w+leg_w),.025,
                          (leg_w-.45)/(img_w+leg_w),.93])
    sidebar.axis('off')
    sidebar.text(0,.99,'HSU (1989) · FIGURE 4',va='top',fontsize=12,
                 fontweight='bold',transform=sidebar.transAxes)
    sidebar.text(0,.91,'Digitized Figure 4 points vs.\nfour-coefficient fit',
                 va='top',fontsize=10,transform=sidebar.transAxes)
    sidebar.text(0,.795,'Colour: digitized θ profiles\nSolid: sampled curve fits\nGrey: intermediate θ predictions',
                 fontsize=8.7,va='top',transform=sidebar.transAxes)
    # Two-column legend permits all 25 theta profiles without overflowing.
    sidebar.legend(handles=legends,loc='upper left',bbox_to_anchor=(-.02,.635),
                   ncol=2,frameon=False,fontsize=7.6,columnspacing=.55,
                   handlelength=1.4,handletextpad=.28,labelspacing=.29)
    sidebar.text(0,.105,f'Digitized curve observations: {shown}',fontsize=8.5,
                 ha='left',transform=sidebar.transAxes)
    sidebar.text(0,.067,f'Outside original axes: {clipped}',fontsize=8.5,
                 ha='left',transform=sidebar.transAxes)
    sidebar.text(0,.030,'Graph limits: β=0–80°, R/R₀=0–1',fontsize=8.0,
                 ha='left',transform=sidebar.transAxes)
    fig.savefig(output/'fit_hsu1989_figure4_overlay.png',dpi=245,facecolor='white')
    plt.close(fig)
    return dict(input_file=image_path.name,image_width_px=width,image_height_px=height,
                plotted_points=shown,extrapolated_points_shown=extrapolated_shown,
                out_of_range_points=clipped,
                axes_corners=FIGURE4_CORNERS)

def make_plots(out,theta,beta,observed,predicted,fit,diagnostics,leaders,image_path=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    from statistics import NormalDist
    e=predicted-observed
    ae=np.abs(e)
    st=stats(observed,predicted)
    ext=extra_statistics(observed,predicted)
    profiles=profile_statistics(theta,beta,observed,predicted)
    labels=np.array([p['theta'] for p in profiles])
    rmse=np.array([p['RMSE'] for p in profiles]);mae=np.array([p['MAE'] for p in profiles])
    maxae=np.array([p['MaxAE'] for p in profiles]);bias=np.array([p['Bias'] for p in profiles])
    counts=np.array([p['N'] for p in profiles])
    plt.rcParams.update({'font.size':10,'axes.titlesize':11,'axes.labelsize':10,
                         'figure.facecolor':'white','savefig.facecolor':'white',
                         'axes.spines.top':False,'axes.spines.right':False})
    def grid(ax):
        ax.grid(True,alpha=.21)
        ax.set_axisbelow(True)
    def zero(ax):ax.axhline(0,color='.35',ls='--',lw=1)

    fig,axes=plt.subplots(3,3,figsize=(19,15),layout='constrained')
    ax=axes[0,0]
    sc=ax.scatter(observed,predicted,c=theta,cmap='viridis',s=20,alpha=.8)
    vmin=min(float(observed.min()),float(predicted.min()))
    vmax=max(float(observed.max()),float(predicted.max()))
    ax.plot([vmin,vmax],[vmin,vmax],'k--',lw=1.25)
    ax.text(.035,.97,f'R²={st["R2"]:.7f}\nRMSE={st["RMSE"]:.6f}\nN={len(e)}',
            transform=ax.transAxes,va='top',fontsize=9,
            bbox=dict(facecolor='white',alpha=.9,edgecolor='.8'))
    ax.set(xlabel='Figure 4 digitized r_ratio',ylabel='Fitted r_ratio',
           title='(A) Predicted versus reference');grid(ax)
    ax=axes[0,1];ax.scatter(predicted,e,c=theta,cmap='viridis',s=18,alpha=.75)
    zero(ax);ax.set(xlabel='Fitted r_ratio',ylabel='Fitted minus reference',
                    title='(B) Residuals versus fitted values');grid(ax)
    ax=axes[0,2];ax.scatter(theta,e,c=beta,cmap='plasma',s=18,alpha=.75)
    zero(ax);ax.set(xlabel='θ (degrees)',ylabel='Signed error',
                    title='(C) Residuals versus θ');grid(ax)
    ax=axes[1,0];ax.scatter(beta,e,c=theta,cmap='viridis',s=18,alpha=.75)
    zero(ax);ax.set(xlabel='β (degrees)',ylabel='Signed error',
                    title='(D) Residuals versus β');grid(ax)
    ax=axes[1,1];bins=min(32,max(12,round(np.sqrt(len(e))*1.4)))
    ax.hist(e,bins=bins,density=True,edgecolor='white',alpha=.8)
    sd=max(float(np.std(e,ddof=1)),1e-12)
    xx=np.linspace(e.min()-sd/2,e.max()+sd/2,400)
    normal=np.exp(-.5*((xx-e.mean())/sd)**2)/(sd*np.sqrt(2*np.pi))
    ax.plot(xx,normal,'k--',lw=1.5,label='Normal comparison')
    ax.axvline(e.mean(),color='C3',lw=1.2,label='Mean error')
    ax.set(xlabel='Signed residual',ylabel='Probability density',
           title='(E) Residual distribution');ax.legend(fontsize=8);grid(ax)
    ax=axes[1,2];n=len(e)
    quantiles=np.array([NormalDist().inv_cdf((i-.375)/(n+.25)) for i in range(1,n+1)])
    ax.scatter(quantiles,np.sort(e),s=16,alpha=.7)
    ax.plot(quantiles,e.mean()+sd*quantiles,'k--',lw=1.2)
    ax.set(xlabel='Theoretical normal quantile',ylabel='Observed residual quantile',
           title='(F) Normal Q–Q plot');grid(ax)
    ax=axes[2,0];ax.plot(labels,rmse,'o-',label='RMSE')
    ax.plot(labels,mae,'s-',label='MAE')
    ax.plot(labels,maxae,'^-',label='MaxAE')
    ax.set(xlabel='θ (degrees)',ylabel='Absolute error',title='(G) Error by θ profile')
    ax.legend(fontsize=8);grid(ax)
    ax=axes[2,1];sorted_ae=np.sort(ae)
    ax.step(sorted_ae,100*np.arange(1,len(e)+1)/len(e),where='post',lw=2)
    for pct in (50,90,95):
        v=float(np.percentile(ae,pct))
        ax.axvline(v,ls='--',lw=1,label=f'P{pct}={v:.5f}')
    ax.set(xlabel='Absolute error',ylabel='Cumulative observations (%)',
           ylim=(0,102),title='(H) Absolute error CDF')
    ax.legend(fontsize=8);grid(ax)
    ax=axes[2,2];lim=max(float(np.max(ae)),1e-9)
    sc=ax.scatter(theta,beta,c=e,cmap='coolwarm',vmin=-lim,vmax=lim,
                  s=26,marker='s',linewidths=0)
    fig.colorbar(sc,ax=ax,shrink=.82,pad=.01,label='Fitted minus digitized')
    ax.set(xlabel='θ (degrees)',ylabel='β (degrees)',
           title='(I) Residual map on angle grid');grid(ax)
    fig.suptitle(f'{MODEL_LABEL} | {fit["term_count"]} fitted coefficients',
                 fontsize=16,fontweight='bold')
    fig.savefig(out/'fit_results.png',dpi=190)
    plt.close(fig)

    # All theta profiles: each plots every beta point in the source grid.
    unique=np.unique(theta)
    cols=min(5,len(unique));rows=int(np.ceil(len(unique)/cols))
    fig,axes=plt.subplots(rows,cols,figsize=(3.9*cols,3.05*rows),
                          squeeze=False,layout='constrained')
    for ax,angle in zip(axes.flat,unique):
        sel=np.isclose(theta,angle,atol=1e-10,rtol=0)
        order=np.argsort(beta[sel]);x=beta[sel][order]
        values=observed[sel][order];pred=predicted[sel][order]
        xx=np.linspace(float(x.min()),float(x.max()),500)
        yy=model(np.full_like(xx,angle),xx,fit)
        ax.scatter(x,values,s=18,color='C0',label='Digitized curve',zorder=4)
        ax.plot(xx,yy,lw=1.8,color='C3',label='Compact fit')
        ax.vlines(x,values,pred,color='.5',lw=.6,alpha=.5)
        s=stats(values,pred)
        ax.text(.035,.97,f'N={len(values)}  RMSE={s["RMSE"]:.5f}\nMaxAE={s["MaxAE"]:.5f}',
                transform=ax.transAxes,va='top',fontsize=8,
                bbox=dict(facecolor='white',alpha=.88,edgecolor='.9'))
        ax.set(title=f'θ = {angle:g}°',xlabel='β (degrees)',ylabel='r_ratio')
        grid(ax)
    for ax in list(axes.flat)[len(unique):]:ax.axis('off')
    axes.flat[0].legend(fontsize=7.5,loc='lower right')
    fig.suptitle('Digitized source curves and compact surrogate',
                 fontsize=16,fontweight='bold')
    fig.savefig(out/'fit_profiles.png',dpi=190,bbox_inches='tight')
    plt.close(fig)

    fig,axs=plt.subplots(2,2,figsize=(16,10),layout='constrained')
    ii=np.arange(len(unique))
    ax=axs[0,0];ax.bar(ii,rmse,alpha=.8,label='RMSE')
    ax.plot(ii,mae,'o-',lw=1,label='MAE');ax.legend();grid(ax)
    ax.set(ylabel='Error',title='(A) Average error by θ')
    ax=axs[0,1];ax.bar(ii,bias,alpha=.8);zero(ax);grid(ax)
    ax.set(ylabel='Fitted - reference',title='(B) Signed bias by θ')
    ax=axs[1,0];ax.bar(ii,maxae,alpha=.8)
    ax.plot(ii,rmse,'o-',label='RMSE');ax.legend();grid(ax)
    ax.set(ylabel='Absolute error',title='(C) Largest error by θ')
    ax=axs[1,1];ax.bar(ii,counts,alpha=.8)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set(ylabel='Number of points',title='(D) Equal-weight sample counts')
    grid(ax)
    for ax in axs.flat:
        ax.set(xticks=ii,xticklabels=[f'{x:g}' for x in labels],xlabel='θ (degrees)')
        ax.tick_params(axis='x',labelrotation=55)
    fig.suptitle(f'Profile performance | SSE={st["SSE"]:.8f} | Bias={ext["Bias"]:+.6f}',
                 fontsize=14,fontweight='bold')
    fig.savefig(out/'fit_error_analysis.png',dpi=195)
    plt.close(fig)

    names=[d['term'] for d in diagnostics]
    sensitivity=np.array([d['RMS_elastic_sensitivity'] for d in diagnostics])
    minus=np.array([d['delta_SSE_minus_1pct'] for d in diagnostics])
    plus=np.array([d['delta_SSE_plus_1pct'] for d in diagnostics])
    kk=np.arange(len(names))
    fig,axs=plt.subplots(2,2,figsize=(16,11),layout='constrained')
    ax=axs[0,0];ax.bar(kk,sensitivity,alpha=.8)
    ax.set(xticks=kk,xticklabels=names,ylabel='RMS of parameter × model derivative',
           title='(A) Local parameter sensitivity (not a term contribution)');grid(ax)
    ax=axs[0,1];ax.bar(kk-.17,minus,width=.34,label='Coefficient -1%')
    ax.bar(kk+.17,plus,width=.34,label='Coefficient +1%')
    ax.set(xticks=kk,xticklabels=names,ylabel='Change in SSE',
           title='(B) Exact ±1% coefficient perturbations')
    ax.legend(fontsize=8);grid(ax)
    ax=axs[1,0]
    for family in ('rational','stretched_exp'):
        candidates=[r for r in leaders if r['family']==family and
                    abs(r['alpha']-fit['alpha'])<1e-12 and r['beta_power']==fit['beta_power']]
        candidates=sorted(candidates,key=lambda r:r['transition_power'])
        if candidates:
            ax.plot([r['transition_power'] for r in candidates],
                    [r['RMSE'] for r in candidates],'o-',label=family)
    ax.scatter([fit['transition_power']],[st['RMSE']],marker='*',s=140,zorder=5,label='Selected form')
    ax.set(xlabel='Fixed integer transition power',ylabel='Training RMSE',
           title='(C) Four-coefficient model-form search')
    ax.legend(fontsize=8);grid(ax)
    ax=axs[1,1]
    cv=fit.get('cross_validation',{})
    folds=cv.get('folds',[])
    if folds:
        xx=[r['theta_deg'] for r in folds]
        ax.plot(xx,[r['RMSE'] for r in folds],'o-',label='Held-out theta profile')
        ax.plot(labels,rmse,'s--',label='Training profile')
        ax.set(xlabel='Omitted theta (degrees)',ylabel='RMSE',
               title='(D) Leave-one-theta-profile-out; model form fixed')
        ax.legend(fontsize=8);grid(ax)
    else:
        ax.text(.05,.7,'Cross-validation not requested.',transform=ax.transAxes)
        ax.axis('off')
    fig.suptitle(MODEL_LABEL+' | sensitivity and validation',fontsize=14,fontweight='bold')
    fig.savefig(out/'fit_coefficient_sensitivity.png',dpi=200)
    plt.close(fig)
    if image_path is not None:
        return plot_hsu_figure4_overlay(out,image_path,theta,beta,observed,fit)
    return None

def plot_grid_profiles(out,grid_t,grid_b,grid_r,grid_status,fit,source_t,source_b,source_r):
    """Twenty-five prediction profiles; display only directly digitized references."""
    import matplotlib.pyplot as plt
    unique=np.unique(grid_t);ncol=5; nrow=int(np.ceil(len(unique)/ncol))
    fig,axes=plt.subplots(nrow,ncol,figsize=(19.5,3.25*nrow),layout='constrained',squeeze=False)
    for ax,ang in zip(axes.flat,unique):
        region=grid_t==ang
        x=grid_b[region];y=grid_r[region]
        status=grid_status[region]
        continuous=np.linspace(float(x.min()),float(x.max()),301)
        yp=model(np.full_like(continuous,ang),continuous,fit)
        # Curved Hsu branch is defined at theta >= beta. Predictions for the
        # complete Cartesian grid remain in predictions.tsv, but should not be
        # presented as measured shoreline curves beyond this branch.
        in_branch=continuous<=ang+1e-10
        line,=ax.plot(continuous,np.where(in_branch,yp,np.nan),lw=1.75,label='Fitted curve')
        if np.any(~in_branch):
            ax.plot(continuous,np.where(~in_branch,yp,np.nan),ls='--',lw=1.1,
                    color=line.get_color(),label='theta < beta: prediction only')
        valid=np.isfinite(y)
        direct=status=='directly_digitized'
        if np.any(direct):
            ax.scatter(x[direct],y[direct],s=22,color='C0',label='Digitized Figure 4',zorder=4)
        ax.axhline(0,color='.45',lw=.6)
        ax.set(title=f'θ={ang:g}°',xlabel='β (degrees)',ylabel='R/R₀',xlim=(0,80))
        ax.grid(alpha=.22)
        if np.any(valid):
            s=stats(y[valid],model(np.full(np.count_nonzero(valid),ang),x[valid],fit))
            ax.text(.03,.97,f'Available N={np.count_nonzero(valid)}\nRMSE={s["RMSE"]:.4f}',
                    transform=ax.transAxes,va='top',fontsize=8,
                    bbox=dict(facecolor='white',alpha=.83,edgecolor='.87'))
    for ax in list(axes.flat)[len(unique):]:ax.axis('off')
    axes.flat[0].legend(fontsize=7,loc='lower right')
    fig.suptitle('Figure 4 original curve pixels (observed) and all requested model predictions',
                 fontsize=15,fontweight='bold')
    fig.savefig(out/'fit_profiles.png',dpi=185)
    plt.close(fig)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--figure4-image',type=Path,default=None)
    parser.add_argument('--theta-min',type=float,default=DEFAULT_THETA_MIN)
    parser.add_argument('--theta-max',type=float,default=DEFAULT_THETA_MAX)
    parser.add_argument('--theta-step',type=float,default=DEFAULT_THETA_STEP)
    parser.add_argument('--beta-min',type=float,default=DEFAULT_BETA_MIN)
    parser.add_argument('--beta-max',type=float,default=DEFAULT_BETA_MAX)
    parser.add_argument('--beta-step',type=float,default=DEFAULT_BETA_STEP)
    parser.add_argument('--starts',type=int,default=12,help='Multistart refinements of selected form (at least 1).')
    parser.add_argument('--quick',action='store_true',help='Fit the default selected structure without the 288-form sweep.')
    parser.add_argument('--no-cross-validation',action='store_true')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--no-plots',action='store_true')
    args=parser.parse_args(argv)
    if args.starts<1:parser.error('--starts must be positive.')
    if args.theta_min<=0 or args.beta_min<0:parser.error('Require theta-min > 0 and beta-min >= 0.')
    out=args.output.expanduser().resolve()
    if not out.is_dir():parser.error('Output directory must already exist; no directories are created.')
    base=Path(__file__).resolve().parent
    try:
        img=find_figure4_image(args.figure4_image,base)
        if img is None:raise FileNotFoundError('Place the original Figure 4 JPG beside the script or use --figure4-image FILE.')
        theta_all,beta_all,observed_all,pixel_all,status_all,image_shape=digitized_plot_samples(img)
        direct=np.asarray(status_all)=='digitized_figure4_stroke'
        theta,beta,observed=theta_all[direct],beta_all[direct],observed_all[direct]
        pixel=pixel_all[direct]
        gt,gb,gref,gstatus=figure4_grid(theta,beta,observed,args)
    except (OSError,ValueError) as exc:
        parser.error(str(exc))
    started=perf_counter()
    print(f'Original image-digitized curve readings: {len(observed)}; no origin anchors.',flush=True)
    fit,search_rows=fit_model(theta,beta,observed,quick=args.quick,starts=args.starts)
    pred=model(theta,beta,fit);st=stats(observed,pred);ext=extra_statistics(observed,pred)
    cvpred=np.full_like(observed,np.nan)
    if not args.no_cross_validation:
        cv,cvpred=cross_validate(theta,beta,observed,fit)
        fit['cross_validation']=cv
        print(f'Fixed-form leave-one-theta-out RMSE={cv["statistics"]["RMSE"]:.9f}',flush=True)
    else:
        cv=None
    diag=coefficient_diagnostics(theta,beta,observed,fit)
    gp=model(gt,gb,fit);known=np.isfinite(gref)
    gres=np.where(known,gp-gref,np.nan)
    profiles=profile_statistics(theta,beta,observed,pred)
    save_tsv(out/'digitized_profiles.tsv',
             ['theta_deg','beta_deg','r_ratio','original_y_pixel','sampling_status'],
             [theta,beta,observed,pixel,np.asarray(status_all)[direct]])
    save_tsv(out/'source_predictions.tsv',
             ['theta_deg','beta_deg','original_image_r_ratio','fitted_r_ratio','signed_residual','abs_residual','leave_theta_out_prediction'],
             [theta,beta,observed,pred,pred-observed,abs(pred-observed),cvpred])
    save_tsv(out/'generated_reference.tsv',
             ['theta_deg','beta_deg','image_reference_r_ratio','reference_provenance'],[gt,gb,gref,gstatus])
    save_tsv(out/'predictions.tsv',
             ['theta_deg','beta_deg','image_reference_r_ratio','fitted_r_ratio','signed_residual','reference_provenance'],
             [gt,gb,gref,gp,gres,gstatus])
    with (out/'search_coverage.tsv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t')
        writer.writerow(['family','fixed_alpha','fixed_theta_power','fixed_beta_power','fixed_transition_power',
                         'fitted_coefficients','A','B','C','D','SSE','RMSE','MAE','MaxAE','R2','starts','successful_starts'])
        for row in search_rows:
            writer.writerow([row['family'],row['alpha'],1-row['alpha'],row['beta_power'],row['transition_power'],
                             4,*row['parameters_raw'],*[row[k] for k in ('SSE','RMSE','MAE','MaxAE','R2','starts','successful_starts')]])
    with (out/'profile_statistics.tsv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t')
        writer.writerow(['theta_deg','original_digitized_points','RMSE','MAE','MaxAE','Bias','SSE','leave_theta_out_RMSE'])
        for angle in sorted(set(gt)|set(theta)):
            mask=theta==angle;s=stats(observed[mask],pred[mask]) if mask.any() else None
            cv_rmse=stats(observed[mask],cvpred[mask])['RMSE'] if mask.any() and cv is not None else ''
            writer.writerow([angle,int(mask.sum()),*([s[k] for k in ('RMSE','MAE','MaxAE')] if s else ['']*3),
                             float(np.mean((pred-observed)[mask])) if mask.any() else '',s['SSE'] if s else '',cv_rmse])
    with (out/'cross_validation.tsv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t')
        writer.writerow(['omitted_theta_deg','heldout_points','RMSE','MAE','MaxAE','SSE','A','B','C','D'])
        for row in cv['folds'] if cv else []:
            writer.writerow([row['theta_deg'],row['N'],*[row[k] for k in ('RMSE','MAE','MaxAE','SSE')],*row['parameters_raw']])
    export_evaluator(out/'r_ratio_model.py',fit)
    worst=int(np.argmax(abs(pred-observed)))
    pixel_error=(pred-observed)*(455.0-0.5*beta/80.0)
    pixels=dict(RMSE=float(np.sqrt(np.mean(pixel_error**2))),MaxAE=float(max(abs(pixel_error))))
    source_hash=hashlib.sha256(json.dumps(FIGURE4_DIGITIZED_PIXEL_Y,sort_keys=True).encode()).hexdigest()
    report=[
        'COMPACT FOUR-COEFFICIENT FIT TO ORIGINAL IMAGE-DIGITIZED CURVES ONLY',
        '='*86,
        f'Source image: {img.name} ({image_shape[0]} x {image_shape[1]} pixels)',
        'Source: fixed original curve-stroke pixel readings, calibrated to four image corners.',
        f'Fitted source points: {len(observed)}; original theta profiles: {len(np.unique(theta))}.',
        'All source readings have equal weight. No point was removed or adjusted.',
        'No origin anchors, interpolated reference curves, or synthetic Hsu data enter the fit.',
        'Stored digitized readings are reused; image tracing is not rerun.',
        'Digitized pixel-dictionary SHA256: '+source_hash,
        '', 'MODEL',formula(fit,17),
        f'Family: {fit["family"]}; fixed theta power={fit["theta_power"]:.12g}, beta power={fit["beta_power"]}, transition power={fit["transition_power"]}.',
        'Four fitted coefficients; fixed powers are model-structure choices, not continuously fitted coefficients.',
        'Angles must be numerical degrees. No radians conversion or normalization at theta=beta.',
        'The equation has r(theta,0)=0 by construction; these zero values were NOT included as observations.',
        *[f'{k} = {v:.17g}' for k,v in zip(PARAMETER_NAMES,fit['selected_coefficients'])],
        '', 'ERROR STATISTICS ON THE 152 ORIGINAL IMAGE-DIGITIZED STROKES',
        *[f'{k:8s} = {st[k]:.12f}' for k in ('SSE','RMSE','MAE','MaxAE','R2')],
        f'Equivalent vertical-image RMSE = {pixels["RMSE"]:.6f} px; maximum = {pixels["MaxAE"]:.6f} px.',
        'These are absolute dimensionless ratio errors, not percentage errors relative to each observation.',
        '', 'WORST POINT',
        f'theta={theta[worst]:g} deg; beta={beta[worst]:g} deg;',
        f'reference={observed[worst]:.12f}; model={pred[worst]:.12f}; residual={pred[worst]-observed[worst]:+.12f}.',
        '', 'SEARCH AND NUMERICAL SCOPE',
        f'Candidate structures evaluated: {len(search_rows)}; two deterministic starts per structure.',
        f'Winning structure refined from {args.starts} starts; model Jacobian rank={fit["matrix_rank"]}.',
        'Bounded nonlinear least squares minimizes SSE. The selected form has the lowest computed SSE in this search.',
        'An unrestricted global optimum over all formulas or nonlinear coefficients is NOT established.',
        'Internal normalized parameter bounds: '+str(fit['coefficient_bounds_normalized']),
        'The fixed-power sweep is documented in search_coverage.tsv.',
        '', 'LEAVE-ONE-ORIGINAL-THETA-PROFILE-OUT CHECK',
    ]
    if cv:
        report += [f'{k:8s} = {cv["statistics"][k]:.12f}' for k in ('SSE','RMSE','MAE','MaxAE','R2')]
        report += ['The model form and fixed powers remain selected using all source data.',
                   'Only four coefficients are refitted in each fold. This is not nested model-selection validation',
                   'and not independent field validation. No omitted readings enter a fold coefficient fit.']
    else:
        report += ['Not requested.']
    report += ['', 'SOURCE PROFILE DIAGNOSTICS','theta_deg     N        RMSE          MAE         MaxAE']
    report += [f'{r["theta"]:9.3f} {r["N"]:5d} {r["RMSE"]:12.8f} {r["MAE"]:12.8f} {r["MaxAE"]:12.8f}' for r in profiles]
    report += ['', 'PREDICTION GRID AND LIMITATIONS',
               f'{len(gt)} grid points: theta={args.theta_min:g}..{args.theta_max:g} step {args.theta_step:g}, beta={args.beta_min:g}..{args.beta_max:g} step {args.beta_step:g}.',
               f'Exact source-reference matches: {known.sum()}; prediction-only positions: {(~known).sum()}.',
               'There are only 11 original theta profiles. Intermediate theta curves are predictions, not observations.',
               'Blank grid references and residuals are intentional; no interpolation fills missing reference values.',
               'The complete rectangular grid is exported. theta<beta predictions are outside the curved branch.',
               'No accuracy guarantee is made outside the digitized support or between the original samples.',
               'Scan line thickness, overlapping symbols and reading uncertainty remain; low SSE cannot remove them.',
               'All outputs are written directly in the existing output directory. No subdirectories are created.',
               f'Elapsed calculation/report time: {perf_counter()-started:.3f} seconds.','']
    (out/'output.txt').write_text('\n'.join(report),encoding='utf-8')
    image_metadata=None
    if not args.no_plots:
        image_metadata=make_plots(out,theta,beta,observed,pred,fit,diag,search_rows,img)
        plot_grid_profiles(out,gt,gb,gref,gstatus,fit,theta,beta,observed)
    files=['output.txt','coefficients.json','predictions.tsv','search_coverage.tsv','profile_statistics.tsv',
           'generated_reference.tsv','digitized_profiles.tsv','source_predictions.tsv','cross_validation.tsv','r_ratio_model.py']
    if not args.no_plots:
        files += ['fit_results.png','fit_profiles.png','fit_error_analysis.png','fit_coefficient_sensitivity.png','fit_hsu1989_figure4_overlay.png']
    result=dict(source='ORIGINAL IMAGE-DIGITIZED CURVE STROKES ONLY',source_image=img.name,
                source_readings=len(observed),source_theta_profiles=np.unique(theta).tolist(),
                source_pixel_dictionary_sha256=source_hash,source_image_size=image_shape,
                equation=formula(fit,17),fit=fit,source_statistics=st,source_additional_statistics=ext,
                equivalent_image_error_pixels=pixels,coefficient_diagnostics=diag,model_search=search_rows,
                figure4_registration=image_metadata,grid=dict(points=len(gt),direct_references=int(known.sum()),
                    prediction_only=int((~known).sum()),theta_min=args.theta_min,theta_max=args.theta_max,
                    theta_step=args.theta_step,beta_min=args.beta_min,beta_max=args.beta_max,beta_step=args.beta_step),
                output_files=files,flat_output_only=True)
    (out/'coefficients.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('\n'+formula(fit,12))
    print('RMSE={RMSE:.9f}; MAE={MAE:.9f}; MaxAE={MaxAE:.9f}; R2={R2:.9f}'.format(**st))
    print('Saved results directly in:',out)
    return result


if __name__=='__main__':
    main()
