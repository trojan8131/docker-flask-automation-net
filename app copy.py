from flask import Flask, config, render_template, request, redirect, url_for, session, jsonify,send_file,send_from_directory,Response,stream_with_context
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate
import yaml
import time
from pyvis.network import Network

from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_inspect import nornir_inspect
from pyzabbix import ZabbixAPI,ZabbixAPIException
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, BooleanField,
                     RadioField,SubmitField,SelectMultipleField,SelectField)
from wtforms.validators import InputRequired, Length
from jinja2 import Template
import glob
from nornir_netmiko.tasks import netmiko_send_config,netmiko_send_command,netmiko_file_transfer
from nornir.core.inventory import Host,Group
from nornir_rich.functions import print_result

from nornir.core.filter import F
import pandas as pd
from unidecode import unidecode
from pymongo import *
import re
import ipaddress


import logging

############ Flask Config ##########
logger = logging.getLogger("flask")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.app_context().push()

try:
    print("RESTART")
except Exception as e:
    print(e)

########### MongoDB #############

client= MongoClient('172.19.0.7', 27017,username="autonet",password="password")
autonet_db=client.autonet
mongo_database= autonet_db.routery_stacje_benzynowe

########### Routes ###########



routes={" ":[["/inventory_nornir","Nornir Inventory","Urządzenia z hosts.yaml","success"],
["/petrol_station_database","Baza stacji beznzynowych","Baza w MongoDB","success"],
["/send_template","Wyślij komendy","Wyślij komendy na urządzenia","success"],
["/inventory","Inventura urządzeń","Stwórz tabelę z inventurą urządzeń","success"],
["/visualize_topology","Topologia sieci","Stwórz tabelę z inventurą urządzeń","success"],
["/upgrade_os_form","Upgrade Routera","Wyślij obraz bin na urządzenie","success"],
]
}



########### Forms #########

class DeviceForm(FlaskForm):
    device_name= StringField("Nazwa Urządzenia", validators=[InputRequired(),Length(min=2,max=10)])
    subnet = StringField('Adres podsieci', validators=[InputRequired()])
    snmp_community = RadioField('SNMP community',
                       choices=['public', 'store-zabbix', 'dc-zabbix'],
                       validators=[InputRequired()])
    vlan_dhcp = BooleanField('Vlan DHCP')
    send_config = BooleanField("Czy wysłać konfigurację do podłączonego urządzenia")


class StationForm(FlaskForm):
    location= StringField("Lokalizacja Stacji")
  #  public_ip= StringField(" Publiczny IP łącza WAN")

class RouterStartupConfig(FlaskForm):
    public_ip= StringField("Publiczny IP łącza WAN")
    login = StringField("Login do routera")
    password = StringField("Hasło do routera")
    lan_interface= StringField("Interfejs LAN")
    wan_interface= StringField("Interfejs WAN")
    vlan_dhcp = BooleanField('Vlan DHCP')

class SendCommands(FlaskForm):
    hosts=TextAreaField("Filtrowanie po Hostach")
    groups=SelectMultipleField("Filtrowanie po Grupach",choices=InitNornir(config_file="static/nornir/config.yaml").inventory.groups.values())
    commands=TextAreaField("Komendy do przesłania")

class UpgradeOS(FlaskForm):
    host = SelectField('Wybierz urządzenie', choices=[])
    image = SelectField('Wybierz Obraz IOS', choices=[])



############# Code ############


def clear(host):
    return False

def filter_hosts(host,hosts):
    if host.name in hosts:
        return True
    else:
        return False



def get_3_octets(subnet):
    return '.'.join(subnet.replace("/24","").split('.')[:3])

############# 

# * 
# !
# ?
# TODO:


#############


# * Strona Główna
@app.route("/")
def homepage():
    return render_template("base_site.html",routes=routes)

@app.route("/test")
def test():
    return render_template("test.html",routes=routes)


# * Inventory Nornir
@app.route("/inventory_nornir")
def inventory_nornir():
    inventory=yaml.load(open("static/nornir/hosts.yaml","r"),Loader=yaml.SafeLoader)
    return render_template("inventory_nornir.html",inventory=inventory)



# * Pobieranie podstawowych informacji o urządzeniu
@app.route("/nornir_facts/<device>")
def nornir_facts(device):
    nr=InitNornir(config_file="static/nornir/config.yaml")
    nr=nr.filter(name=device)
    result=nr.run(napalm_get,getters=["facts"])
    nornir_napalm_facts=result[device][0].result["facts"]
    return render_template("nornir_facts.html",nornir_napalm_facts=nornir_napalm_facts,device=device)


