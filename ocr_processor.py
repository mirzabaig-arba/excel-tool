import easyocr
import pandas as pd
import numpy as np
from PIL import Image
import cv2
import re

class OCRProcessor:
    def __init__(self):
        # Initialize EasyOCR with Swedish and English
        self.reader = easyocr.Reader(['sv', 'en'])
        self.columns = [
            "Pers/Org nr", "Namn, Postadress", "VP", 
            "Innehav per VP", "Summa Innehav", "Innehav %", 
            "Summa Röster", "Röster %"
        ]

    def process_image(self, image_input):
        """
        Processes the image and returns a DataFrame.
        """
        img_np = np.array(image_input)
        if len(img_np.shape) == 3 and img_np.shape[2] == 3:
            pass # Already RGB
        else:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)

        # 1. OCR
        results = self.reader.readtext(img_np)
        
        # 2. Group into Rows
        data = []
        for (bbox, text, prob) in results:
            center_x = sum([p[0] for p in bbox]) / 4
            center_y = sum([p[1] for p in bbox]) / 4
            h = max([p[1] for p in bbox]) - min([p[1] for p in bbox])
            data.append({'text': text, 'x': center_x, 'y': center_y, 'h': h})

        if not data:
            return pd.DataFrame(columns=self.columns)

        # Sort by Y
        df_raw = pd.DataFrame(data).sort_values('y')
        
        # 3. Geometric Grouping into Rows
        rows = []
        if not df_raw.empty:
            current_row = [df_raw.iloc[0].to_dict()]
            for i in range(1, len(df_raw)):
                item = df_raw.iloc[i].to_dict()
                if item['y'] - current_row[-1]['y'] > item['h'] * 0.8:
                    rows.append(current_row)
                    current_row = [item]
                else:
                    current_row.append(item)
            rows.append(current_row)

        # 4. Identify Columns
        width = img_np.shape[1]
        processed_rows = []
        for row in rows:
            row_text_all = " ".join([item['text'] for item in row]).lower()
            # Skip header rows
            if "pers/org" in row_text_all or "namn" in row_text_all:
                continue
            
            row_data = {col: [] for col in self.columns}
            for item in row:
                x_rel = item['x'] / width
                # Approximate column X-ranges for this document type
                if x_rel < 0.18: index = 0
                elif x_rel < 0.45: index = 1
                elif x_rel < 0.53: index = 2
                elif x_rel < 0.63: index = 3
                elif x_rel < 0.72: index = 4
                elif x_rel < 0.80: index = 5
                elif x_rel < 0.90: index = 6
                else: index = 7
                row_data[self.columns[index]].append(item['text'])
            
            processed_rows.append({k: " ".join(v) for k, v in row_data.items()})

        # 5. Merge Multi-line rows
        final_table = []
        for r in processed_rows:
            # If "Pers/Org nr" is missing digits, it's likely a second line of the address above
            if not re.search(r'\d', r[self.columns[0]]) and final_table:
                for col in self.columns:
                    if r[col].strip():
                        final_table[-1][col] += " " + r[col]
            else:
                final_table.append(r)

        return pd.DataFrame(final_table)

    def clean_data(self, df):
        """ Cleans the extracted data (removes 'Förvaltarreg', etc.) """
        if df.empty: return df
        def clean_pn(val):
            m = re.search(r'(\d{6}-\d{4})', val)
            return m.group(1) if m else val
        df[self.columns[0]] = df[self.columns[0]].apply(clean_pn)
        return df
