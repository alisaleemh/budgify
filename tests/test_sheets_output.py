from unittest.mock import MagicMock

from transaction_tracker.outputs.sheets_output import SheetsOutput


def test_apply_table_and_sort_monthly():
    ws = MagicMock()
    rows = [
        ['date', 'description', 'merchant', 'category', 'amount'],
        ['2024-01-01', 'Desc', 'Merc', 'Cat', 10.0],
    ]
    out = object.__new__(SheetsOutput)
    out._apply_table_and_sort(ws, rows, amount_col=5)
    ws.set_basic_filter.assert_called_once_with('A1:E2')
    ws.sort.assert_called_once_with((5, 'des'), range='A2:E2')


def test_apply_table_and_sort_alldata():
    ws = MagicMock()
    rows = [
        ['month', 'date', 'description', 'merchant', 'category', 'amount'],
        ['Jan', '2024-01-01', 'Desc', 'Merc', 'Cat', 20.0],
    ]
    out = object.__new__(SheetsOutput)
    out._apply_table_and_sort(ws, rows, amount_col=6)
    ws.set_basic_filter.assert_called_once_with('A1:F2')
    ws.sort.assert_called_once_with((6, 'des'), range='A2:F2')
