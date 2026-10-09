# Production acceptance

## ASR

Install a pinned whisper.cpp release and a model outside the application directory. Set `VIDEODNA_WHISPER` and `VIDEODNA_WHISPER_MODEL`, enable the `asr` component, then compare `audio.segments` against a labelled transcript. Record WER, segment timestamp error (p95), language accuracy, and failure rate. A result without these measurements is not an accuracy claim.

## Transition evaluation

Create a manifest with one labelled boundary per line:

```json
{"expected":{"12.40":"cut","23.10":"dissolve"},"predicted":{"12.38":"cut","23.14":"dissolve"}}
```

Use `EvaluateTransitions` with a 150 ms tolerance and report precision, recall, F1 per class and macro F1. Keep at least 30 clips per transition type, with separate train/tuning and acceptance sets.

## NLE import acceptance

For each release, export EDL, FCP7 XML, SRT and Cutmark JSON from the same DNA result. Import into DaVinci Resolve and Adobe Premiere Pro on Windows and macOS. Verify source relink, frame rate, timecode, clip order, duration, audio channel mapping, Unicode filenames, and a 10-minute project. Jianying import must be checked with the exact desktop version used by customers; its private formats are not treated as stable interchange formats.

## Credentials

Electron settings use the operating system-backed `safeStorage` store. Never put API keys in logs, URLs, exported DNA, or renderer persistent storage. Model registry metadata now excludes `api_key` from `config.json`; keys are process-local and must be re-injected at desktop startup/model save through `safeStorage`. A headless deployment must inject them through a protected secret manager at process start, never through config files or command-line arguments.

## Plugins and releases

Plugin ZIPs must contain an Ed25519 signed manifest and SHA-256 file map. Release builds require Windows Authenticode or macOS Developer ID signing. macOS release builds additionally require notarization and stapling. Unsigned local builds are for development only.
