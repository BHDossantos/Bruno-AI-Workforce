"""Per-user PNG signatures and email-safe MIME composition; no remote assets."""
from dataclasses import dataclass
from email.message import EmailMessage
from hashlib import sha256
from html import escape
import struct
import zlib

MAX_PNG_BYTES = 2_000_000


def validate_png(data: bytes) -> tuple[int, int]:
    """Validate bounded, non-interlaced 8-bit RGB/RGBA PNGs without external IO."""
    if len(data) > MAX_PNG_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Upload a PNG no larger than 2 MB")
    offset, header, compressed, ended = 8, None, [], False
    while offset + 12 <= len(data):
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("Truncated PNG")
        payload = data[offset + 8:end - 4]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("Invalid PNG checksum")
        if header is None and kind != b"IHDR":
            raise ValueError("Missing PNG header")
        if kind == b"IHDR":
            if header is not None or size != 13:
                raise ValueError("Invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (1 <= width <= 4000 and 1 <= height <= 2000) or depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)):
                raise ValueError("Use a non-interlaced 8-bit RGB/RGBA PNG up to 4000 by 2000")
            header = (width, height, 3 if color == 2 else 4)
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            if size or end != len(data):
                raise ValueError("Invalid PNG ending")
            ended = True
            break
        offset = end
    if not header or not compressed or not ended:
        raise ValueError("Incomplete PNG")
    width, height, channels = header
    expected = height * (1 + width * channels)
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError("Invalid PNG image data") from exc
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Invalid PNG image size")
    if any(pixels[i] > 4 for i in range(0, expected, 1 + width * channels)):
        raise ValueError("Invalid PNG row filter")
    return width, height


@dataclass(frozen=True)
class Signature:
    png: bytes
    plain_text: str

    @property
    def digest(self):
        return sha256(self.png + b"\0" + self.plain_text.encode()).hexdigest()


def compose(body: str, signature: Signature | None = None) -> EmailMessage:
    message = EmailMessage()
    if signature is None:
        message.set_content(body)
        return message
    validate_png(signature.png)
    message.set_content(body + "\n\n" + signature.plain_text)
    cid = "signature-" + signature.digest + "@workforce.invalid"
    html = ('<div style="font-family:Arial,sans-serif;font-size:14px;white-space:pre-wrap">' + escape(body)
            + '</div><br><img src="cid:' + cid + '" width="600" style="max-width:100%;height:auto" alt="'
            + escape(signature.plain_text, quote=True) + '">')
    message.add_alternative(html, subtype="html")
    message.get_payload()[-1].add_related(signature.png, maintype="image", subtype="png",
        cid="<" + cid + ">", disposition="inline", filename="signature.png")
    return message
