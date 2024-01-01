from flask import Flask, config, render_template, request, redirect, url_for, session, jsonify,send_file,send_from_directory
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate

app = Flask(__name__)


routes={}
routes["Szablony"]=[["/templates_router","Szablony dla routera","Opis","warning"]]


@app.route("/")
def homepage():
    return render_template("base_site.html",routes=routes)

@app.route("/templates_router")
def templates_router():
    return render_template("templates_router.html")



if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")