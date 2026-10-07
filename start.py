#!/usr/bin/env python3
import platform
import shutil
import subprocess
import sys


def ask_install_uv():
    print("uv package manager is not installed.")
    if platform.system().lower() == "windows":
        print("uv can be installed via PowerShell with the following command:")
        print(
            'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        )
        choice = input("Would you like to run it now? [y/N]: ").strip().lower()
        if choice == "y":
            try:
                subprocess.check_call(
                    [
                        "powershell",
                        "-ExecutionPolicy",
                        "ByPass",
                        "-c",
                        "irm https://astral.sh/uv/install.ps1 | iex",
                    ]
                )
                print("uv installed successfully.")
                print("Please restart your terminal and run the script again.")
                sys.exit(0)
            except (subprocess.SubprocessError, OSError) as e:
                print(f"Installation failed: {e}")
                sys.exit(1)
        else:
            print("uv is required to run the script with dependencies. Exiting.")
            sys.exit(1)
    else:
        print("uv can be installed via curl with the following command:")
        print("curl -LsSf https://astral.sh/uv/install.sh | sh")
        choice = input("Would you like to run it now? [y/N]: ").strip().lower()
        if choice == "y":
            if shutil.which("curl") is None:
                print("`curl` not found, cannot run command")
                print(
                    "Please install curl with `sudo apt-get install curl -y` "
                    "before running again"
                )
                sys.exit(1)
            try:
                subprocess.check_call(
                    ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
                )
                print("uv installed successfully.")
                print(
                    "Please reload your shell (`exec $SHELL`) and run the script again."
                )
                sys.exit(0)
            except (subprocess.SubprocessError, OSError) as e:
                print(f"Installation failed: {e}")
                sys.exit(1)
        else:
            print("uv is required to run the script with dependencies. Exiting.")
            sys.exit(1)


def main():
    if getattr(sys, "frozen", False):
        from nxapi_cli.__main__ import main as run

        run()
    elif shutil.which("uv") is None:
        ask_install_uv()
    else:
        from nxapi_cli.__main__ import main as run

        run()


if __name__ == "__main__":
    main()
