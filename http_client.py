"""Shared connection pool and bounded retries for read-only export requests."""

import ssl
import sys
from time import sleep

import requests
from xml_responses import ExportResponseError, parse_response, save_response

BASE_URL = 'https://www.livejournal.com'
MAX_ATTEMPTS = 4
TIMEOUT = (15, 60)
EXPORT_REQUESTS = {
    ('POST', '/export_do.bml'),
    ('GET', '/export_comments.bml'),
}
_session = requests.Session()


class LiveJournalRequestError(RuntimeError):
    pass


def _is_tls_eof(error):
    # requests/urllib3 can wrap the original SSL exception several times.
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLEOFError):
            return True
        if 'UNEXPECTED_EOF_WHILE_READING' in str(current):
            return True
        pending.extend(arg for arg in getattr(current, 'args', ())
                       if isinstance(arg, BaseException))
        for name in ('reason', '__cause__', '__context__'):
            nested = getattr(current, name, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def request(method, path, *, retry=False, validate=None, **kwargs):
    """Never replay login. Callers opt in only for read-only export endpoints."""
    retry = retry and (method.upper(), path) in EXPORT_REQUESTS
    attempts = MAX_ATTEMPTS if retry else 1
    kwargs.setdefault('timeout', TIMEOUT)
    for attempt in range(1, attempts + 1):
        response = None
        xml_error = None
        try:
            response = _session.request(method, BASE_URL + path, **kwargs)
            response.raise_for_status()
            if validate is not None:
                validate(response)
            return response
        except ExportResponseError as error:
            xml_error = error
            transient = error.retryable
            reason = error.reason
            if error.position is not None:
                reason += f' at line {error.position[0]}, column {error.position[1]}'
        except requests.exceptions.SSLError as error:
            transient = _is_tls_eof(error)
            reason = 'TLS connection closed unexpectedly' if transient else 'TLS validation or connection failed'
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError):
            transient = True
            reason = 'connection interrupted or timed out'
        except requests.exceptions.HTTPError:
            transient = response.status_code in (502, 503, 504)
            reason = f'HTTP {response.status_code}'
        except requests.exceptions.RequestException:
            transient = False
            reason = 'request failed'

        if not transient or attempt == attempts:
            diagnostic = ''
            if xml_error is not None:
                try:
                    saved = save_response(response, path, kwargs, reason, xml_error.position)
                    diagnostic = f' Response saved locally: {saved}.'
                except OSError:
                    diagnostic = ' Could not save the diagnostic response (check disk access/space).'
            if response is not None:
                response.close()
            # Do not include exceptions, response bodies, cookies, or credentials.
            raise LiveJournalRequestError(
                f'{path}: {reason} after {attempt} attempt(s).{diagnostic}'
            ) from None
        if response is not None:
            response.close()
        delay = 2 ** attempt
        print(f'{path}: {reason}; retry {attempt + 1}/{attempts} in {delay}s.',
              file=sys.stderr, flush=True)
        sleep(delay)


def export_xml(method, path, **kwargs):
    parsed = []
    def validate(response):
        parsed.append(parse_response(response, path, kwargs))
    response = request(method, path, retry=True, validate=validate, **kwargs)
    try:
        return parsed[0]
    finally:
        response.close()
