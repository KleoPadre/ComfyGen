from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console
from rich.table import Table

from comfygen.models import DeviceInfo, GenerationType, Template, VramTier

console = Console()

GENERATION_TYPE_LABELS = {
    GenerationType.PHOTO: "Фото (текст → изображение)",
    GenerationType.VIDEO: "Видео (текст/изображение → видео)",
    GenerationType.AUDIO: "Аудио (текст → звук/музыка)",
    GenerationType.ANIMATE_PHOTO: "Оживление фото (изображение → короткое видео)",
}

TIER_LABELS = {
    VramTier.SAFE: "✅ Уверенно потянет",
    VramTier.WARNING: "⚠️ На грани, может быть медленно или зависнуть",
    VramTier.UNKNOWN: "❓ Требования к VRAM неизвестны — на свой риск",
}


def choose_generation_type() -> GenerationType:
    choice = questionary.select(
        "Что хотите сгенерировать?",
        choices=[
            questionary.Choice(title=label, value=gen_type)
            for gen_type, label in GENERATION_TYPE_LABELS.items()
        ],
    ).ask()
    if choice is None:
        raise KeyboardInterrupt
    return choice


def choose_device_detection_method() -> str:
    choice = questionary.select(
        "Как определить характеристики устройства?",
        choices=[
            questionary.Choice(title="Через API запущенного ComfyUI (точно)", value="api"),
            questionary.Choice(title="Через ОС напрямую (без запущенного ComfyUI)", value="os"),
            questionary.Choice(title="Гибрид: API, а если Comfy не запущен — через ОС", value="hybrid"),
        ],
    ).ask()
    if choice is None:
        raise KeyboardInterrupt
    return choice


def render_templates_table(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> None:
    table = Table(title="Подходящие модели/шаблоны")
    table.add_column("№")
    table.add_column("Название")
    table.add_column("Статус")
    table.add_column("VRAM")
    row_index = 1
    shown_tiers = (VramTier.SAFE, VramTier.WARNING, VramTier.UNKNOWN) if include_unknown else (VramTier.SAFE, VramTier.WARNING)
    for tier in shown_tiers:
        for template in tiers.get(tier, []):
            vram_gb = f"{template.vram_bytes / 1024**3:.1f} GB" if template.vram_bytes else "—"
            table.add_row(str(row_index), template.title, TIER_LABELS[tier], vram_gb)
            row_index += 1
    console.print(table)


def ask_show_unknown_tier(count: int) -> bool:
    if count == 0:
        return False
    return bool(
        questionary.confirm(
            f"Есть ещё {count} шаблон(ов) с неизвестными требованиями к VRAM. Показать их тоже?",
            default=False,
        ).ask()
    )


def choose_template(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> Template | None:
    candidates = tiers.get(VramTier.SAFE, []) + tiers.get(VramTier.WARNING, [])
    if include_unknown:
        candidates += tiers.get(VramTier.UNKNOWN, [])
    if not candidates:
        console.print("[red]Ни один шаблон не подходит под характеристики устройства.[/red]")
        return None
    choice = questionary.select(
        "Выберите модель/шаблон",
        choices=[questionary.Choice(title=t.title, value=t) for t in candidates],
    ).ask()
    return choice


def ask_prompt() -> str:
    return questionary.text("Введите промпт для генерации:").ask() or ""


def ask_extra_params_wanted() -> bool:
    return bool(questionary.confirm("Настроить дополнительные параметры (negative prompt, разрешение, seed, шаги)?", default=False).ask())


def ask_negative_prompt() -> str | None:
    value = questionary.text("Negative prompt (оставьте пустым, чтобы пропустить):").ask()
    return value or None


def ask_resolution() -> tuple[int, int] | None:
    if not questionary.confirm("Задать разрешение вручную?", default=False).ask():
        return None
    width = int(questionary.text("Ширина:", default="1024").ask())
    height = int(questionary.text("Высота:", default="1024").ask())
    return width, height


def ask_seed_and_steps() -> tuple[int | None, int | None]:
    seed = None
    steps = None
    if questionary.confirm("Задать seed вручную?", default=False).ask():
        seed = int(questionary.text("Seed:", default="0").ask())
    if questionary.confirm("Задать количество шагов вручную?", default=False).ask():
        steps = int(questionary.text("Шаги:", default="20").ask())
    return seed, steps


def ask_image_input_choice() -> Path | None:
    choice = questionary.select(
        "Входное изображение для видео/оживления фото:",
        choices=[
            questionary.Choice(title="Указать путь к файлу сейчас", value="now"),
            questionary.Choice(title="Пропустить — выбрать позже прямо в ComfyUI", value="later"),
        ],
    ).ask()
    if choice != "now":
        return None
    path_str = questionary.path("Путь к изображению:").ask()
    return Path(path_str) if path_str else None
