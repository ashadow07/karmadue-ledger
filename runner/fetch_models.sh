#!/usr/bin/env bash
# Download the transcription stack's models into $1 and check every SHA-256 against the stack's components.lock / models.sha256.
set -euo pipefail
M="$1"; mkdir -p "$M"; cd "$M"
get() { [ -f "$2" ] && echo "$3  $2" | sha256sum -c --status && { echo "cached $2"; return; }; curl -fsSL --retry 3 -o "$2" "$1"; echo "$3  $2" | sha256sum -c; }
get https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en-q5_1.bin ggml-small.en-q5_1.bin bfdff4894dcb76bbf647d56263ea2a96645423f1669176f4844a1bf8e478ad30
get https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf qwen.gguf 6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
get https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx 3dspeaker.onnx 1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b
if ! echo "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079  sherpa-onnx-pyannote-segmentation-3-0/model.onnx" | sha256sum -c --status 2>/dev/null; then
  curl -fsSL --retry 3 https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2 | tar xj
  echo "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079  sherpa-onnx-pyannote-segmentation-3-0/model.onnx" | sha256sum -c
fi
P=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US
get $P/amy/medium/en_US-amy-medium.onnx en_US-amy-medium.onnx b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18
get $P/lessac/medium/en_US-lessac-medium.onnx en_US-lessac-medium.onnx 5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f
get $P/ryan/medium/en_US-ryan-medium.onnx en_US-ryan-medium.onnx abf4c274862564ed647ba0d2c47f8ee7c9b717d27bdad9219100eb310db4047a
for v in amy/medium/en_US-amy-medium lessac/medium/en_US-lessac-medium ryan/medium/en_US-ryan-medium; do f=$(basename $v).onnx.json; [ -f "$f" ] || curl -fsSL --retry 3 -o "$f" "$P/$v.onnx.json"; done
ls -la
