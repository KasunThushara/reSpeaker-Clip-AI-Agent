import atexit
import logging

from flask import Flask, render_template, send_from_directory
from flask_cors import CORS
from backend.routes import register_routes
from backend.database import init_db
from backend.clip.store import init_clip_ingestions
from backend.vector import init_index
from backend.clip.worker import ClipWorker
from config import settings

logging.basicConfig(level=logging.INFO)


def start_clip_worker(app, factory=None) -> ClipWorker | None:
    """Attach the Clip worker to the app.

    ``factory`` is used by tests to inject a fake worker object; otherwise a
    real :class:`ClipWorker` is started on its daemon thread.
    """
    if factory is not None:
        worker = factory()
    else:
        worker = ClipWorker()
        worker.start()
        atexit.register(worker.stop)
    app.extensions["clip_worker"] = worker
    app.config["CLIP_ENABLED"] = True
    return worker


def create_app(clip_enabled: bool | None = None, clip_factory=None) -> Flask:
    app = Flask(
        __name__,
        static_folder="frontend/static",
        template_folder="frontend/templates",
    )
    CORS(app)

    register_routes(app)
    init_db()
    init_clip_ingestions()
    init_index()

    if clip_enabled is None:
        clip_enabled = settings.VOICE_INPUT_MODE in ("clip", "both")
    if clip_enabled:
        start_clip_worker(app, factory=clip_factory)

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            clip_config={
                "input_mode": settings.VOICE_INPUT_MODE,
                "clip_enabled": app.extensions.get("clip_worker") is not None,
                "record_mode": settings.CLIP_RECORD_MODE,
            },
        )

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory("frontend/static", filename)

    return app


if __name__ == "__main__":
    app = create_app()
    # The Flask reloader must stay off: the Clip runtime owns one BLE
    # connection per process and a reload would fork a second owner.
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
