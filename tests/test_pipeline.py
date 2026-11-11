import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connection_score.pipeline import local_to_utc, hhmm, outcome, normalize

class ScientificGuards(unittest.TestCase):
    def test_exact_threshold_and_late_arrival(self):
        dep=datetime(2025,1,1,13,30,tzinfo=timezone.utc)
        second={'status':'operated','dep':dep}
        first={'status':'operated','actual':dep-timedelta(minutes=45)}
        self.assertEqual(outcome(first,second,45),('operated',0))
        first['actual']=dep-timedelta(minutes=30)
        self.assertEqual(outcome(first,second,45),('operated',1))
        second['actual']=dep+timedelta(hours=4)
        self.assertEqual(outcome(first,second,45),('operated',1))
    def test_missing_cancelled_diverted(self):
        for status in ['missing','cancelled','diverted']:
            self.assertEqual(outcome({'status':status,'actual':None},{'status':'operated'},45),(status,None))
    def test_midnight(self):
        self.assertEqual(local_to_utc('2025-01-01','2400','America/New_York'),datetime(2025,1,2,5,tzinfo=timezone.utc))
        with self.assertRaises(ValueError): hhmm('1260')
    def test_dst(self):
        for day,clock in [('2025-03-09','0230'),('2025-11-02','0130')]:
            with self.assertRaises(ValueError): local_to_utc(day,clock,'America/New_York')
        self.assertEqual(local_to_utc('2025-07-01','1200','America/New_York').hour,16)
    def test_overnight_and_early_arrival(self):
        row=dict(FlightDate='2025-01-01',CRSDepTime='2300',CRSArrTime='0200',CRSElapsedTime='120',Origin='ORD',Dest='JFK',Cancelled='0',Diverted='0',ArrDelay='-10',ArrTime='0150',Reporting_Airline='AA',Flight_Number_Reporting_Airline='12')
        f=normalize(row,{'ORD':'America/Chicago','JFK':'America/New_York'})
        self.assertEqual(f['arr'],datetime(2025,1,2,7,tzinfo=timezone.utc))
        self.assertEqual((f['actual']-f['arr']).total_seconds(),-600)
    def test_clock_inconsistency(self):
        row=dict(FlightDate='2025-01-01',CRSDepTime='1200',CRSArrTime='1500',CRSElapsedTime='60',Origin='ORD',Dest='JFK',Cancelled='0',Diverted='0',ArrDelay='0',ArrTime='1500',Reporting_Airline='AA',Flight_Number_Reporting_Airline='12')
        with self.assertRaises(ValueError): normalize(row,{'ORD':'America/Chicago','JFK':'America/New_York'})


class LeakageGuards(unittest.TestCase):
    def test_split_boundaries(self):
        from connection_score.pipeline import permitted
        from datetime import date
        f={'dep':datetime(2025,9,3,12,tzinfo=timezone.utc),'arr':datetime(2025,9,3,15,tzinfo=timezone.utc),'actual':datetime(2025,9,3,15,tzinfo=timezone.utc)}
        self.assertTrue(permitted(f,date(2025,9,1),date(2025,10,1),2))
        f['actual']=datetime(2025,10,1,1,tzinfo=timezone.utc)
        self.assertFalse(permitted(f,date(2025,9,1),date(2025,10,1),2))
    def test_outcomes_do_not_change_features(self):
        import pandas as pd
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from train_models import features
        df=pd.DataFrame([dict(origin='ATL',hub='ORD',destination='LAX',carrier='AA',gap_minutes=60,duration_minutes=300,departure_hour=12,weekday=1,month=1,status='operated',label_45=0)])
        before=features(df)
        df['status']='cancelled';df['label_45']=1
        pd.testing.assert_frame_equal(before,features(df))
    def test_test_is_unavailable(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'data/raw/bts_2025_11.zip').exists())
        self.assertFalse((root/'data/raw/bts_2025_12.zip').exists())
        self.assertFalse((root/'data/processed/connections_test.csv.gz').exists())

if __name__=='__main__':unittest.main()
