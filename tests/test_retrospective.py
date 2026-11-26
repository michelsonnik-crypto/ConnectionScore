import sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'src')]
import pandas as pd
import numpy as np
from retrospective import fit,predict,difference
class RetrospectiveTests(unittest.TestCase):
 def test_cdf_equality_and_monotone_thresholds(self):
  d=pd.DataFrame({'first_id':['a','a','b','c'],'gap_minutes':[60,80,60,60],'remaining_from_primary':[60,80,50,40],'label_45':[0,0,0,1]})
  m=fit('gap_cdf',d,45)
  q=pd.DataFrame({'gap_minutes':[55]})
  # gap-tau=10; strict > means only the delay 20 exceeds it.
  self.assertAlmostEqual(predict(m,q,'gap_cdf',45)[0],2/5)
  p=[predict(m,q,'gap_cdf',t)[0] for t in [30,45,60]]
  self.assertEqual(p,sorted(p))
 def test_identical_predictions_have_zero_paired_interval(self):
  d=pd.DataFrame({'departure_date':['2025-01-03','2025-01-03','2025-01-04'],'label_45':[0,1,0]})
  p=np.array([.1,.8,.2]);r=difference(d,p,p)
  self.assertEqual(r['brier_difference'],0);self.assertEqual(r['interval_95'],[0,0])
if __name__=='__main__':unittest.main()
