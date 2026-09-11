"""Veyrion Workspace design system.

A restrained, document-first visual identity:
  * Ink & paper palette with a burnt-sienna accent — deliberately not the
    usual blue/purple AI look.
  * Five full themes: light, dark, OLED, sepia, high-contrast.
  * Custom QSS covering every control, compact professional density,
    visible focus rings (accessibility), and consistent radii/shadows.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ACCENT_FALLBACK = "#C7522A"


@dataclass
class Palette:
    name: str = "light"
    window: str = "#F6F4EF"          # warm paper
    window_alt: str = "#EDEAE2"      # panels
    surface: str = "#FFFFFF"         # document canvas
    surface_sunken: str = "#E6E2D8"
    text: str = "#2A2721"
    text_dim: str = "#6E6A61"
    text_disabled: str = "#A9A49A"
    border: str = "#D8D3C7"
    border_strong: str = "#B9B2A3"
    accent: str = ACCENT_FALLBACK
    accent_text: str = "#FFFFFF"
    accent_soft: str = "#F3E1D7"
    selection_bg: str = "#C7522A"
    selection_text: str = "#FFFFFF"
    success: str = "#3E7C4F"
    warning: str = "#B07A21"
    error: str = "#A33B2E"
    link: str = "#8A5A2B"
    shadow: str = "#00000030"
    tooltip_bg: str = "#33302A"
    tooltip_text: str = "#F6F4EF"
    scrollbar: str = "#C9C3B6"
    tab_active: str = "#FFFFFF"
    code_bg: str = "#EFECE4"

    def is_dark(self) -> bool:
        return self.name in ("dark", "oled", "high-contrast")


LIGHT = Palette("light")

DARK = Palette(
    name="dark",
    window="#26241F",
    window_alt="#2D2A25",
    surface="#1D1B17",
    surface_sunken="#141210",
    text="#E8E4DB",
    text_dim="#A39E92",
    text_disabled="#6E6A61",
    border="#3B372F",
    border_strong="#57524A",
    accent_soft="#4A3527",
    link="#D8A05C",
    tooltip_bg="#0F0E0C",
    tooltip_text="#E8E4DB",
    scrollbar="#4A463D",
    tab_active="#33302A",
    code_bg="#2A2722",
)

OLED = Palette(
    name="oled",
    window="#000000",
    window_alt="#0A0A0A",
    surface="#000000",
    surface_sunken="#000000",
    text="#E8E4DB",
    text_dim="#8B877E",
    text_disabled="#55524B",
    border="#1E1E1E",
    border_strong="#333330",
    accent_soft="#3A2417",
    link="#D8A05C",
    tooltip_bg="#111111",
    tooltip_text="#E8E4DB",
    scrollbar="#2A2A2A",
    tab_active="#141414",
    code_bg="#0E0E0E",
)

SEPIA = Palette(
    name="sepia",
    window="#F0E6D2",
    window_alt="#E8DCC2",
    surface="#FAF3E3",
    surface_sunken="#E3D5B8",
    text="#4A3F2E",
    text_dim="#8A7C64",
    text_disabled="#B5A88E",
    border="#D6C8A8",
    border_strong="#BCA97F",
    accent="#A05A2C",
    accent_soft="#EBD9BD",
    link="#7A4A20",
    tooltip_bg="#4A3F2E",
    tooltip_text="#FAF3E3",
    scrollbar="#C9B892",
    tab_active="#FAF3E3",
    code_bg="#EFE4C9",
)

HIGH_CONTRAST = Palette(
    name="high-contrast",
    window="#FFFFFF",
    window_alt="#F0F0F0",
    surface="#FFFFFF",
    surface_sunken="#E8E8E8",
    text="#000000",
    text_dim="#303030",
    text_disabled="#606060",
    border="#000000",
    border_strong="#000000",
    accent="#003D99",
    accent_soft="#D6E4FF",
    selection_bg="#003D99",
    link="#003D99",
    tooltip_bg="#000000",
    tooltip_text="#FFFFFF",
    scrollbar="#808080",
    tab_active="#FFFFFF",
    code_bg="#F0F0F0",
)

THEMES: dict[str, Palette] = {
    "light": LIGHT, "dark": DARK, "oled": OLED, "sepia": SEPIA,
    "high-contrast": HIGH_CONTRAST,
}

DYSLEXIA_FONT_STACK = "Atkinson Hyperlegible, Verdana, Tahoma, Segoe UI"


def get_palette(theme_name: str, accent: str = "") -> Palette:
    base = THEMES.get(theme_name, LIGHT)
    if accent and len(accent) in (4, 7) and accent.startswith("#"):
        import copy
        p = copy.copy(base)
        p.accent = accent
        # Derive a soft variant by blending with the window color.
        p.accent_soft = _blend(accent, base.window, 0.18)
        p.selection_bg = accent
        p.link = _blend(accent, "#0000FF" if not p.is_dark() else "#88AAFF", 0.35)
        return p
    return base


def _blend(c1: str, c2: str, t: float) -> str:
    def parse(c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    a, b = parse(c1), parse(c2)
    mix = tuple(int(a[i] * t + b[i] * (1 - t)) for i in range(3))
    return "#%02x%02x%02x" % mix


def build_qss(p: Palette, *, large_text: bool = False,
              dyslexia_font: bool = False, reduced_motion: bool = False) -> str:
    base_pt = 10 if not large_text else 12
    font_stack = DYSLEXIA_FONT_STACK if dyslexia_font else \
        "'Segoe UI', 'Noto Sans', 'Helvetica Neue', sans-serif"
    serif_stack = "'Georgia', 'Charter', 'Iowan Old Style', serif"

    return f"""
