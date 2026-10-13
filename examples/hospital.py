"""Fictional hospital access-control sandbox; never connects to real records."""

import argparse
import json

from kjnlae import Guard
from kjnlae.integrations.hosts import run_hospital_case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case", choices=["own_patient", "other_patient", "cross_tenant", "injected_note"]
    )
    args = parser.parse_args()
    guard = Guard()
    print(json.dumps(run_hospital_case(args.case, guard), indent=2))
    guard.close()


if __name__ == "__main__":
    main()
