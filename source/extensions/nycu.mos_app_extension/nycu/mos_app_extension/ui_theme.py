"""Visual tokens shared by the MOS evaluation windows.

The values intentionally mirror the browser-based E3DQA Video Platform so
participants see one coherent evaluation-tool visual language in either mode.
"""

PANEL_BACKGROUND = 0xFF2B2B2B
PANEL_BORDER = 0xFF3A3A3A
# Omni UI integer colours use ABGR channel order, not CSS RGB order.
INTERACTIVE_ACCENT = 0xFFB87A5A  # #5a7ab8
INTERACTIVE_ACCENT_HOVER = 0xFF90624A  # #4a6290
PARTICIPANT_ACCENT = 0xFFFFBBAA  # #aabbff
TEXT_PRIMARY = 0xFFDDDDDD
TEXT_MUTED = 0xFFAAAAAA
TEXT_HINT = 0xFF777777
FIELD_BACKGROUND = 0xFF1E1E1E
CONTROL_BACKGROUND = 0xFF3D3D3D
SLIDER_TRACK = 0xFF555555


def modal_window_flags(ui):
    """Keep study modals fixed and free of Kit's inner title-bar chrome."""
    return (
        ui.WINDOW_FLAGS_NO_TITLE_BAR
        | ui.WINDOW_FLAGS_NO_SCROLLBAR
        | ui.WINDOW_FLAGS_NO_RESIZE
        | ui.WINDOW_FLAGS_NO_DOCKING
    )


def modal_frame_style() -> dict:
    return {
        "background_color": PANEL_BACKGROUND,
        "border_color": PANEL_BORDER,
        "border_width": 1,
    }


def slider_style() -> dict:
    return {
        "color": 0x00000000,
        "secondary_color": INTERACTIVE_ACCENT,
    }


def primary_button_style() -> dict:
    return {
        "background_color": INTERACTIVE_ACCENT,
        "border_color": INTERACTIVE_ACCENT,
        "color": TEXT_PRIMARY,
    }


def text_field_style() -> dict:
    return {
        "background_color": FIELD_BACKGROUND,
        "border_color": SLIDER_TRACK,
        "color": TEXT_PRIMARY,
    }
