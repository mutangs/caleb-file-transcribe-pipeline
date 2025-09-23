# Caleb Transcribe Pipeline (SQS-only, Paris eu-west-3)

Uploads to S3 `media-raw-caleb/` are converted to MP3 (mono 16 kHz), then transcribed by Amazon Transcribe.
Final result is a `.txt` in `media-transcripts-caleb/final/`.

## Flow
S3 (media-raw-caleb) → SQS (q-raw-caleb) → Lambda convert → S3 (media-audio-caleb)
→ SQS (q-audio-caleb) → Lambda start_transcribe → S3 (media-transcripts-caleb/raw/)
→ SQS (q-transcripts-caleb) → Lambda finalize_to_text → S3 (media-transcripts-caleb/final/)

## Language selection by filename
- Ends with `-fr`, `_fr`, `.fr` → French (`fr-FR`)
- Ends with `-eng`, `-en`, `_en`, `.eng`, `.en` → English (`en-US`)
- Else auto-detect within `en-US,en-GB,fr-FR,fr-CA`

Final name:
- If language suffix was present → `<base>.txt`
- Else → `<base>-<LanguageCode>.txt`

## Prereqs
- AWS SAM CLI, AWS CLI configured for `eu-west-3`.
- **Static ffmpeg binary** (Linux x86_64) placed at `layer/bin/ffmpeg` and `chmod +x layer/bin/ffmpeg`.


---

## Windows + Git Bash: prepare the FFmpeg Layer (done)

> You only **package** this Linux binary; Lambda (Linux) runs it.  
> Do **not** use `ffmpeg.exe` here.

From your repo root in **Git Bash**:

```bash
mkdir -p layer/bin

# Download a static Linux x86_64 build (either release or latest git)
curl -L -o ffmpeg-git-amd64-static.tar.xz \
  https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz

# (optional) verify checksum
curl -LO https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz.md5
md5sum -c ffmpeg-git-amd64-static.tar.xz.md5

# Extract and copy binaries
tar -xJf ffmpeg-git-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg  layer/bin/ffmpeg
cp ffmpeg-*-amd64-static/ffprobe layer/bin/ffprobe 2>/dev/null || true

# Mark executable so Lambda can run it
chmod +x layer/bin/ffmpeg
chmod +x layer/bin/ffprobe 2>/dev/null || true

# Ensure git keeps the exec bit
git add layer/bin/ffmpeg layer/bin/ffprobe 2>/dev/null || true
git update-index --chmod=+x layer/bin/ffmpeg
git update-index --chmod=+x layer/bin/ffprobe 2>/dev/null || true


## Deploy
```bash
sam build
sam deploy --guided \
  --region eu-west-3 \
  --stack-name caleb-transcribe-pipeline \
  --capabilities CAPABILITY_IAM
