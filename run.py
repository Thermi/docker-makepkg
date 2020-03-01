#! /bin/python3 -B

import argparse
import glob
import os
import os.path
import pwd
import subprocess
import shutil
import shlex
import sys

def eprint(*args, **kwargs):
    """
    Helper function for printing to sys.stderr
    """
    print(*args, file=sys.stderr, **kwargs)

class DmakepkgContainer:
    """
    Class implementing a package builder for Arch Linux using Docker.
    This is the file running inside the container.
    """
    __restDefaults = "--nosign --force --syncdeps --noconfirm"

    def __init__(self):
        self.parser = None
        self.rest = None
        self.command = None
        self.group = None
        self.run_pacman_syu = None
        self.user = None
        self.use_pump_mode = None
        self.download_keys = None

    @classmethod
    def copy_tree(cls, src, dst, symlinks=False, ignore=None):
        """
        Copy the directory tree from src to dst
        From https://stackoverflow.com/questions/1868714
        Written by user atzz
        """
        for item in os.listdir(src):
            source_directory = os.path.join(src, item)
            destination_directory = os.path.join(dst, item)
            if os.path.isdir(source_directory):
                shutil.copytree(source_directory, destination_directory, symlinks, ignore)
            else:
                shutil.copy2(source_directory, destination_directory)

    @classmethod
    def change_user_or_gid(cls, uid, gid, path):
        """
        Change all owner UIDs and GIDs of the files in the path to the given ones
        to not change either gid or uid, set that value to -1.
        From https://stackoverflow.com/questions/2853723
        Written by user "too much php"
        """
        for root, dirs, files in os.walk(path):
            for momo in dirs:
                try:
                    os.chown(os.path.join(root, momo), uid, gid)
                except Exception as e:
                    eprint(e)
            for momo in files:
                try:
                    os.chown(os.path.join(root, momo), uid, gid)
                except Exception as e:
                    eprint(e)

    # From https://www.tutorialspoint.com/How-to-change-the-permission-of-a-directory-using-Python
    # Written by Rajendra Dharmkar
    @classmethod
    def change_permissions_recursively(cls, path, mode):
        """
        Change the permissions of all files and directories in the given path to the given mode
        """
        for root, dirs, files in os.walk(path, topdown=False):
            for directory in [os.path.join(root, d) for d in dirs]:
                os.chmod(directory, mode)
            for file in [os.path.join(root, f) for f in files]:
                os.chmod(file, mode)

    @classmethod
    def append_to_file(cls, path, content):
        """
        Append the given content to the file found in the given path
        """
        with open(path, "a+") as file:
            file.seek(0, 2)
            file.write(content)

    # From https://stackoverflow.com/questions/17435056/read-bash-variables-into-a-python-script
    # Written by user Taejoon Byun
    @classmethod
    def get_var(cls, script, var_name):
        """
        Source the given script in bash and print out the value of the
        variable varName (bash/sh script)
        """
        cmd = 'echo $(source "{}"; echo ${{{}[@]}})'.format(script, var_name)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')
        return process.stdout.readlines()[0].decode("utf-8").strip()

    # From https://stackoverflow.com/questions/17435056/read-bash-variables-into-a-python-script
    # Written by user Taejoon Byun
    @classmethod
    def call_func(cls, script, func_name):
        """
        Source the given script in bash and print out the value the function funcName returns
        """
        cmd = 'echo $(source "{}"; echo $({}))'.format(script, func_name)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')
        return process.stdout.readlines()[0].decode("utf-8").strip()

    def check_for_pump_mode(self):
        """
        Check if pump mode is enabled for any of the DISTCC_HOSTS in /etc/makepkg.conf
        """
        if ",cpp" in self.get_var("/etc/makepkg.conf", "DISTCC_HOSTS") and self.use_pump_mode:
            return True
        return False

    def main(self):
        """
        Main function for running this python script. Implements the argument parser, logic
        to build a complete package and copying of the build packages to the shared directory.
        """
        self.parser = argparse.ArgumentParser(prog="dmakepkgContainer")
        self.parser.add_argument(
            '-e',
            nargs='?',
            help="CMD to run the command after the source directory was copied")
        self.parser.add_argument(
            '-g',
            nargs='?',
            help="The GID to own any created package (Ignored unless UID is also provided")
        self.parser.add_argument(
            '-p',
            action='store_true',
            help="Run a pacman -Syu before building")
        self.parser.add_argument(
            '-u',
            nargs='?',
            help="UID to own any created package")
        self.parser.add_argument(
            '-y',
            action='store_false',
            help="Do not use pump mode.")
        self.parser.add_argument(
            '-Z',
            action='store_true',
            help="Do not copy the source files. Build in the directory directly."
            )
        self.parser.add_argument(
            '-z',
            action='store_false',
            help="Do not automatically download missing PGP keys")

        namespace, self.rest = self.parser.parse_known_args()

        if not os.path.isfile("/src/PKGBUILD") or os.path.islink("/src/PKGBUILD"):
            eprint("No PKGBUILD file found! Aborting.")
            sys.exit(1)

        self.command = namespace.e
        self.group = int(namespace.g)
        self.run_pacman_syu = namespace.p
        self.user = int(namespace.u)
        self.use_pump_mode = namespace.y
        self.download_keys = namespace.z
        build_user_uid = None
        # -Z arg has several consequences: 1) UID and GID of the PKGBUILD are used as the ones for the user
        if namespace.Z:
            stat_result = os.stat("/src/PKGBUILD")
            subprocess.run(["groupadd", "-g", str(stat_result.st_gid), "build-user"])
            subprocess.run(["useradd", "-m", "-d", "/build", "-s", "/bin/bash", "-u", str(stat_result.st_uid), "-g", str(stat_result.st_gid), "build-user"])
            build_user_uid = stat_result.st_gid
            os.chdir("/src")
        else:
            subprocess.run(["useradd", "-m", "-d", "/build", "-s", "/bin/bash", "build-user"])
            build_user_uid = pwd.getpwnam("build-user").pw_uid
            build_user_gid = pwd.getpwnam("build-user").pw_gid
            self.copy_tree("/src/", "/build")
            self.change_user_or_gid(build_user_uid, build_user_gid, "/build")

        if self.run_pacman_syu:
            arguments = "pacman --noconfirm -Syu".split()
            pacman_process = subprocess.Popen(arguments)
            pacman_process.wait()
        else:
            arguments = "pacman --noconfirm -Sy".split()
            pacman_process = subprocess.Popen(arguments)
            pacman_process.wait()
        flags = None
        built_packages = []

        if not self.rest:
            flags = self.__restDefaults.split()
        else:
            # translate list object to space seperated arguments
            flags = self.rest

        if self.download_keys:
            gnupg = os.path.expanduser("~build-user/.gnupg")
            os.makedirs(gnupg, mode=0o700, exist_ok=True)
            self.change_user_or_gid(build_user_uid, pwd.getpwnam("build-user").pw_gid, "/build")
            self.change_permissions_recursively(gnupg, 0o700)
            self.append_to_file(gnupg + "/gpg.conf", "\nauto-key-retrieve\n")
            self.change_permissions_recursively(gnupg + "/gpg.conf", 0o600)

        # if a command is specified in -e, then run it
        if self.command:
            args = shlex.split(self.command)
            subprocess.run(args)

        # su resets PATH, so distcc doesn't find the distcc directory
        if self.check_for_pump_mode():
            "pump makepkg {}\n".format(" ".join(flags))
            arguments = ['su', '-c', 'DISTCC_HOSTS="{}" DISTCC_LOCATION={} pump makepkg {}'.format(
                self.get_var("/etc/makepkg.conf", "DISTCC_HOSTS"),
                "/usr/bin", " ".join(flags)), '-s', '/bin/bash', 'build-user']
            makepkg_process = subprocess.run(arguments)

            # while makepkgProcess.poll() == None:
            #   outs, errs = makepkgProcess.communicate(input="")
            #   if outs:
            #       print(outs)
            #   if errs:
            #       eprint(errs)
        else:
            arguments = ['su', '-c',
                         'makepkg {}'.format(" ".join(flags)),
                         '-s',
                         '/bin/bash',
                         '-l', 'build-user']
            makepkg_process = subprocess.Popen(arguments)
            while makepkg_process.poll() is None:
                outs, errs = makepkg_process.communicate(input="")
                if outs:
                    print(outs)
                if errs:
                    eprint(errs)

        if self.user and not self.group:
            self.change_user_or_gid(self.user, self.group, "/build")
        elif self.user:
            self.change_user_or_gid(self.user, -1, "/build")

        # copy any packages
        # use globbing to get all packages
        for item in glob.iglob("/build/*pkg.tar*"):
            try:
                shutil.copy(item, "/src")
                built_packages.append(item)
            except Exception as e:
                eprint(e)

        if not built_packages:
            eprint("No packages were built!")
            sys.exit(2)
        sys.exit(0)

if __name__ == "__main__":
    CONTAINERENTRYPOINT = DmakepkgContainer()
    CONTAINERENTRYPOINT.main()
