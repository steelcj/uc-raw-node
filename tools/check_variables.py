#!/usr/bin/env python3
"""Check variable names and secret handling in uc-raw-node.

Implements the CI check described under Variables in Raw Node Controller
Layout Design v0.1.10:

- Every name set by set_fact or register in tasks/, roles/ and the entry
  playbooks must match a row of the naming table, and be set only in a file
  that row lists (rules "prefix" and "file").
- A task whose module arguments or task vars (not its name) contain a
  template that refers to the secrets path, the payload, the contract input
  or a token must carry no_log: true, and so must a task that sets one of
  those variables (rule "no_log"). Two refinements, agreed during the
  session that wrote this check: an assert is judged by its messages, not
  by its "that" expressions, which Ansible never prints with their values;
  and raw_node_input.hostname and raw_node_input.initial_username count as
  public, as the design treats them.
- No file under templates/ may turn on shell tracing with set -x or
  set -o xtrace (rule "xtrace").

A task may carry a comment "# ci-allow: <rule> <reason>" on the line (or
the run of comment lines) directly above it. The check then accepts that
rule's finding for that task, and reports the allowance, so exceptions stay
visible.

Uses only the standard library and PyYAML, which ansible-core requires.
Usage: check_variables.py [--root <repository root>]
Exits 0 when there are no problems, 1 when there are, 2 on a usage error.
"""

import argparse
import fnmatch
import pathlib
import re
import sys

import yaml

# The naming table of layout design v0.1.10, with the transport output row
# widened to raw_node_transport_* (raw_node_transport_state). Each row:
# (what the table calls it, a regular expression for the names, the files
# allowed to set them as glob patterns relative to the repository root).
# A name may match several rows; it passes if any matching row allows the
# file. Test-only names (raw_node_test_*) are allowed only under tests/,
# which this check does not scan, so one found here always fails.
TRANSPORT_ROLES = "roles/raw_node_transport_*/*"
BLOCK_STEPS = [
    "tasks/payload.yml",
    "tasks/wait_phone_home.yml",
    "tasks/write_confirmation.yml",
    TRANSPORT_ROLES,
    "roles/raw_node_validator/*",
]
ROWS = [
    ("raw_node_registry_*", r"raw_node_registry(_\w+)?",
     ["tasks/validate_registry.yml", "tasks/load_registry_layer.yml"]),
    ("raw_node_input", r"raw_node_input", ["tasks/load_input.yml"]),
    ("raw_node_hostname", r"raw_node_hostname",
     ["tasks/load_input.yml", "destroy.yml"]),
    ("raw_node_platform, raw_node_delivery_strategy",
     r"raw_node_platform|raw_node_delivery_strategy",
     ["tasks/resolve_platform.yml"]),
    ("raw_node_*_dir (expanded paths)",
     r"raw_node_(records|reports|logs|secrets)_dir",
     ["tasks/prepare_paths.yml"]),
    ("raw_node_paths_*", r"raw_node_paths_\w+", ["tasks/prepare_paths.yml"]),
    ("raw_node_attempt_*", r"raw_node_attempt_\w+",
     ["tasks/write_attempt.yml", "tasks/set_attempt_state.yml"]),
    ("raw_node_payload_*", r"raw_node_payload_\w+", ["tasks/payload.yml"]),
    ("raw_node_transport_*", r"raw_node_transport_\w+", [TRANSPORT_ROLES]),
    ("raw_node_<transport>_* (Incus)", r"raw_node_incus_\w+",
     ["roles/raw_node_transport_incus_exec/*"]),
    ("raw_node_report_*", r"raw_node_report_\w+", ["tasks/wait_phone_home.yml"]),
    ("raw_node_validation_*", r"raw_node_validation_\w+",
     ["roles/raw_node_validator/*"]),
    ("raw_node_failure_reason", r"raw_node_failure_reason", BLOCK_STEPS),
    ("other raw_node_failure_*", r"raw_node_failure_\w+",
     ["tasks/handle_failure.yml"]),
    ("raw_node_destroy_*", r"raw_node_destroy_\w+", ["destroy.yml"]),
    ("raw_node_test_*", r"raw_node_test_\w+", ["tests/*"]),
    ("target_platform", r"target_platform", ["destroy.yml"]),
]