* {{
    font-family: {font_stack};
    font-size: {base_pt}pt;
    outline: none;
}}
QMainWindow, QDialog {{
    background: {p.window};
    color: {p.text};
}}
QWidget {{
    color: {p.text};
    font-size: {base_pt}pt;
}}
QToolTip {{
    background: {p.tooltip_bg};
    color: {p.tooltip_text};
    border: 1px solid {p.border_strong};
    padding: 5px 8px;
    font-size: {base_pt - 1}pt;
}}
/* ---------- Menus ---------- */
QMenuBar {{
    background: {p.window};
    border-bottom: 1px solid {p.border};
    padding: 1px 4px;
}}
QMenuBar::item {{
    padding: 4px 9px;
    border-radius: 3px;
    background: transparent;
}}
QMenuBar::item:selected {{ background: {p.accent_soft}; }}
QMenu {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    padding: 5px 2px;
}}
QMenu::item {{
    padding: 5px 26px 5px 24px;
    border-radius: 3px;
    margin: 0 6px;
}}
QMenu::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
QMenu::item:disabled {{ color: {p.text_disabled}; }}
QMenu::separator {{
    height: 1px; background: {p.border}; margin: 5px 10px;
}}
QMenu::right-arrow {{ width: 12px; height: 12px; }}

/* ---------- Toolbar ---------- */
QToolBar {{
    background: {p.window};
    border: none;
    border-bottom: 1px solid {p.border};
    spacing: 2px;
    padding: 3px 6px;
}}
QToolBar::separator {{
    width: 1px; background: {p.border}; margin: 5px 5px;
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
    margin: 0px;
    color: {p.text};
}}
QToolButton:hover {{ background: {p.accent_soft}; }}
QToolButton:pressed {{ background: {p.border}; }}
QToolButton:checked {{
    background: {p.accent};
    color: {p.accent_text};
}}
QToolButton:disabled {{ color: {p.text_disabled}; }}
QToolButton::menu-indicator {{ image: none; }}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-top: none;
    background: {p.surface};
}}
QTabBar::tab {{
    background: {p.window_alt};
    color: {p.text_dim};
    border: 1px solid {p.border};
    border-bottom: none;
    padding: 5px 12px;
    margin-right: 1px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 80px;
}}
QTabBar::tab:selected {{
    background: {p.tab_active};
    color: {p.text};
    border-color: {p.border_strong};
}}
QTabBar::tab:hover:!selected {{ background: {p.surface_sunken}; }}

