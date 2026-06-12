import re
import urllib.parse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup


class LookupService:
    """
    Phone lookup optimized for accuracy and speed.
    Sweden: hitta.se + merinfo.se + eniro.se in parallel.
    Denmark: krak.dk only when the address is clearly Danish.
    """

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,da;q=0.8,en;q=0.7",
        }
        self._cache = {}

    def _cache_key(self, person_id, name):
        return f"{person_id}|{name}".strip().lower()

    def _prepare_name_text(self, text):
        match = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s+(.+\d.+)\s+([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+)(.*)$",
            text,
        )
        if match:
            suffix = match.group(4).strip(" ,")
            rebuilt = f"{match.group(1)}, {match.group(3)}, {match.group(2)}"
            return f"{rebuilt}, {suffix}" if suffix else rebuilt

        rev = re.match(
            r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+(?:\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+)+)\s*,\s*"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)(.*)$",
            text,
        )
        if rev:
            suffix = rev.group(3).strip(" ,")
            rebuilt = f"{rev.group(2)}, {rev.group(1)}"
            return f"{rebuilt}, {suffix}" if suffix else rebuilt

        embedded = re.search(
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s*,\s*"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+(?:\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+)*)",
            text,
        )
        if embedded:
            before = text[: embedded.start()].strip(" ,")
            after = text[embedded.end() :].strip(" ,")
            rebuilt = f"{embedded.group(1)}, {embedded.group(2)}"
            if before:
                rebuilt = f"{rebuilt}, {before}"
            if after:
                rebuilt = f"{rebuilt}, {after}"
            return rebuilt
        return text

    def parse_search_query(self, raw_name):
        """Build a precise search query from shareholder address field."""
        text = re.sub(r"\s+", " ", str(raw_name).strip())
        text = self._prepare_name_text(text)

        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) >= 2:
            head = re.match(
                r"^([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+(?:\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø]+)+)\s*,\s*"
                r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)$",
                f"{parts[0]}, {parts[1]}",
            )
            if head:
                text = ", ".join([f"{head.group(2)}, {head.group(1)}"] + parts[2:])

        name_match = re.search(
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\-]+)\s*,\s*"
            r"([A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+(?:\s+[A-ZÅÄÖÆØ][A-ZÅÄÖÆØa-zåäöæø\-]+)*)",
            text,
        )
        city = ""
        zip_match = re.search(r"(\d{3}\s?\d{2})\s+([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\s\-]+)$", text)
        if not zip_match:
            zip_match = re.search(r"(\d{5})\s+([A-ZÅÄÖÆØ][A-ZÅÄÖÆØ\s\-]+)$", text)
        if zip_match:
            city = zip_match.group(2).strip()

        if name_match:
            surname, firstname = name_match.group(1), name_match.group(2)
            base = f"{firstname} {surname}"
            if city:
                return f"{base} {city}", base
            return base, base

        parts = [p.strip() for p in text.split(",") if p.strip()]
        surname = firstname = ""
        if len(parts) >= 2:
            surname = parts[0]
            firstname = parts[1]
        elif len(parts) == 1:
            return parts[0], parts[0]

        if not city:
            for part in reversed(parts[2:]):
                city_match = re.search(
                    r"(?:\d{5}\s+|\d{4}\s+)?([A-ZÅÄÖÆØa-zåäöæø][A-ZÅÄÖÆØa-zåäöæø\s\-]+)$",
                    part,
                )
                if city_match:
                    city = city_match.group(1).strip()
                    break

        if firstname and surname:
            base = f"{firstname} {surname}"
            if city:
                return f"{base} {city}", base
            return base, base
        return text, text

    def _is_danish(self, name):
        upper = str(name).upper()
        if re.search(r"\b(DANMARK|DENMARK|DANMARKS)\b", upper):
            return True
        if re.search(r"\b\d{5}\s+", upper):
            return False
        return bool(re.search(r"\b\d{4}\s+[A-ZÆØÅ]", upper))

    def _digits_only(self, value):
        return re.sub(r"[^0-9]", "", str(value))

    def _is_plausible_swedish_phone(self, digits, person_id=""):
        if not digits or not digits.startswith("0"):
            return False
        if len(digits) not in (9, 10):
            return False
        if digits.startswith("07"):
            return len(digits) == 10
        if person_id:
            pid_digits = self._digits_only(person_id)
            if pid_digits and digits in pid_digits:
                return False
        return True

    def _format_swedish_phone(self, digits):
        if digits.startswith("07") and len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]} {digits[6:8]} {digits[8:]}"
        if len(digits) == 9:
            return (
                f"{digits[:2]}-{digits[2:5]} {digits[5:7]} {digits[7:]}"
                if digits.startswith("08")
                else f"{digits[:3]}-{digits[3:6]} {digits[6:8]} {digits[8:]}"
            )
        if len(digits) == 10:
            return f"{digits[:4]}-{digits[4:7]} {digits[7:]}"
        return None

    def _format_danish_phone(self, digits):
        if digits.startswith("0045"):
            digits = digits[4:]
        elif digits.startswith("45") and len(digits) > 8:
            digits = digits[2:]
        if len(digits) == 8:
            return f"{digits[:2]} {digits[2:4]} {digits[4:6]} {digits[6:]}"
        return None

    def _add_phone(self, phones, digits, person_id="", country="se"):
        if country == "dk":
            formatted = self._format_danish_phone(digits)
        else:
            if not self._is_plausible_swedish_phone(digits, person_id):
                return
            formatted = self._format_swedish_phone(digits)
        if formatted and formatted not in phones:
            phones.append(formatted)

    def _extract_phones_from_html(self, html, person_id="", country="se"):
        phones = []
        soup = BeautifulSoup(html, "html.parser")

        for link in soup.select('a[href^="tel:"]'):
            self._add_phone(phones, self._digits_only(link.get("href", "")), person_id, country)

        visible = soup.get_text(" ", strip=True)
        if country == "dk":
            for match in re.findall(
                r"(?:\+45\s?)?\d{2}[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2}", visible
            ):
                self._add_phone(phones, self._digits_only(match), person_id, country)
        else:
            for match in re.findall(r"07\d-\d{3}\s\d{2}\s\d{2}", visible):
                self._add_phone(phones, self._digits_only(match), person_id, country)
            for match in re.findall(r"\b07\d{8}\b", visible):
                self._add_phone(phones, match, person_id, country)
            for match in re.findall(r"0\d{1,2}-\d{3}\s\d{2}\s\d{2}", visible):
                self._add_phone(phones, self._digits_only(match), person_id, country)

        return ", ".join(phones[:2]) if phones else None

    def _first_profile(self, soup, base_url, selector):
        for link in soup.select(selector):
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = base_url + href
            return href
        return None

    def _fetch(self, url):
        return self.session.get(url, headers=self.headers, timeout=8)

    def _search_hitta(self, query, person_id):
        url = f"https://www.hitta.se/sok?vad={urllib.parse.quote(query)}"
        resp = self._fetch(url)
        if resp.status_code != 200:
            return None

        phones = self._extract_phones_from_html(resp.text, person_id)
        if phones:
            return phones

        if "/person/" in resp.url:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")
        profile = self._first_profile(soup, "https://www.hitta.se", 'a[href*="/person/"]')
        if not profile:
            return None

        resp = self._fetch(profile)
        if resp.status_code != 200:
            return None
        return self._extract_phones_from_html(resp.text, person_id)

    def _search_merinfo(self, query, person_id):
        url = f"https://www.merinfo.se/search?q={urllib.parse.quote(query)}&d=p"
        resp = self._fetch(url)
        if resp.status_code != 200:
            return None

        phones = self._extract_phones_from_html(resp.text, person_id)
        if phones:
            return phones

        soup = BeautifulSoup(resp.content, "html.parser")
        profile = self._first_profile(soup, "https://www.merinfo.se", 'a[href*="/person/"]')
        if not profile:
            return None

        resp = self._fetch(profile)
        if resp.status_code != 200:
            return None
        return self._extract_phones_from_html(resp.text, person_id)

    def _search_krak(self, query):
        url = f"https://www.krak.dk/soeg?query={urllib.parse.quote(query)}"
        resp = self._fetch(url)
        if resp.status_code != 200:
            return None

        phones = self._extract_phones_from_html(resp.text, country="dk")
        if phones:
            return phones

        soup = BeautifulSoup(resp.content, "html.parser")
        profile = self._first_profile(
            soup, "https://www.krak.dk", 'a[href*="/person/"], a[href*="/profil/"]'
        )
        if not profile:
            return None

        resp = self._fetch(profile)
        if resp.status_code != 200:
            return None
        return self._extract_phones_from_html(resp.text, country="dk")

    def _search_eniro(self, query, person_id):
        url = f"https://www.eniro.se/query?search_word={urllib.parse.quote(query)}&geo_area=&company_filter=&person_filter=on"
        resp = self._fetch(url)
        if resp.status_code != 200:
            return None

        phones = self._extract_phones_from_html(resp.text, person_id)
        if phones:
            return phones

        soup = BeautifulSoup(resp.content, "html.parser")
        profile = self._first_profile(
            soup, "https://www.eniro.se", 'a[href*="/person/"], a[href*="/persons/"]'
        )
        if not profile:
            return None

        resp = self._fetch(profile)
        if resp.status_code != 200:
            return None
        return self._extract_phones_from_html(resp.text, person_id)

    def _search_merinfo_pid(self, person_id):
        pid = self._digits_only(person_id)
        if len(pid) < 10:
            return None
        if len(pid) == 10:
            year = int(pid[:2])
            pid = ("20" if year < 25 else "19") + pid
        url = f"https://www.merinfo.se/person/{pid}"
        resp = self._fetch(url)
        if resp.status_code != 200:
            return None
        return self._extract_phones_from_html(resp.text, person_id)

    def _merge_phone_hits(self, hits):
        if not hits:
            return None
        unique = []
        for hit in hits:
            for part in hit.split(","):
                part = part.strip()
                if part and part not in unique:
                    unique.append(part)
        if not unique:
            return None
        if len(unique) == 1:
            return unique[0]
        return f"{unique[0]}, {unique[1]}"

    def _search_sweden(self, query, person_id):
        tasks = {
            "hitta": lambda: self._search_hitta(query, person_id),
            "merinfo": lambda: self._search_merinfo(query, person_id),
            "eniro": lambda: self._search_eniro(query, person_id),
        }
        if person_id and self._digits_only(person_id):
            tasks["merinfo_pid"] = lambda: self._search_merinfo_pid(person_id)

        hits = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                try:
                    phone = future.result()
                    if phone:
                        hits.append(phone)
                except Exception:
                    continue
        return self._merge_phone_hits(hits)

    def find_phone_number(self, person_id, name):
        name_clean = str(name).strip()
        if not name_clean:
            return "Ej hittat"

        cache_key = self._cache_key(person_id, name_clean)
        if cache_key in self._cache:
            return self._cache[cache_key]

        query, _ = self.parse_search_query(name_clean)
        pid = str(person_id).strip()

        if self._is_danish(name_clean):
            result = self._search_krak(query) or "Ej hittat (Danmark)"
        else:
            result = self._search_sweden(query, pid) or "Ej hittat"

        self._cache[cache_key] = result
        return result

    def find_phone_numbers_batch(self, rows):
        """Lookup phones for multiple rows. rows: list of (person_id, name) tuples."""
        return [self.find_phone_number(pid, name) for pid, name in rows]
