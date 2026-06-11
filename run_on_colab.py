import os

# --- STEG 1: Beroenden ---
print("Installerar beroenden... detta tar 1-2 minuter.")
os.system("apt-get install -y tesseract-ocr tesseract-ocr-swe > /dev/null 2>&1")
os.system("pip install streamlit pytesseract beautifulsoup4 requests openpyxl --quiet")
os.system("npm install -g localtunnel --quiet 2>/dev/null")

# --- STEG 2: Starta Streamlit ---
print("\n--- STARTAR APPEN ---")
print("1. Klicka på länken som visas nedan (t.ex. https://...localtunnel.me)")
print("2. När du ombeds ange en 'Endpoint IP', använd IP-adressen som visas här:")
os.system("curl ipv4.icanhazip.com")
print("\n---------------------\n")

os.system("streamlit run app.py & npx localtunnel --port 8501")
