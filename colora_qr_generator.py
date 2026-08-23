#!/usr/bin/env python3
"""Generate authenticated, encrypted COLORA QR codes.

The AES key and P-256 private key are created once and persisted.  Back them up:
losing either key makes existing codes unusable.  The AES key must be provisioned
to trusted COLORA scanner builds; it must never be published with an ordinary web
site if confidentiality is required.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageOps
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styledpil import StyledPilImage

PREFIX = "colora-secure://v1."
VERSION = b"\x01"
NONCE_SIZE = 12
RAW_SIGNATURE_SIZE = 64
DEFAULT_NAVY = (8, 39, 86)
LOGO_SIDE_RATIO = 0.20


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_keys(key_directory: str | Path = "colora_keys") -> tuple[bytes, ec.EllipticCurvePrivateKey]:
    """Load the scanner keys, creating them atomically on first use."""
    directory = Path(key_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    aes_path, signing_path = directory / "aes-256.key", directory / "ecdsa-p256-private.pem"

    if aes_path.exists() != signing_path.exists():
        raise RuntimeError("Incomplete COLORA key set; restore both key files from backup")
    if aes_path.exists():
        aes_key = aes_path.read_bytes()
        private_key = serialization.load_pem_private_key(signing_path.read_bytes(), password=None)
        if len(aes_key) != 32 or not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(private_key.curve, ec.SECP256R1):
            raise ValueError("The stored COLORA keys are not AES-256 and ECDSA P-256 keys")
        return aes_key, private_key

    aes_key = AESGCM.generate_key(bit_length=256)
    private_key = ec.generate_private_key(ec.SECP256R1())
    _exclusive_write(aes_path, aes_key)
    _exclusive_write(
        signing_path,
        private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    )
    return aes_key, private_key


def _exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def scanner_configuration(aes_key: bytes, private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    """Return the values consumed by ``ColoraScanner`` (treat the AES value as secret)."""
    numbers = private_key.public_key().public_numbers()
    return {
        "aesKeyBase64Url": _b64url(aes_key),
        "publicKeyJwk": {
            "kty": "EC", "crv": "P-256", "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")), "ext": True,
        },
    }


def secure_url(url: str, aes_key: bytes, private_key: ec.EllipticCurvePrivateKey) -> str:
    """Encrypt and sign an HTTP(S) URL and return its COLORA URI."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must be an absolute HTTP(S) URL without embedded credentials")
    nonce = os.urandom(NONCE_SIZE)
    encrypted = AESGCM(aes_key).encrypt(nonce, url.encode("utf-8"), PREFIX.encode("ascii"))
    authenticated_payload = VERSION + nonce + encrypted
    der_signature = private_key.sign(authenticated_payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return PREFIX + base64.b85encode(authenticated_payload + raw_signature).decode("ascii")


def _logo_icon(logo_path: str | Path) -> tuple[Image.Image, tuple[int, int, int]]:
    """Extract the upper, centred icon and its dominant ink colour from a logo."""
    with Image.open(logo_path) as source:
        rgba = source.convert("RGBA")
        # COLORA artwork is supplied on white, but compositing also makes this work
        # predictably when a designer exports it with transparency.
        rgb = Image.new("RGB", rgba.size, "white")
        rgb.paste(rgba, mask=rgba.getchannel("A"))

    pixels = rgb.load()
    foreground = Image.new("1", rgb.size)
    mask_pixels = foreground.load()
    occupied_rows: list[int] = []
    colours: dict[tuple[int, int, int], int] = {}
    for y in range(rgb.height):
        row_has_ink = False
        for x in range(rgb.width):
            colour = pixels[x, y]
            # Include antialiased edges, while excluding the white/near-white field.
            is_ink = max(colour) < 245 and sum(255 - channel for channel in colour) > 45
            mask_pixels[x, y] = is_ink
            if is_ink:
                row_has_ink = True
                if max(colour) < 180:
                    colours[colour] = colours.get(colour, 0) + 1
        if row_has_ink:
            occupied_rows.append(y)

    if not occupied_rows:
        raise ValueError(f"Logo contains no visible icon: {logo_path}")

    # The supplied lock-up places the gem in the first substantial horizontal
    # band and the COLORA wordmark in the next. A blank row cleanly separates them.
    bands: list[tuple[int, int]] = []
    start = previous = occupied_rows[0]
    for row in occupied_rows[1:]:
        if row > previous + 1:
            bands.append((start, previous))
            start = row
        previous = row
    bands.append((start, previous))
    substantial = [band for band in bands if band[1] - band[0] >= max(4, rgb.height // 50)]
    icon_band = substantial[0] if substantial else bands[0]
    band_mask = foreground.crop((0, icon_band[0], rgb.width, icon_band[1] + 1))
    bbox = band_mask.getbbox()
    if bbox is None:
        raise ValueError(f"Could not isolate an icon in logo: {logo_path}")
    bbox = (bbox[0], bbox[1] + icon_band[0], bbox[2], bbox[3] + icon_band[0])

    icon = rgb.crop(bbox).convert("RGBA")
    icon_mask = foreground.crop(bbox)
    icon.putalpha(icon_mask.point(lambda value: 255 if value else 0))
    navy = max(colours, key=colours.get) if colours else DEFAULT_NAVY
    return icon, navy


def _embed_icon(qr_image: Image.Image, icon: Image.Image) -> Image.Image:
    """Place an icon on a white, rounded quiet patch at the QR's exact centre."""
    result = qr_image.convert("RGBA")
    patch_side = max(1, round(min(result.size) * LOGO_SIDE_RATIO))
    padding = max(2, patch_side // 10)
    fitted = ImageOps.contain(icon, (patch_side - 2 * padding, patch_side - 2 * padding), Image.Resampling.LANCZOS)
    patch = Image.new("RGBA", (patch_side, patch_side), (255, 255, 255, 0))
    draw = ImageDraw.Draw(patch)
    draw.rounded_rectangle((0, 0, patch_side - 1, patch_side - 1), radius=patch_side // 7, fill="white")
    patch.alpha_composite(fitted, ((patch_side - fitted.width) // 2, (patch_side - fitted.height) // 2))
    result.alpha_composite(patch, ((result.width - patch_side) // 2, (result.height - patch_side) // 2))
    return result.convert("RGB")


def url_to_qr(
    url: str,
    output: str | Path,
    key_directory: str | Path = "colora_keys",
    logo_path: str | Path | None = None,
) -> str:
    """Create a level-H QR PNG and return the encoded proprietary URI."""
    aes_key, private_key = generate_keys(key_directory)
    uri = secure_url(url, aes_key, private_key)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    navy = DEFAULT_NAVY
    icon = None
    if logo_path is not None:
        icon, navy = _logo_icon(logo_path)
    image = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(radius_ratio=1),
        eye_drawer=RoundedModuleDrawer(radius_ratio=0.55),
        color_mask=SolidFillColorMask(back_color=(255, 255, 255), front_color=navy),
    )
    if icon is not None:
        image = _embed_icon(image.get_image(), icon)
    image.save(output)
    return uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an encrypted and signed COLORA QR code")
    parser.add_argument("url", help="absolute HTTP(S) destination")
    parser.add_argument("-o", "--output", default="colora-secure-qr.png")
    parser.add_argument("--key-directory", default="colora_keys")
    parser.add_argument("--logo", type=Path, help='optional path to the "COLORA-16.png" logo')
    parser.add_argument("--print-scanner-config", action="store_true", help="print scanner key props (sensitive)")
    args = parser.parse_args()
    uri = url_to_qr(args.url, args.output, args.key_directory, args.logo)
    print(f"Created {args.output}\n{uri}")
    if args.print_scanner_config:
        print(json.dumps(scanner_configuration(*generate_keys(args.key_directory)), indent=2))


if __name__ == "__main__":
    main()
