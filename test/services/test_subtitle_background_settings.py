import json
from pathlib import Path
import unittest

import numpy as np

from app.models.schema import SubtitleRequest, VideoParams
from app.services import video


class TestSubtitleBackgroundSettings(unittest.TestCase):
    def test_subtitle_background_is_disabled_by_default(self):
        """新任务和独立字幕接口都不应在用户未指定时渲染字幕背景。"""
        video_params = VideoParams(video_subject="default subtitle background")
        subtitle_request = SubtitleRequest(video_script="default subtitle background")

        self.assertFalse(video_params.text_background_color)
        self.assertFalse(subtitle_request.text_background_color)

    def test_all_locales_include_subtitle_background_labels(self):
        """
        WebUI 新增字幕背景开关和颜色选择器后，所有已有语言都必须包含对应
        翻译 key，避免某些语言界面直接显示英文内部 key。
        """
        i18n_dir = Path(__file__).parent.parent.parent / "webui" / "i18n"
        required_keys = {
            "Enable Subtitle Background",
            "Subtitle Background Color",
            "Subtitle Colors Are Indistinguishable",
            "Subtitle Font Does Not Support Text",
            "No Voice",
        }

        for locale_file in i18n_dir.glob("*.json"):
            with self.subTest(locale=locale_file.name):
                data = json.loads(locale_file.read_text(encoding="utf-8"))
                translations = data.get("Translation", {})
                missing_keys = required_keys - translations.keys()

                self.assertEqual(missing_keys, set())

    def test_video_params_accepts_disabled_and_colored_subtitle_background(self):
        """
        UI 会根据开关向后端传递 False 或颜色字符串。这里验证 schema 仍然
        接受这两种值，避免后续依赖或类型调整破坏 WebUI 与合成逻辑的契约。
        """
        base_params = {
            "video_subject": "subtitle background smoke",
        }

        disabled_params = VideoParams(
            **base_params,
            text_background_color=False,
        )
        colored_params = VideoParams(
            **base_params,
            text_background_color="#123456",
        )

        self.assertFalse(disabled_params.text_background_color)
        self.assertEqual(colored_params.text_background_color, "#123456")

    def test_visible_text_position_centers_actual_mask_bounds(self):
        """
        TextClip 的画布会包含字体行高和 baseline 空白，直接居中画布会让
        字幕在背景里看起来偏下。这里用一个假 mask 模拟“可见文字像素
        在画布下半部分”的情况，验证 helper 会按真实可见区域重新计算 y。
        """

        class FakeMask:
            def get_frame(self, _):
                mask = np.zeros((46, 100), dtype=float)
                mask[12:46, 10:90] = 1.0
                return mask

        class FakeTextClip:
            w = 100
            h = 46
            mask = FakeMask()

        x, y = video._get_visible_center_position(
            FakeTextClip(), container_width=100, container_height=93
        )

        self.assertEqual(x, 0)
        # 可见像素高度为 34px，放在 93px 容器中应上下各约 29px；
        # 因为 mask 顶部从 12px 开始，所以 TextClip 本身需要向上移动到 18px。
        self.assertEqual(y, 18)

    def _fake_clip(self, *, w=100, h=46, visible=(12, 46)):
        """Gorunen harfleri tuvalin `visible` satir araliginda olan sahte klip."""

        class FakeMask:
            def get_frame(self, _):
                mask = np.zeros((h, w), dtype=float)
                mask[visible[0] : visible[1], 10 : w - 10] = 1.0
                return mask

        class FakeClip:
            pass

        clip = FakeClip()
        clip.w, clip.h, clip.mask = w, h, FakeMask()
        return clip

    def test_subtitle_clip_position_legacy_branches_unchanged(self):
        """`bottom`/`top`/`custom`/`center` — DW-141 oncesi degerler birebir."""
        clip = self._fake_clip()
        beklenen = {
            "bottom": ("center", 1920 * 0.95 - 46),
            "top": ("center", 1920 * 0.05),
            "custom": ("center", (1920 - 46) * 0.78),
            "center": ("center", "center"),
        }
        for konum, cevap in beklenen.items():
            params = VideoParams(video_subject="t", subtitle_position=konum, custom_position=78.0)
            with self.subTest(konum=konum):
                self.assertEqual(video._subtitle_clip_position(clip, params, 1080, 1920), cevap)

    def test_subtitle_clip_position_pins_visible_glyph_bottom(self):
        """`subtitle_text_bottom` HARFLERIN alt kenarini yerlestirir, kutuyu degil.

        Tuval 46px, harfler 12-45 arasinda. Hedef %71 → 1363,2; klip y'si
        1363,2 − 46 = 1317,2 olmali ki son harf satiri 1362'de bitsin.
        """
        clip = self._fake_clip()
        params = VideoParams(
            video_subject="t", subtitle_position="custom", custom_position=78.0,
            subtitle_text_bottom=71.0, subtitle_center_x=43.5,
        )

        x, y = video._subtitle_clip_position(clip, params, 1080, 1920)

        self.assertAlmostEqual(y, 1920 * 0.71 - 46)
        # merkez 469,8 − 50 = 419,8
        self.assertAlmostEqual(x, 1080 * 0.435 - 50)

    def test_subtitle_clip_position_pin_is_independent_of_canvas_height(self):
        """Ayni harf alt kenari: uzun tuval yukari buyur, asagi kaymaz."""
        params = VideoParams(
            video_subject="t", subtitle_position="custom", subtitle_text_bottom=71.0
        )
        kisa = self._fake_clip(h=46, visible=(12, 46))
        uzun = self._fake_clip(h=300, visible=(12, 300))

        _, y_kisa = video._subtitle_clip_position(kisa, params, 1080, 1920)
        _, y_uzun = video._subtitle_clip_position(uzun, params, 1080, 1920)

        self.assertAlmostEqual(y_kisa + 46, y_uzun + 300)

    def test_subtitle_clip_position_without_mask_uses_box_bottom(self):
        """Maske okunamazsa harfler hedefin ustunde kalir, altina sarkmaz; hata yok."""

        class Maskesiz:
            w, h, mask = 100, 46, None

        params = VideoParams(
            video_subject="t", subtitle_position="custom", subtitle_text_bottom=71.0
        )

        x, y = video._subtitle_clip_position(Maskesiz(), params, 1080, 1920)

        self.assertEqual(x, "center")
        self.assertAlmostEqual(y, 1920 * 0.71 - 46)

    def test_subtitle_clip_position_clamps_inside_frame(self):
        clip = self._fake_clip(w=2000, h=3000)
        params = VideoParams(
            video_subject="t", subtitle_position="custom",
            subtitle_text_bottom=1.0, subtitle_center_x=100.0,
        )

        x, y = video._subtitle_clip_position(clip, params, 1080, 1920)

        self.assertEqual(x, 0)
        self.assertEqual(y, 10)

    def test_detects_indistinguishable_subtitle_colors(self):
        invisible_params = VideoParams(
            video_subject="subtitle color validation",
            text_fore_color="#000000",
            text_background_color="#000000",
            stroke_color="#000000",
            stroke_width=1.5,
        )
        different_outline_params = VideoParams(
            video_subject="subtitle color validation",
            text_fore_color="#000000",
            text_background_color="#000000",
            stroke_color="#FFFFFF",
            stroke_width=1.5,
        )
        background_disabled_params = VideoParams(
            video_subject="subtitle color validation",
            text_fore_color="#000000",
            text_background_color=False,
            stroke_color="#000000",
            stroke_width=1.5,
        )

        self.assertTrue(
            video.subtitle_colors_are_indistinguishable(invisible_params)
        )
        self.assertTrue(
            video.subtitle_colors_are_indistinguishable(different_outline_params)
        )
        self.assertFalse(
            video.subtitle_colors_are_indistinguishable(background_disabled_params)
        )

    def test_detects_font_without_chinese_glyphs(self):
        fonts_dir = (
            Path(__file__).parent.parent.parent / "resource" / "fonts"
        )

        self.assertFalse(
            video.subtitle_font_supports_text(
                str(fonts_dir / "BeVietnamPro-Bold.ttf"), "人工智能改变生活"
            )
        )
        self.assertTrue(
            video.subtitle_font_supports_text(
                str(fonts_dir / "MicrosoftYaHeiBold.ttc"), "人工智能改变生活"
            )
        )
        self.assertTrue(
            video.subtitle_font_supports_text(
                str(fonts_dir / "BeVietnamPro-Bold.ttf"), "Artificial intelligence"
            )
        )

    def test_wrap_text_keeps_closing_punctuation_with_text(self):
        """
        中文长句按字符换行时，句号等闭合标点不能独占一行，否则字幕背景
        会被一个单独的小点撑高。这里复现大字号中文长句的边界情况。
        """
        font_path = (
            Path(__file__).parent.parent.parent
            / "resource"
            / "fonts"
            / "MicrosoftYaHeiBold.ttc"
        )

        wrapped_text, _ = video.wrap_text(
            "如果你调整字号，中文笔画也不能被黑色背景遮挡。",
            max_width=1642,
            font=str(font_path),
            fontsize=72,
        )

        self.assertNotIn("\n。", wrapped_text)
        self.assertIn("挡。", wrapped_text)
