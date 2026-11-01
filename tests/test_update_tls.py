import ssl
import unittest
from unittest.mock import patch
from app.updates import secure_urlopen

class UpdateTLSTests(unittest.TestCase):
    def test_update_requests_load_bundled_roots_and_verify_certificates(self):
        with patch('app.updates.urlopen') as request:
            secure_urlopen('https://api.github.com', timeout=5)
        context=request.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreater(len(context.get_ca_certs()), 0)

    def test_certificate_failure_is_not_retried_without_validation(self):
        with patch('app.updates.urlopen', side_effect=ssl.SSLCertVerificationError('untrusted')) as request:
            with self.assertRaises(ssl.SSLCertVerificationError):
                secure_urlopen('https://api.github.com', timeout=5)
        request.assert_called_once()
