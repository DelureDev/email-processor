#!/bin/bash
# SMB server diagnostic — run against //10.10.10.21/dms_reports to
# produce unambiguous evidence of where the problem is:
#   - TCP layer (Linux network to Windows host)
#   - SMB layer (Windows SMB service responding)
#   - CIFS mount layer (kernel client state)
#   - Filesystem ops (read/write through mount)
#
# Output is suitable for forwarding to the admin who owns 10.10.10.21.
# No sudo needed except for dmesg.
#
# Usage:
#     bash diag_smb.sh [> diag-$(hostname)-$(date +%Y%m%d-%H%M).log]

set -u

SERVER="${SMB_SERVER:-10.10.10.21}"
SHARE="${SMB_SHARE:-dms_reports}"
MOUNT="${SMB_MOUNT:-/mnt/storage}"
CREDS="${SMB_CREDS:-/etc/cifs-creds}"

echo "==========================================================="
echo " SMB diagnostic for //${SERVER}/${SHARE}"
echo " Timestamp:     $(date -Iseconds)"
echo " Run from host: $(hostname) ($(uname -sr))"
echo " Mount point:   ${MOUNT}"
echo "==========================================================="
echo

echo "--- 1. ICMP reachability (TCP network layer health) ---"
timeout 3 ping -c 3 -W 1 "${SERVER}" 2>&1 | sed 's/^/  /'
echo

echo "--- 2. TCP port 445 (SMB port reachability) ---"
timeout 3 bash -c "</dev/tcp/${SERVER}/445" 2>&1 \
    && echo "  TCP 445 OPEN — handshake completed" \
    || echo "  TCP 445 CLOSED or timed out"
echo

echo "--- 3. SMB NEGOTIATE (can the Windows SMB service respond at all?) ---"
echo "    (This bypasses our kernel mount entirely — uses smbclient in userspace.)"
if command -v smbclient >/dev/null; then
    if [[ -r "${CREDS}" ]]; then
        echo "  Using credentials from ${CREDS}"
        timeout 30 smbclient -L "//${SERVER}/" -A "${CREDS}" 2>&1 | sed 's/^/  /'
    else
        echo "  ${CREDS} not readable by $(whoami) — try: sudo bash $0"
        echo "  Skipping SMB NEGOTIATE test."
    fi
else
    echo "  smbclient not installed — install with: sudo apt install -y smbclient"
fi
echo

echo "--- 4. SMB directory listing (read op on target share) ---"
if command -v smbclient >/dev/null && [[ -r "${CREDS}" ]]; then
    timeout 30 smbclient "//${SERVER}/${SHARE}" -A "${CREDS}" -c 'ls; exit' 2>&1 | sed 's/^/  /'
else
    echo "  Skipped (see above)."
fi
echo

echo "--- 5. Kernel CIFS state (session + op counts + errors) ---"
if [[ -r /proc/fs/cifs/DebugData ]]; then
    echo "  /proc/fs/cifs/DebugData (first 50 lines):"
    head -50 /proc/fs/cifs/DebugData 2>&1 | sed 's/^/    /'
else
    echo "  /proc/fs/cifs/DebugData not readable or no CIFS mount active"
fi
echo

if [[ -r /proc/fs/cifs/Stats ]]; then
    echo "  /proc/fs/cifs/Stats:"
    cat /proc/fs/cifs/Stats 2>&1 | sed 's/^/    /'
fi
echo

echo "--- 6. Current mount state ---"
mount | grep -E "cifs|${MOUNT}" | sed 's/^/  /' || echo "  no CIFS mounts"
echo

echo "--- 7. Kernel dmesg — CIFS/SMB messages (last 40) ---"
if [[ $(id -u) -eq 0 ]]; then
    dmesg 2>&1 | grep -iE 'cifs|smb' | tail -40 | sed 's/^/  /' || echo "  (none)"
else
    sudo -n dmesg 2>/dev/null | grep -iE 'cifs|smb' | tail -40 | sed 's/^/  /' \
        || echo "  need sudo: sudo dmesg | grep -iE 'cifs|smb' | tail -40"
fi
echo

echo "--- 8. Mount-layer smoke test (5s touch, then rm) ---"
PROBE="${MOUNT}/.diag-$(date +%s)-$$"
if timeout 5 touch "${PROBE}" 2>&1; then
    echo "  touch OK: ${PROBE}"
    timeout 5 rm -f "${PROBE}" 2>&1 && echo "  rm OK" || echo "  rm TIMED OUT"
else
    echo "  touch TIMED OUT or failed — mount is not writable right now"
fi
echo

echo "--- 9. Read throughput test (100KB, 5s timeout) ---"
timeout 5 dd if=/dev/zero "of=${MOUNT}/.diag-dd-$$" bs=1024 count=100 conv=fsync 2>&1 \
    | sed 's/^/  /'
timeout 5 rm -f "${MOUNT}/.diag-dd-$$" 2>/dev/null
echo

echo "==========================================================="
echo " End of diagnostic report."
echo
echo " Interpretation guide (for admins):"
echo "   - 1 & 2 FAIL: network/firewall between VM and Windows host is down."
echo "   - 1 & 2 OK, 3 FAILS: Windows host is up but SMB service is wedged."
echo "                       Restart LanmanServer on 10.10.10.21 (Services.msc),"
echo "                       or check Event Viewer > Applications and Services >"
echo "                       Microsoft > Windows > SMBServer > Operational."
echo "   - 1-4 OK, 8/9 FAIL: kernel CIFS client state is bad; umount -l + mount"
echo "                       should clear it on this host. Not a Windows problem."
echo "   - 'has not responded in 180 seconds' in #7: explicit server-side stall."
echo "==========================================================="
