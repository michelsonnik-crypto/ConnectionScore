from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connection_score.pipeline import build
if __name__=='__main__':
    build()
