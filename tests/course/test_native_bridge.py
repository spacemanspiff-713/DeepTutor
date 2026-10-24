from pathlib import Path

from deeptutor.course.models import (
    ClassStatus,
    Course,
    CourseClass,
    CourseProgress,
)
from deeptutor.course.native_bridge import (
    sync_interactive_class_status_to_native,
    sync_interactive_course_to_native,
)
from deeptutor.course.storage import CourseStorage
from deeptutor.services.courses import CourseService
from deeptutor.services.path_service import PathService


def _legacy_storage(tmp_path: Path, monkeypatch) -> CourseStorage:
    PathService.reset_instance()
    monkeypatch.setattr(PathService, "_instance", PathService(tmp_path / "data"))
    return CourseStorage()


def test_interactive_course_import_uses_stable_id_and_native_resources(
    tmp_path, monkeypatch
) -> None:
    storage = _legacy_storage(tmp_path, monkeypatch)
    course = Course(
        id="course_legacy123",
        title="Distributed Systems",
        description="Build and reason about distributed services.",
        knowledge_bases=["distributed-notes"],
    )
    first = CourseClass(
        id="class_foundations",
        course_id=course.id,
        title="Foundations",
        status=ClassStatus.COMPLETE,
        learning_objectives=["Explain safety and liveness"],
        knowledge_points=[{"name": "Safety", "type": "concept"}],
        book_ids=["book_123"],
    )
    second = CourseClass(
        id="class_consensus",
        course_id=course.id,
        title="Consensus",
        learning_objectives=["Compare Raft and Paxos"],
    )
    storage.save_course(course)
    storage.save_class(first)
    storage.save_class(second)
    storage.save_progress(CourseProgress(course_id=course.id, completed_class_ids=[first.id]))

    native = CourseService(tmp_path / "native-courses")
    report = sync_interactive_course_to_native(
        course.id,
        engine=type(
            "Engine",
            (),
            {
                "detail": lambda _self, _id: (
                    course,
                    None,
                    [first, second],
                    storage.load_progress(course.id),
                )
            },
        )(),
        service=native,
    )

    imported = native.get(course.id)
    assert report["created"] is True
    assert imported.id == course.id
    assert imported.default_capability == "course_study"
    assert [unit.id for unit in imported.syllabus] == [first.id, second.id]
    assert imported.syllabus[0].covered is True
    assert imported.syllabus[0].topics == ["Safety"]
    assert {(item.kind, item.ref_id) for item in imported.resources} == {
        ("mastery_path", course.id),
        ("knowledge_base", "distributed-notes"),
        ("book", "book_123"),
    }


def test_interactive_course_import_is_idempotent_and_preserves_native_edits(
    tmp_path, monkeypatch
) -> None:
    storage = _legacy_storage(tmp_path, monkeypatch)
    course = Course(id="course_legacy456", title="Compilers")
    item = CourseClass(
        id="class_parse",
        course_id=course.id,
        title="Parsing",
        learning_objectives=["Build a parser"],
    )
    progress = CourseProgress(course_id=course.id)
    storage.save_course(course)
    storage.save_class(item)
    storage.save_progress(progress)
    engine = type(
        "Engine",
        (),
        {"detail": lambda _self, _id: (course, None, [item], progress)},
    )()
    native = CourseService(tmp_path / "native-courses")

    sync_interactive_course_to_native(course.id, engine=engine, service=native)
    native.update(course.id, name="My Compilers Course")
    native.set_syllabus(
        course.id,
        [{"id": "custom", "title": "My revised unit", "topics": []}],
    )
    report = sync_interactive_course_to_native(course.id, engine=engine, service=native)

    imported = native.get(course.id)
    assert report["created"] is False
    assert imported.name == "My Compilers Course"
    assert [unit.id for unit in imported.syllabus] == ["custom"]
    assert len(imported.resources) == 1


def test_legacy_class_completion_mirrors_native_syllabus(tmp_path) -> None:
    native = CourseService(tmp_path / "native-courses")
    native.import_course(course_id="course_sync", name="Sync")
    native.set_syllabus(
        "course_sync",
        [{"id": "class_one", "title": "One", "topics": []}],
    )
    item = CourseClass(
        id="class_one",
        course_id="course_sync",
        title="One",
        status=ClassStatus.COMPLETE,
    )

    assert sync_interactive_class_status_to_native("course_sync", item, service=native)
    assert native.get("course_sync").syllabus[0].covered is True
