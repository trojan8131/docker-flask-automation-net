from flask import Flask, config, render_template, request, redirect, url_for, session, jsonify,send_file,send_from_directory
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate
import yaml

from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_utils.plugins.functions import print_result
from nornir_inspect import nornir_inspect

from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, BooleanField,
                     RadioField)
from wtforms.validators import InputRequired, Length
from jinja2 import Template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'

routes={"Odcinek 12":[["/inventory_nornir","Nornir Inventory","Urządzenia z hosts.yaml","success"]],
        "Odcinek 15":[["/router_config_form","Formularz konfiguracji","Formularz konfiguracji routera","success"]]
}

class DeviceForm(FlaskForm):
    device_name= StringField("Nazwa Urządzenia", validators=[InputRequired(),Length(min=2,max=10)])
    subnet = StringField('Adres podsieci', validators=[InputRequired()])
    snmp_community = RadioField('SNMP community',
                       choices=['public', 'store-zabbix', 'dc-zabbix'],
                       validators=[InputRequired()])
    vlan_dhcp = BooleanField('Vlan DHCP')






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
    form=DeviceForm()

    if form.validate_on_submit():
        data={
            "device_name": form.device_name.data,
            "subnet" : ".".join(form.subnet.data.split(".")[:3]),
            "snmp_community" : form.snmp_community.data,
            "vlan_dhcp":form.vlan_dhcp.data
        }
        with open("static/templates_jinja/router_config.j2") as file:
            cisco_template= Template(file.read(), keep_trailing_newline=True)
        
        cisco_config=cisco_template.render(data)
        return render_template('router_config.html',config=cisco_config.replace("\n","<br>"))

    return render_template('router_config_form.html', form=form)








if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")