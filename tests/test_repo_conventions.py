"""Repository-level packaging and workflow regression tests."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_project_local_settings_are_not_committed():
    assert not (ROOT / '.claude' / 'settings.json').exists()
    assert not (ROOT / '.claude' / 'hooks' / 'no_ai_attribution.py').exists()


def test_gitignore_keeps_local_client_state_out():
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert '.claude/' in gitignore.splitlines()


def test_plugin_hooks_use_repository_scripts():
    path = ROOT / 'hooks' / 'hooks.json'
    with path.open('r', encoding='utf-8') as handle:
        hooks = json.load(handle)['hooks']
    commands = [
        hook['command']
        for groups in hooks.values()
        for group in groups
        for hook in group['hooks']
    ]
    assert any('skill_validate_hook.py' in command for command in commands)
    assert any('skill_stop_hook.py' in command for command in commands)


def test_ci_uses_standard_plugin_locations():
    github_dir = ROOT / '.github'
    if not github_dir.is_dir():
        pytest.skip('not a full checkout (.github absent)')
    workflow = (github_dir / 'workflows' / 'test.yml').read_text(
        encoding='utf-8')
    assert '.claude-plugin/plugin.json' in workflow
    assert 'hooks/hooks.json' in workflow
    assert '.claude/hooks/' not in workflow
