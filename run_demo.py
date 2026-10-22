"""Start the loopback-only MAYA wallet: python run_demo.py"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=str(ROOT / "data/simulator-v1.sqlite"))
    args = parser.parse_args()
    from simulator_service import LiveModel, Simulator
    from simulator_api import create_app
    import uvicorn
    model, calibration = ROOT / "models/xgb_model.json", ROOT / "models/conformal.json"
    if not model.exists() or not calibration.exists():
        parser.error("Model artifacts missing. Run: python scripts/bootstrap_demo.py")
    Path(args.database).parent.mkdir(parents=True, exist_ok=True)
    service = Simulator(args.database, LiveModel(str(model), str(calibration)))
    print(f"MAYA dummy wallet: http://127.0.0.1:{args.port} (no real money)", flush=True)
    try:
        uvicorn.run(create_app(service), host="127.0.0.1", port=args.port, access_log=False)
    finally:
        service.db.close()


if __name__ == "__main__":
    main()