# * Baza Stacji benzynowych
@app.route('/petrol_station_database', methods=['POST',"GET"])
def petrol_station_database():
    stations=list(mongo_database.find().sort("number"))
    return render_template('petrol_station_database.html',stations=stations)



# * Dodanie Lokalizacji do bazy po wygenerowaniu podsieci i numeru stacji
@app.route('/petrol_station_database/add', methods=['POST',"GET"])
def petrol_station_database_add():
    form = StationForm()

    if form.validate_on_submit():
        
        ######## Wygenerowanie numeru sklepu #############
        
        used_numbers=[x["number"] for x in list(mongo_database.find())]
        number=None
        for number in range(1000,10000):
            if number not in used_numbers:
                break
        
        ######### Wygenerowanie wolnej adresacji IP ########
        
        core_subnet = ipaddress.IPv4Network("172.16.0.0/14")
        subnets_in_core_subnet=[str(x) for x in list(core_subnet.subnets(new_prefix=24))]
        used_subnets=[x["subnet"] for x in list(mongo_database.find())]
        subnet=None
        for subnet in subnets_in_core_subnet:
            if subnet not in used_subnets:
                break
        
        petrol_station={
            "number": number,
            "location": unidecode(form.location.data),
            "subnet"  :subnet,
         #   "public_ip" :form.public_ip.data,
        }

        try:
            # * Dodanie lokalizacji do bazy danych
            mongo_database.insert_one(petrol_station)
            
            # ! Dodanie routera do Inventory Nornirowego
            with open('static/nornir/hosts.yaml', 'a') as inventory_file:
                new_router ={
                            f"SB-R-{number}": {
                                "hostname": f"{'.'.join(subnet.split('.')[:3])}.255",
                                "groups": [
                                "SB-ROUTER"
                                ],
                                "data":{
                                    "location": form.location.data,
                                    "number": number,
                                    "subnet": subnet
                                }
                                
                            }
                            }
                            
                yaml.dump(new_router, inventory_file, default_flow_style=False)
                
                
            
        except Exception as error: 
            return render_template('petrol_station_database_add.html',form=form,error=error)
        
        # ! Dodanie urządzenia do Zabbixa
    
        zapi = ZabbixAPI("http://192.168.1.80")
        zapi.login("Admin", "zabbix")

        print("Connected to Zabbix API Version %s" % zapi.api_version())

        try:
            zapi.host.create(
            host=f"SB-R-{number}",
            interfaces={"type": 2,"main": 1,"useip": 1,"ip": get_3_octets(subnet)+".255","dns": "","port": "161","details":{"version":2,"bulk":1,"community":"{$SNMP_COMMUNITY}"},},
            groups={"groupid": "22",},
            templates={"templateid":"10218"},
            inventory_mode=0
            )
        except ZabbixAPIException as e:
            return render_template('petrol_station_database_add.html',form=form,error=e)
        
        
        
        
        
        
        
        return redirect(url_for("petrol_station_database"))

    return render_template('petrol_station_database_add.html',form=form)



# * Usunięcie z basy stacji, o danym numerze 
@app.route('/petrol_station_database/delete/<int:number>', methods=['POST',"GET"])
def petrol_station_database_delete(number):
    mongo_database.find_one_and_delete({"number":number})
    
    # ! usuwanie routera z inventory nornirowego
    with open('static/nornir/hosts.yaml', 'r') as file:
        nornir_inventory = yaml.safe_load(file)
        
    if f'SB-R-{number}' in nornir_inventory:
        del nornir_inventory[f'SB-R-{number}']
        
    with open('static/nornir/hosts.yaml', 'w') as file:
        yaml.dump(nornir_inventory, file, default_flow_style=False)
    
    zapi = ZabbixAPI("http://192.168.1.80")
    zapi.login("Admin", "zabbix")

    print("Connected to Zabbix API Version %s" % zapi.api_version())

    host= zapi.host.get(output=['hostids', 'host'],filter={"host":[f'SB-R-{number}']})
    zapi.host.delete(int(host[0]["hostid"]))
    return redirect(url_for("petrol_station_database"))



