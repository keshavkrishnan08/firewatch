"""Learned-model tests (spread surrogate + smoke segmenter). Skipped if torch is absent."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")


@pytest.mark.slow
def test_smoke_net_trains_and_segments():
    from firewatch.perception.smoke_net import synth_smoke_frame, train_smoke_net

    model, metrics = train_smoke_net(n_train=80, n_val=20, epochs=3, batch=8, log=lambda *_: None)
    assert 0.0 <= metrics["val_mask_iou"] <= 1.0
    img, _ = synth_smoke_frame(np.random.default_rng(1), 256, 192)
    mask = model.segment(img)
    assert mask.shape == img.shape[:2] and mask.dtype == bool


@pytest.mark.slow
def test_surrogate_trains_and_predicts_finite_arrival():
    from firewatch.forecast.grid import synthetic_grid
    from firewatch.forecast.surrogate import train_surrogate

    model, metrics = train_surrogate(n_train=24, n_val=6, epochs=3, batch=4, log=lambda *_: None)
    assert metrics["val_mae_min"] >= 0
    g = synthetic_grid(38.5, -122.6, cell_m=200.0, n=64)
    arr = model.predict_arrival(g, g.cell_to_lonlat(32, 32))
    assert arr.shape == (g.ny, g.nx)
    assert np.isfinite(arr).any()  # the surrogate predicts a real arrival field


def test_smoke_net_frame_generator_shapes():
    from firewatch.perception.smoke_net import synth_smoke_frame

    img, mask = synth_smoke_frame(np.random.default_rng(0), 256, 192)
    assert img.shape == (192, 256, 3) and img.dtype == np.uint8
    assert mask.shape == (192, 256) and mask.dtype == bool
