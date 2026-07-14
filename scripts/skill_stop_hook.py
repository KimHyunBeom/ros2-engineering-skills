#!/usr/bin/env python3
"""Skills 2.0 Stop Hook — Post-execution validation for ros2-engineering-skills.

This hook runs when the skill execution stops. It validates that any generated
ROS 2 artifacts conform to the skill's engineering principles:

- Launch files: valid Python + generate_launch_description present
- package.xml: format 3, <name> and <license> elements
- Nav2 parameter YAML: a *lightweight lint* for syntax and selected legacy
  identifiers (pre-Humble recovery naming, the pre-Galactic BT navigator
  parameter). It does NOT validate plugin exports, parameter types, BT XML
  contents, builds, or lifecycle behavior.

When the workspace is a git repository, validation is scoped to files that
are modified or untracked according to git — i.e. plausibly touched by this
session. A pre-existing broken launch file that is committed and untouched
must not make every Stop fail forever in a repo the skill never modified.
Outside a git repository (or if git is unavailable) all discovered files
are validated, as before.

Execution logging is opt-in: a summary line is appended to .skill-runs.log
only when the SKILL_RUNS_LOG environment variable is set (see
_resolve_log_path). Without the opt-in the hook never writes to the
workspace, so a read-only session leaves the working tree untouched.

Exit codes:
    0 — All checks passed (warnings/advisories do not fail the hook)
    1 — Validation errors found (reported to stdout as JSON)
"""

import json
import os
import subprocess
import sys
import ast


# Maximum directory depth to walk (relative to workspace root).
# Keeps scan cost bounded for large workspaces with deeply nested vendor trees.
_MAX_SCAN_DEPTH = 6

# Directory names to always skip (in addition to hidden dirs).
_SKIP_DIRS = frozenset((
    'build', 'install', 'log', 'node_modules', '__pycache__',
    '.git', '.svn', 'venv', '.venv', 'third_party', 'vendor',
))

# Explicit distro ordering for distro-aware advisories. Never compare distro
# names as strings — alphabetical order matching release order is a
# coincidence, and unknown names (e.g. 'rolling') must mean "cannot order",
# not a silent wrong answer.
_DISTRO_ORDER = {
    'foxy': 1,
    'galactic': 2,
    'humble': 3,
    'iron': 4,
    'jazzy': 5,
    'kilted': 6,
    'lyrical': 7,
}

# PyYAML availability, resolved once at import. The Nav2 YAML lint needs it;
# when absent the lint is skipped and main() reports that in checks_skipped
# so "checks passed" and "checks never ran" are distinguishable.
try:
    import yaml as _yaml  # noqa: F401
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

# Top-level keys that mark a YAML file as a Nav2 parameter file.
_NAV2_KEY_HINTS = frozenset((
    'bt_navigator', 'controller_server', 'planner_server',
    'behavior_server', 'recoveries_server', 'local_costmap',
    'global_costmap', 'velocity_smoother', 'collision_monitor',
    'waypoint_follower', 'smoother_server', 'amcl',
))


def _should_skip(dirpath, workspace):
    """Return True if *dirpath* should be pruned from the walk."""
    rel = os.path.relpath(dirpath, workspace)
    if rel == '.':
        return False  # never skip the workspace root itself
    parts = rel.split(os.sep)
    if len(parts) > _MAX_SCAN_DEPTH:
        return True
    return any(p.startswith('.') or p in _SKIP_DIRS for p in parts)


def find_generated_launch_files(workspace):
    """Find all launch files in the workspace (depth-limited).

    Matches both official Python launch naming conventions
    (*.launch.py and *_launch.py).
    """
    launch_files = []
    for root, dirs, files in os.walk(workspace):
        if _should_skip(root, workspace):
            dirs.clear()  # prune subtree
            continue
        # In-place prune to avoid descending into skippable children
        dirs[:] = [d for d in dirs
                   if not d.startswith('.') and d not in _SKIP_DIRS]
        for f in files:
            if f.endswith('.launch.py') or f.endswith('_launch.py'):
                launch_files.append(os.path.join(root, f))
    return launch_files


