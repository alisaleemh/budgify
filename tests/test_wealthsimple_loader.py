from transaction_tracker.loaders.wealthsimple import (
    WealthsimpleLoader,
    normalize_statement_filename,
)


def test_normalize_statement_filename():
    assert normalize_statement_filename(
        "credit-card-statement-transactions-2026-05-01.csv"
    ) == "ws-05-2026.csv"
    assert normalize_statement_filename("ws-05-2026.csv") == "ws-05-2026.csv"


def test_wealthsimple_loader_parses_sample(tmp_path):
    sample = tmp_path / "credit-card-statement-transactions-2026-05-01.csv"
    sample.write_text(
        "\n".join(
            [
                "transaction_date,post_date,type,details,amount,currency",
                "2026-05-04,2026-05-04,Purchase,DAATA GRILL,15.81,CAD",
                "2026-05-17,2026-05-17,Refund settled,UBER CANADA,-22.14,CAD",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    txs = list(WealthsimpleLoader().load(str(sample)))

    assert len(txs) == 2
    assert [tx.date.isoformat() for tx in txs] == ["2026-05-04", "2026-05-17"]
    assert [tx.description for tx in txs] == ["Purchase", "Refund settled"]
    assert [tx.merchant for tx in txs] == ["DAATA GRILL", "UBER CANADA"]
    assert [tx.amount for tx in txs] == [15.81, -22.14]
