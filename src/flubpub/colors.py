COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "clean": {
        "--bg": "#ffffff",
        "--fg": "#222222",
        "--accent": "#0055cc",
        "--link": "#0055cc",
        "--link-visited": "#551a8b",
        "--border": "#dddddd",
        "--heading": "#222222",
        "--code-bg": "#f5f5f5",
        "--code-fg": "#333333",
    },
    "neon": {
        "--bg": "#1a1a2e",
        "--fg": "#ffcc00",
        "--accent": "#ff6600",
        "--link": "#ff6600",
        "--link-visited": "#ff6600",
        "--border": "#333366",
        "--heading": "#ffcc00",
        "--code-bg": "#111111",
        "--code-fg": "#00ff00",
        "--marquee-bg": "navy",
        "--counter-bg": "#111111",
        "--counter-fg": "#00ff00",
    },
    "midnight": {
        "--bg": "#000040",
        "--fg": "#e0e0e0",
        "--accent": "#ffff99",
        "--link": "#6699ff",
        "--link-visited": "#9966cc",
        "--border": "#444466",
        "--heading": "#ffff99",
        "--code-bg": "#000030",
        "--code-fg": "#e0e0e0",
        "--footer-fg": "#888888",
    },
    "terminal": {
        "--bg": "#000000",
        "--fg": "#00ff00",
        "--accent": "#00ff00",
        "--link": "#00ffff",
        "--link-visited": "#00ffff",
        "--border": "#003300",
        "--heading": "#00ff00",
        "--code-bg": "#001100",
        "--code-fg": "#00ff00",
        "--footer-fg": "#006600",
    },
    "starfield": {
        "--bg": "#000022",
        "--fg": "#aaccff",
        "--accent": "#ffcc00",
        "--link": "#66aaff",
        "--link-visited": "#8888cc",
        "--border": "#333366",
        "--heading": "#ffcc00",
        "--code-bg": "#000030",
        "--code-fg": "#aaccff",
        "--panel-bg": "rgba(0,0,30,0.7)",
        "--footer-fg": "#667799",
        "--badge-bg": "#222222",
        "--badge-fg": "#aaaaaa",
    },
    "parchment": {
        "--bg": "#e8e8e0",
        "--fg": "#333333",
        "--accent": "#cc9900",
        "--link": "#0000cc",
        "--link-visited": "#660099",
        "--border": "#cccccc",
        "--heading": "#333333",
        "--code-bg": "#d8d8d0",
        "--code-fg": "#333333",
        "--nav-bg": "#d0d0d0",
        "--construction-bg": "#ffffee",
        "--construction-border": "#cc9900",
        "--construction-fg": "#663300",
    },
}

DEFAULT_SCHEMES: dict[str, str] = {
    "default": "clean",
    "geocities": "neon",
    "academic": "midnight",
    "hacker": "terminal",
    "angelfire": "starfield",
    "web-ring": "parchment",
}


def available_color_schemes() -> list[str]:
    return list(COLOR_SCHEMES.keys())


def get_color_scheme(name: str) -> dict[str, str]:
    if name not in COLOR_SCHEMES:
        raise ValueError(f"Unknown color scheme: {name}")
    return COLOR_SCHEMES[name]


def color_scheme_css(name: str) -> str:
    props = get_color_scheme(name)
    lines = "; ".join(f"{k}: {v}" for k, v in props.items())
    return f"<style>:root {{ {lines} }}</style>"
