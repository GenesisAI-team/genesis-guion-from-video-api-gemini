"""Política de cobertura estratégica por archivo (100/80/0).

pytest-cov solo expone un umbral global (``--cov-fail-under``). La regla del
proyecto es por archivo, así que se evalúa sobre el informe JSON de coverage.py
con la clasificación declarada en ``coverage-policy.toml``.

Principio fail-closed: un archivo medido sin clasificar es un fallo del gate,
nunca se asume una categoría por defecto.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Final

DEFAULT_POLICY_PATH: Final = Path("coverage-policy.toml")
VALID_CATEGORIES: Final = ("core", "important", "infrastructure")


class PolicyError(ValueError):
    """La política es inválida o un archivo medido no es clasificable."""


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """Archivo cuya cobertura no alcanza el mínimo de su categoría."""

    path: str
    category: str
    threshold: float
    measured: float

    def describe(self) -> str:
        """Descripción legible de la violación."""
        return (
            f"{self.path}: {self.measured:.2f}% < {self.threshold:.2f}% "
            f"exigido por la categoría {self.category}"
        )


@dataclass(frozen=True, slots=True)
class CoveragePolicy:
    """Umbrales por categoría y patrones de clasificación de archivos."""

    thresholds: Mapping[str, float]
    patterns: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY_PATH) -> CoveragePolicy:
        """Carga y valida la política desde un archivo TOML.

        Raises:
            PolicyError: Si el archivo no existe, está mal formado o contiene
                categorías/umbrales incoherentes.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            msg = f"No existe el archivo de política: {path}"
            raise PolicyError(msg) from exc

        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            msg = f"Política TOML inválida en {path}: {exc}"
            raise PolicyError(msg) from exc

        raw_thresholds = data.get("thresholds")
        raw_files = data.get("files")
        if not isinstance(raw_thresholds, dict):
            msg = f"Falta la tabla [thresholds] en {path}"
            raise PolicyError(msg)
        if not isinstance(raw_files, dict) or not raw_files:
            msg = f"La política debe declarar al menos un archivo en {path}"
            raise PolicyError(msg)

        thresholds: dict[str, float] = {}
        for category, value in raw_thresholds.items():
            if category not in VALID_CATEGORIES:
                msg = f"Categoría desconocida en [thresholds]: {category}"
                raise PolicyError(msg)
            if not isinstance(value, int | float):
                msg = f"El umbral de {category} debe ser numérico"
                raise PolicyError(msg)
            thresholds[category] = float(value)

        patterns: list[tuple[str, str]] = []
        for pattern, category in raw_files.items():
            if not isinstance(category, str) or category not in VALID_CATEGORIES:
                msg = f"Categoría desconocida para {pattern}: {category!r}"
                raise PolicyError(msg)
            if category not in thresholds:
                msg = f"No hay umbral declarado para la categoría {category}"
                raise PolicyError(msg)
            patterns.append((pattern, category))

        return cls(thresholds=thresholds, patterns=tuple(patterns))

    def category_for(self, path: str) -> str:
        """Devuelve la categoría del archivo según el primer patrón coincidente.

        Raises:
            PolicyError: Si ningún patrón clasifica el archivo.
        """
        normalized = normalize_path(path)
        for pattern, category in self.patterns:
            if fnmatchcase(normalized, pattern):
                return category
        msg = f"Archivo sin clasificar en coverage-policy.toml: {normalized}"
        raise PolicyError(msg)

    def evaluate(self, measured: Mapping[str, float]) -> tuple[PolicyViolation, ...]:
        """Evalúa los porcentajes medidos contra los umbrales por categoría."""
        violations: list[PolicyViolation] = []
        for path in sorted(measured):
            category = self.category_for(path)
            threshold = self.thresholds[category]
            value = measured[path]
            if value < threshold:
                violations.append(
                    PolicyViolation(
                        path=normalize_path(path),
                        category=category,
                        threshold=threshold,
                        measured=value,
                    )
                )
        return tuple(violations)


def normalize_path(path: str) -> str:
    """Normaliza una ruta a formato POSIX relativo para comparar con la política."""
    return path.replace("\\", "/").removeprefix("./")
