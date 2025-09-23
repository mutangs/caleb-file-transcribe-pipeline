import os, json, re, uuid, time
from urllib.parse import unquote_plus
import boto3

transcribe = boto3.client('transcribe')

RESULT_BUCKET = os.environ['RESULT_BUCKET']
RAW_PREFIX = os.environ.get('RAW_PREFIX', 'raw/')
LANG_OPTIONS = [x.strip() for x in os.environ.get('LANG_OPTIONS', 'en-US,en-GB,fr-FR,fr-CA').split(',') if x.strip()]

def lang_from_name(base: str):
    m = re.search(r'(?i)(?:[-_.])(fr|eng|en)$', base.strip())
    if not m:
        return None
    token = m.group(1).lower()
    return 'fr-FR' if token == 'fr' else 'en-US'

def safe_job_name(base: str) -> str:
    x = re.sub(r'[^A-Za-z0-9_-]+', '-', base).strip('-')[:100]
    return f"{x}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

def start_job(bucket: str, key: str):
    uri = f"s3://{bucket}/{key}"
    base = os.path.splitext(os.path.basename(key))[0]

    params = {
        'TranscriptionJobName': safe_job_name(base),
        'Media': {'MediaFileUri': uri},
        'MediaFormat': 'mp3',
        'OutputBucketName': RESULT_BUCKET,
        'OutputKey': f"{RAW_PREFIX}{base}/",
        'Settings': {}
    }

    code = lang_from_name(base)
    if code:
        params['LanguageCode'] = code
    else:
        params['IdentifyLanguage'] = True
        params['LanguageOptions'] = LANG_OPTIONS

    transcribe.start_transcription_job(**params)

def handler(event, _):
    for msg in event.get('Records', []):
        body = json.loads(msg['body'])
        for rec in body.get('Records', []):
            if rec.get('eventSource') != 'aws:s3':
                continue
            b = rec['s3']['bucket']['name']
            k = unquote_plus(rec['s3']['object']['key'])
            start_job(b, k)
