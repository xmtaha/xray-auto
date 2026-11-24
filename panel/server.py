#!/usr/bin/env python3
"""Ultra-lightweight Web Management Panel for xray-auto (VLESS + XTLS-Reality).

Zero external dependencies (Python 3 stdlib only). Designed for 512 MB RAM / 1 vCPU
Alpine Linux VPS environments as well as local development/config generation.
"""

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from urllib.parse import parse_qs, quote, urlparse
import uuid as uuid_lib

from xray_crypto import generate_x25519_keypair

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

DEFAULT_ETC_XRAY = "/etc/xray"
if os.path.isdir(DEFAULT_ETC_XRAY) and os.access(DEFAULT_ETC_XRAY, os.W_OK):
    DEFAULT_DATA_DIR = os.path.join(DEFAULT_ETC_XRAY, "panel")
    DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_ETC_XRAY, "config.json")
else:
    DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")
    DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_DATA_DIR, "config.json")

DATA_DIR = os.environ.get("XRAY_PANEL_DATA", DEFAULT_DATA_DIR)
CONFIG_PATH = os.environ.get("XRAY_CONFIG_PATH", DEFAULT_CONFIG_PATH)
DB_PATH = os.path.join(DATA_DIR, "panel.db")
XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
HOST = os.environ.get("XRAY_PANEL_HOST", "0.0.0.0")
PORT = int(os.environ.get("XRAY_PANEL_PORT", "8080"))

SESSION_COOKIE = "xray_panel_session"
SESSION_TTL = 86400  # 24 hours
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()
DB_LOCK = threading.Lock()


def _hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, hex_hash = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        candidate = _hash_password(password, salt)
        return hmac.compare_digest(candidate, stored)
    except Exception:
        return False


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def _detect_existing_install() -> dict | None:
    """Import existing /etc/xray/config.json if present on first run."""
    if not os.path.isfile(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        inbound = (cfg.get("inbounds") or [{}])[0]
        stream = inbound.get("streamSettings", {})
        reality = stream.get("realitySettings", {})
        sni_list = reality.get("serverNames") or ["www.speedtest.net"]
        short_ids = reality.get("shortIds") or []
        clients = inbound.get("settings", {}).get("clients", [])
        pbk = ""
        client_info = "/etc/xray/client_info.txt"
        if os.path.isfile(client_info):
            with open(client_info, "r", encoding="utf-8", errors="ignore") as cf:
                for line in cf:
                    m = re.search(r"pbk=([A-Za-z0-9_-]+)", line)
                    if m:
                        pbk = m.group(1)
                        break
        return {
            "port": str(inbound.get("port", 443)),
            "dest": reality.get("dest", "www.speedtest.net:443"),
            "sni": sni_list[0],
            "private_key": reality.get("privateKey", ""),
            "public_key": pbk,
            "short_id": short_ids[0] if short_ids else secrets.token_hex(8),
            "buffer_size": str(
                cfg.get("policy", {}).get("levels", {}).get("0", {}).get("bufferSize", 16)
            ),
            "loglevel": cfg.get("log", {}).get("loglevel", "none"),
            "clients": clients,
        }
    except Exception:
        return None


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with DB_LOCK:
        conn = _get_db()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    uuid TEXT UNIQUE NOT NULL,
                    short_id TEXT NOT NULL,
                    flow TEXT NOT NULL DEFAULT 'xtls-rprx-vision',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            # Initialize auth if missing
            if not _get_db_has_key(conn, "auth_user"):
                init_user = os.environ.get("XRAY_PANEL_USER", "admin")
                init_pass = os.environ.get("XRAY_PANEL_PASS", "admin123")
                _set_setting(conn, "auth_user", init_user)
                _set_setting(conn, "auth_pass_hash", _hash_password(init_pass))
                _set_setting(conn, "is_default_pass", "1" if init_pass == "admin123" else "0")

            # Initialize server settings if missing
            if not _get_db_has_key(conn, "private_key"):
                existing = _detect_existing_install()
                if existing and existing.get("private_key"):
                    kp = {
                        "privateKey": existing["private_key"],
                        "publicKey": existing.get("public_key", ""),
                    }
                    port = existing["port"]
                    sni = existing["sni"]
                    dest = existing["dest"]
                    buf = existing["buffer_size"]
                    loglevel = existing["loglevel"]
                else:
                    kp = generate_x25519_keypair(XRAY_BIN)
                    port = "443"
                    sni = "www.speedtest.net"
                    dest = "www.speedtest.net:443"
                    buf = "16"
                    loglevel = "none"

                defaults = {
                    "server_ip": os.environ.get("XRAY_SERVER_IP", "127.0.0.1"),
                    "port": port,
                    "sni": sni,
                    "dest": dest,
                    "fingerprint": "chrome",
                    "spiderx": "/",
                    "private_key": kp["privateKey"],
                    "public_key": kp["publicKey"],
                    "buffer_size": buf,
                    "loglevel": loglevel,
                }
                for k, v in defaults.items():
                    _set_setting(conn, k, v)

                if existing and existing.get("clients"):
                    now = time.strftime("%Y-%m-%d %H:%M:%S")
                    for idx, c in enumerate(existing["clients"], start=1):
                        cid = c.get("id")
                        if not cid:
                            continue
                        conn.execute(
                            "INSERT OR IGNORE INTO clients (name, email, uuid, short_id, flow, enabled, note, created_at) "
                            "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                            (
                                f"Imported-{idx}",
                                c.get("email", f"user{idx}@xray.local"),
                                cid,
                                existing["short_id"],
                                c.get("flow", "xtls-rprx-vision"),
                                "Imported from existing config.json",
                                now,
                            ),
                        )

            conn.commit()
        finally:
            conn.close()
    sync_xray_config()


