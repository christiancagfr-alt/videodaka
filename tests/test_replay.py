import unittest
from app.core import Tracker

class ReplayTests(unittest.TestCase):
    def sample(self,t,p,clock,**extra):
        t.sample(dict(id='video',title='Video',duration=100,position=p,clock=clock,
                      playing=True,seeking=False,rate=1,adShowing=False) | extra)
    def completed(self):
        t=Tracker();t.video='video';t.duration=100;t.intervals=[(0,95)];t.position=95;t.registered=True
        return t
    def test_replay_requires_fresh_coverage_and_repeats(self):
        t=self.completed();old=t.round_id
        self.sample(t,96,1000);self.sample(t,97,2000)
        self.assertTrue(t.registered);self.assertFalse(t.can_auto_register('name','category'))
        self.sample(t,0,3000)
        self.assertFalse(t.registered);self.assertNotEqual(t.round_id,old);self.assertEqual(t.watched,0)
        for second in range(1,96): self.sample(t,second,3000+second*1000)
        self.assertTrue(t.can_auto_register('name','category'))
        t.registered=True;old=t.round_id
        self.sample(t,0,100000)
        self.assertNotEqual(t.round_id,old);self.assertEqual(t.watched,0)
    def test_ads_pause_and_seek_do_not_rearm(self):
        for extra in ({'adShowing':True},{'playing':False},{'seeking':True}):
            t=self.completed();self.sample(t,0,1000,**extra);self.assertTrue(t.registered)
    def test_restart_keeps_completed_round_until_replay(self):
        t=Tracker();t.restore(self.completed().snapshot());old=t.round_id
        self.sample(t,99,1000);self.assertTrue(t.registered)
        self.sample(t,0,2000);self.assertFalse(t.registered);self.assertNotEqual(t.round_id,old)
