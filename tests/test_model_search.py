import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model_search import calibrate,calibrated,CONFIG,NAMES

class CalibrationGuards(unittest.TestCase):
    def test_methods_are_bounded_and_monotone(self):
        rng=np.random.default_rng(42)
        p=np.linspace(.001,.8,3000)
        true=1/(1+np.exp(-(np.log(p/(1-p))+.4)))
        y=rng.binomial(1,true)
        for method in CONFIG['calibration_methods']:
            with self.subTest(method=method):
                fitted=calibrate(method,p,y)
                out=calibrated(fitted,p)
                self.assertTrue(np.isfinite(out).all())
                self.assertTrue(((out>=0)&(out<=1)).all())
                self.assertTrue((np.diff(out)>=-1e-12).all())
    def test_identity_does_not_fit_labels(self):
        p=np.array([.1,.5,.9])
        a=calibrated(calibrate('none',p,[0,0,1]),p)
        b=calibrated(calibrate('none',p,[1,1,0]),p)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_allclose(a,p)
    def test_test_is_excluded_by_design(self):
        self.assertFalse(CONFIG['test_access'])
        self.assertFalse(CONFIG['selection_uses_demo'])
        self.assertEqual(CONFIG['screen_months'],[6,7,8])
        self.assertEqual(len(NAMES),23)
        root=Path(__file__).resolve().parents[1]
        for month in [11,12]:self.assertFalse((root/f'data/raw/bts_2025_{month}.zip').exists())

if __name__=='__main__':unittest.main()