def _get_db_has_key(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
    return row is not None


def get_server_config_dict() -> dict:
    with DB_LOCK:
        conn = _get_db()
        try:
            keys = [
                "server_ip",
                "port",
                "sni",
                "dest",
                "fingerprint",
                "spiderx",
                "private_key",
                "public_key",
                "buffer_size",
                "loglevel",
            ]
            data = {k: _get_setting(conn, k) for k in keys}
            data["port"] = int(data["port"] or 443)
            data["buffer_size"] = int(data["buffer_size"] or 16)
            return data
        finally:
            conn.close()


def list_clients() -> list[dict]:
    with DB_LOCK:
        conn = _get_db()
        try:
            rows = conn.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def build_xray_config() -> dict:
    srv = get_server_config_dict()
    clients = [c for c in list_clients() if c["enabled"]]

    xray_clients = []
    short_ids = []
    seen_sids = set()
    for c in clients:
        entry = {"id": c["uuid"], "flow": c["flow"]}
        if c["email"]:
            entry["email"] = c["email"]
        xray_clients.append(entry)
        sid = c["short_id"].strip()
        if sid and sid not in seen_sids:
            seen_sids.add(sid)
            short_ids.append(sid)

    if not short_ids:
        short_ids = [""]

    return {
        "log": {"loglevel": srv["loglevel"] or "none"},
        "policy": {
            "levels": {
                "0": {
                    "handshake": 4,
                    "connIdle": 300,
                    "uplinkOnly": 2,
                    "downlinkOnly": 5,
                    "bufferSize": srv["buffer_size"],
                }
            },
            "system": {
                "statsInboundUplink": False,
                "statsInboundDownlink": False,
                "statsOutboundUplink": False,
                "statsOutboundDownlink": False,
            },
        },
        "inbounds": [
            {
                "port": srv["port"],
                "protocol": "vless",
                "settings": {
                    "clients": xray_clients,
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": srv["dest"],
                        "xver": 0,
                        "serverNames": [srv["sni"]],
                        "privateKey": srv["private_key"],
                        "shortIds": short_ids,
                    },
                },
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
        ],
    }


def sync_xray_config() -> str:
    cfg = build_xray_config()
    parent = os.path.dirname(CONFIG_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{CONFIG_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, CONFIG_PATH)
    return CONFIG_PATH


def build_vless_link(client: dict, srv: dict) -> str:
    label = quote(client["name"], safe="")
    spx = quote(srv["spiderx"] or "/", safe="")
    sni = quote(srv["sni"], safe="")
    fp = quote(srv["fingerprint"] or "chrome", safe="")
    flow = quote(client["flow"] or "xtls-rprx-vision", safe="")
    return (
        f"vless://{client['uuid']}@{srv['server_ip']}:{srv['port']}"
        f"?security=reality&encryption=none&pbk={srv['public_key']}"
        f"&headerType=none&fp={fp}&spx={spx}&type=tcp"
        f"&flow={flow}&sni={sni}&sid={client['short_id']}#{label}"
    )


def build_client_json(client: dict, srv: dict) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            },
            {
                "tag": "http-in",
                "port": 10809,
                "listen": "127.0.0.1",
                "protocol": "http",
            },
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": srv["server_ip"],
                            "port": srv["port"],
                            "users": [
                                {
                                    "id": client["uuid"],
                                    "encryption": "none",
                                    "flow": client["flow"],
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "fingerprint": srv["fingerprint"],
                        "serverName": srv["sni"],
                        "publicKey": srv["public_key"],
                        "shortId": client["short_id"],
                        "spiderX": srv["spiderx"],
                    },
                },
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}
            ],
        },
    }


