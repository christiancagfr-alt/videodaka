import json
import io
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from app.security import is_youtube_url, validate_sample, load_service_account, safe_error
from app.core import Tracker
from app.downloads import download_arguments,find_ffmpeg
from app.sync import insert_latest_log_row
from app.updates import version_tuple, latest_release
from app.oauth import oauth_client_id, _store
from app.oauth import login


class SecurityTests(unittest.TestCase):
    def test_ffmpeg_path_detection_prefers_saved_and_path_files(self):
        with tempfile.TemporaryDirectory() as directory:
            saved=Path(directory)/'custom-ffmpeg.exe'; saved.write_bytes(b'')
            from_path=Path(directory)/'ffmpeg.exe'; from_path.write_bytes(b'')
            self.assertEqual(find_ffmpeg(str(saved),which=lambda _name:''),str(saved.resolve()))
            self.assertEqual(find_ffmpeg('',which=lambda name:str(from_path) if name=='ffmpeg.exe' else ''),str(from_path.resolve()))
            self.assertEqual(find_ffmpeg('',which=lambda _name:''),'')

    def test_update_version_parsing(self):
        self.assertEqual(version_tuple('v1.2.3'),(1,2,3))
        self.assertEqual(version_tuple('1.2.3-rc.1'),(1,2,3))
        for value in ('1.2','1.2.3.4','../2.0.0',None):
            self.assertIsNone(version_tuple(value))

    def test_update_check_accepts_only_official_release_links(self):
        class Reply(io.BytesIO): status=200
        release={'draft':False,'prerelease':False,'tag_name':'v0.3.0','name':'New version',
                 'html_url':'https://github.com/christiancagfr-alt/videodaka/releases/tag/v0.3.0'}
        with patch('app.updates.urlopen',return_value=Reply(json.dumps(release).encode())):
            self.assertEqual(latest_release()['version'],'v0.3.0')
        release['html_url']='https://example.test/download'
        with patch('app.updates.urlopen',return_value=Reply(json.dumps(release).encode())):
            with self.assertRaises(RuntimeError): latest_release()

    def test_oauth_desktop_file_validation(self):
        desktop={'installed':{'client_id':'sample.apps.googleusercontent.com','client_secret':'not-a-secret',
            'auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.json'; path.write_text(json.dumps(desktop),encoding='utf-8')
            self.assertEqual(oauth_client_id(path),'sample.apps.googleusercontent.com')
            for data in ({'web':desktop['installed']},desktop|{'installed':desktop['installed']|{'token_uri':'https://evil.test/token'}}):
                path.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError): oauth_client_id(path)

    def test_oauth_login_reports_success_only_after_token_store_readback(self):
        from types import SimpleNamespace
        credentials=SimpleNamespace(id_token={'email':'reader@example.test'},valid=True,to_json=lambda:'{}')
        flow=SimpleNamespace(run_local_server=lambda **_kwargs:credentials,
                             client_config={'client_id':'sample.apps.googleusercontent.com'})
        with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file',return_value=flow), \
             patch('app.oauth.save_tokens') as save, \
             patch('app.oauth.load_credentials',return_value=credentials) as readback:
            self.assertEqual(login('client.json'),('sample.apps.googleusercontent.com','reader@example.test'))
        save.assert_called_once_with('sample.apps.googleusercontent.com',credentials)
        readback.assert_called_once_with('sample.apps.googleusercontent.com')

    def test_oauth_secret_store_uses_native_platform_backend(self):
        backend=_store().get_keyring()
        actual=type(backend).__module__+'.'+type(backend).__name__
        expected={'win32':'keyring.backends.Windows.WinVaultKeyring',
                  'darwin':'keyring.backends.macOS.Keyring'}.get(sys.platform)
        self.assertEqual(actual,expected)

    def test_latest_log_insert_and_retry_dedup(self):
        class Worksheet:
            def __init__(self): self.rows=[]
            def col_values(self,column): return ['header']+[row[-1] for row in self.rows]
            def insert_row(self,values,**kwargs): self.rows.insert(kwargs['index']-2,values); self.kwargs=kwargs
        sheet=Worksheet(); headers=['登记时间','记录ID']
        self.assertTrue(insert_latest_log_row(sheet,headers,['now','id-1'],'id-1'))
        self.assertEqual(sheet.kwargs['index'],2)
        self.assertEqual(sheet.kwargs['value_input_option'],'RAW')
        self.assertFalse(insert_latest_log_row(sheet,headers,['now','id-1'],'id-1'))
        self.assertTrue(insert_latest_log_row(sheet,headers,['later','id-2'],'id-2'))
        self.assertEqual([row[-1] for row in sheet.rows],['id-2','id-1'])

    def test_browser_origin_boundary(self):
        self.assertTrue(is_youtube_url('https://www.youtube.com/watch?v=abc'))
        for url in ('http://www.youtube.com/', 'https://youtube.com.evil.test/',
                    'https://youtube.com@evil.test/', 'file:///tmp/test',
                    'https://youtube.com:8443/', 'https://youtube.com:bad/'):
            self.assertFalse(is_youtube_url(url), url)

    def test_invalid_browser_samples(self):
        sample=dict(id='abc',title='Video',duration=100,position=2,clock=1000,rate=1,playing=True)
        self.assertEqual(validate_sample(sample),sample)
        for key,value in (('position',float('nan')),('duration',float('inf')),
                          ('position','0;alert(1)'),('id','../bad'),('playing','true')):
            self.assertIsNone(validate_sample(sample|{key:value}))

    def test_restore_rejects_executable_and_nonfinite_positions(self):
        value=dict(video='abc',duration=100,position=2,intervals=[[0,2]])
        Tracker().restore(value)
        for mutation in ({'position':'1;alert(1)'},{'duration':float('inf')},
                         {'intervals':[[0,101]]},{'intervals':[[0,float('nan')]]}):
            with self.assertRaises(ValueError): Tracker().restore(value|mutation)

    def test_credentials_reject_untrusted_token_endpoint(self):
        account=dict(type='service_account',client_email='test@example.iam.gserviceaccount.com',
                     project_id='test',private_key='synthetic-not-a-real-key',
                     token_uri='https://oauth2.googleapis.com/token')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'account.json'
            path.write_text(json.dumps(account),encoding='utf-8')
            self.assertEqual(load_service_account(path),account)
            for uri in ('http://oauth2.googleapis.com/token','https://evil.test/token',
                        'https://oauth2.googleapis.com.evil.test/token'):
                path.write_text(json.dumps(account|{'token_uri':uri}),encoding='utf-8')
                with self.assertRaises(ValueError): load_service_account(path)

    def test_download_configuration_isolation(self):
        args=download_arguments('https://example.com/video','downloads')
        for flag in ('--ignore-config','--no-plugin-dirs','--no-exec'):
            self.assertIn(flag,args)
        self.assertEqual(args[-2],'--')
        for url in ('file:///etc/passwd','https://user:password@example.com/', '--exec=bad'):
            with self.assertRaises(ValueError): download_arguments(url,'downloads')

    def test_sensitive_errors_are_redacted(self):
        message='Bearer secret-value https://example.com/?access_token=secret-token&x=1'
        result=safe_error(message)
        self.assertNotIn('secret-value',result)
        self.assertNotIn('secret-token',result)
        self.assertLessEqual(len(safe_error('x'*10000)),1800)

    def test_xml_entities_disabled(self):
        from openpyxl.xml import functions
        from defusedxml.common import DefusedXmlException
        self.assertTrue(functions.DEFUSEDXML)
        payload=b'<!DOCTYPE a [<!ENTITY secret SYSTEM "file:///nonexistent">]><a>&secret;</a>'
        with self.assertRaises(DefusedXmlException): functions.fromstring(payload)
