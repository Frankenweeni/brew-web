from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required
from app.utils import role_required
from app.models import GeneralNote, db

notes_bp = Blueprint("notes_bp", __name__, url_prefix="/notes")

# Same drink types and order as the Home/Recipes page
CATEGORIES = [
    ("Mead", "🍯 Mead"),
    ("Wine", "🍷 Wine"),
    ("Beer", "🍺 Beer"),
    ("Hard Cider", "🍎 Hard Cider"),
    ("General", "📦 General"),
]
CATEGORY_KEYS = {key for key, _ in CATEGORIES}


def _notes_by_category():
    return {n.category: n for n in GeneralNote.query.all()}


@notes_bp.route("/", methods=["GET"])
@login_required
def view_notes():
    return render_template("notes.html", categories=CATEGORIES, notes=_notes_by_category())


@notes_bp.route("/<category>", methods=["POST"])
@login_required
@role_required("admin", "editor")
def save_notes(category):
    if category not in CATEGORY_KEYS:
        abort(404)
    note = GeneralNote.query.filter_by(category=category).first()
    if note is None:
        note = GeneralNote(category=category)
        db.session.add(note)
    note.content = request.form.get("content", "")
    db.session.commit()
    flash(f"{category} notes saved.", "success")
    return redirect(url_for("routes.notes_bp.view_notes") + "#notes-" + category.replace(" ", "-"))
