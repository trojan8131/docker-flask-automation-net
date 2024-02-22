from pyzabbix import ZabbixAPI,ZabbixAPIException

zapi = ZabbixAPI("http://192.168.1.80")
zapi.login("Admin", "zabbix")

print("Connected to Zabbix API Version %s" % zapi.api_version())

host= zapi.host.get(output=['hostids', 'host'],filter={"host":["SB-R-1003"]})
zapi.host.delete(int(host[0]["hostid"]))

# try:
#     zapi.host.create(
#     host="ISP-R1",
#     interfaces={"type": 2,"main": 1,"useip": 1,"ip": "13.0.0.2","dns": "","port": "161","details":{"version":2,"bulk":1,"community":"public"},},
#     groups={"groupid": "22",},
#     templates={"templateid":"10218"},
#     inventory_mode=0
#     )
# except ZabbixAPIException as e:
#     print("Error",e)