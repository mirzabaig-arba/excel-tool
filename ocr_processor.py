import easyocr
import pandas as pd
import numpy as np
from PIL import Image
import cv2
import re
import os

class OCRProcessor:
    def __init__(self):
        # Initialize EasyOCR with Swedish and English
        # We don't specify gpu=True here to allow it to run on CPU if needed (common in free cloud)
        self.reader = easyocr.Reader(['sv', 'en'])
        self.columns = [
            "Pers/Org nr", "Namn, Postadress", "VP", 
            "Innehav per VP", "Summa Innehav", "Innehav %", 
            "Summa Röster", "Röster %"
        ]

    def process_image(self, pil_image):
        """
        Processes a PIL Image and returns a DataFrame.
        """
        # Convert PIL to format EasyOCR/OpenCV likes
        img_np = np.array(pil_image)
        
        # 1. OCR - returns list of ([[x,y],...], text, confidence)
        results = self.reader.readtext(img_np)
        
        # 2. Extract and organize text blocks with coordinates
        data = []
        for (bbox, text, prob) in results:
            # bbox is [top_left, top_right, bottom_right, bottom_left]
            coords = np.array(bbox)
            center_x = np.mean(coords[:, 0])
            center_y = np.mean(coords[:, 1])
            h = np.max(coords[:, 1]) - np.min(coords[:, 1])
            data.append({'text': text, 'x': center_x, 'y': center_y, 'h': h})

        if not data:
            return pd.DataFrame(columns=self.columns)

        # Sort by vertical position (Y)
        df_raw = pd.DataFrame(data).sort_values('y')
        
        # 3. Geometric Grouping into Rows
        # We group items where Y difference is small
        rows = []
        if not df_raw.empty:
            current_row = [df_raw.iloc[0].to_dict()]
            for i in range(1, len(df_raw)):
                item = df_raw.iloc[i].to_dict()
                # If the vertical jump is more than 80% of current text height, it's a new line
                if item['y'] - current_row[-1]['y'] > item['h'] * 0.8:
                    rows.append(current_row)
                    current_row = [item]
                else:
                    current_row.append(item)
            rows.append(current_row)

        # 4. Map text to columns based on relative X position
        width = pil_image.width
        processed_rows = []
        for row in rows:
            row_text_all = " ".join([item['text'] for item in row]).lower()
            # Ignore obvious header rows
            if "pers/org" in row_text_all or "namn" in row_text_all:
                continue
            
            row_data = {col: [] for col in self.columns}
            for item in row:
                x_rel = item['x'] / width
                # Defined X-ranges for your specific document layout
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

        # 5. Merge Multi-line entries
        # In lists like yours, name/address often take 2-3 lines while the ID is only on the first line
        final_table = []
        for r in processed_rows:
            # If "Pers/Org nr" doesn't have a number, it's a continuation of the previous person
            has_id_digit = any(char.isdigit() for char in r[self.columns[0]])
            if not has_id_digit and final_table:
                for col in self.columns:
                    if r[col]:
                        final_table[-1][col] += " " + r[col]
            else:
                final_table.append(r)

        return pd.DataFrame(final_table)

    def clean_data(self, df):
        """ Cleans extracted IDs (extracts only the 6+4 format) """
        if df.empty: return df
        def clean_pn(val):
            # Matches formats like 600803-0352
            m = re.search(r'(\d{6}-\d{4})', str(val))
            return m.group(1) if m else val
        
        if self.columns[0] in df.columns:
            df[self.columns[0]] = df[self.columns[0]].apply(clean_pn)
        return df
