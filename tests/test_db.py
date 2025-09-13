import sqlite3
from click.testing import CliRunner

from transaction_tracker.cli import main as cli
from tests.test_e2e import write_config, write_tdvisa_sample, write_manual


def test_cli_db_storage(tmp_path):
    stmts = tmp_path / 'stmts'
    stmts.mkdir()
    td_file = stmts / 'tdvisa.csv'
    write_tdvisa_sample(td_file)
    manual = tmp_path / 'manual.yaml'
    write_manual(manual)
    cfg_path = write_config(tmp_path, tmp_path / 'data')
    db_path = tmp_path / 'txs.db'

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            '--dir', str(stmts),
            '--output', 'csv',
            '--config', str(cfg_path),
            '--manual-file', str(manual),
            '--db', str(db_path),
        ],
    )
    assert res.exit_code == 0, res.output

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT date, description, merchant, amount, category FROM transactions'
    ).fetchall()
    conn.close()
    assert len(rows) == 3
    dates = sorted(r[0] for r in rows)
    assert dates == ['2025-05-02', '2025-05-03', '2025-05-04']
    amounts = sorted(r[3] for r in rows)
    assert amounts == [10.0, 12.34, 56.78]
    cats = {r[4] for r in rows}
    assert cats == {'groceries', 'restaurants', 'misc'}
