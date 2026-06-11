import requests
from bs4 import BeautifulSoup
import time
import random

class LookupService:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def find_phone_number(self, person_id, name):
        """
        Tries to find the phone number for a person on merinfo.se
        """
        try:
            # Format ID for search
            pid_clean = person_id.replace("-", "")
            if len(pid_clean) == 10:
                year = int(pid_clean[:2])
                pid_clean = ("20" if year < 25 else "19") + pid_clean
            
            url = f"https://www.merinfo.se/search?q={pid_clean}"
            resp = self.session.get(url, headers=self.headers, timeout=10)
            
            if "search" in resp.url:
                soup = BeautifulSoup(resp.content, "html.parser")
                link = soup.select_one("a.link-to-profile")
                if link:
                    time.sleep(random.uniform(0.5, 1.0))
                    resp = self.session.get("https://www.merinfo.se" + link['href'], headers=self.headers)
            
            soup = BeautifulSoup(resp.content, "html.parser")
            # Robust selector for phone number links
            phones = [a['href'].replace("tel:", "") for a in soup.select('a[href^="tel:"]')]
            
            # Remove duplicates and join
            if phones:
                return ", ".join(list(dict.fromkeys(phones)))
            return "Not found"
        except Exception:
            return "Lookup Error"
