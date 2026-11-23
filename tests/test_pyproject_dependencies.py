import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def test_project_dependencies_are_valid_pep508():
    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )

    dependencies = pyproject["project"]["dependencies"]
    requirements = [Requirement(dependency) for dependency in dependencies]

    faster_whisper = next(requirement for requirement in requirements if requirement.name == "faster-whisper")
    assert faster_whisper.marker is not None
    assert not faster_whisper.marker.evaluate(
        {"sys_platform": "darwin", "platform_machine": "arm64"}
    )
    assert faster_whisper.marker.evaluate(
        {"sys_platform": "linux", "platform_machine": "x86_64"}
    )
