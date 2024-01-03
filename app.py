from flask import Flask, config, render_template, request, redirect, url_for, session, jsonify,send_file,send_from_directory
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate
import yaml




app = Flask(__name__)


routes={}
routes["Odcinek 12"]=[["/inventory_nornir","Nornir Inventory","","success"]]

@app.route("/")
def homepage():
    return render_template("base_site.html",routes=routes)


@app.route("/inventory_nornir")
def inventory_nornir():
    inventory=yaml.load(open("static/nornir/hosts.yaml","r"),Loader=yaml.SafeLoader)
    return render_template("inventory_nornir.html",inventory=inventory)



if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")