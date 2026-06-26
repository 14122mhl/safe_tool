from __future__ import annotations

from pathlib import Path

from safe_tool.analysis import build_playbook_analysis


def write_playbook(path: Path, module_name: str, hosts: str = "web") -> Path:
    path.write_text(
        f"""
- name: Test play
  hosts: {hosts}
  tasks:
    - name: Test task
      {module_name}:
        src: a
        dest: b
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_analysis_recognizes_fqcn_copy(tmp_path: Path) -> None:
    playbook = write_playbook(tmp_path / "copy_fqcn.yml", "ansible.builtin.copy")

    analysis = build_playbook_analysis(str(playbook))

    assert analysis.tasks[0].normalized_module == "copy"
    assert analysis.tasks[0].risk == "MEDIUM"


def test_analysis_recognizes_copy(tmp_path: Path) -> None:
    playbook = write_playbook(tmp_path / "copy.yml", "copy")

    analysis = build_playbook_analysis(str(playbook))

    assert analysis.tasks[0].normalized_module == "copy"
    assert analysis.tasks[0].risk == "MEDIUM"


def test_service_risk_is_high(tmp_path: Path) -> None:
    playbook = write_playbook(tmp_path / "service.yml", "service")

    analysis = build_playbook_analysis(str(playbook))

    assert analysis.tasks[0].risk == "HIGH"


def test_hosts_all_promotes_medium_risk_to_high(tmp_path: Path) -> None:
    playbook = write_playbook(tmp_path / "all.yml", "copy", hosts="all")

    analysis = build_playbook_analysis(str(playbook))

    assert analysis.tasks[0].risk == "HIGH"
