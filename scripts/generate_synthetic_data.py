import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

MERCHANTS = ["M-GROCERY", "M-FUEL", "M-TRAVEL", "M-ELECTRONICS", "M-CRYPTO"]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "NG"]


def transaction(index: int) -> dict[str, object]:
    fraud = random.random() < 0.08
    amount = round(random.uniform(15, 600), 2)
    if fraud:
        amount = round(random.uniform(2500, 15000), 2)
    device_known = not fraud or random.random() > 0.75
    ip_risk = random.uniform(0.65, 0.99) if fraud else random.uniform(0.01, 0.30)
    merchant = "M-CRYPTO" if fraud and random.random() < 0.55 else random.choice(MERCHANTS[:-1])
    return {
        "transaction_id": str(uuid4()),
        "customer_id": f"C-{random.randint(1, 250):04d}",
        "account_id": f"A-{random.randint(1, 350):04d}",
        "merchant_id": merchant,
        "amount": amount,
        "currency": "USD",
        "country_code": random.choice(COUNTRIES),
        "device_known": device_known,
        "ip_risk_score": round(ip_risk, 4),
        "merchant_risk_score": round(random.uniform(0.65, 0.95) if merchant == "M-CRYPTO" else random.uniform(0.02, 0.35), 4),
        "amount_zscore": round(random.uniform(3.0, 6.5) if fraud else random.uniform(-1.5, 1.5), 3),
        "velocity_1h": random.randint(6, 15) if fraud else random.randint(1, 3),
        "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=index * 3)).isoformat(),
        "synthetic_label": int(fraud),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--output", type=Path, default=Path("data/generated/transactions.jsonl"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index in range(args.count):
            handle.write(json.dumps(transaction(index)) + "\n")
    print(f"Wrote {args.count} transactions to {args.output}")


if __name__ == "__main__":
    main()