# Variables whose appearance in a template marks a task as handling
# secrets: the secrets path, the payload, the contract input, any token.
SECRET_NAMES = re.compile(
    r"^(raw_node_secrets_dir|raw_node_secrets_path|raw_node_payload_file"
    r"|raw_node_input|\w*token\w*)$"
)

# Task keywords: everything else at the top of a task is its module.
TASK_KEYWORDS = {
    "name", "when", "loop", "loop_control", "register", "vars", "no_log",
    "changed_when", "failed_when", "until", "retries", "delay", "tags",
    "block", "rescue", "always", "environment", "become", "become_user",
    "ignore_errors", "ignore_unreachable", "delegate_to", "delegate_facts",
    "run_once", "notify", "listen", "check_mode", "diff",
    "any_errors_fatal", "throttle", "timeout", "collections",
    "module_defaults", "debugger", "args", "connection", "local_action",
}
# Module arguments that Ansible evaluates as bare Jinja expressions.
EXPRESSION_ARGS = {("debug", "var")}
# Module arguments not scanned: an assert's conditions are never printed
# with their values, so only its messages can leak.
UNSCANNED_ARGS = {("assert", "that")}
# The contract fields the design treats as public: references to these
# alone do not mark a task as handling secrets.
PUBLIC_FIELDS = re.compile(
    r"raw_node_input\s*(\.\s*(hostname|initial_username)\b"
    r"|\[\s*['\"](hostname|initial_username)['\"]\s*\])"
)

TEMPLATE = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")
IDENTIFIER = re.compile(r"(?<![.\w])[A-Za-z_]\w*")
XTRACE = re.compile(r"(^|[;&|\s])set\s+(-[A-Za-z]*x[A-Za-z]*\b|-o\s+xtrace\b)", re.M)
ALLOW = re.compile(r"^\s*#\s*ci-allow:\s*(\S+)\s+(\S.*)$")
TRUE = {"true", "True", "TRUE", "yes", "Yes", "on"}


def plain(node):
    """Turn a YAML node into plain Python data, scalars as strings."""
    if isinstance(node, yaml.MappingNode):
        return {plain(k): plain(v) for k, v in node.value}
    if isinstance(node, yaml.SequenceNode):
        return [plain(v) for v in node.value]
    return node.value


def strings(value):
    """Yield every string inside plain data."""
    if isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, str):
        yield value


def identifiers(expression):
    """Names used in a Jinja expression, ignoring string literals and the
    public contract fields."""
    expression = PUBLIC_FIELDS.sub("public_field", expression)
    return set(IDENTIFIER.findall(STRING_LITERAL.sub("''", expression)))


def template_names(text):
    names = set()
    for match in TEMPLATE.finditer(text):
        names |= identifiers(match.group(1) or match.group(2) or "")
    return names


def task_nodes(node, playbook):
    """Yield (mapping node, plain task) for every task, through blocks."""
    if not isinstance(node, yaml.SequenceNode):
        return
    for item in node.value:
        if not isinstance(item, yaml.MappingNode):
            continue
        keys = {k.value: v for k, v in item.value}
        if playbook and ("hosts" in keys or "import_playbook" in keys
                         or "ansible.builtin.import_playbook" in keys):
            for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
                if section in keys:
                    yield from task_nodes(keys[section], False)
            continue
        yield item, plain(item)
        for section in ("block", "rescue", "always"):
            if section in keys:
                yield from task_nodes(keys[section], False)


def module_of(task):
    for key, value in task.items():
        if key not in TASK_KEYWORDS:
            short = key.rsplit(".", 1)[-1]
            args = value if isinstance(value, (dict, str)) else {}
            if isinstance(args, dict) and isinstance(task.get("args"), dict):
                args = {**args, **task["args"]}
            return short, args
    return None, {}


def allowances(lines, line_number):
    """ci-allow comments in the run of comment lines above a task."""
    found = {}
    index = line_number - 1
    while index >= 0 and lines[index].strip().startswith("#"):
        match = ALLOW.match(lines[index])
        if match:
            found[match.group(1)] = match.group(2).strip()
        index -= 1
    return found


