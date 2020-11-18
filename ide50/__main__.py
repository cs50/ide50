"""Manage CS50 IDE offline"""

import signal
import sys

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(1))

import argparse
import gettext
import json
import os
import shutil
import subprocess

import pkg_resources
import requests

from . import __version__

# Image to use
IMAGE = "cs50/ide:offline"
LABEL = "ide50"

# Port to use
C9_PORT = 1337

# Internationalization
TRANSLATIONS = gettext.translation("ide50", pkg_resources.resource_filename("ide50", "locale"),
                                   fallback=True)
TRANSLATIONS.install()


def main():
    """Entrypoint of script"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-V", "--version", action="version",
                        version="%(prog)s {}".format(__version__ or "Locally installed."))

    subparsers = parser.add_subparsers()

    start_parser = subparsers.add_parser("start", help=_("start container"))
    start_parser.add_argument("-d", "--dotfile", action="append", default=[],
                              help=_("dotfile in your $HOME to mount read-only in container's"
                                     " $HOME"), metavar="DOTFILE")

    start_parser.add_argument("-i", "--image", default=IMAGE,
                              help=_("use IMAGE, else {}").format(IMAGE),
                              metavar="IMAGE")

    start_parser.add_argument("directory", default=os.getcwd(), metavar="DIRECTORY", nargs="?",
                              help=_("directory to mount, else $PWD"))

    start_parser.add_argument("-f", "--fast", action="store_true", help=_("skip autoupdate"))
    start_parser.set_defaults(func=start)

    status_parser = subparsers.add_parser("status", help=_("show container status"))
    status_parser.set_defaults(func=status)

    stop_parser = subparsers.add_parser("stop", help=_("stop container"))
    stop_parser.set_defaults(func=stop)

    update_parser = subparsers.add_parser("update", help=_("update only"))
    update_parser.add_argument("-i", "--image", default=IMAGE,
                              help=_("update IMAGE, else {}").format(IMAGE),
                              metavar="IMAGE")

    update_parser.set_defaults(func=update)

    args = parser.parse_args()
    check_docker()
    args.func(args)


def check_docker():
    """Check if Docker is installed and responding"""
    # Check if Docker installed
    if not shutil.which("docker"):
        sys.exit(_("Docker not installed"))

    # Check if Docker running
    try:
        subprocess.check_call(["docker", "info"], stderr=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, timeout=10)

    except subprocess.CalledProcessError:
        sys.exit(_("Docker not running"))
    except subprocess.TimeoutExpired:
        sys.exit(_("Docker not responding"))


def container_info(container):
    """Print container port mappings and URL"""
    # List port mappings
    print(ports(container))
    print(_("Running on {}. Run `ide50 stop` to stop.").format(
        f"http://{ports(container.split()[0], C9_PORT)}/"))


def get_container():
    """Return ID(s) of running container(s), if any"""
    try:
        return subprocess.check_output([
            "docker", "ps",
            "--all",
            "--filter", f"label={LABEL}",
            "--format", "{{.ID}}"
        ]).decode().rstrip()
    except subprocess.CalledProcessError:
        sys.exit(_("Failed to list containers"))


def ports(container, port=None):
    """Return port mappings for container"""
    cmd = ["docker", "port", container]
    if port:
        cmd.append(str(port))

    return subprocess.check_output(cmd).decode().rstrip()


def pull(image):
    """Pull image as needed"""
    try:

        # Get digest of local image, if any
        digest = subprocess.check_output(["docker", "inspect", "--format",
                                          "{{index .RepoDigests 0}}", image],
                                         stderr=subprocess.DEVNULL).decode().rstrip()

        # Get digest of latest image
        # https://stackoverflow.com/a/50945459/5156190
        repository, tag = image.split(":") if ":" in image else (image, "latest")
        if "/" not in repository:
            repository = "library/" + repository

        response = requests.get(f"https://hub.docker.com/v2/repositories/{repository}/tags/{tag}").json()["images"][0]

        # Pull latest if digests don't match
        assert digest == f"{repository}@{response['digest']}"

    except (AssertionError, requests.exceptions.ConnectionError, subprocess.CalledProcessError):

        # Pull image
        subprocess.call(["docker", "pull", image], stderr=subprocess.DEVNULL)


def start(args):
    """Start container, if stopped"""
    # Check for newer version
    if not args.fast and __version__:
        try:
            latest = max(requests.get("https://pypi.org/pypi/ide50/json").json()["releases"],
                         key=pkg_resources.parse_version)

            assert latest <= __version__
        except (json.decoder.JSONDecodeError, requests.RequestException):
            pass
        except AssertionError:
            print(_("A newer version is available. Run `pip3 install --upgrade ide50` to upgrade."))

    # Get running container
    container = get_container()
    if not container:
        # Ensure directory exists
        directory = os.path.realpath(args.directory)
        if not os.path.isdir(directory):
            sys.exit(_("{}: no such directory").format(args.directory))

        # Check for newer image
        if not args.fast:
            pull(args.image)

        # Options
        options = ["--detach",
                   "--env", "C9_HOSTNAME=0.0.0.0",
                   "--env", "CS50_IDE_TYPE=offline",
                   "--label", LABEL,
                   "--rm",
                   # https://stackoverflow.com/q/35860527#comment62818827_35860527
                   # https://github.com/apple/swift-docker/issues/9#issuecomment-328218803
                   "--security-opt", "seccomp=unconfined",
                   "--volume", directory + ":/home/ubuntu/workspace"]

        # Mount each dotfile in user's $HOME read-only in container's $HOME
        for dotfile in args.dotfile:
            home = os.path.join(os.path.expanduser("~"), "")
            if dotfile.startswith("/") and not dotfile.startswith(home):
                sys.exit(_("{}: not in your $HOME").format(dotfile))
            elif dotfile.startswith(os.path.join("~", "")):
                dotfile = os.path.expanduser(dotfile)
            else:
                dotfile = os.path.join(home, dotfile)
            if not os.path.exists(dotfile):
                sys.exit(_("{}: No such file or directory").format(dotfile))
            if not dotfile[len(home):].startswith("."):
                sys.exit(_("{}: Not a dotfile").format(dotfile))
            options += ["--volume", "{}:/home/ubuntu/{}:ro".format(dotfile, dotfile[len(home):])]

        # Spawn container
        try:

            # Publish container's ports to the host
            # https://stackoverflow.com/a/952952/5156190
            cmd = ["docker", "run", *options]
            ports_ = [f"--publish={port}:{port}" for port in (C9_PORT, 8080, 8081, 8082)]
            container = subprocess.check_output([*cmd, *ports_, args.image],
                                                stderr=subprocess.STDOUT).decode().rstrip()
        except subprocess.CalledProcessError:

            # Publish all exposed ports to random ports
            try:
                container = subprocess.check_output([*cmd, "--publish-all",
                                                     args.image]).decode().rstrip()

            except subprocess.CalledProcessError:
                sys.exit(_("Failed to start container"))

    # Print port mappings and URL
    container_info(container)


def status(args):
    """Show container status"""
    container = get_container()
    if container:
        container_info(container)
    else:
        print(_("No containers are running"))

    sys.exit(0)


def stop(args):
    """Stop container, if running"""
    container = get_container()
    try:
        for id_ in container.splitlines():
            subprocess.check_call(["docker", "stop", id_], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)

        print(_("Stopped"))
    except subprocess.CalledProcessError:
        sys.exit(_("Failed to stop container"))


def update(args):
    """Pull image"""
    pull(args.image)
    print(_("Updated {}").format(args.image))
    sys.exit(0)


if __name__ == "__main__":
    main()
