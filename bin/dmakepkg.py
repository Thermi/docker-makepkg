#! /bin/python3 -B

import argparse
import os
import subprocess
import uuid

class dmakepkg:
    __eDefaults = "--nosign --force --syncdeps --noconfirm"
    def __init__(self):
        self.pacman_conf = "/etc/pacman.conf"
        self.makepkg_conf = "/etc/makepkg.conf"
        self.pacman_pkg_cache = "/var/cache/pacman/pkg"
        self.use_pump_mode = None
        self.download_keys = None
        self.command = None
        self.use_host_pacman = None
        self.parser = None

    # From https://stackoverflow.com/questions/17435056/read-bash-variables-into-a-python-script
    # Written by user Taejoon Byun
    def getVar(self, script, varName):
        cmd = 'echo $(source "{}"; echo ${{{}[@]}})'.format(script, varName)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')
        return process.stdout.readlines()[0].decode("utf-8").strip()

    # From https://stackoverflow.com/questions/17435056/read-bash-variables-into-a-python-script
    # Written by user Taejoon Byun
    def callFunc(self, script, funcName):
        cmd = 'echo $(source {}; echo $({}))'.format(script, funcName)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')
        return process.stdout.readlines()[0].decode("utf-8").strip()

    def signPackages(self):
        args = ["/bin/gpg", "--batch", "--yes", "--detach-sign"]
        key = self.getVar(self.pacman_conf, "GPGKEY")
        if key:
            args.extend(["-u", key])
        files = []
        for (_, _, filenames) in os.walk(os.getcwd()):
            files.extend(filenames)
            break

        for item in files:
            if ".pkg." in item and not item.endswith("sig"):
                pkg_and_not_sigs = []
                pkg_and_not_sigs.extend(args)
                pkg_and_not_sigs.append(item)
                subprocess.run(pkg_and_not_sigs)



    def main(self):
        self.parser = argparse.ArgumentParser(prog="dmakepkg")
        self.parser.add_argument(
            '-x',
            action='store_false',
            help="Do not use host system's /etc/pacman.conf"
            )
        self.parser.add_argument(
            '-X',
            action='store_false',
            help="Do not use host system's /etc/pacman.d/mirrorlist"
            )
        self.parser.add_argument(
            '-y',
            action='store_false',
            help="Never use pump mode, even if pump mode capable servers are configured")
        self.parser.add_argument(
            '-Y',
            action='store_true',
            help="Use the host system's package cache (/var/cache/pacman/pkg)"
            )
        self.parser.add_argument(
            '-z',
            action='store_false',
            help="Do not automatically download missing PGP keys",
            )
        self.parser.add_argument(
            '-e',
            nargs='?',
            help="Executes the argument as a command in the container after copying the package source")

        self.parser.add_argument(
            'rest',
            nargs=argparse.REMAINDER,
            help="The arguments that are passed to the call to pacman in its executions in the container. They default to \"--nosign --force --syncdeps --noconfirm\".")

        namespace = self.parser.parse_args()

        parameters = ["--name", "dmakepkg_{}".format(uuid.uuid4())]

        # pacman.conf is not a bash file, so this doesn't work.
        # local_cache_dir = self.getVar(self.pacmanConf, "CacheDir")
        # if not local_cache_dir:
        #   local_cache_dir = "/var/cache/pacman/pkg"
        local_cache_dir = "/var/cache/pacman/pkg"

        if namespace.x:
            parameters.extend(
                ["-v",
                 "/etc/pacman.conf:/etc/pacman.conf",
                 "-v",
                 "{local_cache_dir}:{local_cache_dir}:ro".format(
                     local_cache_dir=local_cache_dir)])
        else:
            parameters.extend("-v {}:{}".format(local_cache_dir, self.pacman_pkg_cache).split())

        if namespace.X:
            parameters.extend("-v /etc/pacman.d/mirrorlist:/etc/pacman.d/mirrorlist:ro".split(" "))

        if namespace.Y:
            parameters.extend("-v /var/cache/pacman/pkg/:/var/cache/pacman/pkg/:ro".split(" "))

        self.use_pump_mode = namespace.y
        self.download_keys = namespace.z
        self.command = namespace.e
        self.use_host_pacman = namespace.x

        if os.path.isfile(self.pacman_conf):
            parameters += self.find_parameters()

        # set object attributes
        # self.hostPacmanConf = namespace.
        # create first part
        complete_cmd_line = ["/bin/docker",
                             "run",
                             "--init",
                             "--rm",
                             "-ti",
                             "--cpu-shares=128",
                             "--pids-limit=-1",
                             "-v",
                             "{}:/src".format(os.getcwd())]

        complete_cmd_line.extend(parameters)
        complete_cmd_line.append("makepkg")

        if not self.download_keys:
            complete_cmd_line.append("-x")
        if not self.use_pump_mode:
            complete_cmd_line.append("-y")
        complete_cmd_line.extend(["-u", str(os.geteuid()), "-g", str(os.getegid())])
        if self.command:
            complete_cmd_line.extend(["-e", self.command])
        complete_cmd_line += namespace.rest

        docker_process = subprocess.Popen(complete_cmd_line)
        docker_process.wait()

        for i in self.getVar(self.pacman_conf, "BUILDENV").split():
            if "sign" in i:
                if not i.startswith("!"):
                    self.signPackages()

    # this function finds all possible arguments to the docker command line we could need
    # and builds them.
    def find_parameters(self):
        parameters = ["-v", "/etc/makepkg.conf:/etc/makepkg.conf:ro"]

        for i in ["SRCDEST", "PKGDEST", "SRCPKGDEST", "LOGDEST"]:
            value = self.getVar(self.pacman_conf, i)
            if value != "":
                parameters.extend(["-v", "{}:{}".format(i, value)])
        return parameters

if __name__ == '__main__':
    DM = dmakepkg()
    DM.main()
