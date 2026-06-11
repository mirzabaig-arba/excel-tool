import requests
from bs4 import BeautifulSoup
import time
import random
import re
import urllib.parse

class LookupService:
    """
    Söktjänst för telefonnummer via svenska offentliga kataloger.
    Använder hitta.se som primär källa då den har bäst tillgänglighet utan blockeringar.
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

    def _normalize_name(self, name):
        """Om namnet är i formatet 'Efternamn, Förnamn', vänd på det."""
        name = name.strip()
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            if len(parts) >= 2:
                return f"{parts[1]} {parts[0]}"
        return name

    def _clean_phone(self, phone_str):
        """Rensar och formaterar telefonnummer till snygg svensk standard."""
        p = re.sub(r'[^0-9]', '', phone_str)
        if p.startswith('0046'):
            p = '0' + p[4:]
        elif p.startswith('46') and not p.startswith('0'):
            p = '0' + p[2:]
            
        if not p.startswith('0'):
            return None
            
        if len(p) < 9 or len(p) > 11:
            return None
            
        # Formatera mobil: 07X-XXX XX XX
        if p.startswith('07') and len(p) == 10:
            return f"{p[:3]}-{p[3:6]} {p[6:8]} {p[8:]}"
        elif p.startswith('07') and len(p) == 9:
            return f"{p[:3]}-{p[3:5]} {p[5:7]} {p[7:]}"
            
        # Formatera fasta telefonnummer (t.ex. Stockholm, Göteborg, Malmö)
        if p.startswith('08') and len(p) == 9:
            return f"{p[:2]}-{p[2:5]} {p[5:7]} {p[7:]}"
        elif p.startswith('031') and len(p) == 9:
            return f"{p[:3]}-{p[3:6]} {p[6:8]} {p[8:]}"
        elif p.startswith('040') and len(p) == 9:
            return f"{p[:3]}-{p[3:6]} {p[6:8]} {p[8:]}"
            
        # Standard fallback för andra riktnummer
        if len(p) == 9:
            return f"{p[:3]}-{p[3:6]} {p[6:8]} {p[8:]}"
        elif len(p) == 10:
            return f"{p[:4]}-{p[4:7]} {p[7:]}"
            
        return phone_str

    def _search_hitta(self, name):
        """Söker efter telefonnummer på Hitta.se."""
        try:
            search_name = self._normalize_name(name)
            q_enc = urllib.parse.quote(search_name)
            url = f"https://www.hitta.se/sök?vad={q_enc}"
            
            resp = self.session.get(url, headers=self.headers, timeout=12)
            if resp.status_code != 200:
                return None
                
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Sök efter nummer direkt i sökresultatet
            text = soup.get_text()
            phones = re.findall(r'07\d[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}|0\d[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2,3}', text)
            valid_phones = []
            for p in phones:
                cp = self._clean_phone(p)
                if cp and cp not in valid_phones:
                    valid_phones.append(cp)
            
            if valid_phones:
                return ", ".join(valid_phones[:2])
                
            # Om inget direktnummer hittas, gå till första personprofilen
            links = [l.get('href') for l in soup.select('a[href*="/person/"]') if l.get('href')]
            if links:
                href = links[0]
                if not href.startswith('http'):
                    href = "https://www.hitta.se" + href
                
                time.sleep(random.uniform(0.5, 1.0))
                p_resp = self.session.get(href, headers=self.headers, timeout=12)
                if p_resp.status_code == 200:
                    p_soup = BeautifulSoup(p_resp.content, "html.parser")
                    p_text = p_soup.get_text()
                    p_phones = re.findall(r'07\d[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}|0\d[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2,3}', p_text)
                    p_valid = []
                    for p in p_phones:
                        cp = self._clean_phone(p)
                        if cp and cp not in p_valid:
                            p_valid.append(cp)
                    if p_valid:
                        return ", ".join(p_valid[:2])
            return None
        except Exception:
            return None

    def find_phone_number(self, person_id, name):
        """Hittar telefonnummer till en person."""
        # Rensa och validera namnet
        name_clean = name.strip()
        if not name_clean:
            return "Ej hittat"
            
        time.sleep(random.uniform(0.3, 0.6))
        
        # Sök på hitta.se
        result = self._search_hitta(name_clean)
        if result:
            return result
            
        return "Ej hittat"
