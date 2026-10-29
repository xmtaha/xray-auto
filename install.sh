#!/bin/sh
# ==============================================================================
# Alpine Linux - Ultra Hafif Xray VLESS Reality Otomasyon Scripti
# author - xmtaha
# ==============================================================================

set -e

# Renk kodları
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PLAIN='\033[0m'

# Dil Tespiti (Klavye düzenini öncelikli olarak baz alır, bulunamazsa yerel dil ayarlarına bakar)
# Language Detection (Prioritizes keyboard layout, falls back to locale. Defaults to English for non-Turkish systems)
detect_language() {
    # Manuel dil seçimi kontrolü (XRAY_LANG=tr veya XRAY_LANG=en)
    if [ -n "$XRAY_LANG" ]; then
        case "$XRAY_LANG" in
            tr|TR|tr_TR*) echo "tr"; return ;;
            *) echo "en"; return ;;
        esac
    fi

    # 1. Klavye Düzeni Kontrolleri (Keyboard Layout)
    # Alpine Linux OpenRC (/etc/conf.d/keymaps -> örn: keymap="trq" veya keymap="tr")
    if [ -f /etc/conf.d/keymaps ]; then
        if grep -qi 'keymap=.*tr' /etc/conf.d/keymaps 2>/dev/null; then
            echo "tr"
            return
        fi
    fi

    # Debian / Ubuntu (/etc/default/keyboard -> örn: XKBLAYOUT="tr")
    if [ -f /etc/default/keyboard ]; then
        if grep -qi 'xkblayout=.*tr' /etc/default/keyboard 2>/dev/null; then
            echo "tr"
            return
        fi
    fi

    # Systemd / Arch / RHEL (/etc/vconsole.conf -> örn: KEYMAP="trq")
    if [ -f /etc/vconsole.conf ]; then
        if grep -qi 'keymap=.*tr' /etc/vconsole.conf 2>/dev/null; then
            echo "tr"
            return
        fi
    fi

    # localectl (Systemd sistemler)
    if command -v localectl >/dev/null 2>&1; then
        if localectl status 2>/dev/null | grep -iE '(keymap|layout):' | grep -qi 'tr'; then
            echo "tr"
            return
        fi
    fi

    # setxkbmap (X11 grafik arayüz sistemleri)
    if command -v setxkbmap >/dev/null 2>&1; then
        if setxkbmap -query 2>/dev/null | grep -i 'layout:' | grep -qi 'tr'; then
            echo "tr"
            return
        fi
    fi

    # 2. Sistem Dil / Yerel Ayar Kontrolleri (Fallback: Locale / Environment)
    for l_var in "$LC_ALL" "$LC_MESSAGES" "$LANG" "$LANGUAGE"; do
        case "$l_var" in
            tr*|TR*|*tr_TR*|*[tT]urkish*)
                echo "tr"
                return
                ;;
        esac
    done

    if [ -f /etc/locale.conf ]; then
        if grep -qi 'lang=.*tr' /etc/locale.conf 2>/dev/null; then
            echo "tr"
            return
        fi
    fi

    if [ -f /etc/default/locale ]; then
        if grep -qi 'lang=.*tr' /etc/default/locale 2>/dev/null; then
            echo "tr"
            return
        fi
    fi

    # Varsayılan: Türkçe dışındaki tüm sistemlerde İngilizce
    echo "en"
}

SYS_LANG=$(detect_language)

if [ "$SYS_LANG" = "tr" ]; then
    MSG_TITLE="   Alpine Linux - Ultra Düşük Kaynak Xray Reality          "
    MSG_ROOT_ERR="[Hata] Bu scripti çalıştırmak için root yetkisi gereklidir!"
    MSG_STEP1="[1/6] Gerekli paketler yükleniyor..."
    MSG_STEP2="[2/6] Sistem mimarisi tespit ediliyor ve Xray-core indiriliyor..."
    MSG_ARCH_ERR="[Hata] Desteklenmeyen mimari:"
    MSG_DOWNLOADING="İndiriliyor:"
    MSG_ARCH_LABEL="Mimari:"
    MSG_STEP3="[3/6] Anahtarlar ve Reality parametreleri üretiliyor..."
    FALLBACK_IP="SUNUCU_IP_ADRESI"
    MSG_STEP4="[4/6] Optimize edilmiş ve sıfır log için config.json oluşturuluyor..."
    MSG_STEP5="[5/6] OpenRC servisi oluşturuluyor (GOMAXPROCS=1, GOGC=20, Zero-Log)..."
    MSG_STEP6="[6/6] Kurulum ve optimizasyon başarıyla tamamlandı!"
    MSG_CLIENT_BANNER="=================== İSTEMCİ BAĞLANTI BİLGİLERİ ==================="
    MSG_QR_TITLE="Hızlı İçe Aktarma QR Kodu:"
    MSG_SAVED_INFO="Bağlantı parametreleri '/etc/xray/client_info.txt' dosyasına kaydedildi."

    INFO_HEADER="       Xray VLESS-Reality Bağlantı Bilgileri (Speedtest)"
    INFO_SERVER="Sunucu IP / Host   :"
    INFO_PORT="Port               :"
    INFO_PROTOCOL="Protokol           :"
    INFO_UUID="UUID               :"
    INFO_FLOW="Akış (Flow)        :"
    INFO_SECURITY="Güvenlik           :"
    INFO_PUBLIC_KEY="Genel Anahtar (PBK):"
    INFO_SHORT_ID="Short ID (sid)     :"
    INFO_SNI="SNI (Server Name)  :"
    INFO_FINGERPRINT="Fingerprint (fp)   :"
    INFO_SPIDERX="SpiderX            :"
    INFO_LINK="Bağlantı Linki:"
