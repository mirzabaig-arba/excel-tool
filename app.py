import streamlit as st
import pandas as pd
from ocr_processor import OCRProcessor
from lookup_service import LookupService
from PIL import Image
import io
import time
import traceback
import gc

# ============================================================
# Professionell konfiguration
# ============================================================
st.set_page_config(
    page_title="Aktieägarnas Telefonsökare",
    page_icon="🇸🇪",
    layout="centered"
)

# ============================================================
# Språkväxling (Svenska / Engelska)
# ============================================================
LANG = {
    "sv": {
        "title": "🇸🇪 Aktieägarnas Telefonsökare",
        "subtitle": "Hitta telefonnummer till aktieägare automatiskt",
        "instructions": """
### Instruktioner:
1.  **Ladda upp** ett tydligt foto av din aktieägarlista.
2.  **Vänta** medan systemet läser namnen och söker telefonnummer.
3.  **Ladda ner** den färdiga Excel-filen.
""",
        "upload_label": "Steg 1: Ladda upp foto av aktieägarlista",
        "photo_ok": "Foto laddades framgångsrikt",
        "btn_start": "Steg 2: Starta sökning av telefonnummer",
        "processing": "🔍 Bearbetar... detta kan ta en stund.",
        "scanning": "Skannar dokumentet och läser namn...",
        "no_names": "Inga namn hittades. Kontrollera att fotot är tydligt och välbelyst.",
        "found_people": "Hittade {n} personer. Söker nu i telefonkataloger...",
        "checking": "Kontrollerar: {name}",
        "all_done": "✅ Klart!",
        "ready": "Listan är klar! Klicka på knappen nedan för att spara den.",
        "download_btn": "📥 LADDA NER EXCEL-FIL",
        "filename": "Aktieagare_Telefonnummer.xlsx",
        "error_init": "Fel vid initiering av OCR-motor: {e}",
        "error_process": "Ett fel uppstod under bearbetningen: {e}",
        "error_image": "Kunde inte ladda bilden: {e}",
        "error_detail": "Visa detaljerat fel",
        "phone_col": "Telefonnummer",
        "lang_label": "Språk / Language",
        "engine_info": "⚡ Motor: Tesseract OCR (ultralätt, inga minnesproblem)",
        "sources_info": "📞 Källor: merinfo.se, hitta.se, eniro.se",
    },
    "en": {
        "title": "🇸🇪 Shareholder Phone Finder",
        "subtitle": "Automatically find phone numbers for shareholders",
        "instructions": """
### Instructions:
1.  **Upload** a clear photo of your shareholder list.
2.  **Wait** while the system reads names and finds phone numbers.
3.  **Download** the finished Excel file.
""",
        "upload_label": "Step 1: Upload photo of shareholder list",
        "photo_ok": "Photo loaded successfully",
        "btn_start": "Step 2: Start Finding Numbers",
        "processing": "🔍 Processing... this may take a minute.",
        "scanning": "Scanning document and reading names...",
        "no_names": "No names found. Please check if the photo is clear and well-lit.",
        "found_people": "Found {n} people. Now checking phone directories...",
        "checking": "Checking: {name}",
        "all_done": "✅ All finished!",
        "ready": "The list is ready! Click the button below to save it.",
        "download_btn": "📥 DOWNLOAD EXCEL SHEET",
        "filename": "Shareholder_Phone_Numbers.xlsx",
        "error_init": "Error initializing OCR engine: {e}",
        "error_process": "An error occurred during processing: {e}",
        "error_image": "Could not load image: {e}",
        "error_detail": "Show detailed error",
        "phone_col": "Phone Number",
        "lang_label": "Språk / Language",
        "engine_info": "⚡ Engine: Tesseract OCR (ultra-light, no memory issues)",
        "sources_info": "📞 Sources: merinfo.se, hitta.se, eniro.se",
    }
}

# Språkval i sidofältet
lang_choice = st.sidebar.selectbox(
    "🌐 Språk / Language",
    options=["Svenska", "English"],
    index=0
)
lang_key = "sv" if lang_choice == "Svenska" else "en"
t = LANG[lang_key]

# ============================================================
# Sidhuvud
# ============================================================
st.title(t["title"])
st.caption(t["subtitle"])
st.markdown(t["instructions"])

# Visa motorinformation
st.sidebar.markdown("---")
st.sidebar.info(t["engine_info"])
st.sidebar.info(t["sources_info"])

# ============================================================
# Initiera verktyg med caching
# ============================================================
@st.cache_resource
def load_tools():
    return OCRProcessor(), LookupService()

try:
    ocr, lookup = load_tools()
except Exception as e:
    st.error(t["error_init"].format(e=e))
    st.stop()

# ============================================================
# Filuppladdning och bearbetning
# ============================================================
file = st.file_uploader(t["upload_label"], type=["jpg", "png", "jpeg"])

if file:
    try:
        # Ladda och konvertera till RGB
        img = Image.open(file).convert("RGB")
        st.image(img, caption=t["photo_ok"], width=300)
        
        if st.button(t["btn_start"], use_container_width=True):
            with st.status(t["processing"], expanded=True) as status:
                try:
                    status.write(t["scanning"])
                    df = ocr.process_image(img)
                    df = ocr.clean_data(df)
                    
                    # Frigör minne efter OCR
                    gc.collect()
                    
                    if df.empty:
                        st.error(t["no_names"])
                    else:
                        status.write(t["found_people"].format(n=len(df)))
                        phones = []
                        bar = st.progress(0)
                        
                        for i, row in df.iterrows():
                            name = str(row.get("Namn, Postadress", "Person"))
                            pn = str(row.get("Pers/Org nr", ""))
                            
                            status.write(t["checking"].format(name=name))
                            phone = lookup.find_phone_number(pn, name)
                            phones.append(phone)
                            
                            bar.progress((i + 1) / len(df))
                        
                        df[t["phone_col"]] = phones
                        status.update(label=t["all_done"], state="complete")
                        
                        # Generera Excel-fil
                        st.success(t["ready"])
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False)
                        
                        st.download_button(
                            label=t["download_btn"],
                            data=output.getvalue(),
                            file_name=t["filename"],
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                        
                        # Visa förhandsgranskning
                        with st.expander("📋 " + ("Förhandsgranskning" if lang_key == "sv" else "Preview")):
                            st.dataframe(df)
                            
                except Exception as e:
                    st.error(t["error_process"].format(e=e))
                    st.expander(t["error_detail"]).code(traceback.format_exc())
                    
    except Exception as e:
        st.error(t["error_image"].format(e=e))
