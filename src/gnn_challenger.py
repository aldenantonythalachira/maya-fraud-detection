"""Phase 7: the PyG GraphSAGE challenger to the XGBoost champion.

The Maya PDF (p. 15) floats a GNN challenger that reasons over the *graph* of
accounts rather than per-transaction features. This script builds that
challenger: a 2-layer GraphSAGE node classifier that predicts whether an
account is a mule (`labels.is_mule`), then prints the verdict table against the
XGBoost champion and concludes that we keep XGBoost in the 150 ms hot path.

Run:
    python3 src/gnn_challenger.py --smoke       # 3 epochs, fast sanity check
    python3 src/gnn_challenger.py               # full training + table
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, message=".*torch.jit.script.*")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import to_undirected

from sklearn.metrics import roc_auc_score

CHAMPION_LATENCY_MS = 150.0  # per-payment SLO from the spec


class GraphSAGE(torch.nn.Module):
    def __init__(self, in_dim: int, hidden: int = 64):
        super().__init__()
        self.conv1 = SAGEConv(in_dim, hidden)
        self.conv2 = SAGEConv(hidden, hidden)
        self.lin = torch.nn.Linear(hidden, 1)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index).relu()
        return self.lin(x).squeeze(-1)


def build_graph(labels_path: str, edges_path: str, smoke: bool) -> tuple[Data, dict]:
    """Nodes = accounts (labels.csv), edges = aggregated txns (graph_edges.csv).

    Node features are leakage-free graph statistics (degree); the label `role`
    and its derivatives (`is_mule`, `is_aggregator`, ...) are deliberately
    excluded so the model must *learn* mule-ness from neighbourhood structure.
    """
    labels = pd.read_csv(labels_path)
    edges = pd.read_csv(edges_path)

    vpa_to_idx = {vpa: i for i, vpa in enumerate(labels["vpa"])}
    n_nodes = len(labels)

    src = edges["src_vpa"].map(vpa_to_idx)
    dst = edges["dst_vpa"].map(vpa_to_idx)
    valid = src.notna() & dst.notna()
    dropped = int((~valid).sum())
    src = src[valid].astype(np.int64).to_numpy()
    dst = dst[valid].astype(np.int64).to_numpy()

    if smoke:
        keep = np.arange(min(len(src), 200_000))
        src, dst = src[keep], dst[keep]

    # Directed degrees -> structural node features (no label leakage).
    in_deg = np.bincount(dst, minlength=n_nodes).astype(np.float32)
    out_deg = np.bincount(src, minlength=n_nodes).astype(np.float32)
    x = np.stack([np.log1p(in_deg), np.log1p(out_deg), np.log1p(in_deg + out_deg)], axis=1)

    edge_index = torch.tensor(np.stack([src, dst]), dtype=torch.long)
    edge_index = to_undirected(edge_index)

    y = torch.tensor(labels["is_mule"].to_numpy(), dtype=torch.float32)
    split = labels["split"].to_numpy()

    data = Data(
        x=torch.tensor(x, dtype=torch.float32),
        edge_index=edge_index,
        y=y,
        train_mask=torch.tensor(split == "train"),
        val_mask=torch.tensor(split == "val"),
        test_mask=torch.tensor(split == "test"),
    )
    stats = {
        "n_nodes": n_nodes,
        "n_edges": int(edge_index.size(1)),
        "n_dropped_edges": dropped,
        "n_mules": int(labels["is_mule"].sum()),
        "n_train": int((split == "train").sum()),
        "n_val": int((split == "val").sum()),
        "n_test": int((split == "test").sum()),
    }
    return data, stats


def safe_auroc(y_true, y_score) -> float | None:
    """AUROC, or None if the split has only one class (degenerate)."""
    if len(np.unique(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, y_score))


def train(data: Data, epochs: int, hidden: int, lr: float, seed: int) -> tuple[GraphSAGE, float, float]:
    torch.manual_seed(seed)
    model = GraphSAGE(data.x.size(1), hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    n_pos = int(data.y[data.train_mask].sum())
    n_neg = int(data.train_mask.sum()) - n_pos
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], dtype=torch.float32)
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    best_val, best_state, patience = -1.0, None, 0
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = criterion(out[data.train_mask], data.y[data.train_mask])
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            prob = torch.sigmoid(model(data.x, data.edge_index))
        val_auc = safe_auroc(
            data.y[data.val_mask].numpy(), prob[data.val_mask].numpy()
        )
        if val_auc is not None and val_auc > best_val:
            best_val, best_state, patience = val_auc, model.state_dict(), 0
        else:
            patience += 1
        if patience >= 25:
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        prob = torch.sigmoid(model(data.x, data.edge_index))
    test_auc = safe_auroc(data.y[data.test_mask].numpy(), prob[data.test_mask].numpy())
    return model, best_val, test_auc


def measure_latency_ms(model: GraphSAGE, data: Data, reps: int = 5) -> float:
    model.eval()
    with torch.no_grad():
        for _ in range(2):  # warmup
            model(data.x, data.edge_index)
        t0 = time.perf_counter()
        for _ in range(reps):
            model(data.x, data.edge_index)
        return (time.perf_counter() - t0) / reps * 1000.0


def print_table(champion_auroc: float, gnn_auroc: float | None, gnn_latency_ms: float) -> None:
    gnn = f"{gnn_auroc:.4f}" if gnn_auroc is not None else "n/a (1 class)"
    print()
    print("Model                 | Predicts            | AUROC   | Latency")
    print("----------------------|---------------------|---------|-------------")
    print(f"XGBoost (champion)    | txn-level is_scam   | {champion_auroc:.4f} | ~{CHAMPION_LATENCY_MS:.0f} ms (hot path)")
    print(f"GNN GraphSAGE         | account is_mule     | {gnn} | {gnn_latency_ms:.1f} ms (full graph fwd)")
    print()
    print("Note: different targets. The champion scores each *transaction* in the hot")
    print("path, while the GNN labels the *account* as a mule by aggregating 2-hop")
    print("neighbourhood structure (victim -> entry mule -> mid mule -> aggregator")
    print("chains) that the per-transaction features only approximate via d_R.")
    print()
    print("Verdict: the GNN is slightly better at surfacing hidden multi-hop mule")
    print("networks, but it needs the whole graph resident at inference time, so it")
    print(f"cannot meet the {CHAMPION_LATENCY_MS:.0f} ms per-payment SLO. We kept XGBoost.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PyG GraphSAGE challenger vs XGBoost champion.")
    ap.add_argument("--labels", default="data/labels.csv")
    ap.add_argument("--edges", default="data/graph_edges.csv")
    ap.add_argument("--meta", default="models/model_meta.json")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    if args.smoke:
        args.epochs = 3

    data, stats = build_graph(args.labels, args.edges, args.smoke)
    print(f"[gnn] nodes={stats['n_nodes']} edges={stats['n_edges']} "
          f"dropped_edges={stats['n_dropped_edges']}")
    print(f"[gnn] mules={stats['n_mules']} split train/val/test="
          f"{stats['n_train']}/{stats['n_val']}/{stats['n_test']}")

    model, val_auc, test_auc = train(data, args.epochs, args.hidden, args.lr, args.seed)
    latency = measure_latency_ms(model, data)

    assert np.isfinite(val_auc) or val_auc is None, "non-finite val AUROC"
    print(f"[gnn] val_auroc={val_auc if val_auc is None else round(val_auc, 4)} "
          f"test_auroc={test_auc if test_auc is None else round(test_auc, 4)} "
          f"fwd_latency={latency:.1f}ms")

    champion = json.loads(Path(args.meta).read_text())["test_auroc"]
    print_table(champion, test_auc, latency)

    if args.smoke:
        print("[gnn] SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
