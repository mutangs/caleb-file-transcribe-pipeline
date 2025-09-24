
# Caleb File → Transcribe Pipeline (AWS, SQS-only, Paris eu-west-3)

Convert your uploaded media (MKV/MP4/MP3…) into speech text automatically:
1) **Upload** to S3 **`media-raw-caleb`**.
2) Pipeline converts to **MP3 (mono 16kHz)** and runs **Amazon Transcribe**.
3) Final **plain text** appears in **`media-transcripts-caleb/final/`**.

Designed for **Windows + VS Code**; uses **Git Bash** to prep FFmpeg; deploys via **AWS SAM**.

---

## Goal (what this project solves)

- **One-drop workflow**: put any audio/video file in one bucket, get **.txt** transcript out.
- **Durable & decoupled**: uses **SQS** (no direct S3→Lambda), so events are buffered/retried.
- **Language handling**:
  - If filename ends with `-fr`, `_fr`, `.fr` → **French (fr-FR)**
  - If ends with `-eng`, `-en`, `_en`, `.eng`, `.en` → **English (en-US)**
  - Otherwise **auto-detect** (limited to `en-US,en-GB,fr-FR,fr-CA`)
- **Simple output**: only **.txt** (no JSON kept).

---

## Architecture (how it flows)

```

You upload → S3: media-raw-caleb
→ S3 event → SQS: q-raw-caleb
→ Lambda #1 convert\_on\_upload
\- FFmpeg → MP3 mono 16kHz
\- writes S3: media-audio-caleb/<same base>.mp3
→ S3: media-audio-caleb event → SQS: q-audio-caleb
→ Lambda #2 start\_transcribe\_on\_audio
\- Starts Amazon Transcribe
\- output JSON → S3: media-transcripts-caleb/raw/<base>/<job>.json
→ S3: media-transcripts-caleb (prefix raw/) event → SQS: q-transcripts-caleb
→ Lambda #3 finalize\_to\_text
\- Reads JSON, writes final text
\- S3: media-transcripts-caleb/final/<base>.txt (or <base>-<lang>.txt)

```

**Why SQS?** If a Lambda fails or scales down, messages wait safely. With **DLQs**, you can inspect any failures.

---

## File structure (what each file does)

```

caleb-file-transcribe-pipeline/
├─ template.yaml                # SAM template: defines queues, policies, layer, Lambdas
├─ README.md                    # You are here
├─ .gitignore
├─ layer/
│  └─ bin/
│     ├─ ffmpeg                # Linux static ffmpeg (executable)
│     └─ ffprobe              # (optional) Linux static ffprobe (executable)
└─ src/
├─ convert\_on\_upload/
│  └─ app.py               # Lambda #1: SQS(raw) → FFmpeg → MP3 to audio bucket
├─ start\_transcribe\_on\_audio/
│  └─ app.py               # Lambda #2: SQS(audio) → StartTranscriptionJob
└─ finalize\_to\_text/
└─ app.py               # Lambda #3: SQS(transcripts/raw) → write .txt → final/

````

**Key code behaviors**
- `convert_on_upload/app.py`: Converts any media to **MP3 mono 16kHz 128kbps** using **FFmpeg** from the Lambda **Layer** (`/opt/bin/ffmpeg`). Keeps original base name; adds `-v2`, `-v3` if mp3 already exists.
- `start_transcribe_on_audio/app.py`: Forces EN/FR based on filename suffix; otherwise auto-detects (restricted set). Directs Transcribe output JSON into `transcripts/raw/<base>/`.
- `finalize_to_text/app.py`: Extracts first transcript string from JSON; names final `.txt` either `<base>.txt` (if suffix present) or `<base>-<LanguageCode>.txt`. Deletes JSON by default.

---

## What is AWS SAM (and how we used it)?

**AWS SAM (Serverless Application Model)** is a CloudFormation extension for serverless apps. You describe resources in **`template.yaml`** (functions, layers, queues, policies), and SAM builds/deploys them for you.

In this project, SAM:
- Creates **SQS queues** (and DLQs), **SQS QueuePolicies**, **Lambda Layer**, **3 Lambdas**, and **event source mappings** (queues → Lambdas).
- **Does not** create S3 buckets (yours already exist).
- Leaves **S3 → SQS notifications** to you (manual), because the buckets existed before this stack.

**Why some things are manual?**
- CloudFormation can’t safely “take over” pre-existing buckets in a different stack. We therefore parameterize bucket names and let you add **S3 notifications** manually.

---

## Prerequisites

- **AWS account** with permissions to create IAM roles, SQS, Lambda, Transcribe.
- **Windows** (PowerShell + Git Bash), **VS Code**.
- **AWS CLI** + **AWS SAM CLI**.
- (Optional) **Docker Desktop** if you prefer `sam build --use-container`.
- **Existing S3 buckets**:
  - `media-raw-caleb`
  - `media-audio-caleb`
  - `media-transcripts-caleb`
- **Linux static `ffmpeg`** binary (we’ll fetch below).

Set region to **Paris** once:
```powershell
aws configure set region eu-west-3
````

---

## Get FFmpeg (Git Bash)

> You are packaging a **Linux** binary (not `ffmpeg.exe`). Lambda runs on Linux.