@app.route('/router_config_form_startup/<int:number>', methods=['POST',"GET"])
def router_config_form_startup(number):
    form=RouterStartupConfig()
    error=None
    if form.validate_on_submit():
        data_for_template=mongo_database.find_one({"number":number})
        data_for_template["public_ip"]=form.public_ip.data
        data_for_template["lan_interface"]=form.lan_interface.data
        data_for_template["wan_interface"]=form.wan_interface.data
        data_for_template["vlan_dhcp"]=form.vlan_dhcp.data
        data_for_template["hostname"]=f"SB-R-{number}"
        data_for_template["prefix"]=get_3_octets(data_for_template["subnet"])
        
        mongo_database.find_one_and_replace({"number":number},data_for_template)
        
        # ! Renderowanie konfiguracji
        print(data_for_template)
        with open("static/templates_jinja/router_config.j2") as file:
            cisco_template= Template(file.read())
        template=cisco_template.render(data_for_template)
        
        
        # ! Przesłanie konfiguracji na router
        nr= InitNornir("static/nornir/config.yaml")
        nr=nr.filter(clear)
        router= Host(
            name="router",
            hostname=form.public_ip.data,
            platform="cisco_ios",
            username=form.login.data,
            password=form.password.data
        )
        nr.inventory.hosts["router"]=router
        result=nr.run(netmiko_send_config,config_commands=template.splitlines(),read_timeout=120,cmd_verify= False)
        print(nornir_inspect(result))
        if result["router"][0].failed:
            error="Problem z podłączeniem do urządzenia"
            result=""
        else:
            result=result["router"][0].result
        
        
        
        return render_template('router_config.html',result=result.replace("\n","<br>"),error=error)
    
    return render_template('router_config_form_startup.html',form=form)


############################################


@app.route('/oxidized', methods=['POST',"GET"])
def oxidized():
    with open('static/nornir/hosts.yaml', 'r') as file:
        nornir_inventory = yaml.safe_load(file)
    router_db=[]
    for device_name,data in nornir_inventory.items():
        router_db.append({"name":device_name,"group":data["groups"][0],"model":"ios","ip":data["hostname"]})
    return router_db


############################################

@app.route('/send_template', methods=['POST',"GET"])
def send_template():

    def send_commands(task,commands):
        try:
            result=task.run(task=netmiko_send_config,config_commands=commands,read_timeout=120,cmd_verify= False)
            task.host["output"]=str(result.result).replace("\n","<br>")
            task.host["status"]="Przesłane"
        except Exception as e:
            task.host["output"]="Wystąpił Błąd"
            task.host["status"]="Wystąpił Błąd"            


    form=SendCommands()

    if form.is_submitted():
        hosts=form.hosts.data
        groups=form.groups.data
        commands=form.commands.data
        print(hosts)
        print(groups)
        # ! Filtrowanie inventory
        nr= InitNornir("static/nornir/config.yaml")
        if hosts:
            nr=nr.filter(filter_hosts,hosts=hosts.splitlines())
        if groups:
            nr=nr.filter(F(groups__any=groups))
        
        # ! Przesłanie komend
        print(nr.inventory.hosts)
        nr.run(task=send_commands,commands=commands.splitlines())
        nr.close_connections()

        # ! Pobranie wyniku
        output_table={}


        
        
        for host_name, values in nr.inventory.hosts.items():
            output_table[host_name]={"status":values["status"],"output":values["output"]}
        
        return render_template('send_template_table.html',output_table=output_table)



    return render_template('send_template.html',form=form)

####################################
@app.route('/inventory', methods=['POST',"GET"])
def inventory():
    def inventory_nornir_task(task):
        try:
            details=task.run(task=napalm_get,getters=["get_interfaces_ip","get_facts","get_snmp_information"])
        except:
            task.host["data"]={"Status":"Problem pobraniem danych","Hostname":task.host.name}

        facts=details.result["get_facts"]
        version=facts["os_version"]    
        regex=r"(Version\s\d+\.\d+)"
        matches=re.search(regex,version)
        if matches:
            version=matches.group(1)
        ip_prefix_list=[]
        for interface,data in details.result["get_interfaces_ip"].items():
            try:
                for address,prefix in data["ipv4"].items():
                    ip_prefix_list.append(f"{interface}: {address}/{prefix['prefix_length']}")
            except:
                pass
        ip_prefix_string=" , ".join(ip_prefix_list)
        task.host["data"]={"Hostname":facts["hostname"],
                            "Uptime": facts["uptime"],
                            "Model":facts["model"],
                            "Vendor":facts["vendor"],
                            "Serial_number":facts["serial_number"],
                            "Version":version,
                            "Location":details.result["get_snmp_information"]["location"],
                            "IPs":ip_prefix_string,
                            "Status":"Dane pobrane prawidłowo"  }

    # ! Nornir 

    nr = InitNornir("static/nornir/config.yaml")
    nr.run(task=inventory_nornir_task)
    nr.close_connections()

    # ! Pobranie wyników
    data_table={}
    for host_name,values in nr.inventory.hosts.items():
        data_table[host_name]=values["data"]
    dataframe=pd.DataFrame([x for x in data_table.values()])
    filepath="static/files/inwentura.xlsx"
    dataframe.to_excel(filepath,index=True)


    return render_template('inventory.html',data_table=data_table)


