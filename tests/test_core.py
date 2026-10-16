import tempfile
import unittest
from unittest.mock import patch,MagicMock
from datetime import date
from pathlib import Path
from app.core import Store,Tracker,DEFAULTS,locate,growth_level,growth_stage,growth_size,GROWTH_TO_MATURE_DAYS
from app.sync import LocalSheets,GoogleSheets,sync_pending

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.store=Store(self.temp.name); self.cfg=DEFAULTS|{'operator':'测试者'}
    def tearDown(self): self.store.db.close(); self.temp.cleanup()
    def record(self,watched=95,reflection='感恩',duration=100):
        return self.store.add(dict(operator='测试者',title='测试视频',url='https://www.youtube.com/watch?v=test',duration=duration,watched=watched,category='电影',reflection=reflection),self.cfg)
    def test_threshold_repeat_and_notes(self):
        self.record(94); a=self.record(watched=1140,duration=1200); self.record(watched=1140,reflection='坚持',duration=1200)
        self.assertEqual(sync_pending(self.store),(3,[]))
        LocalSheets(self.store).sync(a,self.cfg)
        row=self.store.db.execute('SELECT * FROM local_summary').fetchone()
        self.assertEqual(row['count'],2); self.assertIn('感恩',row['reflection']); self.assertIn('坚持',row['reflection'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM local_log').fetchone()[0],3)
        stats=self.store.stats('测试者','local'); self.assertEqual(stats['qualified'],2); self.assertEqual(stats['days'][date.today().isoformat()],2)
    def test_queue_survives_restart(self):
        self.record(); other=Store(self.temp.name)
        try: self.assertEqual(sync_pending(other),(1,[])); self.assertEqual(sync_pending(other),(0,[]))
        finally: other.db.close()
    def test_failed_sync_retries_without_losing_record(self):
        self.record()
        with patch.object(LocalSheets,'sync',side_effect=ConnectionError('offline')):
            done,errors=sync_pending(self.store)
        self.assertEqual(done,0); self.assertEqual(errors,['offline'])
        self.assertEqual(self.store.records()[0]['status'],'pending')
        self.assertEqual(sync_pending(self.store),(1,[]))
    def test_google_batch_marker_and_formula_guard(self):
        r=self.record(watched=1140,duration=1200); backend=object.__new__(GoogleSheets)
        log=MagicMock(); log.row_values.return_value=list(__import__('app.core',fromlist=['HEADERS']).HEADERS); log.col_values.return_value=[r['id']]
        ws=MagicMock(); ws.title='月份'; ws.id=7
        ws.get_all_values.return_value=[['',date.today().isoformat(),'',''],['姓名','是否达标','认识','电影'],[],[],['测试者','','旧认识',2]]
        ws.spreadsheet.fetch_sheet_metadata.return_value={'sheets':[{'data':[{'rowData':[{'values':[{'note':'保留备注'}]}]}]}]}
        ws.acell.return_value.value='2'; ws.cell.return_value.value='旧认识'
        backend.sheet=lambda key,title: log if title==self.cfg['log_sheet'] else ws
        backend.sync(r,self.cfg)
        req=ws.spreadsheet.batch_update.call_args[0][0]['requests']
        self.assertEqual(len(req),3); self.assertEqual(req[0]['updateCells']['rows'][0]['values'][0]['userEnteredValue']['numberValue'],3)
        note=req[0]['updateCells']['rows'][0]['values'][0]['note']
        self.assertEqual(note,'保留备注\n• 《测试视频》'); self.assertNotIn(r['id'],note)
        self.assertEqual(req[-1]['createDeveloperMetadata']['developerMetadata']['metadataValue'],r['id'])
        self.assertIn('旧认识',req[1]['updateCells']['rows'][0]['values'][0]['userEnteredValue']['stringValue'])
        ws.spreadsheet.batch_update.reset_mock(); ws.acell.return_value.value='=SUM(A1:A2)'
        with self.assertRaises(ValueError): backend.sync(r,self.cfg)
        ws.spreadsheet.batch_update.assert_not_called()
        ws.spreadsheet.fetch_sheet_metadata.return_value={'sheets':[{'data':[{'rowData':[{'values':[{'note':f"[devotion:{r['id']}]"}]}]}]}]}
        backend.sync(r,self.cfg); ws.spreadsheet.batch_update.assert_not_called()
        ws.spreadsheet.fetch_sheet_metadata.return_value={'sheets':[{'data':[{'rowData':[{'values':[{'note':'• 《测试视频》'}]}]}]}], 'developerMetadata':[{'metadataKey':'devotion_record','metadataValue':r['id']}]}
        backend.sync(r,self.cfg); ws.spreadsheet.batch_update.assert_not_called()
    def test_seek_pause_speed_and_repeat(self):
        t=Tracker()
        def sample(pos,clock,playing=True,rate=1): t.sample(dict(id='a',title='A',duration=100,position=pos,clock=clock,playing=playing,rate=rate))
        sample(0,0); sample(1,1000); sample(90,2000); sample(91,3000)
        self.assertEqual(t.watched,2)
        sample(91,4000,False); sample(92,5000); self.assertEqual(t.watched,2)
        sample(0,6000); sample(1,7000); self.assertEqual(t.watched,2)
        sample(2,8000,True,2); sample(4,9000,True,2); self.assertEqual(t.watched,5)
        t.reset(); self.assertEqual(t.watched,0)
    def test_auto_registration_gate_and_new_round(self):
        t=Tracker(); t.video='real'; t.duration=100; t.intervals=[(0,94)]
        self.assertFalse(t.can_auto_register('张三','电影'))
        t.intervals=[(0,95)]; self.assertTrue(t.can_auto_register('张三','电影'))
        self.assertFalse(t.can_auto_register('','电影')); self.assertFalse(t.can_auto_register('张三',''))
        t.registered=True; self.assertFalse(t.can_auto_register('张三','电影'))
        t.reset(); self.assertFalse(t.can_auto_register('张三','电影'))
        t.intervals=[(0,95)]; self.assertTrue(t.can_auto_register('张三','电影'))
        t.video='local-demo'; self.assertFalse(t.can_auto_register('张三','电影'))
    def test_growth_starts_with_seedling(self):
        self.assertEqual(self.store.stats('测试者','local')['level'],1)
        # Short videos remain in the journal but provide no growth nutrition.
        self.record(duration=1199,watched=1199)
        self.assertEqual(self.store.stats('测试者','local')['nutrition_days'],0)
        self.record(duration=1200,watched=1140,reflection='')
        partial=self.store.stats('测试者','local')
        self.assertEqual(partial['nutrition_days'],.25)  # One long video without a reflection.
        self.record(duration=1200,watched=1140,reflection='')
        undernourished=self.store.stats('测试者','local')
        self.assertFalse(undernourished['goal_days'][date.today().isoformat()])
        self.assertEqual(undernourished['nutrition_days'],.5)
        self.record(duration=1200,watched=1140,reflection='感想')
        nourished=self.store.stats('测试者','local')
        self.assertEqual(nourished['qualified'],3)
        self.assertTrue(nourished['goal_days'][date.today().isoformat()])
        self.assertEqual(nourished['nutrition_days'],1)
        self.assertEqual(nourished['level'],1)
        self.assertEqual(growth_level(0),1)
        self.assertEqual(growth_level(GROWTH_TO_MATURE_DAYS/4),2)
        self.assertEqual(growth_level(GROWTH_TO_MATURE_DAYS),5)
    def test_tree_continues_to_gain_size_after_maturity(self):
        self.assertEqual(growth_stage(0),'幼苗')
        self.assertEqual(growth_stage(365),'树苗')
        self.assertEqual(growth_stage(GROWTH_TO_MATURE_DAYS),'青年树')
        self.assertEqual(growth_stage(10*365),'成树')
        self.assertEqual(growth_stage(80*365),'古树')
        self.assertEqual(growth_size(GROWTH_TO_MATURE_DAYS),1)
        self.assertGreater(growth_size(40*365),growth_size(GROWTH_TO_MATURE_DAYS))
        self.assertGreater(growth_size(100*365),growth_size(40*365))

    def test_legacy_google_retry_config_uses_previous_credentials_key(self):
        import json
        from unittest.mock import patch
        cfg={'mode':'google','credentials':'desktop-client.json','log_id':'log','log_sheet':'日志',
             'summary_id':'summary','summary_sheet':'10月'}
        record=dict(operator='测试者',title='待同步',url='https://www.youtube.com/watch?v=old',duration=1200,
                    watched=1140,category='电影',reflection='')
        saved=self.store.add(record,cfg)
        with self.store.db:
            self.store.db.execute('UPDATE records SET config=? WHERE id=?',(json.dumps(cfg),saved['id']))
        with patch('app.sync.GoogleSheets') as backend:
            backend.return_value.sync.side_effect=ValueError('授权未连接')
            done,errors=sync_pending(self.store)
        self.assertEqual(done,0); self.assertEqual(errors,['授权未连接'])
        self.assertEqual(backend.call_args.args[0]['oauth_client_file'],'desktop-client.json')
        self.assertNotIn('oauth_client_file',errors[0])
    def test_draft_restores_coverage_and_crash_deduplication(self):
        tracker=Tracker(); tracker.video='test'; tracker.title='视频'; tracker.duration=100
        tracker.intervals=[(0,50),(70,90)]; tracker.position=90
        draft={'tracker':tracker.snapshot(),'category':'电影','reflection':'未写完的感想'}
        self.store.save_state('draft:test',draft)
        other=Store(self.temp.name)
        try:
            restored=Tracker(); restored.restore(other.load_state('draft:test')['tracker'])
            self.assertEqual(restored.watched,70); self.assertEqual(restored.position,90); self.assertIsNone(restored.last)
            restored.sample(dict(id='test',title='视频',duration=100,position=95,clock=5000,playing=True,rate=1))
            self.assertEqual(restored.watched,70)
            # The first post-resume sample seeds the clock; subsequent playback must continue accruing coverage.
            restored.sample(dict(id='test',title='视频',duration=100,position=96,clock=6000,playing=True,rate=1))
            self.assertEqual(restored.watched,71)
            record=dict(session_id=restored.round_id,operator='测试者',title='视频',url='test',duration=100,watched=95,category='电影',reflection='感想')
            other.add(record,self.cfg); other.add(record,self.cfg)
            self.assertEqual(len(other.records()),1); self.assertTrue(other.has_record(restored.round_id))
        finally: other.db.close()
    def test_download_options_and_playlist(self):
        from app.downloads import download_arguments,playlist_url
        url='https://www.youtube.com/watch?v=abc&list=PL123'
        self.assertEqual(playlist_url(url),'https://www.youtube.com/playlist?list=PL123')
        self.assertEqual(playlist_url('https://example.com/?list=PL123'),'')
        args=download_arguments(url,self.temp.name,'1080')
        self.assertIn('bv*[height<=1080]+ba/b[height<=1080]',args); self.assertIn('--no-playlist',args)
        self.assertIn('--yes-playlist',download_arguments(url,self.temp.name,'2160',True))
        self.assertEqual(args[-1],url)
    def test_mapping_and_duplicate_guard(self):
        r=self.record(); values=[['',date.today().isoformat(),'',''],['姓名','是否达标','认识','电影'],['测试者','','','']]
        cfg=self.cfg|{'first_person_row':3}; self.assertEqual(locate(values,cfg,r),(3,4,3))
        values.append(['测试者'])
        with self.assertRaises(ValueError): locate(values,cfg,r)
    def test_config_snapshot_and_mode_isolation(self):
        self.record(); self.cfg['mode']='google'; self.assertEqual(self.store.records()[0]['mode'],'local'); self.assertEqual(self.store.stats('测试者','google')['total'],0)
    def test_real_sample_mapping(self):
        import openpyxl
        path=Path(__file__).resolve().parents[1]/'视频数据表.xlsx'
        if not path.exists(): self.skipTest('Private local workbook is not distributed')
        wb=openpyxl.load_workbook(path,data_only=True); ws=wb.worksheets[0]; values=[list(row) for row in ws.values]; wb.close()
        # Replace only in-memory anonymous name. Never save the user's workbook.
        values[4][0]='测试者'; values=[[v if v is not None else '' for v in row] for row in values]
        r=self.record(); r['timestamp']='2026-10-31T10:00:00+01:00'; r['category']=values[1][18]
        self.assertEqual(locate(values,self.cfg,r),(5,19,18))

if __name__=='__main__': unittest.main()
