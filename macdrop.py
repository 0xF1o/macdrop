#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys

# Defaults (override via MACDROP_*)
NAME = os.environ.get("MACDROP_NAME", "macdrop")
IMAGE = os.environ.get("MACDROP_IMAGE", "docker:dind")
PLATFORM = os.environ.get("MACDROP_PLATFORM", "linux/amd64")
PORT = os.environ.get("MACDROP_PORT", "8000:8000")
SHELL = os.environ.get("MACDROP_SHELL", "fish")


def find_runtime():
    for cmd in ("container", "docker", "podman"):
        if shutil.which(cmd):
            return cmd
    return None


def base_run_cmd(runtime):
    cmd = [
        runtime,
        "run",
        "-d",
        "--name", NAME,
        "--platform", PLATFORM,
        "-p", PORT,
    ]

    # docker / podman require privileged for dind
    if runtime in ("docker", "podman"):
        cmd.append("--privileged")

    # SSH agent passthrough if available
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if ssh_auth_sock and os.path.exists(ssh_auth_sock):
        cmd += [
            "-e", "SSH_AUTH_SOCK=/ssh-agent",
            "-v", f"{ssh_auth_sock}:/ssh-agent",
        ]

    # Map ~/Projects -> /Projects if it exists
    home_projects = os.path.expanduser("~/Projects")
    if os.path.isdir(home_projects):
        cmd += [
            "-v", f"{home_projects}:/Projects",
            "-w", "/Projects"
        ]

    return cmd


def run_setup(runtime):
    print("Running macdrop setup inside container")

    setup_cmd = (
        "apk add bash sudo fish && "
        "docker network create traefik-public && "
        "docker run -v /usr/local/bin:/setup --rm registry.lakedrops.com/docker/l3d/setup:latest && "
        "l3d reset"
    )

    subprocess.check_call([
        runtime,
        "exec",
        "-it",
        NAME,
        "/bin/sh",
        "-c",
        setup_cmd,
    ])


def start(runtime):
    print(f"Starting {NAME} using {runtime}")

    try:
        subprocess.check_call(base_run_cmd(runtime) + [IMAGE])
    except subprocess.CalledProcessError as e:
        print(f"Failed to start container '{NAME}' using {runtime}.", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        print("Make sure the runtime is installed, the image exists, and no container with this name is running.", file=sys.stderr)
        sys.exit(e.returncode)

    run_setup(runtime)


def stop(runtime):
    print(f"Stopping {NAME}")
    subprocess.run([runtime, "rm", "-f", NAME], check=False)


def shell(runtime):
    proc = subprocess.run([
        runtime,
        "exec",
        "-it",
        NAME,
        SHELL,
    ])
    # Propagate exact exit code
    sys.exit(proc.returncode)


def main():
    runtime = find_runtime()
    if not runtime:
        print(
            "Error: No container runtime found",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Manage the macdrop dind container"
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "shell"],
        help="Action to perform",
    )

    args = parser.parse_args()

    if args.command == "start":
        start(runtime)
    elif args.command == "stop":
        stop(runtime)
    elif args.command == "shell":
        shell(runtime)


if __name__ == "__main__":
    main()

