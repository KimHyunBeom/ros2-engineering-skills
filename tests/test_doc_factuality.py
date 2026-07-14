"""Documentation factuality regression tests.

These pin previously discovered factual errors in the reference documents so
they cannot silently reappear. They are string-level regression checks, not
proof of correctness — see README "Current status" for the scope statement.

Background (found during a real Humble/Nav2 field diagnosis):
- navigation.md presented ``recoveries_server`` / ``nav2_recoveries/`` as the
  CURRENT Humble naming; the rename to ``behavior_server`` /
  ``nav2_behaviors/`` actually happened in the Galactic -> Humble migration,
  so the documented config did not exist on the installed Humble.
- The pre-Galactic ``default_bt_xml_filename`` parameter appeared in a config
  example as if current; Galactic+ uses ``default_nav_to_pose_bt_xml`` and
  the old name is silently ignored.
- Spin/BackUp motion recoveries were presented as a mandatory default; an
  unvalidated +1.57 rad Spin caused an unexpected in-place rotation on a
  quadruped in the field.
"""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), '..')
NAVIGATION_MD = os.path.join(ROOT, 'references', 'navigation.md')
TESTING_MD = os.path.join(ROOT, 'references', 'testing.md')
SKILL_MD = os.path.join(ROOT, 'SKILL.md')
NAV2_EXPECTED = os.path.join(ROOT, 'evals', 'expected',
                             'nav2-configuration.md')

# A line that names a legacy identifier must, on the same line, make clear
# that the identifier is legacy (migration notes, rename explanations).
_LEGACY_CONTEXT = re.compile(
    r'pre-Humble|pre-Galactic|Galactic|legacy|renamed', re.IGNORECASE)


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _lines(path):
    return _read(path).splitlines()


class TestNav2RecoveryNaming:
    """recoveries_server / nav2_recoveries must never be presented as
    current naming — only inside migration/legacy context."""

    def _assert_legacy_context_only(self, path, needles):
        for lineno, line in enumerate(_lines(path), start=1):
            if any(n in line for n in needles):
                assert _LEGACY_CONTEXT.search(line), (
                    f'{os.path.basename(path)}:{lineno} mentions legacy Nav2 '
                    f'recovery naming outside a migration/legacy context: '
                    f'{line.strip()!r}'
                )

    def test_navigation_md(self):
        self._assert_legacy_context_only(
            NAVIGATION_MD, ('recoveries_server', 'nav2_recoveries'))

    def test_skill_md(self):
        self._assert_legacy_context_only(
            SKILL_MD, ('recoveries_server', 'nav2_recoveries'))

    def test_nav2_expected_has_no_legacy_recovery_naming(self):
        content = _read(NAV2_EXPECTED)
        assert 'recoveries_server' not in content
        assert 'nav2_recoveries' not in content

    def test_navigation_md_documents_current_humble_naming(self):
        content = _read(NAVIGATION_MD)
        assert 'behavior_server:' in content, (
            'navigation.md must show a behavior_server config example')
        assert 'nav2_behaviors/Spin' in content, (
            'navigation.md must use the nav2_behaviors/ plugin namespace')


class TestBtNavigatorParameter:
    """default_bt_xml_filename is pre-Galactic (a DIFFERENT boundary from
    the recovery rename) and must only appear flagged as such."""

    def test_old_param_only_in_pre_galactic_context(self):
        marker = re.compile(r'pre-Galactic|Foxy', re.IGNORECASE)
        for path in (NAVIGATION_MD, SKILL_MD, NAV2_EXPECTED):
            for lineno, line in enumerate(_lines(path), start=1):
                if 'default_bt_xml_filename' in line:
                    assert marker.search(line), (
                        f'{os.path.basename(path)}:{lineno} presents the '
                        f'pre-Galactic default_bt_xml_filename without '
                        f'flagging it: {line.strip()!r}'
                    )

    def test_current_param_documented(self):
        for path in (NAVIGATION_MD, NAV2_EXPECTED):
            assert 'default_nav_to_pose_bt_xml' in _read(path), (
                f'{os.path.basename(path)} must document the Galactic+ '
                f'default_nav_to_pose_bt_xml parameter'
            )

    def test_old_default_bt_filename_gone(self):
        """The pre-Galactic default BT filename must not be presented; the
        Humble-era name is navigate_to_pose_w_replanning_and_recovery.xml
        (which does not contain the old token as a substring)."""
        for path in (NAVIGATION_MD, NAV2_EXPECTED):
            assert 'navigate_w_replanning_and_recovery' not in _read(path), (
                f'{os.path.basename(path)} still names the pre-Galactic '
                f'default BT file'
            )


class TestMotionRecoveryGating:
    """Motion recoveries (Spin/BackUp) must not be presented as a mandatory
    default anywhere in the docs or eval fixtures."""

    def test_expected_does_not_mandate_spin_backup(self):
        content = _read(NAV2_EXPECTED)
        assert 'Must configure recovery behaviors: spin' not in content
        assert re.search(r'gate|actuation-free', content), (
            'nav2 expected answer must require safety gating for motion '
            'recoveries'
        )

    def test_navigation_md_keeps_escalation_ladder(self):
        content = _read(NAVIGATION_MD)
        assert 'actuation-free' in content
        assert 'escalation ladder' in content

    def test_costmap_clear_caveat_present(self):
        """Costmap clearing is actuation-free but not automatically safe —
        the re-observation caveat must stay documented."""
        content = _read(NAVIGATION_MD)
        assert re.search(r'can erase \*?real\*? obstacles', content), (
            'navigation.md must keep the costmap-clearing re-observation '
            'caveat'
        )


class TestUseSimTimeExamples:
    """use_sim_time: True examples must always pair with a /clock source
    (ros2 bag play --clock or a simulator); a clockless example hangs
    timer-driven nodes."""

    _WINDOW = 15

    def test_testing_md_sim_time_examples_have_clock_source(self):
        lines = _lines(TESTING_MD)
        for idx, line in enumerate(lines):
            if "'use_sim_time': True" in line:
                lo = max(0, idx - self._WINDOW)
                hi = min(len(lines), idx + self._WINDOW + 1)
                window = '\n'.join(lines[lo:hi])
                assert '--clock' in window, (
                    f'testing.md:{idx + 1} sets use_sim_time without a '
                    f'/clock source nearby'
                )
