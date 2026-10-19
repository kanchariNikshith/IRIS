"""Masked configuration check, voice console and text-only fallback."""
import argparse
import json
from threading import Event

from typing import TYPE_CHECKING, Callable

from iris.config import Config, ConfigurationError, load_config

if TYPE_CHECKING:
    from iris.brain.brain import Brain


def prepare_console_input(stop: Event) -> bool:
    """Give the user a cancellable handoff before dispatching window input."""
    if stop.is_set():
        return False
    print("IRIS: Click the target window and keep the mouse over its content. "
          "Input starts in 3 seconds; Ctrl+Alt+Esc cancels.", flush=True)
    return not stop.wait(3.0)


def create_brain(config: Config, *, before_input: Callable[[Event], bool] | None = None) -> "Brain":
    if config.ai_provider not in {"openai", "gemini"}:
        raise ConfigurationError("AI_PROVIDER must be openai or gemini.")
    from iris.brain.brain import Brain
    from iris.brain.providers import GeminiProvider, OpenAIProvider, UnconfiguredProvider
    from iris.logs.action_log import ActionLog
    from iris.security.permissions import PermissionGate
    from iris.tools.builtins import register_tools
    from iris.tools.registry import ToolRegistry
    gate = PermissionGate()
    registry = ToolRegistry(gate, ActionLog(secrets=config.secrets))
    prepare = before_input or prepare_console_input
    register_tools(registry, before_input=lambda: prepare(gate.kill_switch))
    selected_key = config.gemini_api_key if config.ai_provider == "gemini" else config.openai_api_key
    if not selected_key or not config.model:
        return Brain(None, config.model or "local-only", registry, secrets=config.secrets,
                     provider=UnconfiguredProvider(), local_commands=True)
    if config.ai_provider == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=config.gemini_api_key, vertexai=False,
            http_options=types.HttpOptions(timeout=20_000,
                retry_options=types.HttpRetryOptions(attempts=1)))
        provider = GeminiProvider(client, config.gemini_model)
    else:
        from openai import OpenAI
        client = OpenAI(api_key=config.openai_api_key, max_retries=0, timeout=20.0)
        provider = OpenAIProvider(client, config.openai_model)
    return Brain(client, config.model, registry, secrets=config.secrets, provider=provider, local_commands=True)


def text_console(brain: "Brain", hotkey: str) -> None:
    from iris.security.permissions import start_kill_switch
    listener = start_kill_switch(brain.registry.gate, hotkey)
    try:
        print("IRIS text mode. Type a command; use stop or quit to exit.")
        while not brain.registry.gate.kill_switch.is_set():
            try:
                command = input("You: ")
            except EOFError:
                break
            if command.strip().casefold() in {"quit", "exit"}:
                break
            print("IRIS: " + brain.run(command))
    finally:
        brain.registry.gate.stop()
        listener.stop()
        listener.join(timeout=1)
        brain.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IRIS desktop assistant")
    parser.add_argument("--check", action="store_true", help="Print masked configuration")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--text-only", action="store_true", help="Use the Phase 2 console without audio")
    modes.add_argument("--gui", action="store_true", help="Launch the floating orb and desktop window")
    args = parser.parse_args(argv)
    if args.gui and not args.check:
        try:
            from iris.ui.app import run_gui
            return run_gui(config_factory=lambda: load_config(require_cloud=False), brain_factory=create_brain)
        except Exception:
            print("IRIS couldn't launch the desktop interface. Check the PySide6 installation.")
            return 1
    try:
        config = load_config() if args.check else load_config(require_cloud=False)
    except ConfigurationError as error:
        print(str(error))
        return 1
    if args.check:
        print(json.dumps(config.masked(), indent=2))
    else:
        print("IRIS console mode: for the floating orb and desktop window, launch python -m iris.main --gui.")
        try:
            brain = create_brain(config)
            if args.text_only:
                text_console(brain, config.kill_switch_hotkey)
            else:
                from iris.audio.voice import voice_console
                voice_console(brain, config)
        except KeyboardInterrupt:
            print("Stopped.")
        except Exception:
            # Runtime/hardware boundary: exceptions may contain the API key.
            print("IRIS couldn't start text mode. Check installed dependencies and the hotkey configuration.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
