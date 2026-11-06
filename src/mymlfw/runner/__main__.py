"""Runner process entry for Compose (no Mongo URI / KEK in this image role)."""

from mymlfw.runner.env import validate_runner_env


def main() -> None:
    validate_runner_env()
    print("runner_ready")


if __name__ == "__main__":
    main()
