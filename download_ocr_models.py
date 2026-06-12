"""Pre-download EasyOCR models during setup (avoids SSL errors in the app)."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from ssl_fix import ensure_ssl_for_downloads


def main():
    print("Konfigurerar SSL-certifikat...")
    mode = ensure_ssl_for_downloads(allow_insecure_fallback=False)
    print(f"SSL-lage: {mode}")

    print("Laddar ner EasyOCR-modeller (kan ta flera minuter forsta gangen)...")
    try:
        import easyocr

        easyocr.Reader(["sv", "en"], gpu=False, verbose=True)
    except Exception as exc:
        err = str(exc)
        if "SSL" in err or "CERTIFICATE" in err:
            print("\nSSL-fel med standardcertifikat. Forsoker igen utan verifiering...")
            ensure_ssl_for_downloads(allow_insecure_fallback=True)
            import easyocr

            easyocr.Reader(["sv", "en"], gpu=False, verbose=True)
        else:
            raise

    print("\nKlart! OCR-modellerna ar nedladdade och sparade lokalt.")


if __name__ == "__main__":
    main()
