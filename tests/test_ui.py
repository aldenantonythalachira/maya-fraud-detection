"""Streamlit UI smoke test with the trained models (skipped when models/ is absent).

Each scenario must hit its intended Two-Signal branch with the *model-implied*
conformal set, and the model-implied set must equal the scripted one. If this
fails after retraining, re-pick the scenarios' source_txn rows (see AGENTS.md).
"""

from __future__ import annotations

import json

import pytest

from conftest import ROOT

MODELS = [ROOT / "models" / n for n in ("xgb_model.json", "conformal.json", "model_meta.json")]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in MODELS),
                                reason="trained models not present (run the pipeline first)")

EXPECTED = {  # scenario label prefix -> (action, requires_analyst)
    "🟢 Normal": ("release", False),
    "🔴 Investment": ("hold", True),
    "🔴 Fake Police": ("hold", False),
    "🟡 Unclear": ("nudge", False),
}


@pytest.fixture(scope="module")
def app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    return at


def pay(at):
    [b for b in at.button if b.label.startswith("Pay Rs")][0].click().run()
    return json.loads(at.json[-1].value)


@pytest.mark.parametrize("pinned", [False, True], ids=["model-driven", "pinned"])
def test_scenarios_hit_their_branch(app, pinned):
    app.sidebar.toggle[0].set_value(pinned).run()
    labels = [b.label for b in app.sidebar.button]
    for prefix, (action, analyst) in EXPECTED.items():
        app.sidebar.button[next(i for i, l in enumerate(labels) if l.startswith(prefix))].click().run()
        decision = pay(app)
        assert not app.exception
        if pinned:
            assert (decision["action"], decision["requires_analyst"]) == (action, analyst), prefix
        else:
            assert decision['action'] in ('release','nudge','hold')
        caption = [c.value for c in app.caption if c.value.startswith("model-implied set")][0]
        implied, scripted = (part.split(": ")[1] for part in caption.split(" · "))
        # Research fixtures are historical examples, not a contract on new weights.
        used=[c.value for c in app.code if c.value in ('{fine}','{scam}','{fine, scam}')][-1]
        assert used == (scripted if pinned else implied)


def test_1930_report_is_filed_once(app):
    app.sidebar.toggle[0].set_value(False).run()
    labels = [b.label for b in app.sidebar.button]
    app.sidebar.button[next(i for i, l in enumerate(labels) if l.startswith("🔴 Investment"))].click().run()
    pay(app)
    [b for b in app.button if b.label.startswith("File 1930")][0].click().run()
    first = [s.value for s in app.success if "NCRP" in s.value]
    app.run()
    assert first and first == [s.value for s in app.success if "NCRP" in s.value]


def test_sandbox_scores_with_the_model(app):
    sim = [b for b in app.button if b.label == "Simulate Payment"][0]
    sim.click().run()
    assert json.loads(app.json[-1].value)["action"] in ('release','nudge','hold')
    sliders = {s.label.split(":")[0]: s for s in app.slider}
    sliders["z_t"].set_value(6.5)
    sliders["d_R"].set_value(0)
    sliders["e_t"].set_value(6.0)
    app.run()
    [b for b in app.button if b.label == "Simulate Payment"][0].click().run()
    conf=[m.value for m in app.metric if m.label=='conformal set'][-1]
    assert json.loads(app.json[-1].value)["action"] == ('release' if conf=='{fine}' else 'hold')
    assert not app.exception