else
    MSG_TITLE="   Alpine Linux - Ultra Low Resource Xray Reality          "
    MSG_ROOT_ERR="[Error] Root privileges are required to run this script!"
    MSG_STEP1="[1/6] Installing required packages..."
    MSG_STEP2="[2/6] Detecting system architecture and downloading Xray-core..."
    MSG_ARCH_ERR="[Error] Unsupported architecture:"
    MSG_DOWNLOADING="Downloading:"
    MSG_ARCH_LABEL="Arch:"
    MSG_STEP3="[3/6] Generating keys and Reality parameters..."
    FALLBACK_IP="SERVER_IP_ADDRESS"
    MSG_STEP4="[4/6] Generating optimized zero-log config.json..."
    MSG_STEP5="[5/6] Creating OpenRC service (GOMAXPROCS=1, GOGC=20, Zero-Log)..."
    MSG_STEP6="[6/6] Installation and optimization completed successfully!"
    MSG_CLIENT_BANNER="=================== CLIENT CONNECTION INFO ==================="
    MSG_QR_TITLE="Quick Import QR Code:"
    MSG_SAVED_INFO="Connection parameters saved to '/etc/xray/client_info.txt'."

    INFO_HEADER="       Xray VLESS-Reality Connection Info (Speedtest)"
    INFO_SERVER="Server IP / Host   :"
    INFO_PORT="Port               :"
    INFO_PROTOCOL="Protocol           :"
    INFO_UUID="UUID               :"
    INFO_FLOW="Flow               :"
    INFO_SECURITY="Security           :"
    INFO_PUBLIC_KEY="Public Key (PBK)   :"
    INFO_SHORT_ID="Short ID (sid)     :"
    INFO_SNI="SNI (Server Name)  :"
    INFO_FINGERPRINT="Fingerprint (fp)   :"
    INFO_SPIDERX="SpiderX            :"
    INFO_LINK="Connection Link:"
fi

echo -e "${BLUE}============================================================${PLAIN}"
echo -e "${GREEN}${MSG_TITLE}${PLAIN}"
echo -e "${BLUE}============================================================${PLAIN}"

# 1. Root Yetkisi Kontrolü
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}${MSG_ROOT_ERR}${PLAIN}"
    exit 1
fi

# 2. Minimum Paket Kurulumu
echo -e "\n${YELLOW}${MSG_STEP1}${PLAIN}"
apk update
apk add --no-cache curl jq openssl qrencode unzip ca-certificates tzdata

# 3. Mimari Tespiti ve Xray Binary İndirme
echo -e "\n${YELLOW}${MSG_STEP2}${PLAIN}"
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  XRAY_ARCH="64" ;;
    aarch64) XRAY_ARCH="arm64-v8a" ;;
    armv7l)  XRAY_ARCH="arm32-v7a" ;;
    *)
        echo -e "${RED}${MSG_ARCH_ERR} $ARCH${PLAIN}"
        exit 1
        ;;
esac

LATEST_VER=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r .tag_name 2>/dev/null)
if [ -z "$LATEST_VER" ] || [ "$LATEST_VER" = "null" ]; then
    LATEST_VER="v24.11.30"
fi

DOWNLOAD_URL="https://github.com/XTLS/Xray-core/releases/download/${LATEST_VER}/Xray-linux-${XRAY_ARCH}.zip"
echo -e "${MSG_DOWNLOADING} ${GREEN}${LATEST_VER}${PLAIN} (${MSG_ARCH_LABEL} ${XRAY_ARCH})"

TMP_DIR=$(mktemp -d)
curl -sSL -o "${TMP_DIR}/xray.zip" "$DOWNLOAD_URL"
unzip -qo "${TMP_DIR}/xray.zip" -d "${TMP_DIR}"

