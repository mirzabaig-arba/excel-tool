import requests
from bs4 import BeautifulSoup
import time
import random
import re
import urllib.parse

class LookupService:
    """
    Söktjänst för telefonnummer via svenska offentliga kataloger.
    Fallback: merinfo.se -> hitta.se -> eniro.se
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            "DNT": "1",
            "Connection": "keep-alive",
        }

    def _format_pid(self, person_id):
        """Formaterar personnummer till 12-siffrigt (YYYYMMDDXXXX)."""
        pid = re.sub(r'[^0-9]', '', str(person_id).strip())
        if not pid or len(pid) < 10:
            return None
        if len(pid) == 10:
            year = int(pid[:2])
            prefix = "20" if year < 25 else "19"
            pid = prefix + pid
        return pid

    def _extract_phones(self, soup):
        """Extraherar telefonnummer från en BeautifulSoup-sida."""
        phone_links = soup.select('a[href^="tel:"]')
        phones = []
        for a in phone_links:
            p = a['href'].replace("tel:", "").strip()
            p = re.sub(r'[^0-9+\- ]', '', p)
            if p and p not in phones and len(p) >= 7:
                phones.append(p)
        return ", ".join(phones[:3]) if phones else None

    def _search_merinfo(self, search_val, name):
        """Söker på merinfo.se."""
        try:
            url = f"https://www.merinfo.se/search?q={search_val}&d=p"
            resp = self.session.get(url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Sök profillänk
            links = soup.select('a[href*="/person/"]')
            if not links:
                name_enc = urllib.parse.quote(name)
                url = f"https://www.merinfo.se/search?q={name_enc}&d=p"
                resp = self.session.get(url, headers=self.headers, timeout=15)
                soup = BeautifulSoup(resp.content, "html.parser")
                links = soup.select('a[href*="/person/"]')
            
            if links:
                time.sleep(random.uniform(0.5, 1.2))
                href = links[0].get('href', '')
                if not href.startswith('http'):
                    href = "https://www.merinfo.se" + href
                resp = self.session.get(href, headers=self.headers, timeout=15)
                return self._extract_phones(BeautifulSoup(resp.content, "html.parser"))
            return None
        except Exception:
            return None

    def _search_hitta(self, search_val, name):
        """Söker på hitta.se."""
        try:
            q = urllib.parse.quote(name) if name.strip() else search_val
            url = f"https://www.hitta.se/sök?vad={q}"
            resp = self.session.get(url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.content, "html.parser")
            
            result = self._extract_phones(soup)
            if result:
                return result
            
            links = soup.select('a[href*="/person/"]')
            if links:
                time.sleep(random.uniform(0.5, 1.2))
                href = links[0].get('href', '')
                if not href.startswith('http'):
                    href = "https://www.hitta.se" + href
                resp = self.session.get(href, headers=self.headers, timeout=15)
                return self._extract_phones(BeautifulSoup(resp.content, "html.parser"))
            return None
        except Exception:
            return None

    def _search_eniro(self, search_val, name):
        """Söker på eniro.se."""
        try:
            name_enc = urllib.parse.quote(name)
            url = f"https://www.eniro.se/persons/{name_enc}"
            resp = self.session.get(url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                return None
            return self._extract_phones(BeautifulSoup(resp.content, "html.parser"))
        except Exception:
            return None

    def find_phone_number(self, person_id, name):
        """
        Hittar telefonnummer med fallback: merinfo -> hitta -> eniro.
        """
        formatted = self._format_pid(person_id)
        if not formatted and not name.strip():
            return "Inget ID hittat"
        
        search_val = formatted or ""
        name_clean = name.strip()
        
        time.sleep(random.uniform(0.3, 0.8))
        
        # Försök varje källa i ordning
        for searcher in [self._search_merinfo, self._search_hitta, self._search_eniro]:
            result = searcher(search_val, name_clean)
            if result:
                return result
            time.sleep(random.uniform(0.5, 1.0))
        
        return "Ej hittat"
