"""Bridge legacy interactive-course artifacts into native study courses.

The old workspace remains the owner of tutorials, assignments, projects, and
learner submissions during migration. Native Courses becomes the canonical
container: it owns the syllabus, resource references, progress surfaces, and
course-scoped conversations. Stable shared ids let both sides refer to the same
course without a permanent mapping table.
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.courses import (
    COURSE_COLORS,
    CourseNotFoundError,
    CourseService,
    get_course_service,
)

from .engine import CourseEngine, get_course_engine
from .models import ClassStatus, CourseClass, CourseStatus


def _syllabus_units(
    classes: list[CourseClass], completed_class_ids: set[str]
) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for item in classes:
        topics = [
            str(point.get("name") or "").strip()
            for point in item.knowledge_points
            if str(point.get("name") or "").strip()
        ]
        if not topics:
            topics = [value.strip() for value in item.learning_objectives if value.strip()]
        units.append(
            {
                "id": item.id,
                "title": item.title,
                "topics": topics[:20],
                "covered": item.id in completed_class_ids or item.status == ClassStatus.COMPLETE,
            }
        )
    return units


def _book_labels(classes: list[CourseClass]) -> dict[str, str]:
    book_ids = {book_id for item in classes for book_id in item.book_ids if book_id}
    if not book_ids:
        return {}
    try:
        from deeptutor.book.engine import get_book_engine

        books = get_book_engine().list_books()
    except Exception:
        return {book_id: book_id for book_id in book_ids}
    labels = {str(getattr(book, "id", "")): str(getattr(book, "title", "") or "") for book in books}
    return {book_id: labels.get(book_id) or book_id for book_id in book_ids}


def sync_interactive_course_to_native(
    course_id: str,
    *,
    engine: CourseEngine | None = None,
    service: CourseService | None = None,
) -> dict[str, Any]:
    """Create or enrich the native container for one interactive course.

    The operation is idempotent. Existing native names, descriptions,
    conventions, and edited syllabi are never overwritten; the bridge only
    fills an empty syllabus and attaches missing references.
    """
    legacy_engine = engine or get_course_engine()
    native_service = service or get_course_service()
    detail = legacy_engine.detail(course_id)
    if detail is None:
        raise ValueError("Interactive course not found")
    legacy, _outline, classes, progress = detail

    try:
        native = native_service.get(course_id)
        created = False
    except CourseNotFoundError:
        color_index = sum(ord(character) for character in course_id) % len(COURSE_COLORS)
        native = native_service.import_course(
            course_id=legacy.id,
            name=legacy.title or "Imported course",
            description=legacy.description,
            color=COURSE_COLORS[color_index],
            default_capability="course_study",
            created_at=legacy.created_at,
        )
        created = True

    if not native.syllabus and classes:
        native = native_service.set_syllabus(
            native.id,
            _syllabus_units(classes, set(progress.completed_class_ids)),
        )

    resources_before = len(native.resources)
    if classes:
        native_service.attach_resource(
            native.id,
            kind="mastery_path",
            ref_id=legacy.id,
            label=legacy.title or legacy.id,
        )
    for knowledge_base in legacy.knowledge_bases:
        if knowledge_base.strip():
            native_service.attach_resource(
                native.id,
                kind="knowledge_base",
                ref_id=knowledge_base,
                label=knowledge_base,
            )
    for book_id, label in _book_labels(classes).items():
        native_service.attach_resource(
            native.id,
            kind="book",
            ref_id=book_id,
            label=label,
        )

    if legacy.status == CourseStatus.ARCHIVED:
        native_service.set_status(native.id, "archived")

    native = native_service.get(native.id)
    return {
        "course_id": native.id,
        "created": created,
        "syllabus_units": len(native.syllabus),
        "resources_added": len(native.resources) - resources_before,
        "class_count": len(classes),
        "compiled_class_count": sum(item.content_status == "ready" for item in classes),
    }


def sync_interactive_class_status_to_native(
    course_id: str,
    item: CourseClass,
    *,
    service: CourseService | None = None,
) -> bool:
    """Mirror a legacy class completion into its native syllabus unit."""
    from deeptutor.services.courses import SyllabusUnitNotFoundError

    native_service = service or get_course_service()
    try:
        native_service.set_unit_covered(
            course_id,
            item.id,
            item.status == ClassStatus.COMPLETE,
        )
    except (CourseNotFoundError, SyllabusUnitNotFoundError):
        return False
    return True


def sync_all_interactive_courses_to_native(
    *,
    engine: CourseEngine | None = None,
    service: CourseService | None = None,
) -> list[dict[str, Any]]:
    legacy_engine = engine or get_course_engine()
    native_service = service or get_course_service()
    return [
        sync_interactive_course_to_native(
            course.id,
            engine=legacy_engine,
            service=native_service,
        )
        for course in legacy_engine.list_courses()
    ]
