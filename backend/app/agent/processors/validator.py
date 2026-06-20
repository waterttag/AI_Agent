"""HTML5 game validator — checks that generated games are playable."""

from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class ValidationResult:
    """Result of game validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GameValidator:
    """
    Validates that an AI-generated HTML game meets minimum playability standards.

    Checks performed:
    1. HTML is parseable
    2. Contains a <script> block with game logic
    3. Has a game loop (requestAnimationFrame, setInterval, Phaser config)
    4. Has user interaction handling (keyboard/mouse/touch events)
    5. No eval() usage (security)
    6. No external requests except to approved CDNs
    """

    APPROVED_CDNS = [
        "cdn.jsdelivr.net",
        "cdnjs.cloudflare.com",
        "unpkg.com",
    ]

    def validate(self, html_code: str) -> ValidationResult:
        """Validate the generated game HTML."""
        result = ValidationResult(is_valid=True)

        # 1. Parseability
        try:
            soup = BeautifulSoup(html_code, "html.parser")
        except Exception as e:
            result.is_valid = False
            result.errors.append(f"HTML is not parseable: {e}")
            return result

        # 2. Must have script(s)
        scripts = soup.find_all("script")
        inline_scripts = [s for s in scripts if s.string and len(s.string.strip()) > 50]

        if not inline_scripts and not any(
            s.get("src", "") for s in scripts
        ):
            result.is_valid = False
            result.errors.append("No game logic found: must have <script> with substantive code")

        # 3. Must have a game loop
        all_script_text = " ".join(
            (s.string or "") + (s.get("src", "")) for s in scripts
        )

        has_game_loop = any(
            keyword in all_script_text
            for keyword in [
                "requestAnimationFrame",
                "setInterval",
                "Phaser.Game",
                "new Phaser.Game",
                "gameLoop",
                "game_loop",
                "update(",
            ]
        )

        if not has_game_loop:
            result.warnings.append(
                "No game loop detected (requestAnimationFrame/setInterval/Phaser not found)"
            )

        # 4. Must have input handling
        has_input = any(
            keyword in all_script_text
            for keyword in [
                "addEventListener",
                "keydown",
                "keyup",
                "keypress",
                "mousedown",
                "mouseup",
                "mousemove",
                "click",
                "touchstart",
                "touchend",
                "touchmove",
                "pointerdown",
                "input.keyboard",
                "this.input",
            ]
        )

        if not has_input:
            result.warnings.append(
                "No user input handling detected — game may not be interactive"
            )

        # 5. No eval() — security
        if "eval(" in all_script_text:
            result.errors.append("Security: eval() usage detected — not allowed")
            result.is_valid = False

        # 6. Check external script sources
        for script in scripts:
            src = script.get("src", "")
            if src and not any(cdn in src for cdn in self.APPROVED_CDNS):
                result.warnings.append(
                    f"External script source not in approved CDNs: {src}"
                )

        return result
