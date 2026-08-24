from flask import Flask, send_from_directory
from flask_cors import CORS
from backend.routes import register_routes
from backend.database import init_db
from backend.vector import init_index


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="frontend/static",
        template_folder="frontend/templates",
    )
    CORS(app)

    register_routes(app)
    init_db()
    init_index()

    @app.route("/")
    def index():
        from flask import render_template

        return render_template("index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory("frontend/static", filename)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
