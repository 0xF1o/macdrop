#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys

NAME = os.environ.get("MACDROP_NAME", "macdrop")
IMAGE = os.environ.get("MACDROP_IMAGE", "docker:29-dind")
PLATFORM = os.environ.get("MACDROP_PLATFORM", "linux/amd64")
PORT = os.environ.get("MACDROP_PORT", "8000:8000")
SHELL = os.environ.get("MACDROP_SHELL", "fish")
CACHEVOLUME = os.environ.get("MACDROP_CACHEVOLUME", "macdropcache")


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
        "-p", PORT
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
        
    if len(CACHEVOLUME) > 0:
        subprocess.run([runtime, "volume", "create", CACHEVOLUME], check=False)
        cmd += ["-v", f"{CACHEVOLUME}:/var/lib/docker"]

    return cmd


def run_setup(runtime):
    print("Running macdrop setup inside container")

    setup_cmd = (
        "apk add bash sudo fish tzdata ; "
        "cp /usr/share/zoneinfo/UTC /etc/localtime ; "
        "echo UTC > /etc/timezone ; "
        "until docker info >/dev/null 2>&1; do echo 'Waiting for Docker...'; sleep 2; done; "
        "docker network create traefik-public ; "
        "docker run -v /usr/local/bin:/setup --rm registry.lakedrops.com/docker/l3d/setup:latest"
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
        subprocess.run(
            base_run_cmd(runtime) + [IMAGE],
            check=True,
            stdout=None,  # None means inherit parent stdout
            stderr=None,  # None means inherit parent stderr
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to start container '{NAME}' using {runtime}.", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)

    run_setup(runtime)


def stop(runtime):
    print(f"Stopping {NAME}")
    subprocess.run([runtime, "rm", "-f", NAME], check=False)


def shell(runtime, cmdparam):
    cmd = [
        runtime,
        "exec",
        "-it",
        NAME        
    ]    
    proc = subprocess.run(cmd + cmdparam)
    sys.exit(proc.returncode)


def l3d(runtime, args):
    """
    Run 'l3d' inside the container from the current project directory.
    """
    home_projects = os.path.expanduser("~/Projects")
    cwd = os.getcwd()

    if not cwd.startswith(home_projects):
        print("Error: You must run this command inside a project under ~/Projects.", file=sys.stderr)
        sys.exit(1)

    # Map current directory to container path
    container_dir = "/Projects" + cwd[len(home_projects):]

    # Build command string
    cmdstr = f"cd '{container_dir}' && l3d"
    if args:
        cmdstr += " " + " ".join(args)

    shell(runtime, ["/bin/sh", "-c", cmdstr])



def main():
    runtime = os.environ.get("MACDROP_RUNTIME", find_runtime())
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
        choices=["start", "stop", "shell", "l3d"],
        help="Action to perform",
    )
    parser.add_argument(
        "cmd_args",
        nargs=argparse.REMAINDER,
        help="Optional arguments for command",
    )

    args = parser.parse_args()
    
    if args.command == "start":
        start(runtime)
    elif args.command == "stop":
        stop(runtime)
    elif args.command == "shell":
        shell(runtime, [SHELL])
    elif args.command == "l3d":
        l3d(runtime, args.cmd_args)


if __name__ == "__main__":
    main()

