from __future__ import annotations

import json

import pytest

from deeptutor.services.courses import (
    COURSE_COLORS,
    CourseNameConflictError,
    CourseNotFoundError,
    CourseService,
)


def test_course_registry_round_trip_and_atomic_persistence(tmp_path) -> None:
    service = CourseService(tmp_path / "courses")

    operating_systems = service.create(
        name="  Operating   Systems  ",
        description="Processes and memory",
        color=COURSE_COLORS[1],
    )
    security = service.create(name="Network Security")

    assert operating_systems.name == "Operating Systems"
    assert operating_systems.color == COURSE_COLORS[1]
    assert security.color == COURSE_COLORS[1]
    assert [course.name for course in service.list_courses()] == [
        "Operating Systems",
        "Network Security",
    ]

    updated = service.update(
        operating_systems.id,
        description="Processes, memory, and filesystems",
        color=COURSE_COLORS[3],
    )
    assert updated.description == "Processes, memory, and filesystems"
    assert service.get(operating_systems.id).color == COURSE_COLORS[3]

    stored = json.loads(service.index_file.read_text(encoding="utf-8"))
    assert len(stored["courses"]) == 2

    service.delete(security.id)
    assert [course.id for course in service.list_courses()] == [operating_systems.id]
    with pytest.raises(CourseNotFoundError):
        service.get(security.id)


def test_import_course_preserves_external_id_and_is_create_only(tmp_path) -> None:
    service = CourseService(tmp_path / "courses")

    imported = service.import_course(
        course_id="course_legacy_123",
        name="Imported Course",
        default_capability="course_study",
        created_at=123.0,
    )
    same = service.import_course(
        course_id="course_legacy_123",
        name="A name that must not overwrite the first",
    )

    assert imported.id == "course_legacy_123"
    assert imported.created_at == 123.0
    assert imported.default_capability == "course_study"
    assert same.name == "Imported Course"
    assert len(service.list_courses()) == 1

    with pytest.raises(ValueError, match="Course id"):
        service.import_course(course_id="../escape", name="Bad")


def test_course_names_are_unique_case_insensitively(tmp_path) -> None:
    service = CourseService(tmp_path / "courses")
    course = service.create(name="Operating Systems")

    with pytest.raises(CourseNameConflictError):
        service.create(name="operating systems")

    security = service.create(name="Network Security")
    with pytest.raises(CourseNameConflictError):
        service.update(security.id, name=course.name)
