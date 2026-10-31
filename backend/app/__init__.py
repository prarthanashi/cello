"""BenefitBridge backend application factory."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from types import SimpleNamespace

from flask import Flask, g, jsonify, request

from .catalogue import load_catalogue
from .config import Settings, load_settings
from .retrieval import KeywordRetriever, ingest_documents
from .routes import bp, err

log = logging.getLogger("benefitbridge")


def create_app(settings: Settings | None = None, *, catalogue=None, retriever=None, today=None) -> Flask:
    settings = settings or load_settings()
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # profiles/questions are tiny

    if catalogue is None:  # NB: an empty Catalogue is falsy, so never use `or` here
        catalogue = load_catalogue(settings.data_path, settings.official_domain_suffixes)
    warnings: list[str] = []
    if retriever is None:
        chunks, warnings = ingest_documents(settings.documents_path, catalogue)
        retriever = KeywordRetriever(chunks)
    app.extensions["bb"] = SimpleNamespace(
        settings=settings, catalogue=catalogue, retriever=retriever,
        today=today or date.today, ingestion_warnings=warnings)
    app.register_blueprint(bp)

    @app.before_request
    def _start():
        g.request_id = uuid.uuid4().hex[:12]
        g.started = time.perf_counter()

    @app.after_request
    def _finish(resp):
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and origin in settings.frontend_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Vary"] = "Origin"
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        # Minimal operational log: no query string, body, question text or profile data.
        log.info("req id=%s %s %s -> %s %.0fms", getattr(g, "request_id", "-"), request.method,
                 request.path, resp.status_code, (time.perf_counter() - getattr(g, "started", time.perf_counter())) * 1000)
        return resp

    @app.errorhandler(404)
    def _404(_):
        return err("not_found", "That endpoint does not exist.", 404)

    @app.errorhandler(405)
    def _405(_):
        return err("method_not_allowed", "That method is not allowed for this endpoint.", 405)

    @app.errorhandler(413)
    def _413(_):
        return err("payload_too_large", "The request is too large.", 413)

    @app.errorhandler(Exception)
    def _500(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return err(exc.name.lower().replace(" ", "_"), exc.description or exc.name, exc.code or 500)
        log.error("unhandled_error id=%s category=%s", getattr(g, "request_id", "-"), type(exc).__name__)
        return err("internal_error", "Something went wrong. Please try again.", 500)

    return app
