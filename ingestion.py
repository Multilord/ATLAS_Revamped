"""Bounded document extraction and atomic indexing; no fabricated records."""
import base64
import binascii
import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader
from docx import Document
from ai import AIError

MAX_FILE = 5 * 1024 * 1024
MAX_TEXT = 120000


def now():
    return datetime.now(timezone.utc).isoformat()


def extract_upload(data):
    filename = data.get('filename', '')
    if not isinstance(filename, str) or len(filename) > 255:
        raise ValueError('Invalid filename.')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.txt', '.md', '.json', '.pdf', '.docx'):
        raise ValueError('Upload TXT, MD, JSON, PDF or DOCX files.')
    try:
        content = base64.b64decode(data.get('file_base64', ''), validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise ValueError('Invalid file encoding.') from None
    if not content or len(content) > MAX_FILE:
        raise ValueError('Files must be non-empty and at most 5 MB.')
    try:
        if suffix == '.pdf':
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 150:
                raise ValueError('Use an unencrypted PDF with at most 150 pages.')
            parts = []
            for index, page in enumerate(reader.pages):
                parts.append(f'[Page {index+1}]\n' + (page.extract_text() or ''))
                if sum(len(p) for p in parts) > MAX_TEXT:
                    raise ValueError('Extracted text exceeds 120,000 characters. Split the document.')
            text = '\n\n'.join(parts)
            if not any(re.search(r'\w{3}', p.split('\n', 1)[-1]) for p in parts):
                raise ValueError('No readable PDF text found. Run OCR on scanned documents before upload.')
        elif suffix == '.docx':
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 20 * 1024 * 1024:
                    raise ValueError('DOCX expands beyond the permitted size.')
            doc = Document(io.BytesIO(content))
            text = '\n'.join([p.text for p in doc.paragraphs] + [' | '.join(c.text for c in row.cells) for table in doc.tables for row in table.rows])
        else:
            text = content.decode('utf-8-sig')
            if suffix == '.json':
                json.loads(text)
    except ValueError:
        raise
    except Exception:
        raise ValueError('The file could not be read. Check its format and try again.') from None
    if not text.strip() or len(text) > MAX_TEXT:
        raise ValueError('Extracted text must contain 1–120,000 characters. Split larger documents.')
    return {'content': text, 'filename': Path(filename).name}


def chunks(text):
    output, start = [], 0
    while start < len(text):
        end = min(start + 2200, len(text))
        if end < len(text):
            boundary = text.rfind('\n', start + 1600, end)
            if boundary != -1:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            output.append({'id': f'C{len(output)+1:04}', 'text': piece, 'offset': start})
        if end == len(text):
            break
        start = end - 200
    return output


def index_source(source, store, ai):
    if source['customer'] != store.customer:
        raise ValueError('This source is outside the writable workspace.')
    pieces = chunks(source['content'])
    try:
        vectors = ai.embed([source['title'] + '\n' + part['text'] for part in pieces])
        if len(vectors) != len(pieces) or len({len(v) for v in vectors}) != 1:
            raise AIError('Incomplete embedding response. Retry indexing.')
        for part, vector in zip(pieces, vectors):
            part['embedding'] = vector
        source.update(chunks=pieces, chunk_count=len(pieces), embedding_model=ai.config.embedding_model,
            index_status='Ready', index_error='', indexed_at=now())
    except AIError as exc:
        source.update(chunks=[], chunk_count=0, index_status='Error', index_error=str(exc))
    store.save(source, 'source')
    return {k: v for k, v in source.items() if k != 'chunks'}


def create_source(data, store, ai):
    def text(key, limit, required=True):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise ValueError(f'{key} must be text, up to {limit} characters' + (' and not empty.' if required else '.'))
        return value.strip()
    if data.get('customer', store.customer) != store.customer:
        raise ValueError('Customer scope is not authorised.')
    content = text('content', MAX_TEXT)
    source_type = data.get('source_type', 'Document')
    if source_type not in ('Document', 'Historical ticket', 'Internal KB', 'SharePoint export', 'Confluence export', 'SAP reference'):
        raise ValueError('Invalid source type.')
    stamp = now()
    source = dict(id='SRC-' + uuid.uuid4().hex[:12].upper(), title=text('title', 200),
        content=content, application=text('application', 100), version=text('version', 100, False),
        error_code=text('error_code', 100, False), customer=store.customer, source_type=source_type,
        filename=text('filename', 255, False), source_reference=text('source_reference', 1000, False),
        content_hash=hashlib.sha256(content.encode()).hexdigest(), validation='Unverified',
        validation_evidence={}, solution_kind='Unknown', solution='', steps=[], conflicts_with=[],
        created_at=stamp, updated_at=stamp, index_status='Pending', index_error='', chunk_count=0,
        chunks=[], embedding_model='', revision=0)
    store.save(source, 'source')
    return index_source(source, store, ai)
