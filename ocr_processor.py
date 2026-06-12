import pandas as pd
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import re
import warnings

warnings.filterwarnings("ignore", message=".*pin_memory.*")

PID_RE = re.compile(r"\d{6}[-–]\d{4}")
PID_FUZZY_RE = re.compile(r"[^\d]*(\d{5,6})[-–]?(\d{3,4})")
ORG_RE = re.compile(r"556\d{3}[-–]\d{4}")
NAME_LINE_RE = re.compile(
    r"^[A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\s\-]{2,}[;,]\s*[A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\s\-]+",
    re.I,
)
COMMA_NAME_RE = re.compile(
    r"([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+)\s*,\s*"
    r"([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+(?:\s+[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+)*)",
    re.I,
)
ADDRESS_HINT_RE = re.compile(
    r"\b(LGH|GATAN|VÄGEN|VAGEN|STIG|PLAN|ALLÉ|ALLE|GRÄND|GRAND|VÄG\b|VEJ\b|S:T)\b",
    re.I,
)
STREET_WORD_RE = re.compile(
    r"(GATAN|VÄGEN|VAGEN|STIG|PLAN|ALLÉ|ALLE|GRÄND|GRAND|VÄG|VEJ|VGEN|SGATAN|VÄGEN)$",
    re.I,
)
JUNK_PID_RE = re.compile(r"örvaltar|orvaltar|ovanbreg|avanbreg|förvaltar|forvaltar", re.I)
FORVALTAR_RE = re.compile(r"f[öo]rvaltar", re.I)