def _read_proc_meminfo() -> dict:
    info = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_kb = int(parts[1].strip().split()[0])
                    info[key] = val_kb
    except Exception:
        pass
    total_kb = info.get("MemTotal", 0)
    avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb)
    return {
        "total_mb": round(total_kb / 1024, 1),
        "used_mb": round(used_kb / 1024, 1),
        "available_mb": round(avail_kb / 1024, 1),
        "percent": round((used_kb / total_kb) * 100, 1) if total_kb else 0.0,
    }


def _read_uptime() -> int:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return 0


def _read_loadavg() -> list[float]:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except Exception:
        return [0.0, 0.0, 0.0]


def _detect_service_manager() -> str | None:
    if shutil.which("rc-service") and os.path.exists("/etc/init.d/xray"):
        return "openrc"
    if shutil.which("systemctl") and os.path.exists("/etc/systemd/system/xray.service"):
        return "systemd"
    return None


def _get_xray_process_info() -> dict:
    pid = None
    rss_mb = 0.0
    running = False
    try:
        proc = subprocess.run(
            ["pgrep", "-x", "xray"], capture_output=True, text=True, timeout=2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            pid = int(proc.stdout.strip().splitlines()[0])
            running = True
            status_path = f"/proc/{pid}/status"
            if os.path.isfile(status_path):
                with open(status_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            kb = int(line.split()[1])
                            rss_mb = round(kb / 1024, 2)
                            break
    except Exception:
        pass

    svc_mgr = _detect_service_manager()
    svc_status = "running" if running else "stopped"
    if svc_mgr == "openrc":
        try:
            r = subprocess.run(
                ["rc-service", "xray", "status"], capture_output=True, text=True, timeout=3
            )
            svc_status = "running" if r.returncode == 0 else "stopped"
        except Exception:
            pass

    return {
        "running": running,
        "pid": pid,
        "rss_mb": rss_mb,
        "service_manager": svc_mgr or "standalone",
        "service_status": svc_status,
        "xray_installed": os.path.isfile(XRAY_BIN),
        "is_root": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
    }


def get_system_status() -> dict:
    disk = shutil.disk_usage("/")
    srv = get_server_config_dict()
    clients = list_clients()
    zero_log_disk_clean = not os.path.exists("/var/log/xray") or len(
        os.listdir("/var/log/xray")
    ) == 0
    return {
        "hostname": platform.node(),
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu_count": os.cpu_count() or 1,
        "loadavg": _read_loadavg(),
        "uptime_sec": _read_uptime(),
        "memory": _read_proc_meminfo(),
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0.0,
        },
        "xray": _get_xray_process_info(),
        "zero_log": {
            "loglevel_none": srv["loglevel"] == "none",
            "no_disk_logs": zero_log_disk_clean,
        },
        "config_path": CONFIG_PATH,
        "clients_total": len(clients),
        "clients_enabled": sum(1 for c in clients if c["enabled"]),
    }


def control_xray_service(action: str) -> tuple[bool, str]:
    if action not in {"start", "stop", "restart", "apply"}:
        return False, "Invalid action"

    sync_xray_config()
    if action == "apply":
        mgr = _detect_service_manager()
        if not mgr:
            return True, f"Config written to {CONFIG_PATH} (standalone mode, no init service)."
        action = "restart"

    mgr = _detect_service_manager()
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    if not mgr or not is_root:
        return (
            True,
            f"Config synced to {CONFIG_PATH}. Service '{action}' skipped (not running as root on Alpine/systemd).",
        )

    cmd = ["rc-service", "xray", action] if mgr == "openrc" else ["systemctl", action, "xray"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return True, proc.stdout.strip() or f"Service {action} succeeded."
        return False, proc.stderr.strip() or proc.stdout.strip() or f"Service {action} failed."
    except Exception as exc:
        return False, str(exc)


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "XrayAutoPanel/1.0"

    def log_message(self, format: str, *args) -> None:
        # Zero-log policy: do not write HTTP access logs to stdout/disk
        return

    def _send_json(self, status: int, payload: dict, extra_headers: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 1_048_576:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _get_session(self) -> dict | None:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(SESSION_COOKIE)
        if not morsel:
            return None
        token = morsel.value
        with SESSIONS_LOCK:
            sess = SESSIONS.get(token)
            if not sess:
                return None
            if time.time() - sess["created"] > SESSION_TTL:
                del SESSIONS[token]
                return None
            return {"token": token, **sess}

    def _require_auth(self) -> dict | None:
        sess = self._get_session()
        if not sess:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return None
        return sess

    def _serve_static(self, rel_path: str) -> None:
        if rel_path in {"", "/"}:
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        if ".." in rel_path:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        full_path = os.path.join(STATIC_DIR, rel_path)
        if not os.path.isfile(full_path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ext = os.path.splitext(full_path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            return self._send_json(200, {"ok": True})

        if not path.startswith("/api/"):
            return self._serve_static(path)

        if path == "/api/me":
            sess = self._get_session()
            if not sess:
                return self._send_json(200, {"authenticated": False})
            with DB_LOCK:
                conn = _get_db()
                try:
                    is_def = _get_setting(conn, "is_default_pass", "0") == "1"
                finally:
                    conn.close()
            return self._send_json(
                200,
                {
                    "authenticated": True,
                    "user": sess["user"],
                    "is_default_pass": is_def,
                },
            )

        if not self._require_auth():
            return

        if path == "/api/system":
            return self._send_json(200, get_system_status())

        if path == "/api/server":
            return self._send_json(200, get_server_config_dict())

        if path == "/api/clients":
            srv = get_server_config_dict()
            items = list_clients()
            for item in items:
                item["vless_link"] = build_vless_link(item, srv)
            return self._send_json(200, {"clients": items})

        m = re.fullmatch(r"/api/clients/(\d+)/export", path)
        if m:
            cid = int(m.group(1))
            with DB_LOCK:
                conn = _get_db()
                try:
                    row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
                finally:
                    conn.close()
            if not row:
                return self._send_json(404, {"error": "Client not found"})
            client = dict(row)
            srv = get_server_config_dict()
            return self._send_json(
                200,
                {
                    "client": client,
                    "vless_link": build_vless_link(client, srv),
                    "client_config": build_client_json(client, srv),
                    "params": {
                        "protocol": "VLESS",
                        "address": srv["server_ip"],
                        "port": srv["port"],
                        "uuid": client["uuid"],
                        "flow": client["flow"],
                        "security": "reality",
                        "sni": srv["sni"],
                        "fingerprint": srv["fingerprint"],
                        "publicKey": srv["public_key"],
                        "shortId": client["short_id"],
                        "spiderX": srv["spiderx"],
                    },
                },
            )

        if path == "/api/config/raw":
            return self._send_json(200, {"config": build_xray_config(), "path": CONFIG_PATH})

        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/login":
            try:
                body = self._read_json_body()
            except Exception:
                return self._send_json(400, {"error": "Invalid JSON"})
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            with DB_LOCK:
                conn = _get_db()
                try:
                    stored_user = _get_setting(conn, "auth_user", "admin")
                    stored_hash = _get_setting(conn, "auth_pass_hash", "")
                    is_def = _get_setting(conn, "is_default_pass", "0") == "1"
                finally:
                    conn.close()
            if username != stored_user or not _verify_password(password, stored_hash):
                return self._send_json(401, {"error": "Invalid credentials"})
            token = secrets.token_urlsafe(32)
            with SESSIONS_LOCK:
                SESSIONS[token] = {"user": username, "created": time.time()}
            cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"
            return self._send_json(
                200,
                {"ok": True, "user": username, "is_default_pass": is_def},
                extra_headers={"Set-Cookie": cookie},
            )

        if path == "/api/logout":
            sess = self._get_session()
            if sess:
                with SESSIONS_LOCK:
                    SESSIONS.pop(sess["token"], None)
            cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            return self._send_json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie})

        if not self._require_auth():
            return

        if path == "/api/password":
            body = self._read_json_body()
            old_pw = str(body.get("current_password", ""))
            new_pw = str(body.get("new_password", ""))
            if len(new_pw) < 6:
                return self._send_json(400, {"error": "Password must be at least 6 characters"})
            with DB_LOCK:
                conn = _get_db()
                try:
                    stored_hash = _get_setting(conn, "auth_pass_hash", "")
                    if not _verify_password(old_pw, stored_hash):
                        return self._send_json(400, {"error": "Current password is incorrect"})
                    _set_setting(conn, "auth_pass_hash", _hash_password(new_pw))
                    _set_setting(conn, "is_default_pass", "0")
                    conn.commit()
                finally:
                    conn.close()
            return self._send_json(200, {"ok": True})

        if path == "/api/keys/x25519":
            kp = generate_x25519_keypair(XRAY_BIN)
            return self._send_json(200, kp)

        m = re.fullmatch(r"/api/service/(start|stop|restart|apply)", path)
        if m:
            ok, msg = control_xray_service(m.group(1))
            return self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        if path == "/api/clients":
            try:
                body = self._read_json_body()
            except Exception:
                return self._send_json(400, {"error": "Invalid JSON"})
            name = str(body.get("name", "")).strip()
            if not name:
                return self._send_json(400, {"error": "Client name is required"})
            email = str(body.get("email", "")).strip()
            cid_uuid = str(body.get("uuid", "")).strip() or str(uuid_lib.uuid4())
            try:
                uuid_lib.UUID(cid_uuid)
            except ValueError:
                return self._send_json(400, {"error": "Invalid UUID format"})
            short_id = str(body.get("short_id", "")).strip() or secrets.token_hex(8)
            if not re.fullmatch(r"[0-9a-fA-F]{2,16}", short_id) or len(short_id) % 2 != 0:
                return self._send_json(400, {"error": "Short ID must be 2-16 even hex chars"})
            flow = str(body.get("flow", "xtls-rprx-vision")).strip() or "xtls-rprx-vision"
            note = str(body.get("note", "")).strip()
            enabled = 1 if body.get("enabled", True) else 0
            now = time.strftime("%Y-%m-%d %H:%M:%S")

            with DB_LOCK:
                conn = _get_db()
                try:
                    cur = conn.execute(
                        "INSERT INTO clients (name, email, uuid, short_id, flow, enabled, note, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, email, cid_uuid, short_id.lower(), flow, enabled, note, now),
                    )
                    conn.commit()
                    new_id = cur.lastrowid
                    row = conn.execute("SELECT * FROM clients WHERE id = ?", (new_id,)).fetchone()
                except sqlite3.IntegrityError:
                    return self._send_json(409, {"error": "UUID already exists"})
                finally:
                    conn.close()

            sync_xray_config()
            srv = get_server_config_dict()
            client = dict(row)
            client["vless_link"] = build_vless_link(client, srv)
            return self._send_json(201, {"client": client})

        self._send_json(404, {"error": "Not found"})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._require_auth():
            return

        if path == "/api/server":
            try:
                body = self._read_json_body()
            except Exception:
                return self._send_json(400, {"error": "Invalid JSON"})
            try:
                port = int(body.get("port", 443))
                buf = int(body.get("buffer_size", 16))
            except ValueError:
                return self._send_json(400, {"error": "Invalid numeric field"})
            if not (1 <= port <= 65535):
                return self._send_json(400, {"error": "Port must be between 1 and 65535"})
            if not (4 <= buf <= 512):
                return self._send_json(400, {"error": "bufferSize must be between 4 and 512 KiB"})

            allowed_logs = {"none", "error", "warning", "info", "debug"}
            loglevel = str(body.get("loglevel", "none")).strip()
            if loglevel not in allowed_logs:
                loglevel = "none"

            updates = {
                "server_ip": str(body.get("server_ip", "127.0.0.1")).strip() or "127.0.0.1",
                "port": str(port),
                "sni": str(body.get("sni", "www.speedtest.net")).strip() or "www.speedtest.net",
                "dest": str(body.get("dest", "www.speedtest.net:443")).strip()
                or "www.speedtest.net:443",
                "fingerprint": str(body.get("fingerprint", "chrome")).strip() or "chrome",
                "spiderx": str(body.get("spiderx", "/")).strip() or "/",
                "private_key": str(body.get("private_key", "")).strip(),
                "public_key": str(body.get("public_key", "")).strip(),
                "buffer_size": str(buf),
                "loglevel": loglevel,
            }
            with DB_LOCK:
                conn = _get_db()
                try:
                    for k, v in updates.items():
                        _set_setting(conn, k, v)
                    conn.commit()
                finally:
                    conn.close()
            sync_xray_config()
            return self._send_json(200, get_server_config_dict())

        m = re.fullmatch(r"/api/clients/(\d+)", path)
        if m:
            cid = int(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                return self._send_json(400, {"error": "Invalid JSON"})
            with DB_LOCK:
                conn = _get_db()
                try:
                    existing = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
                    if not existing:
                        return self._send_json(404, {"error": "Client not found"})
                    name = str(body.get("name", existing["name"])).strip() or existing["name"]
                    email = str(body.get("email", existing["email"])).strip()
                    cid_uuid = str(body.get("uuid", existing["uuid"])).strip()
                    try:
                        uuid_lib.UUID(cid_uuid)
                    except ValueError:
                        return self._send_json(400, {"error": "Invalid UUID format"})
                    short_id = str(body.get("short_id", existing["short_id"])).strip().lower()
                    if not re.fullmatch(r"[0-9a-f]{2,16}", short_id) or len(short_id) % 2 != 0:
                        return self._send_json(400, {"error": "Short ID must be 2-16 even hex chars"})
                    flow = str(body.get("flow", existing["flow"])).strip() or "xtls-rprx-vision"
                    note = str(body.get("note", existing["note"])).strip()
                    enabled = 1 if body.get("enabled", bool(existing["enabled"])) else 0

                    conn.execute(
                        "UPDATE clients SET name=?, email=?, uuid=?, short_id=?, flow=?, enabled=?, note=? WHERE id=?",
                        (name, email, cid_uuid, short_id, flow, enabled, note, cid),
                    )
                    conn.commit()
                    row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
                except sqlite3.IntegrityError:
                    return self._send_json(409, {"error": "UUID already exists"})
                finally:
                    conn.close()
            sync_xray_config()
            srv = get_server_config_dict()
            client = dict(row)
            client["vless_link"] = build_vless_link(client, srv)
            return self._send_json(200, {"client": client})

        self._send_json(404, {"error": "Not found"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._require_auth():
            return

        m = re.fullmatch(r"/api/clients/(\d+)", path)
        if m:
            cid = int(m.group(1))
            with DB_LOCK:
                conn = _get_db()
                try:
                    cur = conn.execute("DELETE FROM clients WHERE id = ?", (cid,))
                    conn.commit()
                    deleted = cur.rowcount
                finally:
                    conn.close()
            if not deleted:
                return self._send_json(404, {"error": "Client not found"})
            sync_xray_config()
            return self._send_json(200, {"ok": True})

        self._send_json(404, {"error": "Not found"})


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), PanelHandler)
    print(f"Xray-Auto Panel listening on http://{HOST}:{PORT} (config: {CONFIG_PATH})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
