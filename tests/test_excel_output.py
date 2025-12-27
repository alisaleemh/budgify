from transaction_tracker.outputs.excel_output import ExcelOutput


def test_build_chart_tables_orders_and_aggregates():
    out = object.__new__(ExcelOutput)
    all_rows = [
        ["month", "date", "description", "merchant", "category", "amount"],
        ["March 2024", "2024-03-01", "Desc", "Merc", "Restaurants", 20.0],
        ["January 2024", "2024-01-05", "Desc", "Merc", "Groceries", 10.0],
        ["February 2024", "2024-02-10", "Desc", "Merc", "Restaurants", 4.0],
        ["January 2024", "2024-01-15", "Desc", "Merc", "Groceries", 15.0],
        ["February 2024", "2024-02-20", "Desc", "Merc", "Other", 8.0],
    ]

    tables = out._build_chart_tables(all_rows)

    assert tables["monthly"] == [
        ["Month", "Total"],
        ["January 2024", 25.0],
        ["February 2024", 12.0],
        ["March 2024", 20.0],
    ]
    assert tables["restaurants"] == [
        ["Month", "Total"],
        ["January 2024", 0],
        ["February 2024", 4.0],
        ["March 2024", 20.0],
    ]
    assert tables["groceries"] == [
        ["Month", "Total"],
        ["January 2024", 25.0],
        ["February 2024", 0],
        ["March 2024", 0],
    ]
    assert tables["categories"][0] == ["Category", "Total"]
    assert tables["categories"][1:] == [
        ["Groceries", 25.0],
        ["Restaurants", 24.0],
        ["Other", 8.0],
    ]


def test_build_chart_tables_skips_short_rows():
    out = object.__new__(ExcelOutput)
    all_rows = [
        ["month", "date", "description", "merchant", "category", "amount"],
        ["January 2024", "2024-01-05", "Desc", "Merc", "Groceries", 10.0],
        ["Malformed"],
        ["February 2024", "2024-02-10", "Desc", "Merc", "Restaurants", 5.0],
    ]

    tables = out._build_chart_tables(all_rows)

    assert tables["monthly"] == [
        ["Month", "Total"],
        ["January 2024", 10.0],
        ["February 2024", 5.0],
    ]


def test_build_chart_tables_includes_configured_categories():
    out = object.__new__(ExcelOutput)
    all_rows = [
        ["month", "date", "description", "merchant", "category", "amount"],
        ["January 2024", "2024-01-05", "Desc", "Merc", "groceries", 10.0],
    ]

    tables = out._build_chart_tables(
        all_rows,
        categories={"car": [], "groceries": [], "misc": [], "restaurants": [], "subscription": []},
    )

    assert tables["categories"][0] == ["Category", "Total"]
    assert tables["categories"][1:] == [
        ["groceries", 10.0],
        ["car", 0],
        ["misc", 0],
        ["restaurants", 0],
        ["subscription", 0],
    ]
