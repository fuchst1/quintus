from __future__ import annotations

import base64
import io


class QrCodeService:
    _data_uri_cache: dict[str, str] = {}

    @classmethod
    def qr_data_uri(cls, *, portal_url: str) -> str:
        normalized_url = str(portal_url or "").strip()
        if not normalized_url:
            return ""
        cached = cls._data_uri_cache.get(normalized_url)
        if cached is not None:
            return cached

        data_uri = cls._build_svg_data_uri(normalized_url)
        cls._data_uri_cache[normalized_url] = data_uri
        return data_uri

    @staticmethod
    def _build_svg_data_uri(url: str) -> str:
        try:
            import qrcode
            from qrcode.image.svg import SvgPathImage
        except Exception:
            return ""

        try:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            image = qr.make_image(image_factory=SvgPathImage)
            buffer = io.BytesIO()
            image.save(buffer)
            encoded_svg = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/svg+xml;base64,{encoded_svg}"
        except Exception:
            return ""
