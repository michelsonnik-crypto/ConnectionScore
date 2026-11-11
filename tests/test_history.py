import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connection_score.history import snapshots,allowed_months,augment

class HistoryGuards(unittest.TestCase):
    def test_future_outcomes_do_not_change_earlier_snapshot(self):
        key=('AA','JFK','ORD')
        monthly={1:{key:[20,-100,2]},2:{key:[20,200,4]},8:{key:[100,100000,100]}}
        before=snapshots(monthly)
        monthly[8][key]=[100,-100000,0]
        after=snapshots(monthly)
        self.assertEqual(before[9],after[9])
        self.assertNotIn(8,before[9]['source_months'])
    def test_early_months_have_no_history(self):
        self.assertEqual(allowed_months(1),[])
        self.assertEqual(allowed_months(4),[])
        self.assertEqual(allowed_months(9),[1,2,3,4])
    def test_negative_delay_and_outcomes_not_used(self):
        import pandas as pd
        key=('AA','JFK','ORD')
        snap=snapshots({1:{key:[20,-100,2]}})
        row=pd.DataFrame([dict(departure_date='2025-09-03',origin='JFK',hub='ORD',carrier='AA',status='cancelled',label_45=1)])
        a=augment(row,snap)
        self.assertEqual(a.history_route_mean_delay.iloc[0],-5)
        self.assertEqual(a.history_route_late15_rate.iloc[0],.1)
        self.assertEqual(a.history_missing.iloc[0],0)
        row['status']='operated';row['label_45']=0
        b=augment(row,snap)
        self.assertEqual(a.history_route_mean_delay.iloc[0],b.history_route_mean_delay.iloc[0])
    def test_missing_has_no_future_fallback(self):
        import pandas as pd
        row=pd.DataFrame([dict(departure_date='2025-01-03',origin='JFK',hub='ORD',carrier='AA')])
        a=augment(row,snapshots({8:{('AA','JFK','ORD'):[50,500,25]}}))
        self.assertEqual(a.history_missing.iloc[0],1)
        self.assertEqual(a.history_carrier_late15_rate.iloc[0],0)

if __name__=='__main__':unittest.main()
