from flask import Flask, config, render_template, request, redirect, url_for, session, jsonify,send_file,send_from_directory
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate
import yaml

from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_inspect import nornir_inspect

from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, BooleanField,
                     RadioField,SubmitField)
from wtforms.validators import InputRequired, Length
from jinja2 import Template

from nornir_netmiko.tasks import netmiko_send_config
from nornir.core.inventory import Host,Group
from nornir_rich.functions import print_result

from pymongo import *

import ipaddress


############ Flask Config ##########

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'

########### MongoDB #############

client= MongoClient('172.19.0.7', 27017,username="autonet",password="password")
autonet_db=client.autonet
mongo_database= autonet_db.routery_stacje_benzynowe

########### Routes ###########



routes={" ":[["/inventory_nornir","Nornir Inventory","Urządzenia z hosts.yaml","success"],
["/petrol_station_database","Baza stacji beznzynowych","Baza w MongoDB","success"]]
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
############# Code ############


def clear(host):
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
            "location": form.location.data,
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
                
                
            return redirect(url_for("petrol_station_database"))
        except Exception as error: 
            return render_template('petrol_station_database_add.html',form=form,error=error)


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
        result=nr.run(netmiko_send_config,config_commands=template.splitlines())
        print(nornir_inspect(result))
        if result["router"][0].failed:
            error="Problem z podłączeniem do urządzenia"
            result=""
        else:
            result=result["router"][0].result
        
        
        
        return render_template('router_config.html',result=result.replace("\n","<br>"),error=error)
    
    return render_template('router_config_form_startup.html',form=form)


@app.route('/oxidized', methods=['POST',"GET"])
def oxidized():
    with open('static/nornir/hosts.yaml', 'r') as file:
        nornir_inventory = yaml.safe_load(file)
    router_db=[]
    for device_name,data in nornir_inventory.items():
        router_db.append({"name":device_name,"group":data["groups"][0],"model":"ios","ip":data["hostname"]})
    return router_db








# * Start serwisu
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")