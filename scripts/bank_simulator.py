"""High-Throughput UPI Switch Simulator (HDFC Bank -> Maya Bank API).

Simulates an HDFC remitter switch pushing 100 transactions through Maya's
/api/score-trace in real time, then prints a rich BANK SWITCH REPORT and a red
banner of the scams blocked before NPCI.

Usage:
    python3 scripts/bank_simulator.py            # 100 txns (80 safe / 20 scam)
    python3 scripts/bank_simulator.py --n 500    # custom volume
"""
from __future__ import annotations

import argparse
import random
import time

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

API_URL = "http://127.0.0.1:8000/api/score-trace"
API_KEY = "sk_live_maya_enterprise"

console = Console()


def make_txn(i: int, rng: random.Random) -> dict:
    """Every 5th txn is a scam; the rest are safe."""
    if i % 5 == 4:
        return {
            "amount": float(rng.randint(50_000, 300_000)),
            "d_R": 1,
            "z_t": 3.0,
            "e_t": 1.5,
            "g_t": 1.0,
            "pi_t": 0,
            "is_screen_shared": rng.random() < 0.5,
            "chat_stage": rng.choice(["none", "payment_demand"]),
            "intent_claim": "receive_refund",
            "payment_direction": "outgoing",
        }
    return {
        "amount": float(rng.randint(1_000, 50_000)),
        "d_R": 3,
        "z_t": round(rng.uniform(0.1, 0.5), 2),
        "e_t": 0.1,
        "g_t": 0.0,
        "pi_t": 0,
        "is_screen_shared": False,
        "chat_stage": "none",
        "intent_claim": "none",
        "payment_direction": "outgoing",
    }


def call_maya(payload: dict) -> tuple[dict, float]:
    t0 = time.perf_counter()
    resp = requests.post(
        API_URL,
        json=payload,
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json(), (time.perf_counter() - t0) * 1000.0


def main() -> int:
    ap = argparse.ArgumentParser(description="HDFC UPI switch -> Maya Bank API")
    ap.add_argument("--n", type=int, default=100, help="number of transactions")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    results = []  # (txn, action, amount, latency_ms)

    console.print(
        Panel.fit(
            f"[bold cyan]HDFC BANK[/] → Maya UPI Switch — processing "
            f"[bold]{args.n}[/] transactions",
            border_style="cyan",
        )
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Routing through Maya…", total=args.n)
        for i in range(args.n):
            payload = make_txn(i, rng)
            trace, latency = call_maya(payload)
            action = trace["final_decision"]["action"]
            results.append((i, action, payload["amount"], latency))
            progress.advance(task)

    total = len(results)
    holds = [r for r in results if r[1] == "hold"]
    releases = [r for r in results if r[1] == "release"]
    nudges = [r for r in results if r[1] == "nudge"]
    money_saved = sum(r[2] for r in holds)
    avg_latency = sum(r[3] for r in results) / total if total else 0.0

    report = Table(title="BANK SWITCH REPORT", title_style="bold white on blue",
                   border_style="blue")
    report.add_column("Metric", style="cyan")
    report.add_column("Value", style="bold")
    report.add_row("Total Transactions Processed", f"{total}")
    report.add_row("Total Scams Blocked (HOLD)", f"[red]{len(holds)}[/]")
    report.add_row("Total Safe Payments (RELEASE)", f"[green]{len(releases)}[/]")
    report.add_row("Warnings (NUDGE)", f"[yellow]{len(nudges)}[/]")
    report.add_row("Total Money Saved", f"[green]₹{money_saved:,.0f}[/]")
    report.add_row("Average API Latency", f"{avg_latency:.1f} ms per check")
    console.print(report)

    if holds:
        blocked = Table(title="❌ CRITICAL ALERTS BLOCKED BEFORE NPCI",
                        title_style="bold white on red", border_style="red")
        blocked.add_column("#", justify="right")
        blocked.add_column("Amount", justify="right")
        blocked.add_column("Action", justify="center")
        blocked.add_column("Conformal Set")
        for i, action, amount, _ in holds:
            blocked.add_row(str(i), f"₹{amount:,.0f}", "[red]HOLD[/]",
                            "{fine, scam}")
        console.print(Panel(blocked, border_style="red"))
    else:
        console.print("[green]No scams detected — all clear.[/]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