def validate_launch_file_syntax(filepath):
    """Check that a launch file is valid Python and has generate_launch_description."""
    issues = []
    try:
        with open(filepath, 'r', encoding='utf-8') as fh:
            source = fh.read()
        tree = ast.parse(source, filename=filepath)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        if 'generate_launch_description' not in func_names:
            issues.append({
                'file': filepath,
                'severity': 'error',
                'message': 'Missing generate_launch_description function',
            })
    except SyntaxError as e:
        issues.append({
            'file': filepath,
            'severity': 'error',
            'message': f'Syntax error: {e}',
        })
    except OSError:
        pass  # File may have been removed during session
    return issues


def validate_package_xml(filepath):
    """Check that a package.xml uses format 3 and has required elements."""
    issues = []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(filepath)
        root = tree.getroot()
        fmt = root.attrib.get('format', '')
        if fmt != '3':
            issues.append({
                'file': filepath,
                'severity': 'warning',
                'message': f'package.xml uses format {fmt}, recommend format 3',
            })
        if root.find('name') is None:
            issues.append({
                'file': filepath,
                'severity': 'error',
                'message': 'package.xml missing <name> element',
            })
        if root.find('license') is None:
            issues.append({
                'file': filepath,
                'severity': 'warning',
                'message': 'package.xml missing <license> element',
            })
    except Exception as e:
        issues.append({
            'file': filepath,
            'severity': 'error',
            'message': f'Failed to parse package.xml: {e}',
        })
    return issues


def find_package_xmls(workspace):
    """Find all package.xml files in the workspace (depth-limited)."""
    results = []
    for root, dirs, files in os.walk(workspace):
        if _should_skip(root, workspace):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs
                   if not d.startswith('.') and d not in _SKIP_DIRS]
        for f in files:
            if f == 'package.xml':
                results.append(os.path.join(root, f))
    return results


def find_yaml_files(workspace):
    """Find all YAML files in the workspace (depth-limited)."""
    results = []
    for root, dirs, files in os.walk(workspace):
        if _should_skip(root, workspace):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs
                   if not d.startswith('.') and d not in _SKIP_DIRS]
        for f in files:
            if f.endswith(('.yaml', '.yml')):
                results.append(os.path.join(root, f))
    return results


def _distro_at_least(distro, minimum):
    """Order a distro name against *minimum* using the explicit table.

    Returns True/False when both sides are known, and None when the distro
    is unset or not in _DISTRO_ORDER (e.g. 'rolling') — callers must treat
    None as "cannot decide", not as either boolean.
    """
    rank = _DISTRO_ORDER.get((distro or '').strip().lower())
    if rank is None:
        return None
    return rank >= _DISTRO_ORDER[minimum]


