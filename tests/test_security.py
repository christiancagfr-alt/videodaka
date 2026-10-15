import json
import tempfile
import unittest
from pathlib import Path
from app.security import is_youtube_url, validate_sample, load_service_account, safe_error
from app.core import Tracker
from app.downloads import download_arguments


class SecurityTests(unittest.TestCase):
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
