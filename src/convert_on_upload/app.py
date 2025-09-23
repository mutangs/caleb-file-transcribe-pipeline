import os, json, uuid, subprocess, shlex
from urllib.parse import unquote_plus
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
OUTPUT_BUCKET = os.environ['OUTPUT_BUCKET']
FFMPEG = os.environ.get('FFMPEG_PATH', '/opt/bin/ffmpeg')

def next_available_key(bucket: str, desired_key: str) -> str:
    base, ext = os.path.splitext(desired_key)
    n = 1
    while True:
        candidate = desired_key if n == 1 else f"{base}-v{n}{ext}"
        try:
            s3.head_object(Bucket=bucket, Key=candidate)
            n += 1
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code in ('404', 'NoSuchKey', 'NotFound'):
                return candidate
            raise

def run(cmd: str):
    p = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}):\n{p.stdout}")
    return p.stdout

def handle_s3_record(rec):
    src_bucket = rec['s3']['bucket']['name']
    key = unquote_plus(rec['s3']['object']['key'])
    base = os.path.splitext(os.path.basename(key))[0]
    out_key = next_available_key(OUTPUT_BUCKET, f"{base}.mp3")

    tmp_in = f"/tmp/in-{uuid.uuid4().hex}"
    tmp_out = f"/tmp/out-{uuid.uuid4().hex}.mp3"

    s3.download_file(src_bucket, key, tmp_in)

    # Convert to audio-only MP3 mono 16kHz 128kbps
    cmd = f'{FFMPEG} -y -i "{tmp_in}" -vn -ac 1 -ar 16000 -b:a 128k "{tmp_out}"'
    run(cmd)

    s3.upload_file(tmp_out, OUTPUT_BUCKET, out_key, ExtraArgs={'ContentType': 'audio/mpeg'})

    try:
        os.remove(tmp_in); os.remove(tmp_out)
    except OSError:
        pass

def handler(event, _context):
    # SQS delivers the original S3 Event in message body
    for msg in event.get('Records', []):
        body = json.loads(msg['body'])
        for rec in body.get('Records', []):
            if rec.get('eventSource') == 'aws:s3':
                handle_s3_record(rec)
