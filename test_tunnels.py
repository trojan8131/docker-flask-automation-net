
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_inspect import nornir_inspect
from nornir_netmiko.tasks import netmiko_send_config,netmiko_send_command,netmiko_file_transfer
from nornir.core.inventory import Host,Group
from nornir_rich.functions import print_result
from pprint import pprint
import sys
import logging
import sys
import logging
import importlib
import subprocess

status="0"
# ! Inicjacja Nornira
nr = InitNornir("/opt/docker-flask-automation-net/static/nornir/config.yaml")
# ! Filtrowanie po hoście
nr=nr.filter(name="DC-R1")
# ! Sprawdzenie czy obraz jest juz na urządzeniu
result_dir = nr.run(task=netmiko_send_command,command_string="show crypto session detail", use_textfsm=True)
print(nornir_inspect(result_dir)) 
if result_dir["DC-R1"].failed:
    status="\"Problem z podłączeniem do urządzenia\""
else:
    if result_dir["DC-R1"].result==None:
        status="\"Brak Aktywnych Tunelów\""
    else:
        for session in result_dir["DC-R1"].result:
            if session["session_status"] != 'UP-ACTIVE':
                status=f'\"DC-R1, session to peer {session["peer"]}/{session.get("phase1_id","")} in {session["session_status"]}  Status\"'
            pprint(session)
        else:
            status="0"
    

args = ['zabbix_sender', '-z', '192.168.1.80', '-p', '10051', '-s', 'DC-R1', '-k', 'custom.network.session_error', '-o', status]

# Wywołaj polecenie zabbix_sender
try:
    subprocess.run(args, check=True)
    print("Polecenie zakończone pomyślnie.")
except subprocess.CalledProcessError as e:
    print(f"Błąd podczas wykonywania polecenia: {e}")