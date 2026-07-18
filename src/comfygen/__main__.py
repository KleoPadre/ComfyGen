from __future__ import annotations

import argparse
import sys

import httpx
from rich.console import Console

from comfygen.catalog import fetch_remote_template, filter_by_generation_type, get_index, parse_templates
from comfygen.comfy_client import ComfyClient
from comfygen.config import CACHE_PATH, load_config
from comfygen.device_detect import DeviceDetectionError, UnsupportedPlatformError, detect_hybrid, detect_via_api, detect_via_os
from comfygen.models import DeviceInfo, VramTier
from comfygen.vram_filter import classify_templates
from comfygen.workflow_editor import (
    set_image_input,
    set_negative_prompt,
    set_positive_prompt,
    set_resolution,
    set_seed,
    set_steps,
)
from comfygen import ui

console = Console()


def _detect_device(method: str, client: ComfyClient, config) -> DeviceInfo:
    if method == "api":
        return detect_via_api(client)
    if method == "os":
        return detect_via_os(config.apple_unified_memory_factor)
    return detect_hybrid(client, config.apple_unified_memory_factor)


def run(force_refresh: bool = False) -> None:
    config = load_config()
    client = ComfyClient(config.comfy_base_url)

    gen_type = ui.choose_generation_type()
    method = ui.choose_device_detection_method()

    try:
        device = _detect_device(method, client, config)
    except (DeviceDetectionError, UnsupportedPlatformError) as exc:
        console.print(f"[red]Не удалось определить характеристики устройства: {exc}[/red]")
        return
    except httpx.HTTPError as exc:
        console.print(
            f"[red]ComfyUI не отвечает на {config.comfy_base_url}: {exc}. "
            "Запустите ComfyUI или выберите другой способ детекции.[/red]"
        )
        return

    console.print(f"Обнаружено устройство: {device.device_type}, VRAM ≈ {device.available_vram_bytes / 1024**3:.1f} GB (источник: {device.source})")

    with httpx.Client() as http_client:
        try:
            raw_index = get_index(http_client, CACHE_PATH, config.cache_ttl_seconds, force_refresh=force_refresh)
        except httpx.HTTPError as exc:
            console.print(
                f"[red]Не удалось загрузить каталог моделей с GitHub: {exc}. "
                "Проверьте подключение к интернету и повторите.[/red]"
            )
            return

        templates = parse_templates(raw_index)
        candidates = filter_by_generation_type(templates, gen_type)
        tiers = classify_templates(candidates, device, config.vram_safe_factor, config.vram_warning_factor)

        ui.render_templates_table(tiers)
        unknown_count = len(tiers.get(VramTier.UNKNOWN, []))
        include_unknown = ui.ask_show_unknown_tier(unknown_count)
        if include_unknown:
            ui.render_templates_table(tiers, include_unknown=True)
        template = ui.choose_template(tiers, include_unknown=include_unknown)
        if template is None:
            return

        try:
            workflow = fetch_remote_template(http_client, template.name)
        except httpx.HTTPError as exc:
            console.print(f"[red]Не удалось загрузить файл шаблона {template.name}: {exc}[/red]")
            return

    prompt_text = ui.ask_prompt()
    if not set_positive_prompt(workflow, prompt_text):
        console.print(
            "[yellow]Не удалось автоматически подставить промпт в этот шаблон — "
            "впишите его вручную в узле CLIP/текстового энкодера прямо в ComfyUI.[/yellow]"
        )

    if ui.ask_extra_params_wanted():
        negative = ui.ask_negative_prompt()
        if negative:
            if not set_negative_prompt(workflow, negative):
                console.print("[yellow]Не удалось применить negative prompt — узел не найден в этом шаблоне.[/yellow]")
        resolution = ui.ask_resolution()
        if resolution:
            if not set_resolution(workflow, *resolution):
                console.print("[yellow]Не удалось применить разрешение — узел не найден в этом шаблоне.[/yellow]")
        seed, steps = ui.ask_seed_and_steps()
        if seed is not None:
            if not set_seed(workflow, seed):
                console.print("[yellow]Не удалось применить seed — узел не найден в этом шаблоне.[/yellow]")
        if steps is not None:
            if not set_steps(workflow, steps):
                console.print("[yellow]Не удалось применить количество шагов — узел не найден в этом шаблоне.[/yellow]")

    if gen_type.value in ("video", "animate_photo"):
        image_path = ui.ask_image_input_choice()
        if image_path is not None:
            if not client.health_check():
                console.print("[red]ComfyUI не запущен — не могу загрузить изображение. Запустите ComfyUI и повторите.[/red]")
                return
            try:
                uploaded_name = client.upload_image(image_path)
            except (FileNotFoundError, OSError) as exc:
                console.print(f"[red]Не удалось прочитать файл изображения: {exc}[/red]")
                return
            except httpx.HTTPError as exc:
                console.print(f"[red]Не удалось загрузить изображение в ComfyUI: {exc}[/red]")
                return
            set_image_input(workflow, uploaded_name)

    if not client.health_check():
        console.print(f"[red]ComfyUI не запущен на {config.comfy_base_url} — запустите его, чтобы сохранить workflow.[/red]")
        return

    output_filename = f"comfygen_{template.name}.json"
    try:
        client.save_workflow(output_filename, workflow)
    except httpx.HTTPError as exc:
        console.print(
            f"[red]Не удалось сохранить workflow в ComfyUI: {exc}. "
            "Убедитесь, что ComfyUI запущен, и повторите.[/red]"
        )
        return
    console.print(f"[green]Готово! Workflow сохранён в ComfyUI как \"{output_filename}\" — откройте его на вкладке Workflows и нажмите Queue.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="comfygen", description="CLI-помощник для генерации в ComfyUI")
    parser.add_argument("--refresh", action="store_true", help="Принудительно обновить кеш каталога шаблонов Comfy")
    args = parser.parse_args()
    try:
        run(force_refresh=args.refresh)
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