@app.route('/download_inventory', methods=['POST',"GET"])
def download_inventory():
    filepath = 'static/files/inwentura.xlsx'
    return send_file(filepath, as_attachment=True)



@app.route('/visualize_topology', methods=['POST',"GET"])
def visualize_topology():
    cdp_neighbors={}
    def find_neighbors(task):
        try:
            result_facts=task.run(task=napalm_get,getters=["get_facts"])
            print(result_facts.result["get_facts"])
            result=task.run(task=netmiko_send_command,command_string="show cdp neighbors detail", use_textfsm=True)
            task.host["data"]=[]
            for neighbor in result.result:
                #task.host["data"].append([neighbor["destination_host"],f'{result_facts.result["get_facts"]["fqdn"]}--{neighbor["local_port"]}\n{neighbor["destination_host"]}--{neighbor["remote_port"]}\n'])
                task.host["data"].append([neighbor["destination_host"],neighbor["local_port"],neighbor["remote_port"]])

                task.host["fqdn"]=result_facts.result["get_facts"]["fqdn"]
        except:
            task.host["data"]=[]
            task.host["fqdn"]=task.host.name
    # Przykładowe dane z sąsiadami CDP
    nr = InitNornir("static/nornir/config.yaml")
    result=nr.run(task=find_neighbors)
    #print(nornir_inspect(result))
    nr.close_connections()
    cdp_neighbors={}
    for host_name,values in nr.inventory.hosts.items():
        cdp_neighbors[values["fqdn"]]=values["data"]

    # cdp_neighbors = {
    #     "Switch1": {"Switch2": "Ethernet1/1", "Switch3": "Ethernet1/2"},
    #     "Switch2": {"Switch1": "Ethernet1/1", "Switch4": "Ethernet1/2"},
    #     "Switch3": {"Switch1": "Ethernet1/2", "Switch4": "Ethernet1/1"},
    #     "Switch4": {"Switch2": "Ethernet1/2", "Switch3": "Ethernet1/1"},
    # }

    # Inicjalizacja obiektu Network
    net = Network('1080px','1920px',directed=True)
    # Dodanie wierzchołków (urządzeń)
    for switch in cdp_neighbors:
        if cdp_neighbors[switch]==[]:
            
            net.add_node(switch, label=switch, color = 'red')
        net.add_node(switch, label=switch,color="#2a5760")

    # Dodanie połączeń między wierzchołkami (połączenia CDP)
    in_graph=[]
    for local_switch, neighbors in cdp_neighbors.items():
        for x in neighbors:
            
            
            remote_switch=x[0]
            port1=x[1]
            port2=x[2]
            if [local_switch,port2,port1] not in in_graph:
                in_graph.append(x)
                net.add_edge(local_switch, remote_switch, label=f'{port1 } --- {port2}')
        

  # Wygenerowanie i zapisanie grafu do pliku HTML
    net.set_options('''const options = {
  "nodes": {
    "font": {
      "size": 13,
    "strokeWidth": 5
    }
  },
  "edges": {
    "color": {
      "inherit": true
    },
    "font": {
      "size": 10,
      "align": "top"
    },
    "selfReferenceSize": null,
    "selfReference": {
      "angle": 0.7853981633974483
    }
  },
  "physics": {
    "barnesHut": {
      "springLength": 355
    }
  }
}''')
    
    #net.show_buttons(filter_=[ 'nodes','edges', 'physics'])
    net.show("templates/visualize_topology.html", notebook=False)

    return render_template('visualize_topology.html')





@app.route('/upgrade_os_form', methods=['POST',"GET"])
def upgrade_os_form():
    # ! Utworzenie formularza
    form=UpgradeOS()
    # ! Wypełnienie hostami
    nr = InitNornir("static/nornir/config.yaml")
    form.host.choices=[(host, host) for host in nr.inventory.hosts.keys()]

    # ! Wypełnienie obrazami z dysku
    path="/opt/ios_files/"
    files = glob.glob(f'{path}*.bin')
    form.image.choices=[(image.replace(path,""), image.replace(path,"")) for image in files]
    return render_template('upgrade_os_form.html',form=form)














# * Start serwisu
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")