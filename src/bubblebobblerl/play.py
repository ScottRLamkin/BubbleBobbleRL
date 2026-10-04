"""Play the game yourself: ``uv run --extra play python -m bubblebobblerl.play``

Arrows move, Up or Z jumps, Space shoots. Escape quits, R resets,
[ and ] switch levels.
"""

from __future__ import annotations

import argparse
import sys

from .game import Buttons, Game
from .render import draw_rgb


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--scale", type=int, default=8)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args(argv)

    try:
        import pygame
    except ImportError:
        sys.exit("pygame is required: uv sync --extra play")

    game = Game(level=args.level, lives=3, auto_advance=True)
    pygame.init()
    window = pygame.display.set_mode((96 * args.scale, 64 * args.scale))
    pygame.display.set_caption("Bubble Bobble RL")
    clock = pygame.time.Clock()

    level = args.level
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game.reset(level=level)
                elif event.key == pygame.K_RIGHTBRACKET:
                    level = min(level + 1, len(game.levels))
                    game.reset(level=level)
                elif event.key == pygame.K_LEFTBRACKET:
                    level = max(level - 1, 1)
                    game.reset(level=level)

        keys = pygame.key.get_pressed()
        buttons = Buttons(
            left=keys[pygame.K_LEFT],
            right=keys[pygame.K_RIGHT],
            jump=keys[pygame.K_UP] or keys[pygame.K_z],
            shoot=keys[pygame.K_SPACE],
        )
        game.step(buttons)
        if game.game_over:
            game.reset(level=level)

        frame = draw_rgb(game, scale=args.scale)
        surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        window.blit(surface, (0, 0))
        pygame.display.set_caption(
            f"Bubble Bobble RL - level {game.level_num} "
            f"score {game.score} lives {game.lives}"
        )
        pygame.display.flip()
        clock.tick(args.fps)
    pygame.quit()


if __name__ == "__main__":
    main()
