"""Download a small, attributed SCIN visual reference set for offline comparison.

Uses only Python's standard library. Run from the project root while online.
Reference photos are kept unmodified; case demographics and IDs are not retained.
"""
from __future__ import annotations

import ast
import csv
import io
import json
import re
import urllib.request
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUT = BACKEND_ROOT / "reference_images" / "scin"
BASE = "https://storage.googleapis.com/dx-scin-public-data/"
CASES_URL = BASE + "dataset/scin_cases.csv"
LABELS_URL = BASE + "dataset/scin_labels.csv"
LICENSE_URL = "https://raw.githubusercontent.com/google-research-datasets/scin/main/LICENSE"
MAX_IMAGE_BYTES = 12 * 1024 * 1024

TARGETS = {
    "Eczema": ["eczema", "atopic dermatitis"],
    "Allergic Contact Dermatitis": ["allergic contact dermatitis", "allergic dermatitis"],
    "Urticaria": ["urticaria", "hives"],
    "Insect Bite": ["insect bite", "bug bite"],
    "Folliculitis": ["folliculitis"],
    "Tinea": ["tinea", "ringworm", "fungal rash"],
    "Psoriasis": ["psoriasis"],
    "Acne": ["acne"],
    "Impetigo": ["impetigo"],
    "Cellulitis": ["cellulitis"],
    "Scabies": ["scabies"],
}


def fetch(url: str, limit: int | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Skinwise-Local-Reference-Builder/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        length = response.headers.get("Content-Length")
        if limit is not None and length and int(length) > limit:
            raise ValueError(f"Remote image exceeds size limit: {url}")
        data = response.read((limit + 1) if limit is not None else -1)
    if limit is not None and len(data) > limit:
        raise ValueError(f"Remote image exceeds size limit: {url}")
    return data


def rows(url: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig"))))


def tone_number(row: dict[str, str]) -> int | None:
    for key in ("monk_skin_tone_label_india", "monk_skin_tone_label_us"):
        try:
            value = int(row.get(key, ""))
            if 1 <= value <= 10:
                return value
        except (TypeError, ValueError):
            pass
    match = re.fullmatch(r"FST([1-6])", row.get("fitzpatrick_skin_type", ""))
    return int(match.group(1)) if match else None


def image_path(row: dict[str, str]) -> str:
    for key in ("image_1_path", "image_2_path", "image_3_path"):
        path = row.get(key, "").strip()
        if path.startswith("dataset/images/") and not path.startswith("/") and ".." not in path:
            return path
    return ""


def main() -> None:
    print("Reading SCIN labels and case index…")
    case_rows = {r["case_id"]: r for r in rows(CASES_URL)}
    label_rows = rows(LABELS_URL)
    candidates: dict[str, list[tuple[int, float, dict[str, str], str]]] = {name: [] for name in TARGETS}
    for label_row in label_rows:
        case = case_rows.get(label_row.get("case_id", ""))
        if not case or case.get("body_parts_genitalia_or_groin") == "YES":
            continue
        path = image_path(case)
        if not path:
            continue
        gradable = [v for k, v in label_row.items() if k.startswith("dermatologist_gradable_for_skin_condition_") and v]
        if gradable and not any("YES" in value for value in gradable):
            continue
        try:
            weighted = ast.literal_eval(label_row.get("weighted_skin_condition_label") or "{}")
        except (ValueError, SyntaxError):
            continue
        if not isinstance(weighted, dict):
            continue
        tone = tone_number(label_row) or tone_number(case) or 0
        top_score = max((float(v or 0) for v in weighted.values()), default=0)
        for target in TARGETS:
            score = float(weighted.get(target, 0) or 0)
            if score >= 0.25 and score >= top_score - 0.001:
                candidates[target].append((tone, score, case, path))

    OUT.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "manifest.json", "SCIN_LICENSE.txt"):
        for old in OUT.glob(pattern):
            if old.is_file():
                old.unlink()
    manifest = {
        "dataset": "SCIN (Skin Condition Image Network)",
        "attribution": "Images sourced from the SCIN Dataset, Google Research, with dermatologist-provided differential labels.",
        "dataset_url": "https://github.com/google-research-datasets/scin",
        "license_url": "https://github.com/google-research-datasets/scin/blob/main/LICENSE",
        "license_file": "SCIN_LICENSE.txt",
        "use": "Educational visual comparison only. Labels are differential labels, not confirmed diagnoses.",
        "references": [],
    }

    used_cases: set[str] = set()
    for target, items in candidates.items():
        # Pick two different examples, preferring a wider range of available tones.
        items = [item for item in items if item[2]["case_id"] not in used_cases]
        items.sort(key=lambda x: (x[0], -x[1]))
        chosen: list[tuple[int, float, dict[str, str], str]] = []
        if items:
            chosen.append(items[0])
            for item in reversed(items):
                if item[2]["case_id"] != chosen[0][2]["case_id"]:
                    chosen.append(item)
                    break
        # Fill a missing second tone with the strongest distinct label match.
        if len(chosen) < 2:
            for item in sorted(items, key=lambda x: -x[1]):
                if all(item[2]["case_id"] != old[2]["case_id"] for old in chosen):
                    chosen.append(item)
                    break
        used_cases.update(item[2]["case_id"] for item in chosen)
        for index, (tone, score, _case, path) in enumerate(chosen, start=1):
            ext = Path(path).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            filename = f"{re.sub(r'[^a-z0-9]+', '-', target.lower()).strip('-')}-{index}{ext}"
            try:
                image_bytes = fetch(BASE + path, MAX_IMAGE_BYTES)
                (OUT / filename).write_bytes(image_bytes)
            except Exception as exc:
                print(f"Skipping {target} reference {index}: {exc}", flush=True)
                continue
            manifest["references"].append({
                "condition": target,
                "file": filename,
                "weighted_label_score": round(score, 3),
                "skin_tone_metadata_available": bool(tone),
                "source_url": manifest["dataset_url"],
            })
            print(f"Added {target} reference {index}", flush=True)

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    try:
        (OUT / "SCIN_LICENSE.txt").write_bytes(fetch(LICENSE_URL))
    except Exception as exc:
        print(f"Could not fetch SCIN license copy: {exc}", flush=True)
    print(f"Saved {len(manifest['references'])} reference images to {OUT}")


if __name__ == "__main__":
    main()
