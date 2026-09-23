import importlib.util
import pathlib
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = PACKAGE_DIR / "ui_theme.py"
EXTENSION_PATH = PACKAGE_DIR / "extension.py"


def _load_theme_module():
    spec = importlib.util.spec_from_file_location("ui_theme", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ui_theme"] = module
    spec.loader.exec_module(module)
    return module


class _FakeUi:
    WINDOW_FLAGS_NO_TITLE_BAR = 1
    WINDOW_FLAGS_NO_SCROLLBAR = 2
    WINDOW_FLAGS_NO_RESIZE = 4
    WINDOW_FLAGS_NO_DOCKING = 8


class MosUiThemeTests(unittest.TestCase):
    def test_modal_theme_uses_video_platform_panel_and_accent_tokens(self):
        theme = _load_theme_module()

        self.assertEqual(theme.PANEL_BACKGROUND, 0xFF2B2B2B)
        self.assertEqual(theme.PANEL_BORDER, 0xFF3A3A3A)
        self.assertEqual(theme.INTERACTIVE_ACCENT, 0xFFB87A5A)
        self.assertEqual(theme.PARTICIPANT_ACCENT, 0xFFFFBBAA)

    def test_modal_frame_style_draws_the_panel_instead_of_styling_window_chrome(self):
        theme = _load_theme_module()

        self.assertEqual(
            theme.modal_frame_style(),
            {
                "background_color": theme.PANEL_BACKGROUND,
                "border_color": theme.PANEL_BORDER,
                "border_width": 1,
            },
        )

    def test_slider_style_uses_the_accent_for_the_handle_not_the_value_overlay(self):
        theme = _load_theme_module()

        self.assertEqual(
            theme.slider_style(),
            {
                "color": 0x00000000,
                "secondary_color": theme.INTERACTIVE_ACCENT,
            },
        )

    def test_modal_flags_remove_kit_chrome_and_disable_window_management(self):
        theme = _load_theme_module()

        self.assertEqual(theme.modal_window_flags(_FakeUi), 15)

    def test_prompt_and_scoring_windows_use_the_shared_chrome_free_flags_and_frame_style(self):
        source = EXTENSION_PATH.read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("flags=modal_window_flags(ui)"), 2)
        self.assertIn("self._prompt_win.frame.set_style(modal_frame_style())", source)
        self.assertIn("self._scoring_win.frame.set_style(modal_frame_style())", source)
        self.assertIn("_SLIDER_STYLE = {**slider_style()", source)

    def test_next_button_uses_a_font_safe_right_chevron(self):
        source = EXTENSION_PATH.read_text(encoding="utf-8")

        self.assertIn('"Next  >"', source)
        self.assertNotIn('"Next  ▶"', source)

    def test_scoring_ui_uses_discrete_half_step_controls_and_five_anchors(self):
        source = EXTENSION_PATH.read_text(encoding="utf-8")

        self.assertIn("ui.SimpleIntModel(6)", source)
        self.assertIn("ui.IntSlider(", source)
        self.assertIn("min=2", source)
        self.assertIn("max=10", source)
        self.assertIn("with ui.ZStack(", source)
        self.assertIn("for index, step_label in enumerate(_SLIDER_STEPS)", source)
        self.assertIn("offset_x=ui.Pixel(_score_anchor_offset(index))", source)
        self.assertNotIn("ui.FloatSlider(", source)


if __name__ == "__main__":
    unittest.main()
