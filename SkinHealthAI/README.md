# Skinwise

An offline-ready skin health education app. It can capture a live photo or select one from the device, then ask a local Ollama `gemma3:4b` vision model for cautious, non-diagnostic guidance. The safety guide and app shell are cached for offline use. Photo analysis needs the Ollama service and model to be available.

## Start

1. Install [Ollama](https://ollama.com/download) and run `ollama pull gemma3:4b` once while connected to the internet. The model download is about 3.4 GB; after it is installed, inference works offline.
2. Install Python 3.10 or newer (no Python packages are needed).
3. Run `python backend/server.py` from this folder and open <http://localhost:8000>.
4. Allow camera access when prompted. On phones, open the local app over HTTPS for camera access; `localhost` is trusted on the same device.

## Online / offline

The static app shell and bundled safety guide are cached by its service worker after first visit. The default model endpoint is `http://127.0.0.1:11434`; image analysis stays on the computer and works without internet once Ollama and the model are installed. To use a trusted Ollama host on your network, set `OLLAMA_HOST` before starting the server, for example in PowerShell:

```powershell
$env:OLLAMA_HOST = "http://192.168.1.20:11434"
python backend/server.py
```

The app does not upload images to a cloud service. A network Ollama host receives the image when selected as `OLLAMA_HOST`, so configure only a host you trust. Analysis is unavailable when the selected Ollama host cannot be reached.

## Safety and source bundle

The model prompt and source-grounded safety rules are in `backend/server.py` and `backend/knowledge.json`; the offline help cards are in `frontend/index.html`. This small reference bundle provides conservative guardrails, not a diagnostic database, so it cannot ensure an accurate diagnosis. Skin appearance alone cannot confirm allergy or infection. The app avoids definitive diagnoses, medication instructions, and certainty scores. The bundled urgent guidance is based on:

- American Academy of Dermatology, [Signs your rash needs medical attention](https://www.aad.org/news/signs-your-rash-needs-medical-attention)
- NHS, [Cellulitis](https://www.nhs.uk/conditions/cellulitis/)
- NHS, [Anaphylaxis](https://www.nhs.uk/conditions/anaphylaxis/)

The bundled guide is general education, not a substitute for local emergency services or an in-person clinical assessment. User-submitted photos are processed in memory and are not written to disk or included in access logs. The bundled SCIN reference photos are licensed source images stored in `backend/reference_images/scin/`.

## Offline visual references

`backend/reference_images/scin/` contains a curated set of original SCIN sample photos with dermatologist-weighted differential labels. For a label-matched analysis, the app runs one initial local pass, then (when a label is present in that answer) sends up to three matching examples with the user photo to Gemma for cautious visual comparison. The sample labels are not confirmed diagnoses and visual resemblance must not be treated as proof. User photos are not added to this library.

SCIN's data-use license and attribution details are included alongside the image set. The photos are for education and research. To rebuild the subset while online, run `python backend/tools/build_skin_reference_set.py`; it uses Python's standard library and stores the selected images for later offline use.
