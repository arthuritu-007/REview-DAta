from __future__ import annotations

from collections.abc import Callable
from typing import Any


def animate_widget(
    widget: Any,
    property_name: str,
    start_value: float,
    end_value: float,
    duration: int = 400,
    easing_func: Callable[[float], float] | None = None,
) -> None:
    """
    Anima una propiedad de un widget (relx o rely) durante un tiempo determinado.
    """
    if easing_func is None:
        easing_func = lambda p: p * p  # Ease-out-quad

    total_steps = duration // 15  # Aproximadamente 60fps
    if total_steps == 0:
        total_steps = 1
    
    current_step = 0

    def _animate():
        nonlocal current_step
        current_step += 1
        progress = current_step / total_steps
        eased_progress = easing_func(progress)
        current_value = start_value + (end_value - start_value) * eased_progress

        config = {property_name: current_value}
        widget.place_configure(**config)
        
        if current_step < total_steps:
            widget.after(15, _animate)
            return

        widget.place_configure(**{property_name: end_value})

    _animate()
