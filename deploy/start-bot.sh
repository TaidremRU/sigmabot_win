#!/usr/bin/env bash
# Поднять SigmaSteamBot на VM после /stopbot: включает и запускает задачу планировщика.
# (после /stopbot задача ОТКЛЮЧЕНА, поэтому нужен именно Enable, потом Start.)
#
# Переменные окружения (значения по умолчанию в скобках):
#   SIGMA_VM_HOST (192.168.0.106)  SIGMA_VM_USER (alex)
#   SIGMA_VM_PASS (1)              SIGMA_TASK    (SigmaSteamBot)
#   SIGMA_BASE_DIR (C:\Users\alex\gamebot\stage2)  — только для подсказки про логи
set -euo pipefail

HOST="${SIGMA_VM_HOST:-192.168.0.106}"
USER_="${SIGMA_VM_USER:-alex}"
PASS="${SIGMA_VM_PASS:-1}"
TASK="${SIGMA_TASK:-SigmaSteamBot}"
BASE="${SIGMA_BASE_DIR:-C:\\Users\\alex\\gamebot\\stage2}"

command -v sshpass >/dev/null || { echo "нужен sshpass (apt install sshpass)"; exit 1; }

echo ">> ${USER_}@${HOST}: включаю и запускаю ${TASK}"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${USER_}@${HOST}" \
  "powershell -NoProfile -Command \"Enable-ScheduledTask -TaskName '$TASK' | Out-Null; Start-ScheduledTask -TaskName '$TASK'; Start-Sleep -Seconds 3; Get-ScheduledTask -TaskName '$TASK' | Format-Table TaskName,State -AutoSize\""

echo ">> посмотреть лог:"
echo "   sshpass -p '***' ssh ${USER_}@${HOST} 'powershell -NoProfile -Command \"Get-Content ${BASE}\\logs\\supervisor.log -Tail 15\"'"
