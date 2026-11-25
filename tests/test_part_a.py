import sys
import unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'src')]
import pandas as pd
from part_a import daily_contrast

class AnalysisTests(unittest.TestCase):
    def test_identical_daily_outcomes_have_zero_difference_and_interval(self):
        rows=[]
        for day in ('2025-01-03','2025-01-04','2025-01-05'):
            for hub in ('ATL','ORD'):
                for value in (0,0,1):rows.append(dict(departure_date=day,hub=hub,label_45=value))
        frame=pd.DataFrame(rows)
        result=daily_contrast(frame,frame.hub=='ATL',frame.hub=='ORD','synthetic')
        self.assertEqual(result['difference_b_minus_a'],0)
        self.assertEqual(result['interval_95'],[0,0])
        self.assertEqual(result['days'],3)
        self.assertEqual(result['n_a'],9)

if __name__=='__main__':unittest.main()
