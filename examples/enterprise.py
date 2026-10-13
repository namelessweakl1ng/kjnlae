"""Fictional enterprise access-control sandbox; all data are synthetic."""

import argparse
import json

from kjnlae import Guard
from kjnlae.integrations.hosts import run_enterprise_case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case",
        choices=[
            "public_policy",
            "hr_authorized",
            "other_employee",
            "redirect_email",
            "detector_miss",
            "admin_tool",
        ],
    )
    args = parser.parse_args()
    guard = Guard()
    print(json.dumps(run_enterprise_case(args.case, guard), indent=2))
    guard.close()


if __name__ == "__main__":
    main()