def _walk_yaml(node, keys, values):
    """Collect all mapping keys and string scalars from a parsed YAML tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                keys.add(k)
            _walk_yaml(v, keys, values)
    elif isinstance(node, list):
        for item in node:
            _walk_yaml(item, keys, values)
    elif isinstance(node, str):
        values.append(node)


def validate_nav2_yaml(filepath):
    """Lightweight Nav2 YAML lint: syntax plus selected legacy identifiers.

    Scope (deliberately narrow — this is a lint, not semantic validation):
    - YAML syntax errors, reported only for files whose path mentions nav2
      (an unparseable file cannot be classified by content, and failing the
      hook on arbitrary broken YAML would be a false positive).
    - Distro-aware advisories (severity: warning) on parsed files that look
      like Nav2 parameter files:
        * pre-Humble recovery naming (recoveries_server / nav2_recoveries/)
        * pre-Galactic BT navigator parameter (default_bt_xml_filename)
      Advisories are suppressed when ROS_DISTRO orders below the rename
      boundary (the identifier is valid there) and annotated with a
      confirm-the-target-distro note when ROS_DISTRO is unset or unknown.

    It does NOT verify plugin exports, parameter types, BT XML contents,
    that the stack builds, or lifecycle behavior. Working with parsed keys
    and values means commented-out mentions are never flagged.

    Requires PyYAML; returns no issues when it is unavailable (main()
    surfaces that condition via checks_skipped).
    """
    issues = []
    if not _HAVE_YAML:
        return issues
    import yaml

    try:
        with open(filepath, 'r', encoding='utf-8') as fh:
            docs = list(yaml.safe_load_all(fh))
    except OSError:
        return issues
    except yaml.YAMLError as e:
        if 'nav2' in filepath.lower():
            issues.append({
                'file': filepath,
                'severity': 'error',
                'message': f'YAML syntax error: {e}',
            })
        return issues

    keys = set()
    values = []
    for doc in docs:
        _walk_yaml(doc, keys, values)

    looks_like_nav2 = bool(keys & _NAV2_KEY_HINTS) or any(
        v.startswith('nav2_') for v in values)
    if not looks_like_nav2:
        return issues

    distro = os.environ.get('ROS_DISTRO')

    uses_legacy_recovery = ('recoveries_server' in keys or
                            any('nav2_recoveries/' in v for v in values))
    at_least_humble = _distro_at_least(distro, 'humble')
    if uses_legacy_recovery and at_least_humble is not False:
        msg = ('pre-Humble recovery naming (recoveries_server / '
               'nav2_recoveries/): renamed to behavior_server / '
               'nav2_behaviors/ in Humble — this configuration is ignored '
               'or fails to load on Humble and newer')
        if at_least_humble is None:
            msg += ' (ROS_DISTRO unset/unknown — confirm the target distro)'
        issues.append({
            'file': filepath,
            'severity': 'warning',
            'message': msg,
        })

    at_least_galactic = _distro_at_least(distro, 'galactic')
    if 'default_bt_xml_filename' in keys and at_least_galactic is not False:
        msg = ('pre-Galactic BT navigator parameter '
               '(default_bt_xml_filename): Galactic and newer use '
               'default_nav_to_pose_bt_xml / default_nav_through_poses_bt_xml'
               ' — the old name is silently ignored')
        if at_least_galactic is None:
            msg += ' (ROS_DISTRO unset/unknown — confirm the target distro)'
        issues.append({
            'file': filepath,
            'severity': 'warning',
            'message': msg,
        })

    return issues


def _resolve_log_path(workspace):
    """Return the execution-log path if logging is opted in, else None.

    SKILL_RUNS_LOG unset or empty  -> no logging. A read-only session must
        not dirty the working tree, so opt-in is the default-off.
    '1' / 'true' / 'yes' (any case) -> default '.skill-runs.log' in the
        workspace root (the pre-1.2 behavior).
    any other value                 -> treated as a file path; relative
        paths resolve against the workspace root.
    """
    raw = os.environ.get('SKILL_RUNS_LOG', '').strip()
    if not raw:
        return None
    if raw.lower() in ('1', 'true', 'yes'):
        return os.path.join(workspace, '.skill-runs.log')
    if os.path.isabs(raw):
        return raw
    return os.path.join(workspace, raw)


def _resolve_workspace():
    """Pick the workspace path to scan, preferring explicit signals.

    Real Claude Code (verified 2026-05-21) sends Stop-event payloads via
    stdin including a `cwd` field naming the workspace root. We prefer that
    over `os.getcwd()` because the hook process may be invoked from a
    different working directory than the user's actual project root.

    Resolution order:
      1. SKILL_WORKSPACE env var (explicit override, used by pytest)
      2. stdin JSON payload `cwd` (real Claude Code)
      3. CLAUDE_PROJECT_DIR env var (Claude Code sets this for hooks)
      4. os.getcwd() fallback
    """
    explicit = os.environ.get('SKILL_WORKSPACE')
    if explicit:
        return explicit

    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    cwd = payload.get('cwd')
                    if cwd and os.path.isdir(cwd):
                        return cwd
        except (json.JSONDecodeError, OSError, Exception):  # noqa: BLE001
            pass

    project_dir = os.environ.get('CLAUDE_PROJECT_DIR')
    if project_dir and os.path.isdir(project_dir):
        return project_dir

    return os.getcwd()


def _git_touched_paths(workspace):
    """Return real paths of git-modified/untracked files, or None.

    None means the modification set is unknown (not a git repository, git
    missing, or git failed) — the caller then validates everything found,
    preserving the pre-git behaviour.
    """
    try:
        proc = subprocess.run(
            ['git', '-C', workspace, 'status', '--porcelain',
             '--untracked-files=all', '--no-renames'],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    paths = set()
    for line in proc.stdout.splitlines():
        # Porcelain v1: two status chars, a space, then the path
        # (quoted if it contains special characters).
        p = line[3:].strip()
        if p.startswith('"') and p.endswith('"'):
            p = p[1:-1]
        if p:
            paths.add(os.path.realpath(os.path.join(workspace, p)))
    return paths


def main():
    workspace = _resolve_workspace()
    all_issues = []

    launch_files = find_generated_launch_files(workspace)
    package_xmls = find_package_xmls(workspace)
    yaml_files = find_yaml_files(workspace)

    # Scope validation to files this session plausibly touched (see module
    # docstring). Unknown modification set -> validate everything.
    touched = _git_touched_paths(workspace)
    if touched is not None:
        launch_files = [f for f in launch_files
                        if os.path.realpath(f) in touched]
        package_xmls = [f for f in package_xmls
                        if os.path.realpath(f) in touched]
        yaml_files = [f for f in yaml_files
                      if os.path.realpath(f) in touched]

    for lf in launch_files:
        all_issues.extend(validate_launch_file_syntax(lf))

    for px in package_xmls:
        all_issues.extend(validate_package_xml(px))

    for yf in yaml_files:
        all_issues.extend(validate_nav2_yaml(yf))

    # Distinguish "no findings" from "check never ran": the key is always
    # present so consumers get a stable schema, and the PyYAML entry is
    # only added when there was actually YAML in scope to check.
    checks_skipped = []
    if yaml_files and not _HAVE_YAML:
        checks_skipped.append('nav2_yaml: PyYAML is not installed')

    result = {
        'hook': 'ros2-engineering-skills:stop',
        'version': '1.2.0',
        'issues_count': len(all_issues),
        'issues': all_issues,
        'checks_skipped': checks_skipped,
        'status': 'fail' if any(
            i['severity'] == 'error' for i in all_issues
        ) else 'pass',
    }

    # --- Execution log (opt-in) ---
    # Append a summary so the next session can see what was validated and
    # what issues were found. Only when SKILL_RUNS_LOG is set: without the
    # opt-in the hook must not write into the workspace at all (a read-only
    # session would otherwise end with a dirtied working tree).
    log_path = _resolve_log_path(workspace)
    if log_path is not None:
        try:
            from datetime import datetime, timezone
            # Severity-tagged summaries (errors first) so warning-only runs
            # still leave detail in the log. error_summaries is retained one
            # release for consumers of the pre-1.2 log format.
            ordered = sorted(
                all_issues,
                key=lambda i: 0 if i['severity'] == 'error' else 1)
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': result['status'],
                'issues_count': result['issues_count'],
                'launch_files_checked': len(launch_files),
                'package_xmls_checked': len(package_xmls),
                'yaml_files_checked': len(yaml_files),
                'checks_skipped': checks_skipped,
                'issue_summaries': [
                    f"[{i['severity']}] {i['file']}: {i['message']}"
                    for i in ordered
                ][:5],  # keep log concise
                'error_summaries': [
                    i['message'] for i in all_issues
                    if i['severity'] == 'error'
                ][:5],
            }
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write(json.dumps(log_entry) + '\n')
        except OSError:
            pass  # logging is best-effort; never fail the hook over it

    print(json.dumps(result, indent=2))
    sys.exit(1 if result['status'] == 'fail' else 0)


if __name__ == '__main__':
    main()
