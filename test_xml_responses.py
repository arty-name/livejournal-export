"""Offline regressions for malformed export responses and private diagnostics."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import requests

import http_client
import xml_responses


class XmlResponseTests(unittest.TestCase):
    USERNAME = 'private-example-username'
    COOKIE = 'private-example-session-cookie'
    TOKEN = 'private-example-query-token'
    BODY = 'private-example-post-body'
    VALID = b'<livejournal><entry><itemid>1</itemid><event>ok</event></entry></livejournal>'

    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(folder))
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(self.output))
        self.send = self.enterContext(patch.object(http_client._session, 'request'))
        self.sleep = self.enterContext(patch.object(http_client, 'sleep'))

    def response(self, raw, *, encoding='utf-8'):
        response = requests.Response()
        response.status_code = 200
        response._content = raw
        response._content_consumed = True
        response.encoding = encoding
        response.url = f'https://www.livejournal.com/export_do.bml?token={self.TOKEN}'
        response.headers['Set-Cookie'] = f'ljmastersession={self.COOKIE}'
        response.close = Mock()
        return response

    def export(self):
        return http_client.export_xml(
            'POST', '/export_do.bml',
            data={'year': 2009, 'month': '04', 'user': self.USERNAME},
            cookies={'ljmastersession': self.COOKIE},
            headers={'Authorization': self.TOKEN},
        )

    def assert_no_secrets(self, text):
        for secret in (self.USERNAME, self.COOKIE, self.TOKEN, self.BODY):
            self.assertNotIn(secret, text)

    def diagnostic_path(self, raw):
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return Path(f'diagnostics/export_do-2009-04-{digest}.response.bin')

    def assert_private_diagnostic(self, raw):
        path = self.diagnostic_path(raw)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        metadata_path = path.with_suffix('.json')
        self.assertEqual(stat.S_IMODE(metadata_path.stat().st_mode), 0o600)
        metadata_text = metadata_path.read_text()
        self.assert_no_secrets(metadata_text)
        metadata = json.loads(metadata_text)
        self.assertEqual(metadata['bytes'], len(raw))
        self.assertEqual(metadata['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(metadata['endpoint'], '/export_do.bml')
        self.assertEqual(metadata['status'], 200)
        self.assertEqual(stat.S_IMODE(Path('diagnostics').stat().st_mode), 0o700)

    def assert_bounded_failure(self, raw):
        responses = [self.response(raw) for _ in range(http_client.MAX_ATTEMPTS)]
        self.send.side_effect = responses
        with self.assertRaises(http_client.LiveJournalRequestError) as caught:
            self.export()
        self.assertEqual(self.send.call_count, http_client.MAX_ATTEMPTS)
        self.assertEqual(self.sleep.call_count, http_client.MAX_ATTEMPTS - 1)
        self.assert_no_secrets(str(caught.exception))
        self.assert_no_secrets(self.output.getvalue())
        for response in responses:
            response.close.assert_called_once()
        self.assert_private_diagnostic(raw)
        return caught.exception

    def test_html_then_xml_retries_and_succeeds_without_diagnostics(self):
        invalid = self.response(f'<html><body>{self.BODY}</body></html>'.encode())
        valid = self.response(self.VALID)
        self.send.side_effect = [invalid, valid]

        result = self.export()

        self.assertEqual(result, self.VALID.decode())
        self.assertEqual(self.send.call_count, 2)
        self.sleep.assert_called_once_with(2)
        invalid.close.assert_called_once()
        valid.close.assert_called_once()
        self.assertFalse(Path('diagnostics').exists())
        self.assert_no_secrets(self.output.getvalue())

    def test_repeated_malformed_xml_saves_exact_private_response(self):
        raw = f'<livejournal><entry><event>{self.BODY}</event>'.encode()
        self.assert_bounded_failure(raw)

    def test_control_character_repair_preserves_full_content_and_original_bytes(self):
        raw = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<livejournal><entry><itemid>1</itemid>'
            f'<event>Начало\x01{self.BODY} конец</event></entry>'
            '<entry><itemid>2</itemid><event>Вторая запись</event></entry></livejournal>'
        ).encode('utf-8')
        response = self.response(raw)
        self.send.return_value = response

        result = self.export()

        self.assertEqual(result, raw.decode('utf-8').replace('\x01', '\ufffd'))
        root = ET.fromstring(result)
        self.assertEqual(len(root.findall('entry')), 2)
        self.assertEqual(root[0].findtext('event'), f'Начало\ufffd{self.BODY} конец')
        self.assertEqual(root[1].findtext('event'), 'Вторая запись')
        self.send.assert_called_once()
        self.sleep.assert_not_called()
        response.close.assert_called_once()
        self.assert_private_diagnostic(raw)
        self.assert_no_secrets(self.output.getvalue())
        self.assertIn('U+FFFD', self.output.getvalue())

    def test_xml_declaration_overrides_wrong_http_charset(self):
        text = ('<?xml version="1.0" encoding="windows-1251"?>'
                '<livejournal><entry><event>Привет, мир!</event></entry></livejournal>')
        self.send.return_value = self.response(text.encode('cp1251'), encoding='utf-8')

        result = self.export()

        self.assertEqual(ET.fromstring(result)[0].findtext('event'), 'Привет, мир!')
        self.assertIn('encoding="utf-8"', result)
        self.assertNotIn('\ufffd', result)
        self.assertFalse(Path('diagnostics').exists())

    def test_utf8_body_ignores_incorrect_latin1_http_encoding(self):
        raw = ('<?xml version="1.0" encoding="utf-8"?>'
               '<livejournal><entry><event>Привет</event></entry></livejournal>').encode()
        self.send.return_value = self.response(raw, encoding='ISO-8859-1')

        result = self.export()

        self.assertEqual(result, raw.decode('utf-8'))
        self.assertNotIn('\ufffd', result)

    def test_empty_body_retries_then_saves_zero_byte_diagnostic(self):
        error = self.assert_bounded_failure(b'')
        self.assertIn('empty response', str(error))

    def test_bare_html_is_retried_and_archived_without_printing_body(self):
        raw = f'<!doctype html><html><body>{self.USERNAME} {self.BODY}'.encode()
        error = self.assert_bounded_failure(raw)
        self.assertIn('HTML', str(error))

    def test_truncated_xml_is_never_accepted_even_if_it_contains_control_characters(self):
        raw = (f'<livejournal><entry><event>\x01{self.BODY}</event></entry>'
               '<entry><event>second').encode()
        self.assert_bounded_failure(raw)

    def test_bare_error_text_in_livejournal_root_is_not_an_empty_month(self):
        self.assert_bounded_failure(f'<livejournal>{self.BODY}</livejournal>'.encode())

    def test_nonascii_encoding_declaration_has_bounded_sanitized_failure(self):
        raw = b'<?xml version="1.0" encoding="\xff"?><livejournal/>'
        self.assert_bounded_failure(raw)

    def test_incomplete_existing_diagnostic_stops_repair_without_false_success(self):
        raw = b'<livejournal><entry><event>before\x01after</event></entry></livejournal>'
        path = self.diagnostic_path(raw)
        path.parent.mkdir(mode=0o700)
        path.write_bytes(b'incomplete diagnostic')
        self.send.return_value = self.response(raw)

        with self.assertRaises(http_client.LiveJournalRequestError) as caught:
            self.export()

        self.assertEqual(path.read_bytes(), b'incomplete diagnostic')
        self.assertIn('cannot preserve the original', str(caught.exception))
        self.assertNotIn('original response kept', self.output.getvalue())
        self.assert_no_secrets(self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
