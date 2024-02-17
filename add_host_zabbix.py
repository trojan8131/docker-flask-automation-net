from pyzabbix import ZabbixAPI,ZabbixAPIException

zapi = ZabbixAPI("http://192.168.1.80")
zapi.login("Admin", "zabbix")

print("Connected to Zabbix API Version %s" % zapi.api_version())

for h in zapi.host.get(output="extend"):
    print(h['hostid'])
try:
    zapi.host.create(
    host="SB-R-1002",
    interfaces={"type": 2,"main": 1,"useip": 1,"ip": "172.16.2.255","dns": "","port": "161","details":{"version":2,"bulk":1,"community":"public"},},
    groups={"groupid": "22",},
    templates={"templateid":"10218"},
    inventory_mode=0
    )
except ZabbixAPIException as e:
    print("Error",e)