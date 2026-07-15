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
            'navigation.md must document the Humble/Iron plugin syntax')


class TestPluginTypeSeparator:
    """Nav2 plugin type strings use `/` on Humble/Iron and `::` on Jazzy+
    (some types like dwb_core::DWBLocalPlanner already used `::` earlier).
    Both syntaxes must stay documented, and each occurrence must sit in the
    right distro context — string presence alone would pass even if the
    syntaxes were attributed to the wrong distros."""

    _WINDOW = 3

    def _occurrence_windows(self, path, needle):
        lines = _lines(path)
        for idx, line in enumerate(lines):
            if needle in line:
                lo = max(0, idx - self._WINDOW)
                hi = min(len(lines), idx + self._WINDOW + 1)
                yield idx + 1, '\n'.join(lines[lo:hi])

    def test_humble_slash_syntax_in_humble_context(self):
        found = False
        for lineno, window in self._occurrence_windows(
                NAVIGATION_MD, 'nav2_behaviors/Spin'):
            found = True
            assert re.search(r'Humble|Iron|older', window, re.IGNORECASE), (
                f'navigation.md:{lineno} shows the / plugin syntax without '
                f'Humble/Iron context'
            )
        assert found, 'navigation.md must document nav2_behaviors/Spin'

    def test_jazzy_double_colon_syntax_in_jazzy_context(self):
        found = False
        for lineno, window in self._occurrence_windows(
                NAVIGATION_MD, 'nav2_behaviors::Spin'):
            found = True
            assert re.search(r'Jazzy|newer', window, re.IGNORECASE), (
                f'navigation.md:{lineno} shows the :: plugin syntax without '
                f'Jazzy+ context'
            )
        assert found, 'navigation.md must document nav2_behaviors::Spin'

    def test_jazzy_expected_uses_modern_plugin_separator(self):
        """The nav2 eval prompt targets Jazzy — its expected answer must use
        the :: types and carry no /-style behavior plugin strings."""
        content = _read(NAV2_EXPECTED)
        assert 'nav2_behaviors::Spin' in content
        assert 'nav2_behaviors/Spin' not in content


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


HARDWARE_MD = os.path.join(ROOT, 'references', 'hardware-interface.md')


class TestDistroMatrix:
    """Row-scoped checks on the SKILL.md distro table.

    Deliberately anchored to specific table cells (not global string
    absence) so that changelog prose mentioning an old value never trips
    the check. Pinned errors: Kilted EOL was recorded as Nov 2025 (official
    EOL is Dec 2026), Kilted ros2_control was 4.x while
    hardware-interface.md said 5.x, and the pre-Lyrical EventsExecutor was
    labeled stable although it ships in rclcpp::experimental.
    """

    def _distro_table(self):
        lines = _lines(SKILL_MD)
        header_idx = next(
            i for i, line in enumerate(lines)
            if line.startswith('| Feature') and 'Humble' in line)
        headers = [c.strip() for c in
                   lines[header_idx].strip().strip('|').split('|')]
        rows = {}
        for line in lines[header_idx + 2:]:
            if not line.startswith('|'):
                break
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows[cells[0]] = dict(zip(headers[1:], cells[1:]))
        return rows

    def test_table_has_lyrical_column(self):
        rows = self._distro_table()
        assert 'Lyrical (LTS)' in rows['EOL'], (
            'SKILL.md distro table must carry a Lyrical (LTS) column')

    def test_kilted_eol_cell_is_dec_2026(self):
        assert self._distro_table()['EOL']['Kilted (non-LTS)'] == 'Dec 2026'

    def test_lyrical_eol_cell_is_may_2031(self):
        assert self._distro_table()['EOL']['Lyrical (LTS)'] == 'May 2031'

    def test_lyrical_ubuntu_cell_is_26_04(self):
        assert self._distro_table()['Ubuntu']['Lyrical (LTS)'] == '26.04'

    def test_ros2_control_versions_per_distro(self):
        row = self._distro_table()['ros2_control interface']
        assert row['Kilted (non-LTS)'] == '5.x'
        assert '6.x' in row['Lyrical (LTS)']

    def test_events_executor_cells(self):
        row = self._distro_table()['EventsExecutor']
        assert 'Experimental' in row['Kilted (non-LTS)']
        assert 'EventsCBGExecutor' in row['Lyrical (LTS)']

    def test_hardware_interface_agrees_on_kilted_5x(self):
        content = _read(HARDWARE_MD)
        assert re.search(r'Kilted \(5\.x\)', content), (
            'hardware-interface.md distro comparison must keep Kilted at '
            '5.x, matching the SKILL.md table')


class TestCallbackGroupRule:
    """Service-from-callback semantics: synchronous waiting deadlocks a
    MutuallyExclusiveCallbackGroup; registering a response callback and
    returning is safe even in the same group. Pinned error: an anti-pattern
    row claimed the pattern 'Deadlocks even with async', prescribing group
    surgery where none was needed."""

    def _skill_table_row(self, needle):
        for line in _lines(SKILL_MD):
            if line.startswith('|') and needle in line:
                return line
        raise AssertionError(
            f'no SKILL.md table row containing {needle!r}')

    def test_service_future_row_states_async_is_safe(self):
        row = self._skill_table_row('service future')
        assert 'safe even in the same group' in row
        assert 'Deadlocks even with async' not in row

    def test_principle_bullet_distinguishes_sync_wait(self):
        lines = _lines(SKILL_MD)
        start = next(i for i, line in enumerate(lines)
                     if 'Calling a service from a callback' in line)
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith('- ') or not lines[i].strip()),
                   len(lines))
        block = '\n'.join(lines[start:end])
        assert 'returns without waiting' in block
        assert 'add_done_callback' in block
        assert 'must** be in a separate' not in block


COMMUNICATION_MD = os.path.join(ROOT, 'references', 'communication.md')


class TestDefaultRmwVendor:
    """Fast DDS (rmw_fastrtps_cpp) is the default RMW on every current
    release; only Galactic defaulted to CycloneDDS. Pinned errors: a
    section heading called CycloneDDS the 'default vendor' and the vendor
    table credited CycloneDDS as default for Humble+."""

    def test_cyclonedds_heading_not_called_default(self):
        for lineno, line in enumerate(_lines(COMMUNICATION_MD), start=1):
            if line.startswith('#') and 'CycloneDDS tuning' in line:
                assert 'default vendor' not in line, (
                    f'communication.md:{lineno} still titles CycloneDDS as '
                    f'the default vendor'
                )
                return
        raise AssertionError('CycloneDDS tuning section heading not found')

    def test_vendor_table_default_row(self):
        row = next((line for line in _lines(COMMUNICATION_MD)
                    if line.startswith('|') and 'ROS 2 default' in line),
                   None)
        assert row is not None, 'vendor table must keep a ROS 2 default row'
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        # Column order: Aspect | CycloneDDS | FastDDS | Connext | Zenoh
        assert 'Galactic' in cells[1], (
            f'CycloneDDS default cell must say Galactic only: {cells[1]!r}')
        assert 'Default' in cells[2], (
            f'FastDDS cell must carry the Default marker: {cells[2]!r}')

    def test_default_rmw_stated_in_dds_section(self):
        content = _read(COMMUNICATION_MD)
        assert 'rmw_fastrtps_cpp' in content
