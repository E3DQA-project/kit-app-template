# Repository Guidelines

## Project Structure & Module Organization

This repository is an NVIDIA Omniverse Kit application template. Put working applications in `source/apps/` (`.kit` manifests) and Python/C++ extensions in `source/extensions/`. Reusable application and extension scaffolding belongs in `templates/`; repository tooling and dependency definitions are in `tools/`. Build and repository configuration lives in `premake5.lua`, `repo.toml`, and `repo_tools.toml`. Keep documentation and screenshots in `README.md` and `readme-assets/`.

## Build, Test, and Development Commands

Run commands from the repository root. On Linux use `./repo.sh`; on Windows use `repo.bat`:

- `./repo.sh template new` — create an application or extension from a template.
- `./repo.sh build` — fetch dependencies and build applications/extensions in `source/`.
- `./repo.sh launch` — interactively launch a built Kit application.
- `./repo.sh test` — run configured Kit extension/application tests; build first.
- `./repo.sh package` — create a distributable package. Use `--container` for a container image when supported.

Build only the application under active development when the tooling provides an application-selection option. First-time setup may require Git LFS, an RTX-capable NVIDIA GPU, and Omniverse licensing acceptance.

## Coding Style & Naming Conventions

Follow the repository’s `.editorconfig` and match surrounding code. Use four spaces in Python, descriptive `snake_case` for Python modules/functions, and lowercase namespaced `.kit` files (for example, `nycu.e3dqa_scene_viewer.kit`). Keep extension package directories aligned with their extension name. Preserve TOML/Kit formatting and comments when editing configuration. No separate formatter or linter is configured; keep diffs focused and run the relevant build/test commands.

## Testing Guidelines

Tests are Kit test suites declared in `.kit` manifests and extension `tests/` packages. Run `./repo.sh test` after a successful build; test discovery applies to built applications and extensions. Add regression coverage near the affected extension and use descriptive `test_*.py` names. There is no repository-wide coverage threshold documented.

## Commit & Pull Request Guidelines

Recent commits use short, direct descriptions (for example, `Trajectory replay for scene variants complete`). Keep commits focused and explain the behavior changed. Pull requests should include a summary, testing performed (including platform/GPU where relevant), linked issue or task, and screenshots or launch notes for visible Kit changes. Avoid committing generated build, cache, log, or local score files.

## Security & Configuration Tips

Do not commit credentials, licensing material, generated packages, or machine-specific cache paths. Review `SECURITY.md` before reporting vulnerabilities, and document any required `repo.toml` or streaming configuration changes.
