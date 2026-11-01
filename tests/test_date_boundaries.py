import unittest
from app.core import DEFAULTS,locate

class DateBoundaryTests(unittest.TestCase):
    def test_blank_following_block_does_not_inherit_date(self):
        values=[['','11-01','','',''],['','认识','诗歌舞蹈','认识','诗歌舞蹈'],['测试']]
        record=dict(operator='测试',timestamp='2026-11-01T12:00:00',category='诗歌舞蹈',reflection='感想')
        cfg=DEFAULTS | {'first_person_row':3}
        merges=[dict(startRowIndex=0,endRowIndex=1,startColumnIndex=1,endColumnIndex=3),
                dict(startRowIndex=0,endRowIndex=1,startColumnIndex=3,endColumnIndex=5)]
        self.assertEqual(locate(values,cfg,record,merges),(3,3,2))
        values[0][3]='11-01'
        with self.assertRaises(ValueError): locate(values,cfg,record,merges)
