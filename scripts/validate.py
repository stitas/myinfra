#!/usr/bin/env python3
"""Check local YAML syntax/duplicate keys (skip encrypted Vault files), GitOps
source directories for this repository, and rendered backup-script Bash syntax.
"""

from pathlib import Path
import shlex
import subprocess
import sys

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/stitas/myinfra.git"


def construct_unique_mapping(loader, node):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            raise ValueError(f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node)
    return mapping


def load_yaml_documents(path):
    content = path.read_text()
    if content.startswith("$ANSIBLE_VAULT;"):
        return []

    loader = yaml.SafeLoader(content)
    # Customize this loader only; leave PyYAML's global constructors unchanged.
    loader.yaml_constructors = loader.yaml_constructors.copy()
    loader.yaml_constructors[yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG] = construct_unique_mapping
    documents = []
    try:
        while loader.check_data():
            documents.append(loader.get_data())
    finally:
        loader.dispose()
    return documents


def check_gitops_source(document, root):
    if not isinstance(document, dict) or document.get("kind") != "Application":
        return
    specification = document.get("spec")
    source = specification.get("source") if isinstance(specification, dict) else None
    if not isinstance(source, dict):
        raise ValueError("Application must have a spec.source mapping")
    if source.get("repoURL") == REPOSITORY_URL:
        source_path = source.get("path")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError("Application spec.source.path must be a nonempty string")
        if not (root / source_path).is_dir():
            raise ValueError(f"GitOps source directory does not exist: {source_path}")


def check_yaml_files(root):
    document_count = 0
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or path.suffix not in (".yaml", ".yml"):
            continue
        try:
            for document in load_yaml_documents(path):
                check_gitops_source(document, root)
                document_count += 1
        except (OSError, yaml.YAMLError, ValueError, TypeError) as error:
            raise ValueError(f"{path.relative_to(root)}: {error}") from None
    return document_count


def check_backup_script(root):
    role = root / "ansible/roles/backup"
    defaults_path = role / "defaults/main.yml"
    template_path = role / "templates/backup.sh.j2"
    try:
        defaults = yaml.safe_load(defaults_path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{defaults_path.relative_to(root)}: {error}") from None

    environment = jinja2.Environment(undefined=jinja2.StrictUndefined)
    environment.filters.update(quote=shlex.quote, ternary=lambda value, yes, no: yes if value else no)
    try:
        script = environment.from_string(template_path.read_text()).render(**defaults)
        result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    except (OSError, jinja2.TemplateError, TypeError) as error:
        raise ValueError(f"{template_path.relative_to(root)}: {error}") from None
    if result.returncode:
        raise ValueError(f"{template_path.relative_to(root)}: Bash syntax check failed:\n{result.stderr.strip()}")


def main():
    try:
        document_count = check_yaml_files(ROOT)
        check_backup_script(ROOT)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {document_count} YAML documents (unique keys), local GitOps paths, rendered backup Bash syntax")
    return 0


if __name__ == "__main__":
    sys.exit(main())