/* ---------- Dock widgets ---------- */
QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    color: {p.text};
}}
QDockWidget::title {{
    background: {p.window_alt};
    border: 1px solid {p.border};
    padding: 5px 10px;
    font-weight: 600;
    font-size: {base_pt - 1}pt;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}

/* ---------- Inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 4px;
    padding: 4px 7px;
    selection-background-color: {p.selection_bg};
    selection-color: {p.selection_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {p.accent};
    padding: 3px 6px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background: {p.surface_sunken};
    color: {p.text_disabled};
}}
QComboBox::drop-down {{
    border: none; width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_dim};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {p.window_alt};
    border: 1px solid {p.border};
    width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {p.accent_soft};
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {p.window_alt};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 20px;
}}
QPushButton:hover {{ background: {p.accent_soft}; border-color: {p.accent}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:default {{
    background: {p.accent};
    color: {p.accent_text};
    border-color: {p.accent};
    font-weight: 600;
}}
QPushButton:default:hover {{ background: {p.accent}; border-color: {p.accent}; }}
QPushButton:disabled {{ color: {p.text_disabled}; background: {p.surface_sunken}; }}
QPushButton#accentButton {{
    background: {p.accent}; color: {p.accent_text}; border: none;
    font-weight: 600;
}}
QPushButton#dangerButton {{
    background: {p.error}; color: #fff; border: none; font-weight: 600;
}}

/* ---------- Lists / trees / tables ---------- */
QTreeView, QListView, QTableView, QListWidget, QTreeWidget, QTableWidget {{
    background: {p.surface};
    alternate-background-color: {p.window_alt};
    border: 1px solid {p.border};
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
    outline: 0;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 3px 6px;
    border: none;
}}
QTreeView::item:hover, QListView::item:hover {{ background: {p.accent_soft}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {p.accent};
    color: {p.accent_text};
}}
QHeaderView::section {{
    background: {p.window_alt};
    color: {p.text_dim};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border_strong};
    padding: 5px 8px;
    font-weight: 600;
    font-size: {base_pt - 1}pt;
}}
QTableCornerButton::section {{
    background: {p.window_alt};
    border: none;
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.scrollbar}; border-radius: 4px; min-height: 30px;
    margin: 2px 3px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.border_strong}; }}
QScrollBar:horizontal {{
    background: transparent; height: 11px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p.scrollbar}; border-radius: 4px; min-width: 30px;
    margin: 3px 2px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- Status bar ---------- */
QStatusBar {{
    background: {p.window_alt};
    color: {p.text_dim};
    border-top: 1px solid {p.border};
}}
QStatusBar::item {{ border: none; }}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {p.surface_sunken};
    border: 1px solid {p.border};
    border-radius: 3px;
    text-align: center;
    color: {p.text};
    font-size: {base_pt - 1}pt;
    min-height: 14px;
}}
QProgressBar::chunk {{
    background: {p.accent};
    border-radius: 2px;
}}

/* ---------- Checkbox / radio ---------- */
QCheckBox, QRadioButton {{
    spacing: 7px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {p.border_strong};
    background: {p.surface};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent};
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.7, fx:0.5, fy:0.5,
        stop:0 {p.accent}, stop:0.55 {p.accent}, stop:0.7 {p.surface}, stop:1 {p.surface});
    border-color: {p.accent};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: {p.surface_sunken}; border-color: {p.border};
}}

/* ---------- Sliders ---------- */
QSlider::groove:horizontal {{
    height: 4px; background: {p.surface_sunken}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p.accent};
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}

/* ---------- Splitter ---------- */
QSplitter::handle {{
    background: {p.border};
}}
QSplitter::handle:hover {{ background: {p.accent}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}

/* ---------- Group box ---------- */
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 6px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {p.text_dim};
    font-size: {base_pt - 1}pt;
    letter-spacing: 0.4px;
}}

/* ---------- Scroll area (document canvas) ---------- */
QScrollArea {{
    background: {p.surface_sunken};
    border: none;
}}
QAbstractScrollArea::corner {{ background: {p.window_alt}; }}

/* ---------- Cards / panels ---------- */
QFrame#panelCard {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 5px;
}}
QFrame#sidebarPanel {{
    background: {p.window_alt};
    border: none;
    border-right: 1px solid {p.border};
}}
QLabel#panelHeader {{
    color: {p.text_dim};
    font-weight: 600;
    font-size: {base_pt - 1}pt;
    letter-spacing: 0.6px;
}}
QLabel#dimLabel {{ color: {p.text_dim}; }}
QLabel#titleLabel {{ font-size: {base_pt + 4}pt; font-weight: 700; }}
QLabel#docCanvas {{ background: {p.surface_sunken}; }}

/* ---------- Command palette ---------- */
QFrame#paletteFrame {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
}}
QListView#paletteList::item {{ padding: 7px 10px; border-radius: 4px; margin: 1px 4px; }}

/* ---------- Links ---------- */
QLabel[hyperlink="true"] {{
    color: {p.link};
    text-decoration: underline;
}}
/* ---------- Document text views ---------- */
QPlainTextEdit#documentText {{
    background: {p.surface};
    color: {p.text};
    border: none;
    font-family: {serif_stack};
    font-size: {base_pt + 2}pt;
    padding: 24px 30px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QTextEdit#codeEditor {{
    background: {p.code_bg};
    color: {p.text};
    border: none;
    font-family: 'Consolas', 'Cascadia Mono', monospace;
    font-size: {base_pt}pt;
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
}}
"""
