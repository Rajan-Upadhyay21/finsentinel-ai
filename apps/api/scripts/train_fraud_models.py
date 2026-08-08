from __future__ import annotations

import argparse
import json

from app.ml.training import train_fraud_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train FinSentinel fraud and anomaly models."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=12000,
        help="Number of synthetic training rows.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/ml/fraud",
        help="Directory for model artifacts.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Reproducible random seed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = train_fraud_bundle(
        output_dir=args.output_dir,
        n_rows=args.rows,
        random_state=args.random_state,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
