"""Configure SSL certificates for EasyOCR model downloads on Windows."""
import os
import ssl
import urllib.request


def ensure_ssl_for_downloads(allow_insecure_fallback=False):
    """
    Point urllib (used by EasyOCR) at a trusted CA bundle.
    On some Windows/corporate PCs Python cannot verify HTTPS otherwise.
    """
    cafile = None
    try:
        import certifi

        cafile = certifi.where()
        os.environ["SSL_CERT_FILE"] = cafile
        os.environ["REQUESTS_CA_BUNDLE"] = cafile
    except ImportError:
        pass

    if cafile and os.path.isfile(cafile):
        context = ssl.create_default_context(cafile=cafile)
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
        urllib.request.install_opener(opener)
        return "certifi"

    if allow_insecure_fallback:
        ssl._create_default_https_context = ssl._create_unverified_context
        return "insecure"

    return "default"
