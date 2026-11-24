"use strict";

const I18N = {
  tr: {
    login_sub: "VLESS + XTLS-Reality Yönetim Paneli",
    username: "Kullanıcı Adı",
    password: "Şifre",
    login_btn: "Giriş Yap",
    change_pass: "Şifre Değiştir",
    logout: "Çıkış",
    default_pass_warn: "Varsayılan şifre (admin123) kullanılıyor. Güvenlik için şifrenizi değiştirin.",
    ram_usage: "RAM Kullanımı",
    cpu_uptime: "CPU & Çalışma Süresi",
    disk_privacy: "Disk & Gizlilik",
    xray_service: "Xray Servisi",
    apply: "Uygula",
    restart: "Yeniden Başlat",
    stop: "Durdur",
    tab_clients: "Kişiye Özel Configler",
    tab_server: "Sunucu & Reality Ayarları",
    tab_raw: "Sunucu config.json",
    clients_title: "Kullanıcı / Cihaz Profilleri",
    new_client: "Yeni Kişiye Özel Config",
    edit_client: "Kullanıcıyı Düzenle",
    col_name: "İsim / Etiket",
    col_status: "Durum",
    col_actions: "İşlemler",
    server_title: "VLESS + Reality Sunucu Ayarları",
    gen_keys: "Yeni X25519 Anahtar Üret",
    server_ip: "Sunucu IP / Alan Adı",
    port: "Port",
    buffer_size: "Buffer Size (KiB - Düşük RAM için 16)",
    log_level: "Log Seviyesi (Zero-Log: none)",
    save_apply: "Kaydet ve Config'i Güncelle",
    refresh: "Yenile",
    copy: "Kopyala",
    active: "Aktif",
    disabled: "Pasif",
    note: "Not",
    cancel: "İptal",
    save: "Kaydet",
    client_json: "İstemci config.json (v2rayN / Xray)",
    copy_json: "JSON Kopyala",
    download_json: "JSON İndir",
    current_pass: "Mevcut Şifre",
    new_pass: "Yeni Şifre (en az 6 karakter)",
    copied: "Panoya kopyalandı",
    saved: "Kaydedildi",
    deleted: "Silindi",
    confirm_del: "Bu kullanıcı configini silmek istediğinize emin misiniz?",
    no_clients: "Henüz kişiye özel config oluşturulmamış. Sağ üstten ekleyin.",
    qr_link: "QR & Link",
    edit: "Düzenle",
    del: "Sil",
    running: "Çalışıyor",
    stopped: "Durdu",
  },
  en: {
    login_sub: "VLESS + XTLS-Reality Management Panel",
    username: "Username",
    password: "Password",
    login_btn: "Sign In",
    change_pass: "Change Password",
    logout: "Logout",
    default_pass_warn: "Default password (admin123) is active. Please change it for security.",
    ram_usage: "RAM Usage",
    cpu_uptime: "CPU & Uptime",
    disk_privacy: "Disk & Privacy",
    xray_service: "Xray Service",
    apply: "Apply",
    restart: "Restart",
    stop: "Stop",
    tab_clients: "Personalized Configs",
    tab_server: "Server & Reality Settings",
    tab_raw: "Server config.json",
    clients_title: "User / Device Profiles",
    new_client: "New Personalized Config",
    edit_client: "Edit Client",
    col_name: "Name / Label",
    col_status: "Status",
    col_actions: "Actions",
    server_title: "VLESS + Reality Server Settings",
    gen_keys: "Generate X25519 Keypair",
    server_ip: "Server IP / Domain",
    port: "Port",
    buffer_size: "Buffer Size (KiB - 16 for Low RAM)",
    log_level: "Log Level (Zero-Log: none)",
    save_apply: "Save & Update Config",
    refresh: "Refresh",
    copy: "Copy",
    active: "Active",
    disabled: "Disabled",
    note: "Note",
    cancel: "Cancel",
    save: "Save",
    client_json: "Client config.json (v2rayN / Xray)",
    copy_json: "Copy JSON",
    download_json: "Download JSON",
    current_pass: "Current Password",
    new_pass: "New Password (min 6 chars)",
    copied: "Copied to clipboard",
    saved: "Saved",
    deleted: "Deleted",
    confirm_del: "Delete this personalized client config?",
    no_clients: "No personalized configs yet. Click the button above to create one.",
    qr_link: "QR & Link",
    edit: "Edit",
    del: "Delete",
    running: "Running",
    stopped: "Stopped",
  },
};

