"""Local-first skin concern helper. Images are sent only to configured Ollama."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
import base64
import json
import os
import re
import mimetypes

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT.parent / "frontend"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
REFERENCE_DIR = ROOT / "reference_images" / "scin"
REFERENCE_ALIASES = {
    "Eczema": ["eczema", "atopic dermatitis"],
    "Allergic Contact Dermatitis": ["allergic contact dermatitis", "contact dermatitis"],
    "Urticaria": ["urticaria", "hives"],
    "Insect Bite": ["insect bite", "bug bite", "insect sting"],
    "Folliculitis": ["folliculitis"],
    "Tinea": ["tinea", "ringworm"],
    "Psoriasis": ["psoriasis"],
    "Acne": ["acne"],
    "Impetigo": ["impetigo"],
    "Cellulitis": ["cellulitis"],
    "Scabies": ["scabies"],
}


def reference_samples_for(answer):
    """Select a few local reference photos whose labels appear in a first-pass answer."""
    try:
        manifest = json.loads((REFERENCE_DIR / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    answer_lower = answer.lower()
    entries_by_condition = {}
    for entry in manifest.get("references", []):
        entries_by_condition.setdefault(entry.get("condition", ""), []).append(entry)
    matches = []
    for condition, entries in entries_by_condition.items():
        aliases = REFERENCE_ALIASES.get(condition, [condition.lower()])
        positions = [m.start() for alias in aliases for m in re.finditer(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", answer_lower)]
        if positions:
            matches.append((min(positions), condition, entries))
    selected = []
    for _, condition, entries in sorted(matches):
        for entry in entries[:2]:
            filename = Path(entry.get("file", "")).name
            if not filename or filename != entry.get("file"):
                continue
            try:
                image = (REFERENCE_DIR / filename).read_bytes()
            except OSError:
                continue
            if len(image) > MAX_IMAGE_BYTES:
                continue
            selected.append({"condition": condition, "file": filename, "image": base64.b64encode(image).decode("ascii"), "source_url": entry.get("source_url", manifest.get("dataset_url", ""))})
            if len(selected) >= 3:
                return selected
    return selected


def ask_ollama(messages, timeout=180):
    payload = json.dumps({"model": MODEL, "stream": False, "messages": messages, "options": {"temperature": 0.2}}).encode()
    request = Request(OLLAMA_HOST + "/api/chat", data=payload, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read())
    return result.get("message", {}).get("content", "").strip()

SYSTEM_PROMPT = """You are a cautious skin-health education assistant, not a clinician. You cannot diagnose from an image. Helpfully name the single most plausible skin condition or type of reaction only when visible features and reported symptoms reasonably support one (examples: contact dermatitis, eczema, hives, fungal rash, or possible bacterial infection). Put that name first under Possible explanations and say it is a possibility, not a diagnosis. Include up to two alternatives only if useful. If the image/details do not support narrowing it down, say that clearly instead of guessing. Never state a condition as certain or give a numeric confidence. Describe visible features. A photo cannot reliably distinguish allergy, infection, or other conditions. Never recommend prescription medicines, antibiotics, steroid creams, or stopping prescribed treatment. Give low-risk general care only. Ask the person to seek professional assessment when symptoms suggest infection, are worsening, affect sensitive areas, or do not improve. If the user reports difficulty breathing/swallowing, swelling of tongue/throat/face, fainting, confusion, rapidly spreading purple/black skin, severe pain, fever with feeling very unwell, advise emergency services now. Avoid diagnosing children under 2 from image; recommend clinician. Avoid assuming skin tone: redness may look different on different skin. Do not make recommendations based only on image quality. Answer in plain language with exactly these headings: What I can see; Possible explanations (not a diagnosis); What you can do; Avoid; When to get help. Keep concise. If uncertain, say so clearly."""
try:
    SOURCES = json.loads((ROOT / "knowledge.json").read_text(encoding="utf-8"))
    SOURCE_CONTEXT = "\n\nBundled safety reference (follow these conservative rules):\n" + "\n".join("- " + item for item in SOURCES["rules"])
except Exception:
    SOURCE_CONTEXT = ""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/status":
            try:
                req = Request(OLLAMA_HOST + "/api/tags")
                with urlopen(req, timeout=2) as response:
                    tags = json.loads(response.read())
                names = [m.get("name", "") for m in tags.get("models", [])]
                available = any(n == MODEL or n.startswith(MODEL + ":") for n in names)
                self._send(200, json.dumps({"ollama": True, "model": MODEL, "available": available, "host": OLLAMA_HOST, "message": "Ready for private photo analysis." if available else f"Ollama is running, but {MODEL} is not installed. Run: ollama pull {MODEL}"}))
            except Exception:
                self._send(200, json.dumps({"ollama": False, "model": MODEL, "available": False, "host": OLLAMA_HOST, "message": "Ollama is not running. Start Ollama to analyze photos; the safety guide remains available."}))
            return
        path = "/index.html" if self.path == "/" else self.path.split("?", 1)[0]
        if ".." in path:
            self._send(400, "Bad path", "text/plain")
            return
        file = FRONTEND_DIR / path.lstrip("/")
        if not file.is_file():
            self._send(404, "Not found", "text/plain")
            return
        content_type = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/manifest+json"):
            content_type += "; charset=utf-8"
        self._send(200, file.read_bytes(), content_type)

    def do_POST(self):
        if self.path != "/api/analyze":
            self._send(404, json.dumps({"error": "Not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_IMAGE_BYTES * 2:
                self._send(413, json.dumps({"error": "Image is too large. Choose a photo under 8 MB."}))
                return
            data = json.loads(self.rfile.read(length))
            image = data.get("image", "")
            if "," in image:
                image = image.split(",", 1)[1]
            raw = base64.b64decode(image, validate=True)
            if len(raw) > MAX_IMAGE_BYTES:
                self._send(413, json.dumps({"error": "Image is too large. Choose a photo under 8 MB."}))
                return
            mime = data.get("mime", "image/jpeg")
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                self._send(400, json.dumps({"error": "Use a JPEG, PNG, or WebP image."}))
                return
            context = str(data.get("context", ""))[:1800]
            prompt = "Review this skin photo as a cautious health education assistant. "
            if context:
                prompt += "The person adds: " + context + "\n"
            prompt += "Follow the required headings. Do not diagnose."
            original_image = base64.b64encode(raw).decode("ascii")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT + SOURCE_CONTEXT},
                {"role": "user", "content": prompt, "images": [original_image]},
            ]
            answer = ask_ollama(messages)
            if not answer:
                raise ValueError("The model returned an empty answer.")
            references = reference_samples_for(answer)
            if references:
                compare_prompt = SYSTEM_PROMPT + SOURCE_CONTEXT + "\n\nFor this second pass, the first image is the person's photo. Later user messages contain source reference images and their dataset labels. These examples are for weak visual comparison only; they are not confirmed diagnoses and may not represent the same skin tone or presentation. Do not call a condition a match just because one looks similar. Explicitly keep uncertainty, consider alternatives, and do not let the reference labels override the symptoms or visible evidence."
                comparison_messages = [
                    {"role": "system", "content": compare_prompt},
                    {"role": "user", "content": prompt, "images": [original_image]},
                ]
                for index, reference in enumerate(references, start=1):
                    comparison_messages.append({"role": "user", "content": f"Reference example {index}: SCIN dermatologist-weighted differential label: {reference['condition']}. This is a comparison example, not a diagnosis.", "images": [reference["image"]]})
                comparison_messages.append({"role": "user", "content": "Compare the primary photo with the labeled examples cautiously. You may revise the first impression if the images do not look similar. Follow the required headings and include safe next steps."})
                try:
                    compared = ask_ollama(comparison_messages, timeout=240)
                    if compared:
                        answer = compared
                except Exception:
                    # A reference comparison is optional; preserve the first-pass guidance if it fails.
                    pass
            public_refs = [{"condition": r["condition"], "source_url": r["source_url"]} for r in references]
            self._send(200, json.dumps({"answer": answer, "model": MODEL, "references": public_refs}))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            self._send(502, json.dumps({"error": "Ollama returned an error. Is the model installed? " + detail}))
        except URLError:
            self._send(503, json.dumps({"error": "Ollama is not reachable. Start Ollama and install gemma3:4b to analyze photos. The safety guide still works offline."}))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, json.dumps({"error": str(exc) or "Invalid request."}))
        except Exception as exc:
            self._send(500, json.dumps({"error": "Analysis failed: " + str(exc)[:240]}))

    def log_message(self, fmt, *args):
        # Do not log submitted content, photos, or context.
        if self.path not in ("/api/analyze",):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Skin Health Guide: http://localhost:{port}  |  Ollama: {OLLAMA_HOST} ({MODEL})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
