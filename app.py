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

############ Flask Config ##########

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'



########### MongoDB #############

client= MongoClient('172.19.0.7', 27017,username="autonet",password="password")
autonet_db=client.autonet
mongo_database= autonet_db.routery_stacje_benzynowe

#Inicjalizacja bazy
# index_model = ["number","location","subnet","public_ip"]
# for index in index_model:
#     mongo_database.create_index(index, unique=True)

# Dodawanie obietków
# petrol_station={
#     "number": 1000,
#     "location": "Warszawa Parkowa",
#     "subnet": "172.16.0.0/24",
#     "public_ip": "3.4.5.6"
# }
# mongo_database.insert_one(petrol_station)

########### Routes ###########



routes={"Odcinek 13/14":[["/inventory_nornir","Nornir Inventory","Urządzenia z hosts.yaml","success"]],
        "Odcinek 15/16":[["/router_config_form","Formularz konfiguracji","Formularz konfiguracji routera","success"]],
        "Odcinek 17":[["/petrol_station_database","Baza stacji beznzynowych","Baza w MongoDB","success"]]
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





############# Code ############

@app.route("/")
def homepage():
    return render_template("base_site.html",routes=routes)


@app.route("/inventory_nornir")
def inventory_nornir():
    inventory=yaml.load(open("static/nornir/hosts.yaml","r"),Loader=yaml.SafeLoader)
    return render_template("inventory_nornir.html",inventory=inventory)

@app.route("/nornir_facts/<device>")
def nornir_facts(device):
    nr=InitNornir(config_file="static/nornir/config.yaml")
    nr=nr.filter(name=device)
    result=nr.run(napalm_get,getters=["facts"])
    nornir_napalm_facts=result[device][0].result["facts"]
    return render_template("nornir_facts.html",nornir_napalm_facts=nornir_napalm_facts,device=device)

@app.route('/router_config_form', methods=['POST',"GET"])
def router_config_form():
    def clear(host):
        return False



    form=DeviceForm()
    error=None
    if form.validate_on_submit():
        data={
            "device_name": form.device_name.data,
            "subnet" : ".".join(form.subnet.data.split(".")[:3]),
            "snmp_community" : form.snmp_community.data,
            "vlan_dhcp":form.vlan_dhcp.data
        }
        with open("static/templates_jinja/router_config.j2") as file:
            cisco_template= Template(file.read())
        result=cisco_template.render(data)

        if form.send_config.data:
            nr= InitNornir("static/nornir/config.yaml")
            nr=nr.filter(clear)
            new_host= Host(
                name="console",
                hostname="192.168.1.80",
                platform="cisco_ios_telnet",
                port="2000"
            )
            nr.inventory.hosts["console"]=new_host
            result=nr.run(netmiko_send_config,config_commands=result.splitlines())

            if result["console"][0].failed:
                error="Problem z podłączeniem do urządzenia"
                result=""
            else:
                result=result["console"][0].result




        return render_template('router_config.html',result=result.replace("\n","<br>"),error=error)

    return render_template('router_config_form.html', form=form)


@app.route('/petrol_station_database', methods=['POST',"GET"])
def petrol_station_database():
    stations=list(mongo_database.find().sort("number"))
    return render_template('petrol_station_database.html',stations=stations)

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")