"""Calibration of the burn-probability field (first-class deliverable, docs/EVALUATION.md §3.2).

A probabilistic forecast is only useful if its probabilities mean what they say: cells assigned 30%
should burn ~30% of the time. This module provides the proper scores (Brier, CRPS), the reliability
diagram, empirical coverage, and two recalibration maps (temperature scaling, isotonic/PAV), the
standard toolkit (Guo et al. 2017), applied to the spread field rather than a classifier.

Everything is numpy-only so it runs in CI with no heavy deps.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    """Mean squared error of probabilistic forecast vs binary outcome (lower = better)."""
    p = np.asarray(p, float).ravel()
    y = np.asarray(y, float).ravel()
    return float(np.mean((p - y) ** 2))


@dataclass
class ReliabilityCurve:
    bin_edges: np.ndarray
    pred_mean: np.ndarray  # mean predicted prob in each bin
    obs_freq: np.ndarray  # observed burn frequency in each bin
    counts: np.ndarray


def reliability_curve(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> ReliabilityCurve:
    p = np.asarray(p, float).ravel()
    y = np.asarray(y, float).ravel()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    pred_mean = np.full(n_bins, np.nan)
    obs_freq = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins)
    for b in range(n_bins):
        m = idx == b
        counts[b] = m.sum()
        if counts[b] > 0:
            pred_mean[b] = p[m].mean()
            obs_freq[b] = y[m].mean()
    return ReliabilityCurve(edges, pred_mean, obs_freq, counts)


def expected_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Weighted mean gap between predicted prob and observed frequency across bins."""
    rc = reliability_curve(p, y, n_bins)
    total = rc.counts.sum()
    if total == 0:
        return float("nan")
    valid = ~np.isnan(rc.pred_mean)
    return float(np.sum(rc.counts[valid] * np.abs(rc.pred_mean[valid] - rc.obs_freq[valid])) / total)


def crps_ensemble(member_arrivals: np.ndarray, weights: np.ndarray, truth_arrival: np.ndarray, horizon: float) -> float:
    """CRPS of the ensemble burn-time forecast vs truth, averaged over cells the truth burned.

    For each cell we treat "did it burn by horizon" but score the full arrival-time ensemble against
    the truth arrival using the empirical-CRPS identity CRPS = E|X−y| − ½E|X−X'|.
    """
    A = np.where(np.isfinite(member_arrivals), member_arrivals, horizon * 4)  # (M, ny, nx)
    y = np.where(np.isfinite(truth_arrival), truth_arrival, horizon * 4)
    w = np.asarray(weights, float)
    w = w / w.sum()
    # only score cells the truth reached within a generous window
    scored = truth_arrival <= horizon * 2
    if not scored.any():
        return float("nan")
    term1 = np.tensordot(w, np.abs(A - y[None, ...]), axes=(0, 0))  # E|X-y| per cell
    # E|X - X'| via weighted pairwise (small M): sum_ij w_i w_j |A_i - A_j|
    M = A.shape[0]
    term2 = np.zeros_like(y)
    for i in range(M):
        term2 += w[i] * np.tensordot(w, np.abs(A - A[i][None, ...]), axes=(0, 0))
    crps = term1 - 0.5 * term2
    return float(crps[scored].mean())


def coverage(prob_field: np.ndarray, truth_mask: np.ndarray, levels=(0.5, 0.8, 0.9)) -> dict[float, float]:
    """For each nominal level α, region = {p ≥ 1−α}; report the fraction of truly-burned area inside.

    A well-calibrated envelope contains ~α of the truth at level α (docs/EVALUATION.md §3.2).
    """
    p = np.asarray(prob_field, float)
    y = np.asarray(truth_mask, bool)
    ny = y.sum()
    out: dict[float, float] = {}
    for a in levels:
        region = p >= (1.0 - a)
        out[a] = float((y & region).sum() / ny) if ny > 0 else float("nan")
    return out


# ── recalibration maps ───────────────────────────────────────────────────────


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Fit a scalar temperature T (>0) minimizing log-loss of the scaled probabilities."""
    from scipy.optimize import minimize_scalar

    p = np.asarray(p, float).ravel()
    y = np.asarray(y, float).ravel()
    z = _logit(p)

    def nll(logT: float) -> float:
        T = np.exp(logT)
        q = 1.0 / (1.0 + np.exp(-z / T))
        q = np.clip(q, 1e-9, 1 - 1e-9)
        return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))

    res = minimize_scalar(nll, bounds=(-3.0, 3.0), method="bounded")
    return float(np.exp(res.x))


def temperature_scale(p: np.ndarray, T: float) -> np.ndarray:
    z = _logit(p)
    return 1.0 / (1.0 + np.exp(-z / T))


def isotonic_fit(p: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool-adjacent-violators isotonic regression. Returns (sorted_x, fitted_y) as a step map."""
    p = np.asarray(p, float).ravel()
    y = np.asarray(y, float).ravel()
    order = np.argsort(p)
    x = p[order]
    g = y[order].astype(float).copy()
    w = np.ones_like(g)
    # PAV
    i = 0
    while i < len(g) - 1:
        if g[i] > g[i + 1]:
            new = (g[i] * w[i] + g[i + 1] * w[i + 1]) / (w[i] + w[i + 1])
            g[i] = new
            g = np.delete(g, i + 1)
            w[i] = w[i] + w[i + 1]
            w = np.delete(w, i + 1)
            x = np.delete(x, i + 1)
            if i > 0:
                i -= 1
        else:
            i += 1
    return x, g


def isotonic_apply(x_knots: np.ndarray, y_knots: np.ndarray, p: np.ndarray) -> np.ndarray:
    return np.interp(np.asarray(p, float), x_knots, y_knots, left=y_knots[0], right=y_knots[-1])
