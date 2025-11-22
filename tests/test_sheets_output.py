from transaction_tracker.outputs.sheets_output import SheetsOutput


def test_table_and_sort_requests_monthly():
    rows = [
        ['date', 'description', 'merchant', 'category', 'amount'],
        ['2024-01-01', 'Desc', 'Merc', 'Cat', 10.0],
    ]
    out = object.__new__(SheetsOutput)
    reqs = out._table_and_sort_requests(sheet_id=1, row_count=len(rows), column_count=len(rows[0]), amount_col_index=4)
    assert reqs[0]['setBasicFilter']['filter']['range'] == {
        'sheetId': 1,
        'startRowIndex': 0,
        'endRowIndex': len(rows),
        'startColumnIndex': 0,
        'endColumnIndex': len(rows[0])
    }
    assert reqs[1]['sortRange']['sortSpecs'][0]['dimensionIndex'] == 4


def test_table_and_sort_requests_alldata():
    rows = [
        ['month', 'date', 'description', 'merchant', 'category', 'amount'],
        ['Jan', '2024-01-01', 'Desc', 'Merc', 'Cat', 20.0],
    ]
    out = object.__new__(SheetsOutput)
    reqs = out._table_and_sort_requests(sheet_id=2, row_count=len(rows), column_count=len(rows[0]), amount_col_index=5)
    assert reqs[0]['setBasicFilter']['filter']['range']['endColumnIndex'] == len(rows[0])
    assert reqs[1]['sortRange']['range']['sheetId'] == 2
