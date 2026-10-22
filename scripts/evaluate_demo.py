"""Behavioral live-model audit, not a held-out detection benchmark."""
import argparse
import json
import math
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from simulator_service import LiveModel, Simulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "data/evaluation-demo.json"))
    args = parser.parse_args()
    service = Simulator(":memory:", LiveModel(str(ROOT / "models/xgb_model.json"), str(ROOT / "models/conformal.json")))
    rows = []
    try:
        for seed in (11, 29, 47):
            for preset in ("everyday", "investment", "refund", "probes"):
                world = service.create_world("evaluation", seed, preset)
                message = world["default_message"]
                p = service.intent(world["id"], "evaluation", world["default_recipient"], world["default_amount_paise"], message, bool(message))
                r = service.review(world["id"], "evaluation", p["id"])
                service.replay(world["id"], "evaluation", r["id"], True)
                rows.append(dict(seed=seed, preset=preset, action=r["decision"]["action"], score=r["model"]["score"],
                                 prediction_set=r["model"]["uncertainty"], groups=r["groups"], latency_ms=r["latency_ms"]))
        latencies = sorted(row["latency_ms"] for row in rows)
        calibration = json.loads((ROOT / "models/conformal.json").read_text())
        report = dict(kind="generated behavioral audit; not held-out accuracy", samples=len(rows), seeds=[11,29,47],
                      hardware=platform.platform(), python=platform.python_version(),
                      model_version=service.model.version, calibration_version=service.model.calibration_version,
                      scope="single-process review processing including features, inference, SHAP, policy and preceding trace commits; excludes final review commit, HTTP/network and rendering",
                      p95_review_processing_ms=latencies[math.ceil(.95 * len(latencies)) - 1],
                      snapshot_replays_passed=len(rows), calibration_test=calibration.get("test"), rows=rows,
                      limitations=["No new detection accuracy claim", "Small sample", "Cold startup excluded", "Legacy report-outward graph semantics"])
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k not in ("rows","calibration_test")}, indent=2))
        print("Wrote", out)
    finally:
        service.db.close()


if __name__ == "__main__":
    main()