def check(root):
    files = sorted(
        [p for p in (root / "tasks").glob("*.yml")]
        + [p for p in (root / "roles").glob("*/tasks/*.yml")]
        + [root / name for name in ("build.yml", "validate.yml", "destroy.yml")
           if (root / name).exists()]
    )
    problems, allowed = [], []
    rows = [(label, re.compile(rf"^(?:{pattern})$"), globs)
            for label, pattern, globs in ROWS]

    def report(path, line, task_name, rule, message, allow):
        where = f"{path}:{line}: task '{task_name}'"
        if rule in allow:
            allowed.append(f"{where}: {rule} allowed: {allow[rule]}")
        else:
            problems.append(f"{where}: {rule}: {message}")

    for file in files:
        rel = file.relative_to(root).as_posix()
        text = file.read_text()
        lines = text.splitlines()
        document = yaml.compose(text)
        playbook = rel in ("build.yml", "validate.yml", "destroy.yml")
        for node, task in task_nodes(document, playbook):
            line = node.start_mark.line
            name = task.get("name", "(unnamed)")
            allow = allowances(lines, line)
            module, args = module_of(task)

            # Names set by set_fact or register.
            set_names = []
            if module == "set_fact" and isinstance(args, dict):
                set_names += [k for k in args if k != "cacheable"]
            if isinstance(task.get("register"), str):
                set_names.append(task["register"])
            for var in set_names:
                matching = [(label, globs) for label, regex, globs in rows
                            if regex.match(var)]
                if not matching:
                    report(rel, line + 1, name, "prefix",
                           f"{var} matches no row of the naming table", allow)
                elif not any(fnmatch.fnmatch(rel, g)
                             for _, globs in matching for g in globs):
                    labels = "; ".join(label for label, _ in matching)
                    report(rel, line + 1, name, "file",
                           f"{var} ({labels}) may not be set in {rel}", allow)

            # Secret handling.
            if str(task.get("no_log", "")) in TRUE:
                continue
            sets_secret = sorted(n for n in set_names if SECRET_NAMES.match(n))
            if sets_secret:
                report(rel, line + 1, name, "no_log",
                       f"sets {', '.join(sets_secret)} without no_log: true",
                       allow)
            used = set()
            for text_value in strings(task.get("vars", {})):
                used |= template_names(text_value)
            if isinstance(args, dict):
                for key, value in args.items():
                    if (module, key) in UNSCANNED_ARGS:
                        continue
                    if (module, key) in EXPRESSION_ARGS:
                        for expression in strings(value):
                            used |= identifiers(expression)
                    else:
                        for text_value in strings(value):
                            used |= template_names(text_value)
            elif isinstance(args, str):
                used |= template_names(args)
            secret = sorted(n for n in used if SECRET_NAMES.match(n))
            if secret:
                report(rel, line + 1, name, "no_log",
                       f"refers to {', '.join(secret)} without no_log: true",
                       allow)

    templates = root / "templates"
    if templates.is_dir():
        for file in sorted(p for p in templates.rglob("*") if p.is_file()):
            rel = file.relative_to(root).as_posix()
            for number, text_line in enumerate(file.read_text().splitlines(), 1):
                if XTRACE.search(text_line) and not text_line.lstrip().startswith("#"):
                    problems.append(f"{rel}:{number}: xtrace: shell tracing "
                                    f"turned on ({text_line.strip()})")

    return files, problems, allowed


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=pathlib.Path(__file__).resolve().parent.parent,
                        type=pathlib.Path, help="repository root (default: this script's)")
    options = parser.parse_args()
    root = options.root.resolve()
    if not (root / "tasks").is_dir():
        print(f"check_variables: {root} has no tasks/ directory", file=sys.stderr)
        return 2
    files, problems, allowed = check(root)
    for line in allowed:
        print(f"ALLOWED {line}")
    for line in problems:
        print(f"PROBLEM {line}")
    print(f"check_variables: {len(files)} files, {len(problems)} problems, "
          f"{len(allowed)} allowances")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
