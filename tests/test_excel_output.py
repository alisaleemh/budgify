from datetime import date
from transaction_tracker.outputs.excel_output import ExcelOutput
from transaction_tracker.core.models import Transaction

class FakeWorksheet:
    def __init__(self, name):
        self.name = name
    def freeze_panes(self, *args, **kwargs):
        pass
    def write_row(self, *args, **kwargs):
        pass
    def write_number(self, *args, **kwargs):
        pass
    def add_table(self, *args, **kwargs):
        pass
    def set_column(self, *args, **kwargs):
        pass

class FakeWorkbook:
    def __init__(self, path):
        self.path = path
        self.add_pivot_table_calls = []
    def add_format(self, *args, **kwargs):
        return None
    def add_worksheet(self, name):
        return FakeWorksheet(name)
    def add_pivot_table(self, options):
        self.add_pivot_table_calls.append(options)
    def close(self):
        pass

def test_summary_pivot_uses_constant_sheet_name(monkeypatch, tmp_path):
    created = {}
    def fake_workbook_init(path):
        wb = FakeWorkbook(path)
        created['wb'] = wb
        return wb
    monkeypatch.setattr('transaction_tracker.outputs.excel_output.xlsxwriter.Workbook', fake_workbook_init)
    cfg = {"categories": {}, "output_dir": tmp_path}
    tx = Transaction(date=date(2024, 1, 1), description="desc", merchant="store", amount=1.0)
    out = ExcelOutput(cfg)
    out.append([tx])
    wb = created['wb']
    summary_call = [c for c in wb.add_pivot_table_calls if c["name"] == "Pivot_Summary"][0]
    assert summary_call["dest"] == f"'{ExcelOutput.SUMMARY}'!A1"

