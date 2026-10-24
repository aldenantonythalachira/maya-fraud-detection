"""SHAP explanations must explain the model that actually scored the payment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from conftest import ROOT
from reasons import make_explainer, native_contrib, shap_matrix
from risk_common import FEATURE_COLUMNS


def early_stopped_model():
    """A tiny model with more trees trained than kept (best_iteration < rounds)."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(600, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS).astype("float32")
    y = (X["z_t"] + X["d_R"] * -0.5 + rng.normal(scale=0.8, size=600) > 1.0).astype(int)
    Xv = pd.DataFrame(rng.normal(size=(200, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS).astype("float32")
    yv = (Xv["z_t"] + rng.normal(scale=3.0, size=200) > 1.0).astype(int)  # noisy: stops early
    m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.3, early_stopping_rounds=5,
                          eval_metric="logloss")
    m.fit(X, y, eval_set=[(Xv, yv)], verbose=False)
    assert m.best_iteration + 1 < m.get_booster().num_boosted_rounds()
    return m, X.head(8)


def check_additivity(model, X):
    margin = model.predict(X, output_margin=True)
    explainer = make_explainer(model)
    tree = shap_matrix(explainer, X).sum(1) + explainer.expected_value
    np.testing.assert_allclose(tree, margin, atol=1e-3)
    booster = model.get_booster()
    stop = model.best_iteration + 1
    bias = booster.predict(xgb.DMatrix(X, feature_names=FEATURE_COLUMNS), pred_contribs=True,
                           iteration_range=(0, stop))[:, -1]
    np.testing.assert_allclose(native_contrib(model, X).sum(1) + bias, margin, atol=1e-3)


def test_both_shap_paths_add_up_to_the_score():
    check_additivity(*early_stopped_model())


@pytest.mark.skipif(not (ROOT / "models" / "xgb_model.json").exists(), reason="trained model not present")
def test_trained_model_explanations_add_up():
    from scenario_features import SCENARIO_FEATURES

    m = xgb.XGBClassifier()
    m.load_model(ROOT / "models" / "xgb_model.json")
    X = pd.DataFrame([s["features"] for s in SCENARIO_FEATURES.values()], columns=FEATURE_COLUMNS).astype("float32")
    check_additivity(m, X)
