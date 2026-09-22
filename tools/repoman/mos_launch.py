"""Keep the upstream launch tool intact while enabling the MOS NVRTC cache."""
import argparse
import platform
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from omni.repo.kit_tools import launch as upstream


MOS_APP = "nycu.mos_app.kit"


def choose_app(app_name: Optional[str], target_directory: Path, config: dict) -> str:
    """Use upstream selection, which lists kit files without strict TOML parsing."""
    return app_name if app_name is not None else upstream.select_kit(target_directory, config)


def launch_kit(
    app_name: Optional[str],
    target_directory: Path,
    config: dict = {},
    extra_args: List[str] = [],
    no_nvrtc_cache: bool = False,
) -> None:
    app_name = choose_app(app_name, target_directory / "apps", config)
    print(f"launching {app_name}!")

    app_build_path = Path(upstream.resolve_tokens(str(target_directory / app_name) + "${shell_ext}"))
    if not app_build_path.is_file():
        upstream._quiet_error(
            f"\nDesired built Kit App: {app_name} is missing the built entrypoint script: "
            f"{app_build_path}. Have you built your app via `{Path(upstream._get_repo_cmd()).name} build`?"
        )

    command = [str(app_build_path), *extra_args]
    if app_name == MOS_APP and not no_nvrtc_cache:
        command.append(
            "--/exts/nycu.mos_app_extension/sceneListPath="
            + upstream.resolve_tokens("${root}/source/data/mos_scenes.json")
        )
        wrapper = Path(upstream.resolve_tokens("${root}/tools/mos_nvrtc_cache_v2/default_launch.py"))
        command = [sys.executable, str(wrapper), "--app-command", command[0], "--", *command[1:]]

    upstream._run_process(command, exit_on_error=False)


def add_cache_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-nvrtc-cache",
        action="store_true",
        help="Launch local MOS without the default NVRTC cache wrapper.",
    )


def setup_repo_tool(parser: argparse.ArgumentParser, config: Dict) -> Optional[Callable]:
    """Register upstream launch UX plus a local-MOS-only cache adapter."""
    parser.description = "Application-specific tooling for launching local applications and containerized applications."
    upstream.add_container_arg(parser)
    add_cache_arg(parser)
    upstream.add_package_arg(parser)
    upstream.add_name_arg(parser)

    if not config.get("repo_launch_app", {}).get("enabled", False):
        return None

    apps = upstream.discover_kit_files(upstream.KIT_APP_PATH)
    subparsers = parser.add_subparsers()
    for app in apps:
        subparser = subparsers.add_parser(app)
        subparser.set_defaults(app_name=app)
        upstream.add_container_arg(subparser)
        add_cache_arg(subparser)

    def run_repo_tool(options: argparse.Namespace, config_dict: Dict) -> None:
        app_name = options.app_name
        upstream.console.print("[ctrl+c to Exit]", style=upstream.INFO_COLOR)
        try:
            if options.from_package:
                upstream.launch_kit(app_name, upstream.expand_package(options.from_package), config_dict, options.extra_args)
                return

            build_path = Path(config_dict["repo"]["folders"].get("build", "_build"))
            build_path /= f"{upstream.get_host_platform()}/release"
            if options.container:
                if platform.system() != "Linux":
                    upstream._quiet_error("Currently container launch workflows are only supported on Linux hosts.")
                upstream.nvidia_driver_check()
                upstream.launch_container(app_name, options.extra_args, options.verbose)
                return

            launch_kit(app_name, build_path, config_dict, options.extra_args, options.no_nvrtc_cache)
        except (KeyboardInterrupt, SystemExit):
            upstream.console.print("Exiting", style=upstream.INFO_COLOR)
            sys.exit(0)

    return run_repo_tool
