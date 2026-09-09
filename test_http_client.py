"""Offline regression checks for the export HTTP transport."""

import contextlib
import io
import ssl
import unittest
from unittest.mock import Mock, patch

import requests
from urllib3.exceptions import MaxRetryError, SSLError as Urllib3SSLError

import http_client


class HttpClientTests(unittest.TestCase):
    SECRET = 'ljmastersession=do-not-print-this-cookie'

    def setUp(self):
        self.send = self.enterContext(patch.object(http_client._session, 'request'))
        self.sleep = self.enterContext(patch.object(http_client, 'sleep'))
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(self.output))

    def response(self, status=200):
        response = requests.Response()
        response.status_code = status
        response.url = 'https://www.livejournal.com/export_do.bml'
        response._content = (
            b'<livejournal />' if status == 200 else self.SECRET.encode()
        )
        response.close = Mock()
        return response

    def eof(self):
        return requests.exceptions.SSLError(
            MaxRetryError(
                None,
                '/export_do.bml',
                reason=Urllib3SSLError(
                    ssl.SSLEOFError(8, 'TLS connection closed ' + self.SECRET)
                ),
            )
        )

    def assert_safe_failure(self, method='POST', path='/export_do.bml', retry=True):
        with self.assertRaises(http_client.LiveJournalRequestError) as caught:
            http_client.request(method, path, retry=retry)
        self.assertNotIn(self.SECRET, str(caught.exception))
        self.assertNotIn(self.SECRET, self.output.getvalue())

    def test_nested_ssl_eof_retries_then_returns_response(self):
        response = self.response()
        self.send.side_effect = [self.eof(), response]

        result = http_client.request('POST', '/export_do.bml', retry=True)

        self.assertIs(result, response)
        self.assertEqual(self.send.call_count, 2)
        self.sleep.assert_called_once()
        self.assertNotIn(self.SECRET, self.output.getvalue())

    def test_ssl_eof_text_is_also_retryable(self):
        response = self.response()
        self.send.side_effect = [
            requests.exceptions.SSLError('UNEXPECTED_EOF_WHILE_READING'),
            response,
        ]

        self.assertIs(
            http_client.request('GET', '/export_comments.bml', retry=True),
            response,
        )
        self.assertEqual(self.send.call_count, 2)

    def test_ssl_eof_exhausts_after_four_attempts(self):
        self.send.side_effect = self.eof()

        self.assert_safe_failure()

        self.assertEqual(self.send.call_count, 4)
        self.assertEqual(self.sleep.call_count, 3)

    def test_login_is_not_replayed(self):
        self.send.side_effect = self.eof()

        self.assert_safe_failure(path='/login.bml', retry=False)

        self.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_certificate_verification_failure_is_not_retried(self):
        self.send.side_effect = requests.exceptions.SSLError(
            ssl.SSLCertVerificationError(
                1, 'CERTIFICATE_VERIFY_FAILED ' + self.SECRET
            )
        )

        self.assert_safe_failure()

        self.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_other_ssl_failure_is_not_retried(self):
        self.send.side_effect = requests.exceptions.SSLError(
            'WRONG_VERSION_NUMBER ' + self.SECRET
        )

        self.assert_safe_failure()

        self.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_forbidden_is_not_retried_or_leaked(self):
        self.send.return_value = self.response(403)

        self.assert_safe_failure()

        self.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_retryable_http_response_is_closed_before_retry(self):
        for status in (502, 503, 504):
            with self.subTest(status=status):
                failed = self.response(status)
                successful = self.response()
                self.send.reset_mock()
                self.sleep.reset_mock()
                self.send.side_effect = [failed, successful]

                self.assertIs(
                    http_client.request('POST', '/export_do.bml', retry=True),
                    successful,
                )

                self.assertEqual(self.send.call_count, 2)
                failed.close.assert_called_once()
                successful.close.assert_not_called()
                self.sleep.assert_called_once()

    def test_retryable_http_exhaustion_is_bounded_and_sanitized(self):
        self.send.side_effect = [self.response(503) for _ in range(4)]

        self.assert_safe_failure()

        self.assertEqual(self.send.call_count, 4)
        self.assertEqual(self.sleep.call_count, 3)

    def test_timeout_and_connection_error_retry_for_export(self):
        for error_type in (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ):
            with self.subTest(error_type=error_type.__name__):
                successful = self.response()
                self.send.reset_mock()
                self.sleep.reset_mock()
                self.send.side_effect = [error_type(self.SECRET), successful]

                self.assertIs(
                    http_client.request('GET', '/export_comments.bml', retry=True),
                    successful,
                )

                self.assertEqual(self.send.call_count, 2)
                self.assertNotIn(self.SECRET, self.output.getvalue())

    def test_incomplete_login_response_is_not_replayed(self):
        self.send.side_effect = requests.exceptions.ChunkedEncodingError(self.SECRET)
        self.assert_safe_failure(path='/login.bml', retry=False)
        self.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_requests_have_timeout_and_keep_certificate_validation(self):
        self.send.return_value = self.response()

        http_client.request('POST', '/export_do.bml', retry=True, data={'year': 2024})

        self.send.assert_called_once()
        kwargs = self.send.call_args.kwargs
        self.assertEqual(kwargs['timeout'], (15, 60))
        self.assertIs(http_client._session.verify, True)
        self.assertIs(kwargs.get('verify', True), True)
        self.assertEqual(kwargs['data'], {'year': 2024})
        self.assertNotIn('retry', kwargs)


if __name__ == '__main__':
    unittest.main()
