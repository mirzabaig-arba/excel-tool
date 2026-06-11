import streamlit as st
import pandas as pd
from ocr_processor import OCRProcessor
from lookup_service import LookupService
from PIL import Image
import io
import time

# Professional configuration
st.set_page_config(page_title="Shareholder Phone Finder", page_icon="🇸🇪", layout="centered")

st.title("🇸🇪 Shareholder Phone Finder")
st.markdown("""
### Instructions:
1.  **Upload** a clear photo of your shareholder list.
2.  **Wait** while the computer reads the names and finds their phone numbers.
3.  **Download** the finished Excel file.
""")

@st.cache_resource
def load_tools():
    # Cache tools to avoid reloading EasyOCR models on every click
    return OCRProcessor(), LookupService()

ocr, lookup = load_tools()

file = st.file_uploader("Step 1: Upload photo of shareholder list", type=["jpg", "png", "jpeg"])

if file:
    img = Image.open(file)
    st.image(img, caption="Photo loaded successfully", width=300)
    
    if st.button("Step 2: Start Finding Numbers", use_container_width=True):
        with st.status("🔍 Processing... this may take a minute.", expanded=True) as status:
            status.write("Scanning document and reading names...")
            df = ocr.process_image(img)
            df = ocr.clean_data(df)
            
            if df.empty:
                st.error("No names found. Please check if the photo is clear and well-lit.")
            else:
                status.write(f"Found {len(df)} people. Now checking phone directories...")
                phones = []
                bar = st.progress(0)
                for i, row in df.iterrows():
                    name = row.get("Namn, Postadress", "Person")
                    phone = lookup.find_phone_number(row.get("Pers/Org nr", ""), name)
                    phones.append(phone)
                    bar.progress((i + 1) / len(df))
                
                df["Phone Number"] = phones
                status.update(label="✅ All finished!", state="complete")
                
                # Excel Download Generation
                st.success("The list is ready! Click the button below to save it.")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 DOWNLOAD EXCEL SHEET",
                    data=output.getvalue(),
                    file_name="Shareholder_Phone_Numbers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
