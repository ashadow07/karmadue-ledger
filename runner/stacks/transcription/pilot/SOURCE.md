# Sample source (WO-1, SHRLOK, 2026-10-09 8:42 PM ET)

| field | value |
|---|---|
| File | `sample/librivox_on_first_looking_into_chapmans_homer_keats_leonard_wilson.ogg` |
| Title | "On First Looking into Chapman's Homer" (John Keats, 1816 sonnet) |
| Reader | Leonard Wilson (1930-2024), solo reading |
| LibriVox project | John Keats: Selected Poems, section 14 (catalog playtime 84 s) |
| LibriVox catalog page | https://librivox.org/john-keats-selected-poems-by-john-keats/ |
| archive.org item | https://archive.org/details/john_keats_selected_poems_lw_librivox |
| Original LibriVox MP3 | https://www.archive.org/download/john_keats_selected_poems_lw_librivox/poems_14_keats_64kb.mp3 |
| Mirror actually downloaded | https://commons.wikimedia.org/wiki/File:On-First-Looking-Into-Chapman%E2%80%99s-Homer-LibriVox-Vorbis.ogg |
| Direct file URL used | https://upload.wikimedia.org/wikipedia/commons/b/be/On-First-Looking-Into-Chapman%E2%80%99s-Homer-LibriVox-Vorbis.ogg |
| Format (ffprobe) | Ogg Vorbis, mono, 44,100 Hz, ~72 kb/s, 761,673 bytes |
| Duration (ffprobe) | 84.28 s (1 min 24 s) |
| sha256 | `0b930a4c9a63ff009debb0ae818640cbb7d5d767eee5da8fc865bd4eae1d00e4` |
| License | Public domain. LibriVox recordings are dedicated to the public domain; the Commons page tags this file CC0 and names its source as the LibriVox MP3 above. The poem (1816) is public domain. |

## Why the Commons mirror
archive.org returned HTTP 503 for every download and metadata request from this box between 8:34 and 8:41 PM ET (several LibriVox items, with retries). The Wikimedia Commons file is a Vorbis re-encode of the same LibriVox recording (Commons cites the archive.org MP3 as its source, and the 84 s length matches LibriVox's catalog playtime for section 14). If byte-for-byte LibriVox provenance matters, re-download the MP3 above when archive.org recovers and record its own sha256. The two files will NOT share a checksum, since they're different encodings.

## Reference transcript for WER
- `sample/reference_chapmans_homer_gutenberg8209.txt` (sha256 `bf0e25e9025c6e121653a8b4a2d5f50d26d38d8b5cb278022836fcce089f16a3`): the 14 lines of the poem, copied from Project Gutenberg eBook #8209, *Poems 1817* by John Keats, https://www.gutenberg.org/ebooks/8209 (plain text: https://www.gutenberg.org/cache/epub/8209/pg8209.txt, lines 1584-1597, leading indentation stripped).
- Caveat for WER: the recording is expected to include LibriVox's spoken preamble/disclaimer and probably a title/author line and closing sign-off that aren't in the reference. I haven't listened to it to confirm. Either trim those from the hypothesis or add them to the reference before scoring. Normalize case and punctuation; watch the archaic spellings (traveled, deep-brow'd, star'd, Look'd) and proper nouns (Cortez, Darien, demesne).

## Convert for engines that need 16 kHz mono WAV
```
ffmpeg -i sample/librivox_on_first_looking_into_chapmans_homer_keats_leonard_wilson.ogg -ar 16000 -ac 1 -c:a pcm_s16le sample/chapmans_homer_16k.wav
```