mkdir -p /usr/local/bin /etc/xray
cp "${TMP_DIR}/xray" /usr/local/bin/xray
chmod +x /usr/local/bin/xray
rm -rf "${TMP_DIR}"

# 4. Parametreler & Anahtar Üretimi
echo -e "\n${YELLOW}${MSG_STEP3}${PLAIN}"

PORT=443
DEST_SERVER="www.speedtest.net:443"
SNI="www.speedtest.net"

UUID=$(/usr/local/bin/xray uuid)
KEYPAIR=$(/usr/local/bin/xray x25519)
PRIVATE_KEY=$(echo "$KEYPAIR" | awk '/Private key:/ {print $3}')
PUBLIC_KEY=$(echo "$KEYPAIR" | awk '/Public key:/ {print $3}')
SHORT_ID=$(openssl rand -hex 8)

# Dış IP tespiti
SERVER_IP=$(curl -s4 https://api.ipify.org || curl -s4 https://ifconfig.me || curl -s4 https://icanhazip.com || echo "${FALLBACK_IP}")

# 5. Xray Yapılandırması (Zero-Log & Optimize)
echo -e "\n${YELLOW}${MSG_STEP4}${PLAIN}"

cat <<EOF > /etc/xray/config.json
{
  "log": {
    "loglevel": "none"
  },
  "policy": {
    "levels": {
      "0": {
        "handshake": 4,
        "connIdle": 300,
        "uplinkOnly": 2,
        "downlinkOnly": 5,
        "bufferSize": 16
      }
    },
    "system": {
      "statsInboundUplink": false,
      "statsInboundDownlink": false,
      "statsOutboundUplink": false,
      "statsOutboundDownlink": false
    }
  },
  "inbounds": [
    {
      "port": ${PORT},
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${UUID}",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${DEST_SERVER}",
          "xver": 0,
          "serverNames": [
            "${SNI}"
          ],
          "privateKey": "${PRIVATE_KEY}",
          "shortIds": [
            "${SHORT_ID}"
          ]
        }
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    }
  ]
}
EOF

# 6. OpenRC Servisi
echo -e "\n${YELLOW}${MSG_STEP5}${PLAIN}"

cat <<'EOF' > /etc/init.d/xray
#!/sbin/openrc-run

name="xray"
description="Xray-core Low-Spec Service"

# optimizasyon
export GOMAXPROCS=1
export GOGC=20
export GOMEMLIMIT=350MiB

command="/usr/local/bin/xray"
command_args="run -c /etc/xray/config.json"
command_background="yes"
pidfile="/run/xray.pid"

# Sıfır log: stdout ve stderr /dev/null'a yönlendirilir
output_log="/dev/null"
error_log="/dev/null"

depend() {
    need net
    after firewall
}
EOF

chmod +x /etc/init.d/xray
rc-update add xray default
rc-service xray restart

# 7. Bağlantı Bilgilerini Hazırlama
VLESS_LINK="vless://${UUID}@${SERVER_IP}:${PORT}?security=reality&encryption=none&pbk=${PUBLIC_KEY}&headerType=none&fp=chrome&spx=%2F&type=tcp&flow=xtls-rprx-vision&sni=${SNI}&sid=${SHORT_ID}#Alpine-Reality-Speedtest"

# İstemci parametrelerini kaydet (bağlantı konfigürasyonu)
cat <<EOF > /etc/xray/client_info.txt
============================================================
${INFO_HEADER}
============================================================
${INFO_SERVER} ${SERVER_IP}
${INFO_PORT} ${PORT}
${INFO_PROTOCOL} VLESS
${INFO_UUID} ${UUID}
${INFO_FLOW} xtls-rprx-vision
${INFO_SECURITY} reality
${INFO_PUBLIC_KEY} ${PUBLIC_KEY}
${INFO_SHORT_ID} ${SHORT_ID}
${INFO_SNI} ${SNI}
${INFO_FINGERPRINT} chrome
${INFO_SPIDERX} /

${INFO_LINK}
${VLESS_LINK}
============================================================
EOF

# Sonuçları Ekrana Yazdır
echo -e "\n${GREEN}${MSG_STEP6}${PLAIN}\n"
echo -e "${BLUE}${MSG_CLIENT_BANNER}${PLAIN}"
cat /etc/xray/client_info.txt

echo -e "\n${YELLOW}${MSG_QR_TITLE}${PLAIN}\n"
qrencode -t ANSI256 "${VLESS_LINK}" || qrencode -t UTF8 "${VLESS_LINK}"

echo -e "\n${GREEN}${MSG_SAVED_INFO}${PLAIN}"
