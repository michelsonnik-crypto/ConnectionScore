"""Fail-closed development IO and positive feature contracts.

These controls cover repository entry points, not arbitrary code a user runs outside
this project. No TEST opening implementation is included: G4 must be reviewed first.
"""
from pathlib import Path
from datetime import date
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_SPLITS = ('train', 'validation', 'calibration', 'demo')
BASE_FEATURES = {'origin','hub','destination','carrier','gap_minutes','duration_minutes',
                 'hour_sin','hour_cos','week_sin','week_cos','year_sin','year_cos'}
HISTORY_FEATURES = {'history_route_count','history_route_mean_delay','history_route_late15_rate',
                    'history_carrier_mean_delay','history_carrier_late15_rate','history_missing'}

class SafetyError(RuntimeError):
    pass


def assert_month(year, month):
    # Keep TEST sealed even if a placeholder G4 file is added accidentally.
    # Opening requires a separately reviewed implementation and a signed decision.
    if year != 2025 or not 1 <= month <= 10:
        raise SafetyError('Only development months 2025-01 through 2025-10 are authorized; TEST is sealed')


def assert_date(value):
    day = date.fromisoformat(str(value)[:10])
    assert_month(day.year, day.month)
    return day


def validate_config(config):
    for split in DEVELOPMENT_SPLITS:
        for month in config['split_months'][split]:
            assert_month(config['year'], month)
        start, end = map(date.fromisoformat, config['split_windows'][split])
        assert_date(start)
        # End is exclusive, so November 1 is a valid development endpoint.
        if end <= start or end > date(2025, 11, 1):
            raise SafetyError('Unauthorized development window')
    if config['split_months']['test'] != [11, 12]:
        raise SafetyError('Reserved TEST definition changed')
    if config['gap_min'] > config['gap_max'] or config['embargo_days'] < 0:
        raise SafetyError('Invalid pairing or embargo configuration')


def assert_features(columns, allow_history=False):
    allowed = BASE_FEATURES | (HISTORY_FEATURES if allow_history else set())
    unexpected = set(columns) - allowed
    if unexpected:
        raise SafetyError('Unapproved model features: ' + ', '.join(sorted(unexpected)))


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def raw_archive(path, root=ROOT):
    path = Path(path).resolve()
    match = re.fullmatch(r'bts_(\d{4})_(\d{2})\.zip', path.name)
    if not match or path.parent != (root/'data/raw').resolve():
        raise SafetyError('Uncatalogued raw archive')
    assert_month(*map(int, match.groups()))  # before opening or hashing the archive
    manifest = json.loads((root/'data/manifest.json').read_text())
    expected = next((r for r in manifest if r['file'] == path.name), None)
    if not expected:
        raise SafetyError('Raw source missing provenance')
    assert_date(expected['coverage_start']); assert_date(expected['coverage_end'])
    if sha256(path) != expected['sha256']:
        raise SafetyError('Immutable raw source checksum mismatch')
    return zipfile.ZipFile(path)


def read_development(path, root=ROOT, **kwargs):
    """Only catalogued development files; reject unknown hashes BEFORE CSV parsing."""
    import pandas as pd
    path = Path(path).resolve()
    match = re.fullmatch(r'connections_(train|validation|calibration|demo)\.csv\.gz', path.name)
    if not match or path.parent != (root/'data/processed').resolve():
        raise SafetyError('Uncatalogued/TEST processed file; refusing to open')
    config = json.loads((root/'configs/research.json').read_text())
    validate_config(config)
    split = match[1]
    provenance = json.loads((root/'reports/connections.json').read_text())
    if provenance['configuration'] != config:
        raise SafetyError('Processed provenance/configuration mismatch; rebuild explicitly')
    expected = provenance['splits'][split]['sha256']
    if sha256(path) != expected:
        raise SafetyError('Processed checksum mismatch; refusing to parse')
    if kwargs.get('chunksize') or kwargs.get('iterator'):
        raise SafetyError('Use full verified frame; chunk readers not supported here')
    requested = kwargs.get('usecols')
    if requested is not None and 'departure_date' not in requested:
        kwargs['usecols'] = list(requested) + ['departure_date']
    frame = pd.read_csv(path, **kwargs)
    if frame.departure_date.isna().any():
        raise SafetyError('Missing event date')
    dates = pd.to_datetime(frame.departure_date, errors='raise')
    start, end = map(pd.Timestamp, config['split_windows'][split])
    if not ((dates >= start) & (dates < end) & (dates < pd.Timestamp('2025-11-01'))).all():
        raise SafetyError('Dates outside authorized split')
    if requested is not None:
        frame = frame[list(requested)]
    return frame
