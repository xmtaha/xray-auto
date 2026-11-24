"""Pure-Python RFC 7748 X25519 keypair generator compatible with Xray-core.

Uses /usr/local/bin/xray x25519 when available on the host, and falls back
to a zero-dependency pure-Python Curve25519 implementation otherwise.
"""

import base64
import os
import secrets
import subprocess

_P = (1 << 255) - 19
_A24 = 121665
_BASE_U = 9


def _cswap(swap: int, x2: int, x3: int) -> tuple[int, int]:
    dummy = swap * (x2 ^ x3)
    return x2 ^ dummy, x3 ^ dummy


def _x25519_scalar_mult(k_bytes: bytes, u_bytes: bytes) -> bytes:
    k_list = list(k_bytes)
    k_list[0] &= 248
    k_list[31] &= 127
    k_list[31] |= 64
    k = int.from_bytes(bytes(k_list), "little")

    u_list = list(u_bytes)
    u_list[31] &= 127
    u = int.from_bytes(bytes(u_list), "little") % _P

    x_1 = u
    x_2 = 1
    z_2 = 0
    x_3 = u
    z_3 = 1
    swap = 0

    for t in range(254, -1, -1):
        k_t = (k >> t) & 1
        swap ^= k_t
        x_2, x_3 = _cswap(swap, x_2, x_3)
        z_2, z_3 = _cswap(swap, z_2, z_3)
        swap = k_t

        a = (x_2 + z_2) % _P
        aa = (a * a) % _P
        b = (x_2 - z_2) % _P
        bb = (b * b) % _P
        e = (aa - bb) % _P
        c = (x_3 + z_3) % _P
        d = (x_3 - z_3) % _P
        da = (d * a) % _P
        cb = (c * b) % _P

        x_3 = pow((da + cb) % _P, 2, _P)
        z_3 = (x_1 * pow((da - cb) % _P, 2, _P)) % _P
        x_2 = (aa * bb) % _P
        z_2 = (e * (aa + _A24 * e)) % _P

    x_2, x_3 = _cswap(swap, x_2, x_3)
    z_2, z_3 = _cswap(swap, z_2, z_3)

    res = (x_2 * pow(z_2, _P - 2, _P)) % _P
    return res.to_bytes(32, "little")


def _b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_x25519_keypair(xray_bin: str = "/usr/local/bin/xray") -> dict[str, str]:
    """Generate an X25519 keypair in Xray's base64url (unpadded) format."""
    if os.path.isfile(xray_bin) and os.access(xray_bin, os.X_OK):
        try:
            proc = subprocess.run(
                [xray_bin, "x25519"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            priv = pub = ""
            for line in proc.stdout.splitlines():
                if line.startswith("Private key:"):
                    priv = line.split(":", 1)[1].strip()
                elif line.startswith("Public key:"):
                    pub = line.split(":", 1)[1].strip()
            if priv and pub:
                return {"privateKey": priv, "publicKey": pub, "source": "xray"}
        except Exception:
            pass

    priv_raw = bytearray(secrets.token_bytes(32))
    priv_raw[0] &= 248
    priv_raw[31] &= 127
    priv_raw[31] |= 64
    priv_bytes = bytes(priv_raw)
    base_bytes = _BASE_U.to_bytes(32, "little")
    pub_bytes = _x25519_scalar_mult(priv_bytes, base_bytes)
    return {
        "privateKey": _b64url_nopad(priv_bytes),
        "publicKey": _b64url_nopad(pub_bytes),
        "source": "python",
    }
