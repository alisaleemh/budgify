import pandas as pd

from transaction_tracker.loaders.amex import AmexLoader


def test_amex_loader_skips_blank_amount_rows(monkeypatch):
    """Rows without an amount should be skipped instead of raising."""

    header_probe = pd.DataFrame([
        ['Date', 'Description', 'Amount'],
        ['2024-01-01', 'Charge', '12.34'],
    ])

    data_df = pd.DataFrame({
        'Date': ['2024-01-01', '2024-01-02'],
        'Description': ['Charge 1', 'Charge 2'],
        'Amount': ['12.34', float('nan')],
    })

    call_state = {'count': 0}

    def fake_read_excel(*args, **kwargs):
        if call_state['count'] == 0:
            call_state['count'] += 1
            return header_probe
        return data_df

    monkeypatch.setattr(pd, 'read_excel', fake_read_excel)

    loader = AmexLoader()
    txs = list(loader.load('fake.xlsx'))

    assert len(txs) == 1
    assert txs[0].amount == 12.34
