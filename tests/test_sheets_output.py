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


def test_build_chart_tables_orders_and_aggregates():
    out = object.__new__(SheetsOutput)
    all_rows = [
        ['month', 'date', 'description', 'merchant', 'category', 'amount'],
        ['March 2024', '2024-03-01', 'Desc', 'Merc', 'Restaurants', 20.0],
        ['January 2024', '2024-01-05', 'Desc', 'Merc', 'Groceries', 10.0],
        ['February 2024', '2024-02-10', 'Desc', 'Merc', 'Restaurants', 4.0],
        ['January 2024', '2024-01-15', 'Desc', 'Merc', 'Groceries', 15.0],
        ['February 2024', '2024-02-20', 'Desc', 'Merc', 'Other', 8.0],
    ]

    tables = out._build_chart_tables(all_rows)

    assert tables['monthly'] == [
        ['Month', 'Total'],
        ['January 2024', 25.0],
        ['February 2024', 12.0],
        ['March 2024', 20.0],
    ]
    assert tables['car'] == [
        ['Month', 'Total'],
        ['January 2024', 0],
        ['February 2024', 0],
        ['March 2024', 0],
    ]
    assert tables['categories'][0] == ['Category', 'Total']
    assert tables['categories'][1:] == [
        ['Groceries', 25.0],
        ['Restaurants', 24.0],
        ['Other', 8.0],
    ]


def test_build_chart_tables_skips_short_rows():
    out = object.__new__(SheetsOutput)
    all_rows = [
        ['month', 'date', 'description', 'merchant', 'category', 'amount'],
        ['January 2024', '2024-01-05', 'Desc', 'Merc', 'Groceries', 10.0],
        ['Malformed'],
        ['February 2024', '2024-02-10', 'Desc', 'Merc', 'Restaurants', 5.0],
    ]

    tables = out._build_chart_tables(all_rows)

    assert tables['monthly'] == [
        ['Month', 'Total'],
        ['January 2024', 10.0],
        ['February 2024', 5.0],
    ]


def test_charts_tab_requests_anchors_pie_within_grid():
    out = object.__new__(SheetsOutput)
    chart_layout = {
        'monthly': {'start_row': 0, 'row_count': 2},
        'car': {'start_row': 4, 'row_count': 2},
        'categories': {'start_row': 8, 'row_count': 3},
    }

    requests = out._charts_tab_requests(chart_sheet_id=5, chart_layout=chart_layout)

    pie_request = next(
        req for req in requests
        if 'addChart' in req and 'pieChart' in req['addChart']['chart']['spec']
    )
    anchor = pie_request['addChart']['chart']['position']['overlayPosition']['anchorCell']
    assert anchor['columnIndex'] == 8