```bash
# from repo root
mkdir -p layer/bin

# Download static Linux x86_64 build
curl -L -o ffmpeg-git-amd64-static.tar.xz \
  https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz

# (optional) verify checksum
curl -LO https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz.md5
md5sum -c ffmpeg-git-amd64-static.tar.xz.md5

# Extract and copy binaries
tar -xJf ffmpeg-git-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg  layer/bin/ffmpeg
cp ffmpeg-*-amd64-static/ffprobe layer/bin/ffprobe 2>/dev/null || true

# Mark executable for Lambda
chmod +x layer/bin/ffmpeg
chmod +x layer/bin/ffprobe 2>/dev/null || true

# Ensure Git keeps exec bit
git add layer/bin/ffmpeg layer/bin/ffprobe 2>/dev/null || true
git update-index --chmod=+x layer/bin/ffmpeg
git update-index --chmod=+x layer/bin/ffprobe 2>/dev/null || true
```

*(Alternative: `sam build --use-container` with a `layer/Makefile` that copies + `chmod +x` inside Linux.)*

---

## Deploy (SAM)

**Why deploy now?** This creates the **queues**, **roles**, **layer**, and **Lambdas**.

```powershell
# optional sanity
sam validate

# build (local Python 3.11 or use --use-container)
sam build

# deploy (you will be prompted for bucket names)
sam deploy --guided --region eu-west-3 --stack-name caleb-transcribe-pipeline --capabilities CAPABILITY_IAM
```

When prompted, enter:

* `RawBucketName` → `media-raw-caleb`
* `AudioBucketName` → `media-audio-caleb`
* `TranscriptsBucketName` → `media-transcripts-caleb`

**After deploy**, note the **Outputs**:

* `RawQueueArn/Url`, `AudioQueueArn/Url`, `TranscriptsQueueArn/Url`.

---

## Wire your existing S3 buckets → SQS (manual, one-time)

Because buckets existed before the stack, add notifications yourself.

> ⚠ If a bucket already has notifications, **GET**, **merge**, then **PUT** (the PUT replaces the full config).

**RAW → q-raw-caleb**

```powershell
aws s3api put-bucket-notification-configuration `
  --bucket media-raw-caleb `
  --notification-configuration "{
    \"QueueConfigurations\":[
      {\"QueueArn\":\"arn:aws:sqs:eu-west-3:<ACCOUNT_ID>:q-raw-caleb\",
       \"Events\":[\"s3:ObjectCreated:Put\"]}
    ]}"
```

**AUDIO → q-audio-caleb**

```powershell
aws s3api put-bucket-notification-configuration `
  --bucket media-audio-caleb `
  --notification-configuration "{
    \"QueueConfigurations\":[
      {\"QueueArn\":\"arn:aws:sqs:eu-west-3:<ACCOUNT_ID>:q-audio-caleb\",
       \"Events\":[\"s3:ObjectCreated:Put\"]}
    ]}"
```

**TRANSCRIPTS (prefix `raw/`) → q-transcripts-caleb**

```powershell
aws s3api put-bucket-notification-configuration `
  --bucket media-transcripts-caleb `
  --notification-configuration "{
    \"QueueConfigurations\":[
      {\"QueueArn\":\"arn:aws:sqs:eu-west-3:<ACCOUNT_ID>:q-transcripts-caleb\",
       \"Events\":[\"s3:ObjectCreated:Put\"],
       \"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"raw/\"}]}}}
    ]}"
```

**If buckets already have other notifications**:

```powershell
aws s3api get-bucket-notification-configuration --bucket <BUCKET> > notif.json
# edit notif.json and add the new QueueConfiguration (don't remove existing configs!)
aws s3api put-bucket-notification-configuration --bucket <BUCKET> --notification-configuration file://notif.json
```

---

## Test

Upload a small file:

```powershell
aws s3 cp "C:\path\to\team call-eng.mkv" s3://media-raw-caleb/
```

You should see:

* `s3://media-audio-caleb/team call-eng.mp3`
* `s3://media-transcripts-caleb/raw/team call-eng/<job>.json`
* `s3://media-transcripts-caleb/final/team call-eng.txt`

Upload without suffix for auto-detect:

```powershell
aws s3 cp "C:\path\to\reunion.mkv" s3://media-raw-caleb/
```

Expected: `.../final/reunion-fr-FR.txt` (or `...-en-US.txt`) depending on detection.

---

## Troubleshooting

* **“Lambda was unable to configure env vars… reserved key AWS\_REGION”**
  → Don’t set `AWS_REGION` in env vars (SAM template fixed).
* **“MemorySize must be ≤ 3008”**
  → Set converter Lambda `MemorySize: 3008`.
* **“ffmpeg: not found”**
  → Ensure `layer/bin/ffmpeg` is a **Linux** binary with **chmod +x**; rebuild & deploy.
* **Nothing triggers**
  → Verify S3 bucket **notifications** point to the right **queue ARNs**; check SQS **QueuePolicy** allows S3.
* **Messages stuck / failing**
  → Inspect **DLQs**; check Lambda **CloudWatch Logs**; fix & re-drive.

---

## Day-to-day

1. Drop any media file into `s3://media-raw-caleb/` (use `-fr` / `-en` naming when you want to force language).
2. Collect your transcript from `s3://media-transcripts-caleb/final/`.
3. Optional later: add an S3→SNS notification on `final/` for a single “done” alert.

```

---
