import pytesseract
import pandas as pd
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import cv2
import re
import os

class OCRProcessor:
    def __init__(self):
        """
        Initierar OCR-processorn med Tesseract (ultralätt, ~0 MB RAM).
        Ersätter EasyOCR (~750 MB RAM) för att fungera på Streamlit Cloud (1 GB gräns).
        """
        # Tesseract konfiguration för svenska + engelska
        # PSM 6 = Antag ett enda enhetligt textblock (bra för tabeller)
        self.tesseract_config = '--oem 3 --psm 6 -l swe+eng'
        self.columns = [
            "Pers/Org nr", "Namn, Postadress", "VP", 
            "Innehav per VP", "Summa Innehav", "Innehav %", 
            "Summa Röster", "Röster %"
        ]

    def _preprocess_image(self, pil_image):
        """
        Förbehandlar bilden för bättre OCR-resultat.
        Steg: Gråskala → Kontrast → Skärpa → Binarisering (Otsu)
        """
        # Konvertera till OpenCV-format
        img_np = np.array(pil_image)
        
        # 1. Konvertera till gråskala
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np
        
        # 2. Skala upp om bilden är liten (Tesseract fungerar bäst med ~300 DPI)
        h, w = gray.shape
        if w < 1500:
            scale = 1500 / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        # 3. Öka kontrasten med CLAHE (adaptiv histogram-utjämning)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 4. Lätt gaussisk oskärpa för att minska brus
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # 5. Otsu-tröskling (automatisk binarisering)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return Image.fromarray(binary)

    def process_image(self, pil_image):
        """
        Bearbetar en PIL-bild och returnerar en DataFrame.
        Använder Tesseract med TSV-output för att få textpositioner.
        """
        # Förbehandla bilden
        processed_img = self._preprocess_image(pil_image)
        
        # Kör Tesseract med TSV-output (ger koordinater för varje ord)
        tsv_data = pytesseract.image_to_data(
            processed_img, 
            config=self.tesseract_config,
            output_type=pytesseract.Output.DATAFRAME
        )
        
        # Filtrera bort tomma/låg-konfidens resultat
        tsv_data = tsv_data.dropna(subset=['text'])
        tsv_data = tsv_data[tsv_data['text'].str.strip() != '']
        tsv_data = tsv_data[tsv_data['conf'] > 20]  # Minst 20% konfidens
        
        if tsv_data.empty:
            return pd.DataFrame(columns=self.columns)
        
        # Beräkna mittpunkter för varje textblock
        tsv_data['center_x'] = tsv_data['left'] + tsv_data['width'] / 2
        tsv_data['center_y'] = tsv_data['top'] + tsv_data['height'] / 2
        
        # Hämta bildens bredd för relativ X-positionering
        img_width = processed_img.width
        
        # Gruppera ord till rader baserat på Y-position (block_num + line_num)
        rows = []
        for (block, par, line), group in tsv_data.groupby(['block_num', 'par_num', 'line_num']):
            row_items = []
            for _, item in group.iterrows():
                row_items.append({
                    'text': str(item['text']).strip(),
                    'x': item['center_x'],
                    'y': item['center_y'],
                    'h': item['height']
                })
            if row_items:
                rows.append(row_items)
        
        # Sortera rader efter Y-position
        rows.sort(key=lambda r: np.mean([item['y'] for item in r]))
        
        # Mappa text till kolumner baserat på relativ X-position
        processed_rows = []
        for row in rows:
            row_text_all = " ".join([item['text'] for item in row]).lower()
            # Ignorera uppenbar rubrikrad
            if "pers/org" in row_text_all or "namn" in row_text_all or "postadress" in row_text_all:
                continue
            
            row_data = {col: [] for col in self.columns}
            for item in row:
                x_rel = item['x'] / img_width
                # Definierade X-intervall för dokumentlayouten
                if x_rel < 0.18: index = 0
                elif x_rel < 0.45: index = 1
                elif x_rel < 0.53: index = 2
                elif x_rel < 0.63: index = 3
                elif x_rel < 0.72: index = 4
                elif x_rel < 0.80: index = 5
                elif x_rel < 0.90: index = 6
                else: index = 7
                row_data[self.columns[index]].append(item['text'])
            
            processed_rows.append({k: " ".join(v).strip() for k, v in row_data.items()})

        # Sammanfoga flerraders poster
        # I aktieägarlistor tar namn/adress ofta 2-3 rader medan personnumret bara finns på första raden
        final_table = []
        for r in processed_rows:
            has_id_digit = any(char.isdigit() for char in r[self.columns[0]])
            if not has_id_digit and final_table:
                for col in self.columns:
                    if r[col]:
                        final_table[-1][col] += " " + r[col]
            else:
                final_table.append(r)

        return pd.DataFrame(final_table)

    def clean_data(self, df):
        """Rensar extraherade personnummer (extraherar bara 6+4-format)"""
        if df.empty: return df
        def clean_pn(val):
            # Matchar format som 600803-0352 eller 19600803-0352
            m = re.search(r'(\d{6,8}-\d{4})', str(val))
            if m:
                result = m.group(1)
                # Normalisera till 6-siffror + bindestreck + 4 (ta bort sekel-prefix)
                if len(result) > 11:  # 12-siffrigt: 19600803-0352
                    result = result[2:]  # → 600803-0352
                return result
            return val
        
        if self.columns[0] in df.columns:
            df[self.columns[0]] = df[self.columns[0]].apply(clean_pn)
        return df
