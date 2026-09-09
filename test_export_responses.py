import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

import download_posts
import download_comments
import http_client


def response(body):
    result = requests.Response()
    result.status_code = 200
    result._content = body.encode('utf-8')
    result.encoding = 'utf-8'
    result._content_consumed = True
    return result


class ExportResponseTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(folder))
        self.enterContext(patch.object(http_client, 'sleep'))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def test_valid_empty_month_is_accepted(self):
        xml = '<livejournal/>'
        with patch.object(http_client._session, 'request', return_value=response(xml)):
            self.assertEqual(http_client.export_xml('POST', '/export_do.bml'), xml)

    def test_html_and_malformed_responses_are_rejected_without_body(self):
        for body in ('<html><body>private-token</body></html>',
                     '<html>private-token', 'private-token'):
            with self.subTest(body=body):
                with patch.object(http_client._session, 'request', return_value=response(body)):
                    with self.assertRaises(http_client.LiveJournalRequestError) as caught:
                        http_client.export_xml('POST', '/export_do.bml')
                self.assertNotIn('private-token', str(caught.exception))

    def test_download_recovers_from_eof_and_saves_post(self):
        xml = ('<livejournal><entry><itemid>256</itemid>'
               '<eventtime>2024-01-02 03:04:05</eventtime>'
               '<subject>Test</subject><event>Post body</event>'
               '</entry></livejournal>')
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder), \
                patch('builtins.input', side_effect=['2024-01', '2024-01']), \
                patch.object(download_posts, 'authenticated_request_params', return_value={}), \
                patch.object(http_client._session, 'request', side_effect=[
                    requests.exceptions.SSLError('UNEXPECTED_EOF_WHILE_READING'), response(xml)
                ]) as send, patch.object(http_client, 'sleep'), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            posts = download_posts.download_posts()
            self.assertEqual(posts[0]['body'], 'Post body')
            self.assertEqual(Path('posts-xml/2024-01.xml').read_text(), xml)
            self.assertTrue(Path('posts-json/all.json').is_file())
            self.assertEqual(send.call_count, 2)

    def test_invalid_response_does_not_overwrite_existing_month(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder), \
                patch('builtins.input', side_effect=['2024-01', '2024-01']), \
                patch.object(download_posts, 'authenticated_request_params', return_value={}), \
                patch.object(http_client._session, 'request', return_value=response('<html/>')), \
                contextlib.redirect_stdout(io.StringIO()):
            os.mkdir('posts-xml')
            existing = Path('posts-xml/2024-01.xml')
            existing.write_text('previous backup')
            with self.assertRaises(http_client.LiveJournalRequestError):
                download_posts.download_posts()
            self.assertEqual(existing.read_text(), 'previous backup')

    def test_comment_download_uses_same_retry_client(self):
        xml = '<livejournal><comments/></livejournal>'
        with patch.object(download_comments, 'authenticated_request_params', return_value={}), \
                patch.object(http_client._session, 'request', side_effect=[
                    requests.exceptions.Timeout(), response(xml)
                ]) as send, patch.object(http_client, 'sleep'), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(download_comments.fetch_xml({'get': 'comment_body', 'startid': 1}), xml)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args.args[:2],
                             ('GET', 'https://www.livejournal.com/export_comments.bml'))


if __name__ == '__main__':
    unittest.main()
