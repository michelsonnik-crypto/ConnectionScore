"""Download the initial public data; Python 3.11+, no dependencies."""
from pathlib import Path
import datetime
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("bts_2025_01.zip", "https://www.transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip", "2025-01-01", "2025-01-31"),
    ("airports.csv", "https://davidmegginson.github.io/ourairports-data/airports.csv", None, None),
    ("bts_fields.html", "https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ", None, None),
]


def main():
    raw = ROOT / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "data/manifest.json"
    old = {x["file"]: x for x in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
    manifest = []
    for name, url, start, end in SOURCES:
        path = raw / name
        if path.exists() and name in old:
            digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
            if digest == old[name]["sha256"]:
                manifest.append(old[name])
                print(f"Verified cached file: {name}")
                continue
        temp = path.with_suffix(path.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temp.open("wb") as f:
                while chunk := response.read(1024 * 1024):
                    f.write(chunk)
                resolved = response.url
            if name.endswith(".zip"):
                with zipfile.ZipFile(temp) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise ValueError(f"Corrupt ZIP member: {bad}")
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        manifest.append(dict(file=name, source_url=url, resolved_url=resolved,
                             retrieved_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             coverage_start=start, coverage_end=end, bytes=path.stat().st_size,
                             sha256=hashlib.file_digest(path.open("rb"), "sha256").hexdigest()))
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Downloaded: {name}")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