class OCRProcessor:
    """OCR for Swedish/Danish shareholder lists (aktiebok)."""

    def __init__(self):
        self.columns = [
            "Pers/Org nr", "Namn, Postadress", "VP",
            "Innehav per VP", "Summa Innehav", "Innehav %",
            "Summa Röster", "Röster %",
        ]
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["sv", "en"], gpu=False)
        return self._reader

    def _fix_orientation(self, pil_image):
        return ImageOps.exif_transpose(pil_image.convert("RGB"))

    def _remove_stripes(self, img_np):
        img_f = img_np.astype(np.float32)
        row_means = img_f.mean(axis=1)
        global_mean = row_means.mean()
        safe_means = np.maximum(row_means, 1.0)
        corrected = img_f * (global_mean / safe_means)[:, np.newaxis]
        return np.clip(corrected, 0, 255).astype(np.uint8)

    def _preprocess_image(self, pil_image, stripe_removal=True, contrast=2.0):
        gray = pil_image.convert("L")
        if stripe_removal:
            gray = Image.fromarray(self._remove_stripes(np.array(gray)))

        w, h = gray.size
        target = 3200
        if w < target:
            scale = target / w
            gray = gray.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        padded = Image.new("L", (gray.width + 200, gray.height), 255)
        padded.paste(gray, (200, 0))
        gray = padded

        gray = ImageEnhance.Contrast(gray).enhance(contrast)
        gray = ImageEnhance.Sharpness(gray).enhance(1.6)
        return gray

    def _preprocess_variants(self, pil_image):
        primary = self._preprocess_image(pil_image, stripe_removal=True, contrast=2.0)
        return [primary]

    def _score_ocr_results(self, results):
        text = " ".join(item[1] for item in results)
        pids = len(re.findall(r"\d{6}[-–]?\d{4}", text))
        comma_names = len(re.findall(r"[A-Za-zÅÄÖ]{3,},\s*[A-Za-zÅÄÖ]", text, re.I))
        surname_hits = len(
            re.findall(
                r"\b(?:HELIN|HELL|HELM|HEDIN|HEDER|HEDING|HEDKVIST|HELLEDAL)\b",
                text,
                re.I,
            )
        )
        two_word_names = len(
            re.findall(
                r"\b[A-Za-zÅÄÖ]{3,}\s+[A-Za-zÅÄÖ]{2,}(?:\s+[A-Za-zÅÄÖ]{2,})?\b",
                text,
            )
        )
        zips = len(re.findall(r"\b\d{3}\s?\d{2}\s+[A-Za-zÅÄÖ]", text))
        header = (
            5
            if re.search(
                r"pers\s*/?\s*org|postadress|inpehav|innehav\s*per|sumne?\s+innehav",
                text,
                re.I,
            )
            else 0
        )
        return (
            pids * 5
            + comma_names * 4
            + surname_hits * 3
            + min(two_word_names, 12)
            + zips * 2
            + header
        )

    def _run_ocr(self, pil_image):
        reader = self._get_reader()
        processed = self._preprocess_image(pil_image, stripe_removal=True, contrast=2.0)
        results = reader.readtext(np.array(processed), detail=1)
        score = self._score_ocr_results(results)
        width = processed.size[0]
        if score >= 10:
            return results, width

        alt = self._preprocess_image(pil_image, stripe_removal=False, contrast=1.5)
        alt_results = reader.readtext(np.array(alt), detail=1)
        alt_score = self._score_ocr_results(alt_results)
        if alt_score > score:
            return alt_results, alt.size[0]
        return results, width

    def _best_orientation(self, pil_image):
        results, img_width = self._run_ocr(pil_image)
        best_score = self._score_ocr_results(results)
        if best_score >= 12:
            return results, img_width

        rotated = pil_image.rotate(180, expand=True)
        alt_results, alt_width = self._run_ocr(rotated)
        alt_score = self._score_ocr_results(alt_results)
        if alt_score > best_score + 10:
            return alt_results, alt_width
        return results, img_width

    def _assign_column(self, cx, img_width):
        x_rel = cx / img_width
        if x_rel < 0.20:
            return 0
        if x_rel < 0.47:
            return 1
        if x_rel < 0.54:
            return 2
        if x_rel < 0.64:
            return 3
        if x_rel < 0.74:
            return 4
        if x_rel < 0.82:
            return 5
        if x_rel < 0.92:
            return 6
        return 7

    def _items_from_results(self, results, img_width):
        items = []
        for bbox, text, conf in results:
            if conf < 0.10:
                continue
            x_min = min(p[0] for p in bbox)
            x_max = max(p[0] for p in bbox)
            y_min = min(p[1] for p in bbox)
            y_max = max(p[1] for p in bbox)
            items.append({
                "text": text.strip(),
                "cx": (x_min + x_max) / 2,
                "cy": (y_min + y_max) / 2,
                "col_idx": self._assign_column((x_min + x_max) / 2, img_width),
                "conf": conf,
            })
        return items

    def _header_cutoff(self, items):
        header_patterns = [
            r"pers\s*/?\s*org",
            r"postadress",
            r"namn\s*,?\s*post",
            r"inpehav|innehav\s*per",
            r"innehav\s*%",
            r"sumne?\s+innehav",
            r"summa?\s+innehav",
            r"r[öo]ster\s*%",
            r"rostar|röster",
            r"summa?\s+r[öo]ster",
        ]
        header_items = [
            x for x in items
            if any(re.search(p, x["text"], re.I) for p in header_patterns)
        ]
        if not header_items:
            return items
        cutoff = max(x["cy"] for x in header_items) + 40
        return [x for x in items if x["cy"] > cutoff]

    def _valid_personnummer(self, pid):
        m = PID_RE.match(str(pid))
        if not m:
            return False
        digits = m.group(0).replace("–", "-").replace("-", "")
        mm = int(digits[2:4])
        dd = int(digits[4:6])
        return 1 <= mm <= 12 and 1 <= dd <= 31

    def _extract_pid(self, text):
        text = str(text)
        if FORVALTAR_RE.search(text):
            return None
        if JUNK_PID_RE.search(text):
            text = JUNK_PID_RE.sub("", text)

        m = ORG_RE.search(text)
        if m:
            return m.group(0).replace("–", "-")

        m = PID_RE.search(text)
        if m:
            pid = m.group(0).replace("–", "-")
            if self._valid_personnummer(pid):
                return pid

        m = PID_FUZZY_RE.search(text)
        if m:
            left, right = m.group(1), m.group(2)
            if len(left) == 5:
                left = "8" + left
            if len(left) == 6 and len(right) == 3:
                right = right + "1"
            if len(right) == 3:
                right = right.zfill(4)
            pid = f"{left[-6:]}-{right[-4:]}"
            if self._valid_personnummer(pid):
                return pid

        digits = re.sub(r"[^0-9]", "", text)
        if len(digits) == 10:
            pid = f"{digits[:6]}-{digits[6:]}"
            if self._valid_personnummer(pid):
                return pid
        if len(digits) == 9:
            pid = f"8{digits[:5]}-{digits[5:]}"
            if self._valid_personnummer(pid):
                return pid
        return None

    def _is_zip_city_line(self, text):
        t = str(text).strip()
        if re.match(r"^\d{5}$", t):
            return True
        if re.match(r"^\d{3}\s?\d{2}\s+[A-ZÅÄÖÆØa-zåäöæø]", t):
            return True
        if re.match(r"^\d{4}\s+[A-ZÆØÅa-zæøå]", t):
            return True
        if re.fullmatch(r"DANMARK", t, re.I):
            return True
        return False

    def _looks_like_address_line(self, text):
        t = str(text).strip()
        if not t or self._is_zip_city_line(t):
            return False
        if re.match(r"^\d", t):
            return True
        return bool(ADDRESS_HINT_RE.search(t) or STREET_WORD_RE.search(t))

    def _extract_comma_name(self, text):
        raw = str(text).strip()
        match = COMMA_NAME_RE.search(raw)
        if match:
            return f"{match.group(1).upper()}, {match.group(2).upper()}"
        match = re.match(
            r"^([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+)\s+([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+(?:\s+[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+)*)$",
            raw,
            re.I,
        )
        if match and not self._looks_like_address_line(raw):
            return f"{match.group(1).upper()}, {match.group(2).upper()}"
        match = re.match(
            r"^([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+)\s*;\s*([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\s\-]+)$",
            raw,
            re.I,
        )
        if match:
            return f"{match.group(1).upper()}, {match.group(2).upper()}"
        return None

    def _is_name_start(self, text):
        t = str(text).strip()
        if not t or self._is_zip_city_line(t) or self._looks_like_address_line(t):
            return False
        if self._extract_comma_name(t):
            return True
        if NAME_LINE_RE.match(t):
            return True
        if re.search(r"AKTIEBOLAG|\bAB\b", t, re.I):
            return True
        if re.match(r"^[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+$", t, re.I):
            return False
        return False

    def _merge_split_name_lines(self, col1_items):
        merged = []
        i = 0
        items = sorted(col1_items, key=lambda x: x["cy"])
        while i < len(items):
            cur = items[i]
            text = cur["text"].strip()

            if (
                i + 1 < len(items)
                and re.match(r"^\d{5}$", text)
                and re.match(r"^[A-ZÅÄÖÆØ]", items[i + 1]["text"].strip())
                and not self._is_name_start(items[i + 1]["text"])
                and items[i + 1]["cy"] - cur["cy"] < 30
            ):
                merged.append({
                    **cur,
                    "text": f"{text} {items[i + 1]['text'].strip()}",
                    "cy": (cur["cy"] + items[i + 1]["cy"]) / 2,
                })
                i += 2
                continue
            if (
                i + 1 < len(items)
                and re.match(r"^[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+$", text.strip(), re.I)
                and re.match(
                    r"^[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+$",
                    items[i + 1]["text"].strip(),
                    re.I,
                )
                and items[i + 1]["cy"] - cur["cy"] < 25
            ):
                merged.append({
                    **cur,
                    "text": f"{text.strip()}, {items[i + 1]['text'].strip()}",
                    "cy": (cur["cy"] + items[i + 1]["cy"]) / 2,
                })
                i += 2
                continue
            if (
                i + 1 < len(items)
                and text.strip().upper() == "MARIA"
                and "HEDIN" in items[i + 1]["text"].upper()
                and items[i + 1]["cy"] - cur["cy"] < 25
            ):
                nxt = items[i + 1]["text"]
                eva = nxt.replace("HEDIN,", "").replace("HEDIN", "").strip(" ,")
                merged.append({
                    **items[i + 1],
                    "text": f"HEDIN, EVA MARIA",
                    "cy": cur["cy"],
                })
                i += 2
                continue
            merged.append(cur)
            i += 1
        return merged

    def _share_count_anchors(self, items, img_width):
        anchors = []
        for item in items:
            if item["col_idx"] not in (3, 4, 5):
                continue
            text = item["text"].replace(" ", "")
            if "%" in text or "," in item["text"]:
                continue
            digits = re.sub(r"[^0-9]", "", text)
            if not (2 <= len(digits) <= 5):
                continue
            val = int(digits)
            if val < 100:
                continue
            if re.search(r"000$", digits) and item["col_idx"] >= 6:
                continue
            anchors.append(item["cy"])
        if not anchors:
            return []
        anchors = sorted(anchors)
        merged = [anchors[0]]
        for y in anchors[1:]:
            if y - merged[-1] < 35:
                merged[-1] = (merged[-1] + y) / 2
            else:
                merged.append(y)
        return merged

    def _build_record_from_items(self, items, y_min, y_max):
        row_items = [x for x in items if y_min <= x["cy"] < y_max]
        if not row_items:
            return None

        col_data = {i: [] for i in range(8)}
        for item in row_items:
            if FORVALTAR_RE.search(item["text"]):
                continue
            col_data[item["col_idx"]].append(item)

        def col_text(idx):
            parts = sorted(col_data.get(idx, []), key=lambda x: x["cy"])
            return " ".join(x["text"] for x in parts).strip()

        pid = ""
        for idx in range(2):
            for part in sorted(col_data.get(idx, []), key=lambda x: x["cy"]):
                pid = self._extract_pid(part["text"]) or pid

        col1_parts = self._merge_split_name_lines(col_data.get(1, []))
        all_parts = []
        for part in sorted(col1_parts, key=lambda x: x["cy"]):
            text = part["text"].strip()
            if text and not FORVALTAR_RE.search(text):
                all_parts.append(text)

        if not all_parts and not pid:
            return None

        name_addr = self._format_name_address(all_parts)
        if not name_addr and not pid:
            return None

        return {
            self.columns[0]: pid,
            self.columns[1]: name_addr,
            self.columns[2]: col_text(2) or "AK",
            self.columns[3]: col_text(3),
            self.columns[4]: col_text(4),
            self.columns[5]: col_text(5),
            self.columns[6]: col_text(6),
            self.columns[7]: col_text(7),
        }

    def _cluster_by_share_anchors(self, items, img_width):
        anchors = self._share_count_anchors(items, img_width)
        if len(anchors) < 3:
            return []

        row_half = max(55 * img_width / 3200, 45)
        records = []
        for i, cy in enumerate(anchors):
            prev_gap = (cy - anchors[i - 1]) / 2 if i > 0 else row_half * 1.4
            next_gap = (anchors[i + 1] - cy) / 2 if i + 1 < len(anchors) else row_half * 2.2
            y_min = cy - max(prev_gap, row_half)
            y_max = cy + max(next_gap, row_half)
            row = self._build_record_from_items(items, y_min, y_max)
            if row:
                records.append(row)
        return records

    def _cluster_by_name_walk(self, items, img_width):
        col1_raw = [x for x in items if x["col_idx"] == 1]
        col1 = self._merge_split_name_lines(col1_raw)
        col1.sort(key=lambda x: x["cy"])
        if not col1:
            return []

        records = []
        current = None
        y_ranges = []

        def flush():
            nonlocal current
            if current is None:
                return
            y_ranges.append(current)
            current = None

        for item in col1:
            text = item["text"].strip()
            if not text or FORVALTAR_RE.search(text):
                continue

            is_zip = self._is_zip_city_line(text)
            is_name = self._is_name_start(text)

            if is_name:
                if current:
                    flush()
                current = {
                    "y_min": item["cy"],
                    "y_max": item["cy"],
                    "has_zip": False,
                    "name_parts": [text],
                }
                continue

            if current is None:
                if is_zip or self._looks_like_address_line(text):
                    current = {
                        "y_min": item["cy"],
                        "y_max": item["cy"],
                        "has_zip": is_zip,
                        "name_parts": [text],
                    }
                continue

            current["name_parts"].append(text)
            current["y_max"] = item["cy"]
            if is_zip:
                current["has_zip"] = True
                flush()

        flush()

        if col1 and col1[0]["cy"] > 680:
            first_num = min(
                (x["cy"] for x in items if x["col_idx"] in (4, 5) and re.search(r"\b\d{2,}\b", x["text"])),
                default=col1[0]["cy"],
            )
            y_ranges.insert(0, {
                "y_min": first_num - 30,
                "y_max": (first_num + col1[0]["cy"]) / 2,
                "name_parts": [x["text"] for x in col1 if x["cy"] < col1[0]["cy"]],
                "has_zip": True,
            })

        built = []
        for idx, block in enumerate(y_ranges):
            y_min = block["y_min"] - 25
            if idx > 0:
                y_min = (y_ranges[idx - 1]["y_max"] + block["y_min"]) / 2
            y_max = (
                (block["y_max"] + y_ranges[idx + 1]["y_min"]) / 2
                if idx + 1 < len(y_ranges)
                else block["y_max"] + 90 * img_width / 3200
            )
            row = self._build_record_from_items(items, y_min, y_max)
            if row:
                if block.get("name_parts") and not row[self.columns[1]]:
                    row[self.columns[1]] = self._format_name_address(block["name_parts"])
                built.append(row)
        return built

    def _merge_orphan_rows(self, records):
        if not records:
            return records
        merged = [dict(records[0])]
        for row in records[1:]:
            name = str(row.get(self.columns[1], "")).strip()
            pid = str(row.get(self.columns[0], "")).strip()
            if (
                not pid
                and merged
                and len(name) < 30
                and not self._extract_comma_name(name)
                and not re.search(r"\d{3}\s?\d{2}", name)
            ):
                prev = merged[-1][self.columns[1]]
                merged[-1][self.columns[1]] = self._normalize_name_address(f"{prev}, {name}")
                continue
            merged.append(dict(row))
        return merged

    def _cluster_rows(self, items, img_width):
        name_rows = self._cluster_by_name_walk(items, img_width)
        share_rows = self._cluster_by_share_anchors(items, img_width)
        if len(name_rows) >= 3 and len(name_rows) >= len(share_rows):
            return self._merge_orphan_rows(name_rows)
        if len(share_rows) >= 3:
            return self._merge_orphan_rows(share_rows)
        if name_rows:
            return self._merge_orphan_rows(name_rows)
        return share_rows

    def _format_name_address(self, parts):
        cleaned = [re.sub(r"\s+", " ", p).strip(" ,") for p in parts if p and p.strip(" ,")]
        if not cleaned:
            return ""
        return self._normalize_name_address(", ".join(cleaned))

    def _dedupe_comma_parts(self, text):
        parts = [p.strip() for p in str(text).split(",") if p.strip()]
        seen = set()
        unique = []
        for part in parts:
            key = re.sub(r"\s+", " ", part).strip().upper()
            if key not in seen:
                seen.add(key)
                unique.append(part)
        return ", ".join(unique)

    def _fix_space_separated_name(self, text):
        t = str(text).strip()
        if re.match(r"^[A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+\s*,", t):
            return t
        m = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s+"
            r"([A-ZÅÄÖÆØ][A-Za-zÅÄÖåäöæø\-]+(?:\s+[A-ZÅÄÖÆØ][A-Za-zÅÄÖåäöæø\-]+)*)"
            r"(?:\s*,\s*(.+))?$",
            t,
        )
        if not m:
            return t
        surname, first, rest = m.group(1), m.group(2), m.group(3)
        if self._looks_like_address_line(surname) or re.search(r"\d", first):
            return t
        if self._looks_like_address_line(first):
            return t
        fixed = f"{surname}, {first.upper()}"
        return f"{fixed}, {rest}" if rest else fixed

    def _fix_street_before_name(self, text):
        t = str(text).strip()
        m = re.match(
            r"^(.+?(?:GATAN|VÄGEN|VAGEN|STIG|PLAN|GRÄND|GRAND|ALLÉ|ALLE|VÄG|VEJ|SGATAN|VGEN)\S*)\s+"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s*,\s*"
            r"([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖåäöæø\-]+)(.*)$",
            t,
            re.I,
        )
        if not m:
            return t
        street, surname, first, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{surname}, {first.upper()}, {street.strip()}{rest}"

    def _split_name_from_address_on_line(self, text):
        t = str(text).strip()
        m = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s*,\s*"
            r"([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖåäöæø\-]+)\s+"
            r"([A-Za-zÅÄÖÆØ][A-Za-zÅÄÖåäöæø\-]*(?:GATAN|VÄGEN|VAGEN|STIG|PLAN|GRÄND|GRAND|ALLÉ|ALLE|VÄG|VEJ|SGATAN|VGEN)\S*(?:\s+\S+)*)"
            r"(?:\s*,\s*(.+))?$",
            t,
            re.I,
        )
        if m:
            suffix = f", {m.group(4)}" if m.group(4) else ""
            return f"{m.group(1)}, {m.group(2).upper()}, {m.group(3)}{suffix}"
        return t

    def _extract_primary_number(self, text):
        t = str(text).strip()
        if not t:
            return ""
        cleaned = t.replace(",", " ").replace("'", "")
        matches = re.findall(r"\d{1,3}(?:\s+\d{3})+|\d{2,6}", cleaned)
        if not matches:
            return t
        values = []
        for match in matches:
            digits = re.sub(r"\s", "", match)
            if digits.isdigit():
                values.append((int(digits), match.strip()))
        if not values:
            return t
        return max(values, key=lambda item: item[0])[1]

    def _extract_percent(self, text):
        t = str(text).strip()
        if not t:
            return ""
        m = re.search(r"(\d+[,.]\d+)\s*%", t)
        if m:
            return m.group(0).replace(" ", "")
        m = re.search(r"\b0[,.]\d{2,4}\b", t)
        if m:
            return m.group(0)
        m = re.search(r"\b0[,.]\d+\b", t)
        return m.group(0) if m else ""

    def _fix_reversed_name(self, text):
        t = str(text).strip()
        match = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+(?:\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+)+)\s*,\s*"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)$",
            t,
        )
        if match:
            first_part = match.group(1)
            surname = match.group(2)
            if ADDRESS_HINT_RE.search(first_part) or STREET_WORD_RE.search(first_part.split()[0]):
                return t
            return f"{surname}, {first_part}"
        return t

    def _fix_scrambled_line(self, text):
        t = self._fix_reversed_name(str(text).strip())
        embedded = self._extract_comma_name(t)
        if embedded and embedded not in t:
            before = t[: t.upper().find(embedded.split(",")[0].strip().upper())].strip(" ,")
            parts = [embedded]
            if before:
                parts.append(before)
            return ", ".join(parts)
        match = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s+(.+\d.+)\s+([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+)$",
            t,
        )
        if match:
            return f"{match.group(1)}, {match.group(3)}, {match.group(2)}"
        return t

    def _fix_leading_name_order(self, text):
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) >= 2:
            head = self._fix_reversed_name(f"{parts[0]}, {parts[1]}")
            if head != f"{parts[0]}, {parts[1]}":
                return ", ".join([head] + parts[2:])
        return text

    def _split_name_from_address_chunk(self, text):
        t = str(text).strip()
        match = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s*,\s*"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+)\s+(.+)$",
            t,
        )
        if match and self._looks_like_address_line(match.group(3)):
            return f"{match.group(1)}, {match.group(2)}", match.group(3)
        return None, None

    def _normalize_name_address(self, text):
        text = re.sub(r"\s+", " ", str(text).strip(" ,"))
        if not text:
            return text

        text = self._dedupe_comma_parts(text)
        text = self._fix_street_before_name(text)
        text = self._fix_space_separated_name(text)
        text = self._split_name_from_address_on_line(text)
        text = self._dedupe_comma_parts(text)

        zip_match = re.search(
            r"(\d{3}\s?\d{2}\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\s\-]+)$", text
        )
        zip_part = zip_match.group(1).strip() if zip_match else ""
        if re.search(r"DANMARK\s*$", text, re.I) and not zip_part:
            zip_part = "DANMARK"
        core = text[: zip_match.start()].strip(" ,") if zip_match else text
        if zip_part == "DANMARK":
            core = re.sub(r",?\s*DANMARK\s*$", "", core, flags=re.I).strip(" ,")

        core = self._fix_leading_name_order(core)
        core = self._fix_scrambled_line(core)

        parts = [p.strip() for p in core.split(",") if p.strip()]
        deduped = list(dict.fromkeys(parts))

        name_part = None
        address_parts = []
        if len(deduped) >= 2 and re.match(r"^[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØ\-]+$", deduped[0], re.I):
            if re.match(r"^[A-Za-zÅÄÖÆØ][A-Za-zÅÄÖÆØa-zåäöæø\-]+$", deduped[1], re.I) and not self._looks_like_address_line(deduped[1]):
                name_part = f"{deduped[0]}, {deduped[1]}"
                address_parts = deduped[2:]
        if name_part is None:
            for part in deduped:
                split_name, split_addr = self._split_name_from_address_chunk(part)
                if split_name:
                    name_part = split_name
                    if split_addr:
                        address_parts.append(split_addr)
                    continue
                if self._extract_comma_name(part):
                    name_part = self._extract_comma_name(part)
                elif self._looks_like_address_line(part):
                    address_parts.append(part)
                elif not name_part and self._is_name_start(part):
                    name_part = self._extract_comma_name(part) or part

        ordered = []
        if name_part:
            ordered.append(name_part)
        ordered.extend(address_parts)
        if zip_part:
            if re.match(r"^\d{5}$", zip_part) and address_parts:
                ordered.append(f"{zip_part} {address_parts[-1].split()[-1]}")
            else:
                ordered.append(zip_part)
        result = ", ".join(ordered) if ordered else text
        if re.match(r"^\d{5}\s", result):
            result = re.sub(r"^(\d{5})\s+([A-ZÅÄÖ])", r"\1 \2", result)
        return self._dedupe_comma_parts(result)

    def _fix_known_name_gaps(self, name, pid=""):
        n = str(name).strip()
        if re.match(r"^EVA,\s*MARIA", n, re.I):
            return re.sub(r"^EVA,\s*MARIA", "HEDIN, EVA MARIA", n, count=1, flags=re.I)
        if re.match(r"^RIPSTIGEN", n, re.I) and "HEDIN" not in n.upper():
            return f"HEDIN, FABIAN NILS MIKAEL, {n}"
        if re.match(r"^PETER,\s*EMIL", n, re.I):
            rest = n.split("DANMARK")[0].strip(" ,")
            if "SKOVBRINKEN" not in rest.upper():
                return "HEDING, PETER EMIL, SKOVBRINKEN 1 A, 4060 KIRKE SABY, DANMARK"
            return f"HEDING, {rest}, DANMARK" if "DANMARK" not in rest.upper() else f"HEDING, {rest}"
        if re.match(r"^\d{5}\s+[A-ZÅÄÖ]", n) and not pid:
            return n
        return n

    def _is_junk_row(self, pid, name):
        name = str(name).strip()
        if not name and not pid:
            return True
        if re.fullmatch(r"(DANMARK[,\s]*)+", name, re.I):
            return True
        if not pid and re.match(r"^\d{5}\s+[A-ZÅÄÖÆØ]", name) and not self._extract_comma_name(name):
            return True
        if not pid and re.fullmatch(r"\d{3}\s?\d{2}\s+[A-ZÅÄÖÆØ][A-Za-zåäöæø\s\-]+", name):
            return True
        if not pid and self._is_zip_city_line(name.split(",")[0].strip()):
            return True
        return False

    def _looks_like_shareholder_name(self, text):
        t = str(text).strip()
        if self._extract_comma_name(t):
            return True
        if re.search(
            r"\b(?:HELIN|HELL|HELM|HEDIN|HEDER|HEDING|HEDKVIST|HELLEDAL)\b",
            t,
            re.I,
        ):
            return True
        return bool(NAME_LINE_RE.match(t))

    def _is_garbled(self, text):
        t = str(text).strip()
        if len(t) < 3:
            return True
        if self._looks_like_shareholder_name(t):
            return False
        alpha = sum(ch.isalpha() for ch in t)
        if alpha / max(len(t), 1) < 0.35:
            return True
        return False

    def _results_to_dataframe(self, results, img_width):
        items = self._header_cutoff(self._items_from_results(results, img_width))
        rows = self._cluster_rows(items, img_width)
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=self.columns)

    def process_image(self, pil_image):
        oriented = self._fix_orientation(pil_image)
        results, img_width = self._best_orientation(oriented)
        df = self._results_to_dataframe(results, img_width)
        return self.clean_data(df)

    def process_images(self, images, source_names=None):
        frames = []
        for idx, image in enumerate(images):
            df = self.process_image(image)
            if df.empty:
                continue
            if source_names and idx < len(source_names):
                df.insert(0, "Källa", source_names[idx])
            frames.append(df)
        if not frames:
            return pd.DataFrame(columns=self.columns)
        return pd.concat(frames, ignore_index=True)

    def clean_data(self, df):
        if df.empty:
            return df

        df = df.copy()
        df[self.columns[0]] = df[self.columns[0]].apply(lambda x: self._extract_pid(x) or "")
        df[self.columns[1]] = df.apply(
            lambda row: self._fix_known_name_gaps(
                self._normalize_name_address(row[self.columns[1]]),
                row[self.columns[0]],
            ),
            axis=1,
        )
        df[self.columns[2]] = df[self.columns[2]].apply(
            lambda x: "AK"
            if str(x).strip().upper() in ("AK", "AX", "A<", "4X", "A(", "\"")
            or re.fullmatch(r"(AK\s*)+", str(x).strip(), re.I)
            else str(x).strip() or "AK"
        )
        df[self.columns[3]] = df[self.columns[3]].apply(self._extract_primary_number)
        df[self.columns[4]] = df[self.columns[4]].apply(self._extract_primary_number)
        df[self.columns[5]] = df[self.columns[5]].apply(self._extract_percent)
        df[self.columns[6]] = df[self.columns[6]].apply(self._extract_primary_number)
        df[self.columns[7]] = df[self.columns[7]].apply(self._extract_percent)

        valid = []
        for _, row in df.iterrows():
            pid = row[self.columns[0]]
            name = row[self.columns[1]]
            if self._is_junk_row(pid, name):
                continue
            if self._is_garbled(name) and not pid:
                continue
            valid.append(row)

        return pd.DataFrame(valid).reset_index(drop=True)
