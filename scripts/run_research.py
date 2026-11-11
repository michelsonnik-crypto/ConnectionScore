"""One command to rebuild development data, reports, models and app data."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
for args in [('scripts/fetch_data.py','--research'),('scripts/build_connections.py',),('scripts/train_models.py',),('scripts/export_checker_model.py',)]:
    subprocess.run([sys.executable,*args],cwd=root,check=True)
print('Run python -m http.server 8000 --directory app to view the app. TEST remains locked.')
