from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Template


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    prompt: str
    description: str = ""


class PromptRegistry:
    def __init__(self, folder: str):
        self.folder = Path(folder)
        self._templates = self._load()

    def _load(self) -> dict[str, PromptTemplate]:
        templates = {}

        for path in self.folder.rglob("*.yaml"):
            data = yaml.safe_load(path.read_text())

            if data is None:
                continue

            template = PromptTemplate(**data)
            templates[template.name] = template

        return templates

    def render(self, name: str, **variables) -> str:
        if name not in self._templates:
            raise KeyError(f"Prompt '{name}' does not exist.")

        template = self._templates[name]

        return Template(template.prompt).render(**variables)