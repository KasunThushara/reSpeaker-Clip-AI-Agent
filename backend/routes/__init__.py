from backend.routes.health import health_bp
from backend.routes.chat import chat_bp
from backend.routes.voice import voice_bp
from backend.routes.tts import tts_bp
from backend.routes.clip import clip_bp


def register_routes(app):
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(voice_bp, url_prefix="/api")
    app.register_blueprint(tts_bp, url_prefix="/api")
    app.register_blueprint(clip_bp, url_prefix="/api")
