"""Bounded-lifetime document parser subprocess; no credentials are passed in its environment."""
import json
import sys

if __name__ == '__main__':
    from ingestion import extract_upload
    import historical
    request = json.load(sys.stdin)
    try:
        value = historical.preview(request['data']) if request['mode'] == 'history' else extract_upload(request['data'])
        print(json.dumps({'result': value}))
    except Exception:
        print(json.dumps({'error': 'Unable to parse this file safely. Check its format and size.'}))
