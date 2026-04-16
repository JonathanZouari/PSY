import logging
import os
import traceback
import uuid
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, request
from flask_cors import CORS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("backend.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

from services.analysis import analyze
from services.auth import require_auth
from services.supabase_client import get_storage_bucket, get_supabase
from services.transcription import transcribe

app = Flask(__name__)
CORS(
    app,
    origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5500")],
    supports_credentials=True,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _set_status(recording_id: str, status: str, error: str | None = None) -> None:
    payload = {"status": status}
    if error is not None:
        payload["error_message"] = error
    get_supabase().table("recordings").update(payload).eq("id", recording_id).execute()


def _process_recording(recording_id: str, audio_bytes: bytes, filename: str) -> None:
    sb = get_supabase()
    try:
        _set_status(recording_id, "transcribing")
        transcript = transcribe(audio_bytes, filename=filename)

        sb.table("analyses").insert(
            {"recording_id": recording_id, "transcript": transcript}
        ).execute()

        _set_status(recording_id, "analyzing")
        result = analyze(transcript)

        sb.table("analyses").update(
            {
                "summary": result["summary"],
                "key_points": result["key_points"],
                "topics": result["topics"],
                "tasks": result["tasks"],
                "sentiment": result["sentiment"],
                "sentiment_explanation": result["sentiment_explanation"],
                "entities": result["entities"],
            }
        ).eq("recording_id", recording_id).execute()

        _set_status(recording_id, "done")
    except Exception as exc:
        _set_status(recording_id, "failed", error=str(exc)[:500])
        raise


@app.post("/api/recordings")
@require_auth
def create_recording():
    if "file" not in request.files:
        return jsonify({"error": "missing_file"}), 400

    upload = request.files["file"]
    audio_bytes = upload.read()
    if not audio_bytes:
        return jsonify({"error": "empty_file"}), 400

    filename = upload.filename or "audio.webm"
    duration = request.form.get("duration_seconds", type=int)

    sb = get_supabase()
    bucket = get_storage_bucket()
    recording_id = str(uuid.uuid4())
    storage_path = f"{g.user_id}/{recording_id}.webm"

    sb.storage.from_(bucket).upload(
        path=storage_path,
        file=audio_bytes,
        file_options={"content-type": upload.mimetype or "audio/webm"},
    )

    sb.table("recordings").insert(
        {
            "id": recording_id,
            "user_id": g.user_id,
            "audio_path": storage_path,
            "duration_seconds": duration,
            "status": "pending",
        }
    ).execute()

    _process_recording(recording_id, audio_bytes, filename)

    return jsonify({"recording_id": recording_id, "status": "done"}), 201


@app.get("/api/recordings")
@require_auth
def list_recordings():
    sb = get_supabase()
    rows = (
        sb.table("recordings")
        .select("id,created_at,duration_seconds,status,analyses(summary)")
        .eq("user_id", g.user_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    items = []
    for r in rows.data or []:
        a = r.get("analyses")
        if isinstance(a, list):
            a = a[0] if a else None
        summary = a.get("summary") if a else None
        items.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "duration_seconds": r.get("duration_seconds"),
                "status": r["status"],
                "summary": summary,
            }
        )
    return jsonify({"items": items})


@app.get("/api/recordings/<recording_id>")
@require_auth
def get_recording(recording_id: str):
    sb = get_supabase()
    rec = (
        sb.table("recordings")
        .select("*,analyses(*)")
        .eq("id", recording_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not rec.data:
        abort(404)

    analysis = rec.data.get("analyses")
    if isinstance(analysis, list):
        analysis = analysis[0] if analysis else None

    bucket = get_storage_bucket()
    audio_url = None
    try:
        signed = sb.storage.from_(bucket).create_signed_url(
            rec.data["audio_path"], int(timedelta(minutes=10).total_seconds())
        )
        audio_url = signed.get("signedURL") or signed.get("signed_url")
    except Exception:
        pass

    return jsonify(
        {
            "id": rec.data["id"],
            "created_at": rec.data["created_at"],
            "duration_seconds": rec.data.get("duration_seconds"),
            "status": rec.data["status"],
            "error_message": rec.data.get("error_message"),
            "audio_url": audio_url,
            "analysis": analysis,
        }
    )


@app.get("/api/recordings/<recording_id>/status")
@require_auth
def get_status(recording_id: str):
    sb = get_supabase()
    row = (
        sb.table("recordings")
        .select("status,error_message")
        .eq("id", recording_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not row.data:
        abort(404)
    return jsonify(row.data)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "not_found"}), 404


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES}), 413


@app.errorhandler(Exception)
def handle_exception(exc):
    tb = traceback.format_exc()
    logging.error("Unhandled exception: %s\n%s", exc, tb)
    return jsonify({"error": "internal_error", "type": type(exc).__name__, "message": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
