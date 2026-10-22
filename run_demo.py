"""Start the loopback-only MAYA wallet: python run_demo.py"""
import argparse
import sys
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=str(ROOT / "data/simulator-v2.sqlite"))
    parser.add_argument("--demo-docs", action="store_true", help="Expose local API documentation")
    parser.add_argument("--bootstrap", action="store_true", help="Build synthetic model artifacts only if missing")
    args = parser.parse_args()
    from simulator_service import LiveModel, Simulator, UnavailableModel
    from simulator_api import create_app
    import uvicorn
    model, calibration = ROOT / "models/xgb_model.json", ROOT / "models/conformal.json"
    if args.bootstrap and (not model.exists() or not calibration.exists()):
        subprocess.run([sys.executable, str(ROOT / "scripts/bootstrap_demo.py")], cwd=ROOT, check=True)
    try:
        scorer = LiveModel(str(model), str(calibration))
    except Exception as error:
        print(f"Model unavailable ({type(error).__name__}). Wallet will block payments. Run scripts/bootstrap_demo.py and restart.", flush=True)
        scorer = UnavailableModel()
    Path(args.database).parent.mkdir(parents=True, exist_ok=True)
    service = Simulator(args.database, scorer)
    controller_key = secrets.token_urlsafe(32)
    print(f"MAYA dummy wallet: http://127.0.0.1:{args.port} (no real money)", flush=True)
    print(f"Local console: http://127.0.0.1:{args.port}/console", flush=True)
    print(f"Controller key (keep out of payer views and recordings): {controller_key}", flush=True)
    try:
        uvicorn.run(create_app(service, controller_key, args.demo_docs), host="127.0.0.1", port=args.port, access_log=False)
    finally:
        service.db.close()


if __name__ == "__main__":
    main()
