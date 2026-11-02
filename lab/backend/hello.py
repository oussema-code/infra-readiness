"""Disposable lab API, adapted from docker/awesome-compose; see ../UPSTREAM.md."""

import os
import time

from flask import Flask, jsonify
import pymysql

server = Flask(__name__)


@server.get("/live")
def live():
    return jsonify(status="alive")


@server.get("/ready")
def ready():
    try:
        with pymysql.connect(
            host="db", user="lab", password=os.environ["LAB_DB_PASSWORD"],
            database="example", connect_timeout=1, read_timeout=1, write_timeout=1,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT title FROM blog ORDER BY id")
                titles = [row[0] for row in cursor.fetchall()]
        if titles != ["Lab post #1", "Lab post #2"]:
            return jsonify(status="not_ready", reason="unexpected_seed_data"), 503
        return jsonify(status="ready", verified_records=len(titles))
    except pymysql.MySQLError:
        return jsonify(status="not_ready", reason="database_query_failed"), 503


@server.get("/slow-ready")
def slow_ready():
    """Fixed delay for the local deadline exercise; normal health routes stay fast."""
    time.sleep(3)
    return ready()


@server.get("/")
def index():
    return jsonify(service="infrastructure-readiness-lab", endpoints=["/live", "/ready", "/slow-ready"])