let lang = localStorage.getItem("xray_panel_lang") || ((navigator.language || "").startsWith("tr") ? "tr" : "en");
let clientsCache = [];
let statsTimer = null;

function t(key) {
  return (I18N[lang] && I18N[lang][key]) || key;
}

function applyLang() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (I18N[lang][key]) el.textContent = I18N[lang][key];
  });
  document.getElementById("langToggle").textContent = lang === "tr" ? "EN" : "TR";
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/api/login") {
    showLogin();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    throw new Error(data.error || data.message || `HTTP ${res.status}`);
  }
  return data;
}

function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }

function showLogin() {
  clearInterval(statsTimer);
  document.getElementById("appView").classList.add("hidden");
  document.getElementById("loginView").classList.remove("hidden");
}

function showApp(isDefaultPass) {
  document.getElementById("loginView").classList.add("hidden");
  document.getElementById("appView").classList.remove("hidden");
  document.getElementById("defaultPassAlert").classList.toggle("hidden", !isDefaultPass);
  refreshAll();
  clearInterval(statsTimer);
  statsTimer = setInterval(loadSystem, 8000);
}

function formatUptime(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

async function loadSystem() {
  try {
    const s = await api("/api/system");
    document.getElementById("statRamVal").textContent = `${s.memory.used_mb} / ${s.memory.total_mb} MB`;
    document.getElementById("statRamBar").style.width = `${Math.min(100, s.memory.percent)}%`;
    document.getElementById("statRamSub").textContent =
      `Xray RSS: ${s.xray.rss_mb} MB (${s.memory.percent}%)`;

    document.getElementById("statLoadVal").textContent = s.loadavg.join(" / ");
    document.getElementById("statUptimeSub").textContent = `Uptime: ${formatUptime(s.uptime_sec)}`;
    document.getElementById("statHostSub").textContent = `${s.hostname} (${s.os} ${s.arch}, ${s.cpu_count} vCPU)`;

    document.getElementById("statDiskVal").textContent = `${s.disk.used_gb} / ${s.disk.total_gb} GB`;
    document.getElementById("statPrivacySub").textContent =
      s.zero_log.loglevel_none && s.zero_log.no_disk_logs
        ? "Zero-Log: OK (none / no disk logs)"
        : "Zero-Log: Check settings";
    document.getElementById("statClientsCount").textContent =
      `Clients: ${s.clients_enabled} active / ${s.clients_total} total`;

    const svcEl = document.getElementById("statSvcVal");
    svcEl.textContent = s.xray.running ? t("running") : t("stopped");
    svcEl.style.color = s.xray.running ? "var(--accent)" : "var(--amber)";
    document.getElementById("statSvcSub").textContent =
      `Mode: ${s.xray.service_manager} | Binary: ${s.xray.xray_installed ? "OK" : "Missing"}`;
  } catch (e) {
    // handled by api()
  }
}

async function loadServer() {
  const srv = await api("/api/server");
  document.getElementById("srvIp").value = srv.server_ip || "";
  document.getElementById("srvPort").value = srv.port || 443;
  document.getElementById("srvSni").value = srv.sni || "";
  document.getElementById("srvDest").value = srv.dest || "";
  document.getElementById("srvFp").value = srv.fingerprint || "chrome";
  document.getElementById("srvSpx").value = srv.spiderx || "/";
  document.getElementById("srvPriv").value = srv.private_key || "";
  document.getElementById("srvPub").value = srv.public_key || "";
  document.getElementById("srvBuf").value = srv.buffer_size || 16;
  document.getElementById("srvLog").value = srv.loglevel || "none";
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function loadClients() {
  const data = await api("/api/clients");
  clientsCache = data.clients || [];
  const tbody = document.getElementById("clientsTbody");
  if (!clientsCache.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">${escapeHtml(t("no_clients"))}</td></tr>`;
    return;
  }
  tbody.innerHTML = clientsCache.map((c) => {
    const badge = c.enabled
      ? `<span class="badge">${escapeHtml(t("active"))}</span>`
      : `<span class="badge warn">${escapeHtml(t("disabled"))}</span>`;
    return `
      <tr>
        <td>
          <strong>${escapeHtml(c.name)}</strong>
          ${c.note ? `<div class="stat-sub">${escapeHtml(c.note)}</div>` : ""}
        </td>
        <td class="mono">${escapeHtml(c.uuid.slice(0, 8))}...${escapeHtml(c.uuid.slice(-4))}</td>
        <td class="mono">${escapeHtml(c.short_id)}</td>
        <td>${badge}</td>
        <td>
          <div class="actions-cell">
            <button class="btn btn-sm btn-primary" onclick="openExport(${c.id})">${escapeHtml(t("qr_link"))}</button>
            <button class="btn btn-sm" onclick="openEditClient(${c.id})">${escapeHtml(t("edit"))}</button>
            <button class="btn btn-sm btn-danger" onclick="deleteClient(${c.id})">${escapeHtml(t("del"))}</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function loadRawConfig() {
  const data = await api("/api/config/raw");
  document.getElementById("rawPath").textContent = data.path;
  document.getElementById("rawConfigPre").textContent = JSON.stringify(data.config, null, 2);
}

async function refreshAll() {
  await Promise.all([loadSystem(), loadServer(), loadClients(), loadRawConfig()]);
}

function randomUuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function randomShortId() {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

window.regenUuid = () => { document.getElementById("cliUuid").value = randomUuid(); };
window.regenSid = () => { document.getElementById("cliSid").value = randomShortId(); };

window.setSni = (host) => {
  document.getElementById("srvSni").value = host;
  document.getElementById("srvDest").value = `${host}:443`;
};

window.svcAction = async (action) => {
  try {
    const res = await api(`/api/service/${action}`, { method: "POST" });
    showToast(res.message || "OK");
    await loadSystem();
  } catch (e) {
    showToast(e.message);
  }
};

window.openEditClient = (id) => {
  const c = clientsCache.find((x) => x.id === id);
  if (!c) return;
  document.getElementById("clientModalTitle").textContent = t("edit_client");
  document.getElementById("cliId").value = c.id;
  document.getElementById("cliName").value = c.name;
  document.getElementById("cliEmail").value = c.email || "";
  document.getElementById("cliUuid").value = c.uuid;
  document.getElementById("cliSid").value = c.short_id;
  document.getElementById("cliFlow").value = c.flow || "xtls-rprx-vision";
  document.getElementById("cliEnabled").value = c.enabled ? "1" : "0";
  document.getElementById("cliNote").value = c.note || "";
  openModal("clientModal");
};

window.deleteClient = async (id) => {
  if (!confirm(t("confirm_del"))) return;
  try {
    await api(`/api/clients/${id}`, { method: "DELETE" });
    showToast(t("deleted"));
    await Promise.all([loadClients(), loadRawConfig(), loadSystem()]);
  } catch (e) {
    showToast(e.message);
  }
};

window.openExport = async (id) => {
  try {
    const data = await api(`/api/clients/${id}/export`);
    document.getElementById("exportTitle").textContent = data.client.name;
    document.getElementById("exportVless").value = data.vless_link;
    const jsonStr = JSON.stringify(data.client_config, null, 2);
    document.getElementById("exportJson").textContent = jsonStr;
    document.getElementById("qrContainer").innerHTML = XrayQR.toSVG(data.vless_link, 220);

    document.getElementById("btnDownloadJson").onclick = () => {
      const blob = new Blob([jsonStr], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const safeName = data.client.name.toLowerCase().replace(/[^a-z0-9-_]+/g, "-");
      a.download = `xray-${safeName || "client"}.json`;
      a.click();
    };
    openModal("exportModal");
  } catch (e) {
    showToast(e.message);
  }
};

window.copyText = async (txt) => {
  try {
    await navigator.clipboard.writeText(txt);
    showToast(t("copied"));
  } catch {
    showToast("Copy failed");
  }
};

window.copyInput = (id) => copyText(document.getElementById(id).value);

// Event Listeners
document.getElementById("langToggle").addEventListener("click", () => {
  lang = lang === "tr" ? "en" : "tr";
  localStorage.setItem("xray_panel_lang", lang);
  applyLang();
  loadClients();
  loadSystem();
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.getAttribute("data-tab");
    ["clients", "server", "raw"].forEach((id) => {
      document.getElementById(`tab-${id}`).classList.toggle("hidden", id !== target);
    });
    if (target === "raw") loadRawConfig();
  });
});

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  document.getElementById("loginError").textContent = "";
  try {
    const res = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("loginUser").value,
        password: document.getElementById("loginPass").value,
      }),
    });
    showApp(res.is_default_pass);
  } catch (err) {
    document.getElementById("loginError").textContent = err.message;
  }
});

document.getElementById("btnLogout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  showLogin();
});

document.getElementById("btnNewClient").addEventListener("click", () => {
  document.getElementById("clientModalTitle").textContent = t("new_client");
  document.getElementById("cliId").value = "";
  document.getElementById("cliName").value = "";
  document.getElementById("cliEmail").value = "";
  document.getElementById("cliUuid").value = randomUuid();
  document.getElementById("cliSid").value = randomShortId();
  document.getElementById("cliFlow").value = "xtls-rprx-vision";
  document.getElementById("cliEnabled").value = "1";
  document.getElementById("cliNote").value = "";
  openModal("clientModal");
});

document.getElementById("clientForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("cliId").value;
  const payload = {
    name: document.getElementById("cliName").value,
    email: document.getElementById("cliEmail").value,
    uuid: document.getElementById("cliUuid").value,
    short_id: document.getElementById("cliSid").value,
    flow: document.getElementById("cliFlow").value,
    enabled: document.getElementById("cliEnabled").value === "1",
    note: document.getElementById("cliNote").value,
  };
  try {
    if (id) {
      await api(`/api/clients/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/clients", { method: "POST", body: JSON.stringify(payload) });
    }
    closeModal("clientModal");
    showToast(t("saved"));
    await Promise.all([loadClients(), loadRawConfig(), loadSystem()]);
  } catch (err) {
    showToast(err.message);
  }
});

document.getElementById("serverForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    server_ip: document.getElementById("srvIp").value,
    port: Number(document.getElementById("srvPort").value),
    sni: document.getElementById("srvSni").value,
    dest: document.getElementById("srvDest").value,
    fingerprint: document.getElementById("srvFp").value,
    spiderx: document.getElementById("srvSpx").value,
    private_key: document.getElementById("srvPriv").value,
    public_key: document.getElementById("srvPub").value,
    buffer_size: Number(document.getElementById("srvBuf").value),
    loglevel: document.getElementById("srvLog").value,
  };
  try {
    await api("/api/server", { method: "PUT", body: JSON.stringify(payload) });
    showToast(t("saved"));
    await Promise.all([loadClients(), loadRawConfig(), loadSystem()]);
  } catch (err) {
    showToast(err.message);
  }
});

