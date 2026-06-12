import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from ocr_processor import OCRProcessor
from lookup_service import LookupService
from PIL import Image
import io
import traceback
import gc
import warnings

warnings.filterwarnings("ignore", message=".*pin_memory.*")

MAX_IMAGES = 5

st.set_page_config(
    page_title="Aktieägarnas Telefonsökare",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 760px; }
    .app-header {
        text-align: center; margin-bottom: 1.5rem;
        border-bottom: 1px solid #e5e7eb; padding-bottom: 1.2rem;
    }
    .app-header h1 {
        font-size: 1.75rem; font-weight: 600; color: #1f2937; margin: 0;
    }
    .app-header p { color: #6b7280; margin: 0.4rem 0 0; font-size: 1rem; }
    .step-row {
        display: flex; align-items: flex-start; gap: 0.75rem;
        padding: 0.65rem 0; border-bottom: 1px solid #f3f4f6;
        font-size: 0.98rem; color: #374151;
    }
    .step-badge {
        background: #e8f5e9; color: #2e7d32; font-weight: 600;
        border-radius: 50%; width: 1.6rem; height: 1.6rem;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0; font-size: 0.85rem;
    }
    .tip-panel {
        background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
        padding: 0.85rem 1rem; color: #4b5563; font-size: 0.9rem;
        margin: 1rem 0 1.5rem;
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #2e7d32 !important;
        border-color: #2e7d32 !important;
        color: #ffffff !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        padding: 0.7rem 1.5rem !important;
        border-radius: 6px !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #1b5e20 !important;
        border-color: #1b5e20 !important;
        color: #ffffff !important;
    }
    div[data-testid="stDownloadButton"] button {
        background-color: #1b5e20 !important;
        border-color: #1b5e20 !important;
        color: #ffffff !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        padding: 0.7rem 1.5rem !important;
        border-radius: 6px !important;
    }
    .thumb-caption { font-size: 0.8rem; color: #6b7280; text-align: center; margin-top: 0.25rem; }
    .thumb-wrap { text-align: center; margin-bottom: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-header">
        <h1>Aktieägarnas Telefonsökare</h1>
        <p>Skanna aktieägarlistor och hämta telefonnummer till Excel</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="step-row"><div class="step-badge">1</div><div>Välj upp till 5 foton av aktieägarlistan</div></div>
    <div class="step-row"><div class="step-badge">2</div><div>Klicka <b>Starta sökning</b></div></div>
    <div class="step-row"><div class="step-badge">3</div><div>Ladda ner Excel-filen när bearbetningen är klar</div></div>
    <div class="tip-panel">
        <b>För bästa resultat:</b> Fotografera rakt ovanifrån, med bra ljus.
        Hela sidan ska synas, inklusive personnummer-kolumnen till vänster.
        Klicka på ett foto för att förstora det.
    </div>
    """,
    unsafe_allow_html=True,
)

if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "preview_idx" not in st.session_state:
    st.session_state.preview_idx = None


@st.cache_resource
def load_tools():
    return OCRProcessor(), LookupService()


@st.dialog("Förhandsvisning", width="large")
def preview_dialog(image, title):
    st.image(image, width="stretch")
    st.caption(title)


try:
    ocr, lookup = load_tools()
except Exception as e:
    st.error(f"Kunde inte starta programmet: {e}")
    st.stop()

show_results = st.session_state.results_df is not None

if show_results:
    if st.button("Börja om", width="stretch"):
        st.session_state.results_df = None
        st.session_state.preview_idx = None
        st.rerun()

if show_results:
    df = st.session_state.results_df
    found = sum(
        1 for p in df["Telefonnummer"]
        if p and not str(p).startswith("Ej hittat")
    )
    st.success(f"Senaste sökning: {found} av {len(df)} telefonnummer hittades.")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    st.download_button(
        label="Ladda ner Excel-fil",
        data=output.getvalue(),
        file_name="Aktieagare_Telefonnummer.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    with st.expander("Förhandsgranska resultat"):
        st.dataframe(df, width="stretch", hide_index=True)

    st.divider()

else:
    files = st.file_uploader(
        "Välj foton (max 5)",
        type=["jpg", "png", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

if not show_results and files:
    if len(files) > MAX_IMAGES:
        st.warning(f"Max {MAX_IMAGES} foton per sökning. Endast de första {MAX_IMAGES} används.")
        files = files[:MAX_IMAGES]

    images, names = [], []
    thumb_cols = st.columns(min(len(files), 4))
    for idx, uploaded in enumerate(files):
        img = Image.open(uploaded).convert("RGB")
        images.append(img)
        names.append(uploaded.name)
        with thumb_cols[idx % len(thumb_cols)]:
            st.image(img, width=130)
            if st.button(f"Foto {idx + 1}", key=f"preview_btn_{idx}", width="stretch"):
                preview_dialog(img, names[idx])
            st.caption(names[idx][:28])

    st.caption(f"{len(files)} foto valda (max {MAX_IMAGES}).")

    if st.button("Starta sökning", type="primary", width="stretch"):
        progress = st.progress(0, text="Initierar...")
        status = st.empty()

        try:
            all_dfs = []
            for i, (img, name) in enumerate(zip(images, names)):
                status.info(
                    f"Läser foto {i + 1} av {len(names)} (OCR kan ta 1–2 min per foto)..."
                )
                df = ocr.process_image(img)
                if df.empty:
                    status.warning(
                        f"Inga personer hittades i foto {i + 1} ({name}). "
                        "Kontrollera att hela listan syns."
                    )
                if not df.empty:
                    df.insert(0, "Källa", name)
                    all_dfs.append(df)
                progress.progress((i + 1) / (len(names) + 2))

            if not all_dfs:
                st.error("Inga personer hittades. Kontrollera bildkvalitet och att hela listan syns.")
            else:
                df = pd.concat(all_dfs, ignore_index=True)
                gc.collect()

                total = len(df)
                status.info(
                    f"Hittade {total} personer. Söker via Hitta.se och Merinfo.se..."
                )
                phones = [None] * total
                rows = list(df.iterrows())

                def lookup_row(item):
                    idx, row = item
                    return idx, lookup.find_phone_number(
                        str(row.get("Pers/Org nr", "")),
                        str(row.get("Namn, Postadress", "")),
                    )

                completed = 0
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = [pool.submit(lookup_row, item) for item in rows]
                    for future in as_completed(futures):
                        idx, phone = future.result()
                        phones[idx] = phone
                        completed += 1
                        progress.progress(
                            (len(names) + 1 + completed) / (len(names) + 2 + total),
                            text=f"Telefonnummer {completed} av {total}",
                        )

                df["Telefonnummer"] = phones
                st.session_state.results_df = df

                found = sum(
                    1 for p in phones if p and not str(p).startswith("Ej hittat")
                )
                progress.progress(1.0, text="Klar")
                status.success(f"Klar. {found} av {total} telefonnummer hittades.")
                st.rerun()

        except Exception as e:
            st.error("Ett fel uppstod. Försök igen.")
            with st.expander("Felinformation"):
                st.code(traceback.format_exc())

elif not show_results:
    st.caption("Välj foton ovan för att börja.")
