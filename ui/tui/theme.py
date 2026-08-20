"""Aletheia's own Textual themes.

The identity green is a three-stop ramp (`$aletheia-green` / `-soft` / `-dim`)
rather than a single value parked in `primary`/`accent`, for two measured
reasons:

1. `primary` and `accent` are not free. Textual 8 derives markdown-fence syntax
   colours from them (`textual/highlight.py`): `Token.Keyword -> $text-accent`,
   `Token.Name -> $text-primary`. The `text-*` variables are *not* overridable
   through `Theme.variables`, so `primary == accent` collapses keywords and
   identifiers to one colour — measured byte-identical `#56ff56`.
2. One brand value used for thirteen elements emphasises none of them. The ramp
   lets the wordmark, the focus ring, and a border be three deliberate weights
   of the same identity.

The text tiers are literal hex rather than Textual's default `auto NN%`. `auto`
resolves in a CSS `color:` declaration but *not* inside Rich markup, where the
alpha is dropped and `[$text-disabled]` renders as pure `#ffffff` — which made
the dimmest tokens in the app (splash labels, status cwd/branch) the brightest
pixels on screen.

Contrast ratios in the comments are against each theme's own background.
"""
from textual.theme import Theme

# Identity ramp: hue ~142, three luminances, spent by tier in styles.tcss.
GREEN = "#2fcc68"       # hero      9.28:1 — wordmark, markdown h1. One at a time.
GREEN_SOFT = "#22a556"  # active    6.13:1 — focus, state dot/spinner, "❯", h2.
GREEN_DIM = "#1b7540"   # structure 3.41:1 — splash border, user-turn rule.

ALETHEIA_THEME = Theme(
    name="aletheia",
    # The base colours exist to drive `text-*` (markdown + syntax highlighting).
    # Their job is to be six mutually distinguishable hues, not to be the brand.
    primary="#5f9e72",    # sage   -> text-primary: Token.Name, bullets. Quiet
                          #           identifiers are the point; a bright primary
                          #           painted every identifier brand-green.
    secondary="#4d9dc4",  # steel  -> Token.Name.Variable, links, blockquotes.
    accent="#a98cc4",     # violet -> Token.Keyword. Deliberately not green and
                          #           not the brand: it appears only inside code,
                          #           so it can never compete with the chrome.
    foreground="#c8ccc9",  # body text 12.05:1, with a one-step green cast.
    background="#0c0c0c",  # near-black; quantises safely to xterm 232/233.
    surface="#141414",     # code-fence field — must be LIGHTER than background.
    panel="#1c1c1c",       # command-palette field.
    success="#3fb96b",     # green -> Token.String: where green lives inside code.
    warning="#d99a3f",     # amber -> functions, numbers, inline code.
    error="#e06c6c",       # red   -> constants, namespaces, error notes.
    dark=True,
    variables={
        "aletheia-green": GREEN,
        "aletheia-green-soft": GREEN_SOFT,
        "aletheia-green-dim": GREEN_DIM,
        # Literal hex, not `auto NN%` — see the module docstring.
        "text": "#c8ccc9",                 # 12.05:1  body
        "text-muted": "#949b96",           #  6.88:1  user echo, status verb
        "text-disabled": "#7f8781",         #  5.30:1  hints, labels, notes
        "foreground-disabled": "#5a615c",   #  3.07:1  the input while streaming
        "boost": "#ffffff0d",               # 5% lift so a blockquote has a field
        # One structural neutral at the 3:1 floor for everything that delimits
        # but does not speak.
        "border": "#5a615c",
        "border-blurred": "#5a615c",
        "scrollbar": "#5a615c",
        "scrollbar-hover": "#7f8781",
        "scrollbar-active": GREEN_SOFT,     # grabbing it is an interaction
        # Textual defaults the trough to #000000 — a visible seam on #0c0c0c.
        "scrollbar-background": "#0c0c0c",
        "scrollbar-background-hover": "#0c0c0c",
        "scrollbar-background-active": "#0c0c0c",
        "scrollbar-corner-color": "#0c0c0c",
        # h1/h2/h3 all default to `primary`: three identical headings. A ladder:
        "markdown-h1-color": GREEN,         # 9.28:1
        "markdown-h2-color": GREEN_SOFT,    # 6.13:1
        "markdown-h3-color": "#c8ccc9",     # neutral + bold; green stops at h2
        # link-color defaults to `auto 87%` (#dfdfdf): links were body text with
        # an underline. Steel is the only cool hue in the transcript.
        "link-color": "#8abed8",
        "link-background-hover": "#8abed8",
        "link-color-hover": "#0c0c0c",      # default was white on accent: 1.4:1
        "input-cursor-background": "#c8ccc9",
        "input-cursor-foreground": "#0c0c0c",
        "input-selection-background": GREEN_SOFT + "59",
        "screen-selection-background": GREEN_SOFT + "40",
        "block-cursor-background": GREEN_SOFT,
        "block-cursor-foreground": "#0c0c0c",
        "block-cursor-blurred-background": GREEN_SOFT + "2b",
        "block-cursor-blurred-foreground": "#c8ccc9",
        "footer-key-foreground": GREEN,
    },
)

