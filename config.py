from pathlib import Path

import yaml


def load_yaml_config():
    """
    Load a YAML configuration file.

    Returns:
        dict: Parsed YAML content.
    """
    try:
        current_dir = Path(__file__).parent
    except NameError:
        current_dir = Path.cwd()

    yaml_path = current_dir / "config.yaml"

    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
