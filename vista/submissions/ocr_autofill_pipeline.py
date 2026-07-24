"""
Rule-based OCR Auto-Fill Pipeline (No ML) -- v2
=================================================
Calibrated against three real USTP-OSA forms:
    FM-USTP-OSA-04B  (Accomplishment Report)
    FM-USTP-OSA-11   (Local Off-Campus Activities Certificate of Compliance)
    FM-USTP-OSA-010  (Student Activity Request Form / SARF)

Architecture:
    Upload -> Preprocess -> Template Identification -> Zonal Extraction
           -> Fuzzy Cleanup -> STAFF REVIEW (draft only) -> Confirmed Submit

Findings from the real samples that shaped this version
---------------------------------------------------------
1. The "Document Code No." box sits at the TOP RIGHT of the page on all
   three forms, not the top left. Zones below are calibrated from actual
   pixel coordinates measured on each form at 300 DPI.

2. The printed code on the SARF form is "FM-USTP-OSA-010" (leading zero),
   while the uploaded filename says "FM-USTP-OSA-10". Exact-string
   matching anywhere in the intake pipeline (e.g. against a filename or a
   strict equality check) would silently disagree with what's on the
   page. Fuzzy matching for template ID absorbs this; anything downstream
   that assumes an exact code string should not.

3. Two of the three forms print a "Name of Organization:" field
   (Accomplishment Report, SARF). The Certificate of Compliance has no
   organization field anywhere on the page -- it's a signature-only
   attestation -- so no organization zone is registered for it at all,
   rather than a zone that's just expected to come back empty. A missing
   zone reads as "not applicable"; an empty zone would read as
   "extraction failed," which is a different (and misleading) signal.

4. Page orientation differs: 04B and the SARF are landscape (4200x2550 @
   300 DPI); the Certificate of Compliance is portrait (2481x3509 @ 300
   DPI). Zones are meaningless without knowing which orientation they
   were calibrated against, so page_size is part of the template
   definition and is checked before zones are applied.

Critical guardrail (per requirements)
--------------------------------------
This pipeline NEVER writes extracted data directly to the system of
record. Every run produces a draft suggestion with per-field confidence.
A human staff member must explicitly confirm (or correct) the draft
before anything is persisted. See `confirm_and_submit()` -- it is the
ONLY function in this module allowed to touch persistent storage, and it
refuses to run without an explicit reviewer identity.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from rapidfuzz import fuzz, process
from PIL import Image
import pytesseract
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# 1. Template Registry -- calibrated from the real forms
# ---------------------------------------------------------------------------

@dataclass
class FieldZone:
    bbox: tuple                          # (x0, y0, x1, y1) px @ template DPI
    allowed_values: Optional[list] = None  # None => free text


@dataclass
class CheckboxOption:
    """
    One option in a checkbox/mark group (e.g. "In-Campus" in the
    In-Campus/Off-Campus choice on the SARF). Unlike FieldZone, this isn't
    read via OCR text -- it's detected by ink density, since the "value"
    here is a check, slash, or X drawn over a blank line, not printed text.
    """
    bbox: tuple            # (x0, y0, x1, y1) over the blank/line where a mark goes
    blank_baseline: float  # ink density measured on the UNMARKED template at this bbox
                            # (captures the printed rule line/table border ink that's
                            # present even with nothing filled in -- see calibration
                            # notes in detect_checkbox_group())


@dataclass
class CheckboxGroup:
    options: dict                       # option_name -> CheckboxOption
    mark_delta_threshold: float = 0.03  # density must rise this much above an
                                         # option's own baseline to count as marked


@dataclass
class TemplateDef:
    template_id: str
    display_name: str
    anchor_phrases: list
    page_size: tuple                     # (width, height) px @ TEMPLATE_DPI
    zones: dict = field(default_factory=dict)
    checkbox_groups: dict = field(default_factory=dict)  # group_name -> CheckboxGroup


TEMPLATE_DPI = 300

TEMPLATE_REGISTRY = [
    TemplateDef(
        template_id="FM-USTP-OSA-04B",
        display_name="Accomplishment Report",
        anchor_phrases=["FM-USTP-OSA-04B", "ACCOMPLISHMENT REPORT"],
        page_size=(4200, 2550),  # landscape
        zones={
            "document_code": FieldZone(bbox=(3260, 140, 3980, 300)),
            "organization_name": FieldZone(bbox=(560, 720, 1520, 800)),
        },
    ),
    TemplateDef(
        template_id="FM-USTP-OSA-010",
        display_name="Student Activity Request Form (SARF)",
        # Anchor on multiple forms of the code (with/without leading zero)
        # since the printed code and the filename disagree.
        anchor_phrases=[
            "FM-USTP-OSA-010", "FM-USTP-OSA-10",
            "STUDENT ACTIVITY REQUEST FORM",
        ],
        page_size=(4200, 2550),  # landscape
        zones={
            "document_code": FieldZone(bbox=(3260, 140, 3980, 300)),
            "organization_name": FieldZone(bbox=(540, 775, 1200, 850)),
        },
        checkbox_groups={
            # The "Venue __ In-Campus __ Off-Campus" line. Staff mark one
            # blank with a check or slash rather than typing anything, so
            # this is read via ink density, not OCR text (see
            # detect_checkbox_group()). Baselines below were measured
            # directly on the blank/unfilled sample form.
            "venue_category": CheckboxGroup(
                options={
                    "in_campus": CheckboxOption(
                        bbox=(2300, 1260, 2390, 1300), blank_baseline=0.0706,
                    ),
                    "off_campus": CheckboxOption(
                        bbox=(2300, 1310, 2390, 1350), blank_baseline=0.1183,
                    ),
                },
                mark_delta_threshold=0.03,
            ),
        },
    ),
    TemplateDef(
        template_id="FM-USTP-OSA-11",
        display_name="Local Off-Campus Activities Certificate of Compliance",
        anchor_phrases=[
            "FM-USTP-OSA-11", "CERTIFICATE OF COMPLIANCE",
            "LOCAL OFF-CAMPUS ACTIVITIES",
        ],
        page_size=(2481, 3509),  # portrait
        zones={
            "document_code": FieldZone(bbox=(1330, 180, 2220, 300)),
            # NOTE: deliberately no "organization_name" zone -- this form
            # never prints an organization name anywhere on the page.
        },
    ),
]

TEMPLATE_MATCH_FLOOR = 75
FIELD_MATCH_FLOOR = 70


# ---------------------------------------------------------------------------
# 2. Preprocessing
# ---------------------------------------------------------------------------

def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left: smallest x+y
    rect[2] = pts[np.argmax(s)]   # bottom-right: largest x+y
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right: smallest y-x
    rect[3] = pts[np.argmax(diff)]  # bottom-left: largest y-x
    return rect


def find_document_quad(image_bgr: np.ndarray, min_area_fraction: float = 0.25):
    """
    Looks for the largest 4-sided contour in the image -- the document's
    outer edge against its background. Returns ordered corner points, or
    None if nothing confidently rectangular is found (e.g. the image is
    already tightly cropped to the page with no visible border, in which
    case there's nothing to correct and we should just resize as-is).
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = image_bgr.shape[0] * image_bgr.shape[1]
    best_quad, best_area = None, 0

    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(c)
        if area < image_area * min_area_fraction or area <= best_area:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            best_quad, best_area = approx.reshape(4, 2), area

    return _order_corners(best_quad.astype("float32")) if best_quad is not None else None


def perspective_correct(image_bgr: np.ndarray, target_size: tuple) -> np.ndarray:
    """
    Detects the document's quadrilateral against its background and warps
    it directly onto a rectangle of `target_size`. Because this is a true
    perspective warp (not a stretch of already-rectangular content), it
    corrects rotation, keystoning, and camera-angle skew in the same step
    that resizes to the calibrated template dimensions -- so the fixed
    pixel zones in TEMPLATE_REGISTRY line up correctly regardless of how
    the photo was framed.

    Falls back to a plain resize if no confident document quad is found
    (typical when the input is already tightly cropped by a client-side
    scanner, e.g. react-native-document-scanner-plugin, and has no visible
    border left to detect).
    """
    quad = find_document_quad(image_bgr)
    target_w, target_h = target_size

    if quad is None:
        resized = cv2.resize(image_bgr, target_size)
        return resized

    dst = np.array([
        [0, 0], [target_w - 1, 0],
        [target_w - 1, target_h - 1], [0, target_h - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(image_bgr, M, (target_w, target_h))


def preprocess(image: Image.Image, target_size: tuple) -> Image.Image:
    """
    Corrects rotation/perspective from an unguided photo and normalizes to
    the exact page size a template's zones were calibrated against.

    IMPORTANT: contour-based document detection is only attempted when the
    incoming image's aspect ratio meaningfully differs from the template's
    calibrated aspect ratio. A flatbed scan, a PDF render, or anything
    already cropped by a client-side scanner will already be close to the
    expected page proportions -- running edge/contour detection on that
    input is not just unnecessary, it's actively harmful: on a page with
    a large internal table or boxed section (e.g. the Accomplishment
    Report's data grid), the contour search can mistake that internal
    rectangle for the document's outer edge and apply a bogus perspective
    warp, shifting every calibrated zone off target. This was caught
    directly in testing -- see ocr-integration-documentation.md section
    8.4a for the specific case and reproduction.

    Only images with a meaningfully different aspect ratio (the realistic
    signature of an unguided photo with visible background) go through
    quad detection at all.
    """
    image_bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    target_w, target_h = target_size

    img_h, img_w = image_bgr.shape[:2]
    target_aspect = target_w / target_h
    img_aspect = img_w / img_h
    aspect_deviation = abs(img_aspect - target_aspect) / target_aspect

    ASPECT_DEVIATION_FLOOR = 0.08  # 8% -- tune against real upload traffic

    if aspect_deviation < ASPECT_DEVIATION_FLOOR:
        # Already flat and correctly proportioned -- resize only, no
        # contour search, so internal page content can't be misdetected.
        if (img_w, img_h) != (target_w, target_h):
            image_bgr = cv2.resize(image_bgr, target_size)
        return Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

    # Aspect ratio suggests an unguided photo (background, wrong
    # orientation, etc.) -- rotate if sideways, then attempt perspective
    # correction.
    target_is_landscape = target_w >= target_h
    image_is_landscape = img_w >= img_h
    if target_is_landscape != image_is_landscape:
        image_bgr = cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)

    corrected = perspective_correct(image_bgr, target_size)
    return Image.fromarray(cv2.cvtColor(corrected, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------------------
# 3. Template Identification
# ---------------------------------------------------------------------------

def identify_template(full_text: str):
    best_template, best_score = None, 0
    for tmpl in TEMPLATE_REGISTRY:
        score = max(
            fuzz.partial_ratio(phrase.upper(), full_text.upper())
            for phrase in tmpl.anchor_phrases
        )
        if score > best_score:
            best_template, best_score = tmpl, score
    if best_score < TEMPLATE_MATCH_FLOOR:
        return None, best_score
    return best_template, best_score


# ---------------------------------------------------------------------------
# 4. Zonal Extraction (real pytesseract calls -- no stubs)
# ---------------------------------------------------------------------------

def ocr_zone(image: Image.Image, bbox: tuple) -> str:
    crop = image.crop(bbox)
    return pytesseract.image_to_string(crop).strip()


def extract_fields(image: Image.Image, template: TemplateDef) -> dict:
    return {
        field_name: ocr_zone(image, zone.bbox)
        for field_name, zone in template.zones.items()
    }


# ---------------------------------------------------------------------------
# 4b. Checkbox / Mark Detection (optical mark recognition, not OCR)
# ---------------------------------------------------------------------------
# For fields where staff mark a blank with a check or slash rather than
# writing text (e.g. Venue: In-Campus / Off-Campus on the SARF), OCR isn't
# the right tool -- there's no text to read. Instead this measures how much
# dark ink sits in each option's zone and compares it to that option's own
# calibrated blank-form baseline.
#
# The comparison is against each option's OWN baseline, not a single global
# threshold, because the printed rule line (and, for options sitting inside
# a table, nearby border ink) already contributes some density even on a
# completely blank form -- and that baseline differs from option to option.
# A global threshold would either miss real marks on a high-baseline option
# or false-positive on a low-baseline one.

def _ink_density(image: Image.Image, bbox: tuple, dark_threshold: int = 180) -> float:
    crop = image.crop(bbox)
    gray = cv2.cvtColor(np.array(crop.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return float(np.sum(gray < dark_threshold)) / gray.size


def detect_checkbox_group(image: Image.Image, group: CheckboxGroup) -> dict:
    deltas = {
        name: round(_ink_density(image, opt.bbox) - opt.blank_baseline, 4)
        for name, opt in group.options.items()
    }
    marked = [name for name, delta in deltas.items() if delta >= group.mark_delta_threshold]

    if len(marked) == 1:
        return {"value": marked[0], "confidence": None, "needs_review": False,
                "deltas": deltas}
    if len(marked) == 0:
        return {"value": None, "confidence": None, "needs_review": True,
                "reason": "no_option_marked", "deltas": deltas}

    # More than one option crossed the threshold. In practice this usually
    # means a single mark's ink bled across the boundary between two
    # adjacent zones (e.g. an oversized checkmark glyph tall enough to span
    # both lines, or a mark drawn slightly off-position) -- not that the
    # form was genuinely double-marked. Rather than discard the signal
    # entirely, check whether one option has meaningfully more ink than the
    # others; if so, suggest it, but keep needs_review=True regardless,
    # since this IS a genuinely ambiguous read that deserves a human glance
    # rather than a silent guess.
    ranked = sorted(marked, key=lambda name: deltas[name], reverse=True)
    top, runner_up = ranked[0], ranked[1]
    dominant = deltas[top] >= deltas[runner_up] * 1.5

    if dominant:
        return {"value": top, "confidence": None, "needs_review": True,
                "reason": "multiple_options_marked_dominant_suggested", "deltas": deltas}
    return {"value": None, "confidence": None, "needs_review": True,
            "reason": "multiple_options_marked", "deltas": deltas}


def extract_checkbox_groups(image: Image.Image, template: TemplateDef) -> dict:
    return {
        group_name: detect_checkbox_group(image, group)
        for group_name, group in template.checkbox_groups.items()
    }


# ---------------------------------------------------------------------------
# 5. Fuzzy Cleanup
# ---------------------------------------------------------------------------

# Common OCR substitution errors seen on scanned/photographed forms.
# Applied only within the numeric suffix of a document code, where the
# expected character class (digit) is known, so a letter substitution can
# be corrected with confidence instead of guessed.
_DIGIT_LOOKALIKES = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5"}

_CODE_PATTERN = re.compile(r"FM[-\s]?USTP[-\s]?OSA[-\s]?[O0]?\d+[A-Za-z]?", re.IGNORECASE)


def normalize_document_code(raw_value: str) -> dict:
    """
    Pulls a "FM-USTP-OSA-<code>" pattern out of noisy zone text (which may
    include the "Document Code No." label, stray icon glyphs, etc.) and
    corrects common digit/letter OCR confusions in the numeric part.
    """
    match = _CODE_PATTERN.search(raw_value)
    if not match:
        return {"value": raw_value.strip(), "confidence": None,
                "needs_review": True, "reason": "no_code_pattern_found"}

    found = match.group(0).upper().replace(" ", "")
    prefix, _, suffix = found.rpartition("-")
    # Correct lookalike substitutions only in the trailing numeric/letter suffix.
    corrected_suffix = "".join(_DIGIT_LOOKALIKES.get(c, c) for c in suffix[:-1]) + suffix[-1:] \
        if suffix and suffix[-1].isalpha() else \
        "".join(_DIGIT_LOOKALIKES.get(c, c) for c in suffix)
    normalized = f"{prefix}-{corrected_suffix}"

    return {"value": normalized, "confidence": None,
            "needs_review": False, "raw_zone_text": raw_value.strip()}


def clean_field(raw_value: str, zone: FieldZone, field_name: str = "") -> dict:
    raw_value = raw_value.strip()

    if field_name == "document_code":
        if not raw_value:
            return {"value": "", "confidence": None, "needs_review": True,
                    "reason": "blank_zone"}
        return normalize_document_code(raw_value)

    if not raw_value:
        return {"value": "", "confidence": None, "needs_review": True,
                "reason": "blank_zone"}

    if not zone.allowed_values:
        return {"value": " ".join(raw_value.split()),
                "confidence": None, "needs_review": False}

    match, score, _ = process.extractOne(raw_value, zone.allowed_values, scorer=fuzz.ratio)
    return {"value": match, "confidence": score,
            "needs_review": score < FIELD_MATCH_FLOOR}


# ---------------------------------------------------------------------------
# 6. Orchestration -- produces a DRAFT only
# ---------------------------------------------------------------------------

def run_autofill_pipeline(page_image: Image.Image, full_ocr_text: str) -> dict:
    """
    Returns a draft suggestion. This function has no side effects on the
    system of record -- it is read-only by design.
    """
    template, template_score = identify_template(full_ocr_text)
    if template is None:
        return {"status": "unrecognized_template",
                "best_score": template_score, "fields": {}}

    image = preprocess(page_image, template.page_size)
    raw_fields = extract_fields(image, template)
    cleaned_fields = {
        name: clean_field(raw_value, template.zones[name], field_name=name)
        for name, raw_value in raw_fields.items()
    }
    # Checkbox/mark groups (optical mark detection) merge into the same
    # `fields` dict as OCR text fields -- both shapes carry value/
    # confidence/needs_review, so downstream consumers (staff review UI,
    # confirm_and_submit) don't need to special-case which extraction
    # method produced which field.
    cleaned_fields.update(extract_checkbox_groups(image, template))

    return {
        "status": "draft_pending_review",
        "template_id": template.template_id,
        "display_name": template.display_name,
        "template_confidence": template_score,
        "fields": cleaned_fields,
    }


# ---------------------------------------------------------------------------
# 7. Staff Review Gate -- the ONLY path allowed to persist data
# ---------------------------------------------------------------------------

class SubmissionBlocked(Exception):
    pass


def confirm_and_submit(draft: dict, reviewer_id: str, reviewed_fields: dict) -> dict:
    """
    The single choke point for turning a draft into a real record.

    - `reviewer_id` must be a real staff identity; refuses to run without one.
    - `reviewed_fields` must be explicitly passed by the caller (i.e. by
      whatever UI the staff member used to confirm/edit each value) --
      the function never falls back to the raw OCR draft silently.
    - Nothing here reaches out to a database in this reference version;
      in production this is where you'd call
      Submission.objects.create(...) with reviewed_fields, plus an
      audit_logs entry recording reviewer_id and what was changed from
      the original draft.
    """
    if not reviewer_id:
        raise SubmissionBlocked("A staff reviewer identity is required to submit.")
    if draft.get("status") != "draft_pending_review":
        raise SubmissionBlocked(f"Cannot submit a draft with status={draft.get('status')!r}.")

    changes = {
        field_name: {
            "ocr_value": draft["fields"].get(field_name, {}).get("value"),
            "final_value": reviewed_fields.get(field_name),
            "changed": draft["fields"].get(field_name, {}).get("value")
                       != reviewed_fields.get(field_name),
        }
        for field_name in draft["fields"]
    }

    return {
        "status": "submitted",
        "template_id": draft["template_id"],
        "reviewer_id": reviewer_id,
        "final_fields": reviewed_fields,
        "audit_trail": changes,
    }


if __name__ == "__main__":
    import json
    from pdf2image import convert_from_path

    samples = {
        "FM-USTP-OSA-04B-Accomplishment-Report.pdf": None,
        "FM-USTP-OSA-11-Local-Off-Campus-Activities-Certificate-of-Compliance-2.pdf": None,
        "FM-USTP-OSA-10-Student-Activity-Request-Form-1.pdf": None,
    }

    for filename in samples:
        path = f"/mnt/user-data/uploads/{filename}"
        page = convert_from_path(path, dpi=TEMPLATE_DPI)[0]
        full_text = pytesseract.image_to_string(page)
        draft = run_autofill_pipeline(page, full_text)
        print("=====", filename)
        print(json.dumps(draft, indent=2))
        print()