import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connection_score.safety import SafetyError, assert_month, assert_date, assert_features, read_development, raw_archive, validate_config
import json

class SafetyTests(unittest.TestCase):
    def test_reject_test_before_any_open(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('file must not open')):
            for name in ('connections_test.csv.gz','connections_unknown.csv.gz'):
                with self.assertRaises(SafetyError):
                    read_development(Path('/tmp')/name)
            with self.assertRaises(SafetyError):
                raw_archive(Path(__file__).resolve().parents[1]/'data/raw/bts_2025_11.zip')
    def test_dates_and_config(self):
        for value in ('2025-11-01','2025-12-31','2026-01-01'):
            with self.assertRaises(SafetyError): assert_date(value)
        assert_date('2025-10-31')
        config=json.loads((Path(__file__).resolve().parents[1]/'configs/research.json').read_text())
        validate_config(config)
        config['split_months']['train'].append(11)
        with self.assertRaises(SafetyError):validate_config(config)
    def test_positive_contract_including_aliases(self):
        assert_features(['origin','gap_minutes'])
        assert_features(['history_route_mean_delay'],allow_history=True)
        for col in ('ArrDelay','first_actual_arrival','Cancelled','WeatherDelay','label_45','status','Tail_Number','unknown_new_column'):
            with self.assertRaises(SafetyError):assert_features(['gap_minutes',col],allow_history=True)
        with self.assertRaises(SafetyError):assert_features(['history_route_mean_delay'])
    def test_modified_processed_data_rejected_before_parser(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'data/processed').mkdir(parents=True);(root/'configs').mkdir();(root/'reports').mkdir()
            config=json.loads((Path(__file__).resolve().parents[1]/'configs/research.json').read_text())
            (root/'configs/research.json').write_text(json.dumps(config))
            (root/'reports/connections.json').write_text(json.dumps({'configuration':config,'splits':{'train':{'sha256':'wrong'}}}))
            path=root/'data/processed/connections_train.csv.gz';path.write_bytes(b'not a dataset')
            with patch.object(pd,'read_csv',side_effect=AssertionError('parser must not run')):
                with self.assertRaises(SafetyError):read_development(path,root=root)

if __name__=='__main__':unittest.main()
