# -*- coding: utf-8 -*-
"""设备预警看板 - Flask 入口

启动：python app.py   （默认 0.0.0.0:8092，同网段可访问）
"""
import logging
from pathlib import Path

from flask import Flask, send_from_directory

import config.settings as settings
from auth import models as auth
from api.routes import bp as api_bp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("board")

WEB_DIR = Path(__file__).resolve().parent / "web"


def create_app():
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
    app.secret_key = settings.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # 初始化内置用户库
    auth.init_db()

    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/<path:name>")
    def static_files(name):
        return send_from_directory(WEB_DIR, name)

    return app


if __name__ == "__main__":
    app = create_app()
    logger.info("设备预警看板启动: http://%s:%s", settings.BOARD_HOST, settings.BOARD_PORT)
    app.run(host=settings.BOARD_HOST, port=settings.BOARD_PORT, debug=False)
