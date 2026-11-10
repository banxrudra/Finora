from urllib.parse import urlparse

from flask import abort, request, url_for
from flask_login import current_user

from ..extensions import db


def owned(model, obj_id):
    """Fetch a row by id that belongs to the current user, else 404.

    Returning 404 (not 403) avoids leaking whether another user's id exists.
    """
    obj = db.session.get(model, obj_id)
    if obj is None or obj.user_id != current_user.id:
        abort(404)
    return obj


def back(default_endpoint: str, **kwargs) -> str:
    """Return to the referring page on this host, else a default."""
    ref = request.form.get("next") or request.referrer
    if ref:
        p = urlparse(ref)
        if (not p.netloc or p.netloc == request.host) and p.path.startswith("/"):
            return p.path + (f"?{p.query}" if p.query else "")
    return url_for(default_endpoint, **kwargs)
