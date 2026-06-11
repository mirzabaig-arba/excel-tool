import requests
from bs4 import BeautifulSoup
import time
import random

class LookupService:
    def __init__(self):
        self.session = requests.Session()
        # Modern browser headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"
        }

    def find_phone_number(self, person_id, name):
        """
        Tries to find the phone number for a person on merinfo.se
        """
        try:
            # 1. Clean and format the ID for search (YYYYMMDD-XXXX)
            pid_clean = str(person_id).replace("-", "").strip()
            if not pid_clean:
                return "No ID found"

            if len(pid_clean) == 10:
                # Add century prefix for modern search
                year = int(pid_clean[:2])
                prefix = "20" if year < 25 else "19"
                search_val = prefix + pid_clean
            else:
                search_val = pid_clean
            
            url = f"https://www.merinfo.se/search?q={search_val}"
            resp = self.session.get(url, headers=self.headers, timeout=10)
            
            # 2. Handle search results vs direct profile
            if "search" in resp.url:
                soup = BeautifulSoup(resp.content, "html.parser")
                # Look for the first profile link
                link = soup.select_one("a.link-to-profile")
                if link:
                    time.sleep(random.uniform(0.5, 1.2)) # Be polite to the server
                    profile_url = "https://www.merinfo.se" + link['href']
                    resp = self.session.get(profile_url, headers=self.headers, timeout=10)
            
            # 3. Extract phone numbers from profile page
            soup = BeautifulSoup(resp.content, "html.parser")
            # Look for all links starting with 'tel:'
            phone_links = soup.select('a[href^="tel:"]')
            
            if phone_links:
                phones = []
                for a in phone_links:
                    p = a['href'].replace("tel:", "").strip()
                    if p not in phones:
                        phones.append(p)
                return ", ".join(phones)
            
            return "Not found"
            
        except Exception as e:
            return f"Search Error"
