from datetime import date

import yaml
from click.testing import CliRunner

from transaction_tracker.cli import main as cli
from transaction_tracker.recurring import expand_recurring_transactions


def test_expand_recurring_daily_weekly_monthly():
    daily = expand_recurring_transactions(
        [
            {
                "description": "Daily",
                "merchant": "Test",
                "amount": 1,
                "cadence": "daily",
                "start_date": "2025-01-01",
                "end_date": "2025-01-03",
            }
        ]
    )
    assert [tx.date for tx in daily] == [
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
    ]

    weekly = expand_recurring_transactions(
        [
            {
                "description": "Weekly",
                "merchant": "Test",
                "amount": 2,
                "cadence": "weekly",
                "start_date": "2025-01-01",
                "count": 3,
            }
        ]
    )
    assert [tx.date for tx in weekly] == [
        date(2025, 1, 1),
        date(2025, 1, 8),
        date(2025, 1, 15),
    ]

    monthly = expand_recurring_transactions(
        [
            {
                "description": "Monthly",
                "merchant": "Test",
                "amount": 3,
                "cadence": "monthly",
                "start_date": "2025-01-31",
                "count": 3,
            }
        ]
    )
    assert [tx.date for tx in monthly] == [
        date(2025, 1, 31),
        date(2025, 2, 28),
        date(2025, 3, 31),
    ]


def test_expand_recurring_end_date_is_inclusive():
    txs = expand_recurring_transactions(
        [
            {
                "description": "Daily",
                "merchant": "Test",
                "amount": 1,
                "cadence": "daily",
                "start_date": "2025-01-01",
                "end_date": "2025-01-05",
            }
        ]
    )
    assert [tx.date for tx in txs] == [
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 4),
        date(2025, 1, 5),
    ]


def test_cli_merges_recurring_and_manual(tmp_path):
    stmts = tmp_path / "stmts"
    stmts.mkdir()
    config_path = tmp_path / "config.yaml"
    manual_path = tmp_path / "manual.yaml"
    data_dir = tmp_path / "data"

    manual_path.write_text(
        """\
- date: 2025-05-04
  description: Farmers Market
  merchant: CASH
  amount: 10
"""
    )

    config = {
        "bank_loaders": {},
        "output_modules": {
            "csv": "transaction_tracker.outputs.csv_output.CSVOutput",
        },
        "categories": {"groceries": ["farmers"]},
        "output_dir": str(data_dir),
        "recurring_transactions": [
            {
                "description": "Farmers Market",
                "merchant": "CASH",
                "amount": 10,
                "cadence": "monthly",
                "start_date": "2025-05-04",
                "count": 1,
            },
            {
                "description": "Streaming",
                "merchant": "StreamCo",
                "amount": 15,
                "cadence": "monthly",
                "start_date": "2025-05-10",
                "count": 1,
            },
        ],
    }
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "--dir",
            str(stmts),
            "--output",
            "csv",
            "--config",
            str(config_path),
            "--manual-file",
            str(manual_path),
        ],
    )
    assert res.exit_code == 0, res.output
    out_csv = data_dir / "Budget2025.csv"
    assert out_csv.exists()
    lines = out_csv.read_text().splitlines()
    assert len(lines) == 3