# On a light background a 60x6 block-shadow glyph slab in saturated green is a
# heavy stain, so the identity moves off the logo and into the *state*: focus
# ring, status dot, "❯", h2. "The logo is green" becomes "the attention is green".
LIGHT_GREEN = "#0a6b34"       # hero      6.23:1
LIGHT_GREEN_SOFT = "#118040"  # active    4.71:1
LIGHT_GREEN_DIM = "#1a9a52"   # structure 3.41:1

ALETHEIA_LIGHT_THEME = Theme(
    name="aletheia-light",
    primary="#3d7a55",    # light themes tint text-* toward black, not white
    secondary="#1f6f96",
    accent="#7a5c9e",
    foreground="#161917",
    background="#f7f8f7",
    surface="#eff1f0",
    panel="#e4e7e5",
    success="#1d8a4e",
    warning="#8a5c10",
    error="#b03a3a",
    dark=False,
    variables={
        "aletheia-green": LIGHT_GREEN,
        "aletheia-green-soft": LIGHT_GREEN_SOFT,
        "aletheia-green-dim": LIGHT_GREEN_DIM,
        "text": "#161917",
        "text-muted": "#545a56",
        "text-disabled": "#6a716c",
        "foreground-disabled": "#a9b0ab",
        "boost": "#0000000d",
        "border": "#868d88",
        "border-blurred": "#868d88",
        "scrollbar": "#868d88",
        "scrollbar-hover": "#6a716c",
        "scrollbar-active": LIGHT_GREEN_SOFT,
        "scrollbar-background": "#f7f8f7",
        "scrollbar-background-hover": "#f7f8f7",
        "scrollbar-background-active": "#f7f8f7",
        "scrollbar-corner-color": "#f7f8f7",
        "markdown-h1-color": "#161917",
        "markdown-h2-color": LIGHT_GREEN,
        "markdown-h3-color": "#161917",
        "link-color": "#144963",
        "link-background-hover": "#144963",
        "link-color-hover": "#f7f8f7",
        "input-cursor-background": "#161917",
        "input-cursor-foreground": "#f7f8f7",
        "input-selection-background": LIGHT_GREEN_SOFT + "33",
        "screen-selection-background": LIGHT_GREEN_SOFT + "26",
        "block-cursor-background": LIGHT_GREEN_SOFT,
        "block-cursor-foreground": "#f7f8f7",
        "block-cursor-blurred-background": LIGHT_GREEN_SOFT + "1f",
        "block-cursor-blurred-foreground": "#161917",
        "footer-key-foreground": LIGHT_GREEN,
    },
)

#: Defaults for the identity ramp. styles.tcss is parsed before on_mount runs,
#: so `$aletheia-green*` must already resolve or startup dies with
#: UnresolvedVariableError; App.get_theme_variable_defaults() returns these.
RAMP_DEFAULTS = {
    "aletheia-green": GREEN,
    "aletheia-green-soft": GREEN_SOFT,
    "aletheia-green-dim": GREEN_DIM,
}


def apply_theme(app, name: str) -> None:
    """Register both themes and select `name`, falling back to the dark one.

    An unknown ALETHEIA_THEME must not take the app down on startup.
    """
    app.register_theme(ALETHEIA_THEME)
    app.register_theme(ALETHEIA_LIGHT_THEME)
    try:
        app.theme = name
    except Exception:
        app.theme = ALETHEIA_THEME.name
