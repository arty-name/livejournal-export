"""Strict export parsing, with private copies of unexpected server responses."""

import codecs
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from xml.parsers import expat


class ExportResponseError(Exception):
    def __init__(self, reason, *, retryable=True, position=None):
        self.reason = reason
        self.retryable = retryable
        self.position = position


def save_response(response, endpoint, options, reason, position=None):
    """Save body locally, never cookies/request headers or credentials."""
    raw = response.content
    digest = hashlib.sha256(raw).hexdigest()
    label = endpoint.strip('/').replace('.bml', '')
    data = options.get('data', {})
    if str(data.get('year', '')).isdigit() and str(data.get('month', '')).isdigit():
        label += f'-{int(data["year"]):04d}-{int(data["month"]):02d}'
    folder = Path('diagnostics')
    folder.mkdir(mode=0o700, exist_ok=True)
    path = folder / f'{label}-{digest[:16]}.response.bin'
    metadata = {'endpoint': endpoint, 'status': response.status_code,
                'bytes': len(raw), 'sha256': digest, 'reason': reason,
                'xml_error_position': position}
    for target, body in ((path, raw), (path.with_suffix('.json'),
                         json.dumps(metadata, indent=2).encode('utf-8'))):
        fd, temporary = tempfile.mkstemp(prefix='.response-', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(body)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = target.read_bytes()
                if existing != body:
                    # The same response may first fail and later be repaired.
                    # Keep the original diagnostic note if its identity matches.
                    if target == path:
                        raise OSError('Existing diagnostic copy differs from the response.')
                    try:
                        previous = json.loads(existing)
                        matches = (previous['sha256'] == digest
                                   and previous['bytes'] == len(raw)
                                   and previous['endpoint'] == endpoint)
                    except (ValueError, KeyError, TypeError):
                        matches = False
                    if not matches:
                        raise OSError('Existing diagnostic metadata is incomplete or inconsistent.')
        finally:
            os.unlink(temporary)
    return path


def _decode(raw):
    # The XML declaration/BOM takes precedence over the HTTP charset.
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        encoding = 'utf-32'
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = 'utf-16'
    elif raw.startswith(b'\x00<\x00?'):
        encoding = 'utf-16-be'
    elif raw.startswith(b'<\x00?\x00'):
        encoding = 'utf-16-le'
    else:
        declaration = re.match(br'\s*<\?xml\b[^?]*\bencoding\s*=\s*[\'"]([^\'"]+)', raw[:256])
        try:
            encoding = declaration.group(1).decode('ascii') if declaration else 'utf-8-sig'
        except UnicodeError:
            raise ExportResponseError('response has an invalid XML encoding declaration') from None
    try:
        text = raw.decode(encoding)
    except (UnicodeError, LookupError):
        raise ExportResponseError('response has invalid or unsupported XML encoding') from None
    # Callers save strings as UTF-8, so keep the declaration consistent.
    return re.sub(r'(<\?xml\b[^?]*\bencoding\s*=\s*)([\'"])[^\'"]+\2',
                  r'\1"utf-8"', text, count=1)


def _transcode_comment_fields(raw):
    """Repair legacy CP1251 fields without re-decoding modern UTF-8 fields.

    The single-byte parser is used only to locate XML field byte boundaries;
    its decoded text is never used as archive content.
    """
    parser = expat.ParserCreate('iso-8859-1')
    stack = []
    ranges = []
    starts = {}
    parent = ['livejournal', 'comments', 'comment']

    def start(name, attrs):
        if stack[:3] == parent and len(stack) > 3:
            raise ExportResponseError('nested markup in a legacy comment text field', retryable=False)
        if stack == parent and name in ('body', 'subject'):
            offset = parser.CurrentByteIndex
            opening_end = raw.find(b'>', offset) + 1
            opening = raw[offset:opening_end]
            if attrs:
                raise ExportResponseError('unexpected attributes in a legacy comment text field', retryable=False)
            if not opening.rstrip().endswith(b'/>'):
                starts[name] = opening_end
        stack.append(name)

    def end(name):
        if stack == parent + [name] and name in starts:
            ranges.append((starts.pop(name), parser.CurrentByteIndex))
        stack.pop()

    def reject_doctype(*args):
        raise ExportResponseError('DTD is unsupported in a legacy comment export', retryable=False)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.ExternalEntityRefHandler = lambda *args: 0
    try:
        # Locate fields even when legacy text also contains XML-forbidden C0
        # bytes. This shadow copy has identical byte offsets; original payloads
        # are transcoded below and the strict parser handles control repair.
        shadow = re.sub(br'[\x00-\x08\x0b\x0c\x0e-\x1f]', b' ', raw)
        parser.Parse(shadow, True)
        chunks = []
        cursor = 0
        converted = 0
        for first, last in ranges:
            payload = raw[first:last]
            try:
                payload.decode('utf-8')
            except UnicodeDecodeError:
                payload = payload.decode('cp1251').encode('utf-8')
                converted += 1
            chunks.extend((raw[cursor:first], payload))
            cursor = last
        chunks.append(raw[cursor:])
        result = b''.join(chunks)
        result.decode('utf-8')  # No guessing for bytes outside known text fields.
    except (UnicodeError, expat.ExpatError):
        raise ExportResponseError(
            'comment XML cannot be decoded as UTF-8 with legacy Windows-1251 text fields',
            retryable=False,
        ) from None
    return result, converted


def parse_response(response, endpoint, options):
    raw = response.content
    if not raw.strip():
        raise ExportResponseError('empty response body')
    if re.match(br'\s*(?:<!doctype\s+html\b|<html\b)', raw, re.I):
        raise ExportResponseError('server returned an HTML page instead of an XML export')
    legacy_fields = 0
    try:
        text = _decode(raw)
    except ExportResponseError:
        if endpoint != '/export_comments.bml':
            raise
        normalized, legacy_fields = _transcode_comment_fields(raw)
        text = _decode(normalized)
    repaired = 0
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        # Only XML-forbidden literal characters are repairable here. Never use
        # a permissive parser that could silently discard entries or content.
        cleaned, repaired = re.subn(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]', '\ufffd', text)
        if repaired:
            try:
                root = ET.fromstring(cleaned)
                text = cleaned
            except ET.ParseError:
                raise ExportResponseError('malformed XML', position=error.position) from None
        else:
            raise ExportResponseError('malformed XML', position=error.position) from None
    if root.tag != 'livejournal':
        raise ExportResponseError('response is not a LiveJournal XML export')
    if (root.text and root.text.strip()) or any(child.tail and child.tail.strip() for child in root):
        raise ExportResponseError('export contains unexpected text outside its records')
    if endpoint == '/export_do.bml' and any(child.tag != 'entry' for child in root):
        raise ExportResponseError('post export contains an unexpected error or element')
    if root.find('error') is not None:
        raise ExportResponseError('LiveJournal returned an XML error', retryable=False)
    if repaired or legacy_fields:
        changes = []
        if repaired:
            changes.append(f'replaced {repaired} XML-forbidden literal characters with U+FFFD')
        if legacy_fields:
            changes.append(f'transcoded {legacy_fields} Windows-1251 comment fields to UTF-8')
        reason = '; '.join(changes)
        try:
            saved = save_response(response, endpoint, options, reason)
        except OSError:
            raise ExportResponseError('cannot preserve the original response before repairing XML',
                                      retryable=False) from None
        print(f'{endpoint}: {reason}; original response kept in {saved}.',
              file=sys.stderr, flush=True)
    return text
