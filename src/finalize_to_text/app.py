import os, json, re
from urllib.parse import unquote_plus
import boto3

s3 = boto3.client('s3')

RESULT_BUCKET = os.environ.get('RESULT_BUCKET', 'media-transcripts-caleb')
RAW_PREFIX = os.environ.get('RAW_PREFIX', 'raw/')
FINAL_PREFIX = os.environ.get('FINAL_PREFIX', 'final/')
DELETE_JSON = os.environ.get('DELETE_JSON', 'true').lower() == 'true'

def had_lang_suffix(base: str) -> bool:
    return re.search(r'(?i)(?:[-_.])(fr|eng|en)$', base.strip()) is not None

def extract_text(doc: dict) -> str:
    return doc.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')

def finalize_object(bucket: str, key: str):
    # Expect: raw/<base>/<job>.json
    if not key.startswith(RAW_PREFIX) or not key.endswith('.json'):
        return
    parts = key.split('/')
    if len(parts) < 3:
        return

    base = parts[1]
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = json.loads(obj['Body'].read())
    text = extract_text(data)

    # Prefer language_code from the results if present
    lang = data.get('results', {}).get('language_code', 'und')

    if had_lang_suffix(base):
        final_txt_key = f"{FINAL_PREFIX}{base}.txt"
    else:
        final_txt_key = f"{FINAL_PREFIX}{base}-{lang}.txt"

    s3.put_object(Bucket=RESULT_BUCKET, Key=final_txt_key, Body=text.encode('utf-8'),
                  ContentType='text/plain; charset=utf-8')

    if DELETE_JSON:
        s3.delete_object(Bucket=bucket, Key=key)

def handler(event, _):
    for msg in event.get('Records', []):
        body = json.loads(msg['body'])
        for rec in body.get('Records', []):
            if rec.get('eventSource') != 'aws:s3':
                continue
            b = rec['s3']['bucket']['name']
            k = unquote_plus(rec['s3']['object']['key'])
            finalize_object(b, k)