document.getElementById("btnGenKeys").addEventListener("click", async () => {
  try {
    const kp = await api("/api/keys/x25519", { method: "POST" });
    document.getElementById("srvPriv").value = kp.privateKey;
    document.getElementById("srvPub").value = kp.publicKey;
    showToast(`X25519 (${kp.source})`);
  } catch (err) {
    showToast(err.message);
  }
});

document.getElementById("btnRefreshRaw").addEventListener("click", loadRawConfig);
document.getElementById("btnCopyRaw").addEventListener("click", () => {
  copyText(document.getElementById("rawConfigPre").textContent);
});

const openPassModal = () => {
  document.getElementById("oldPass").value = "";
  document.getElementById("newPass").value = "";
  openModal("passModal");
};
document.getElementById("btnChangePass").addEventListener("click", openPassModal);
document.getElementById("btnWarnChangePass").addEventListener("click", openPassModal);

document.getElementById("passForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: document.getElementById("oldPass").value,
        new_password: document.getElementById("newPass").value,
      }),
    });
    closeModal("passModal");
    document.getElementById("defaultPassAlert").classList.add("hidden");
    showToast(t("saved"));
  } catch (err) {
    showToast(err.message);
  }
});

// Boot
applyLang();
api("/api/me")
  .then((me) => {
    if (me.authenticated) showApp(me.is_default_pass);
    else showLogin();
  })
  .catch(() => showLogin());
