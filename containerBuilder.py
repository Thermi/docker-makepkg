#! /bin/python3 -B

import atexit
import ipaddress
import os
import subprocess
import sys

import netifaces

def eprint(*args, **kwargs):
    """
    Shorthand for using print(file=sys.stderr)
    """
    print(*args, file=sys.stderr, **kwargs)

class DmakepkgBuilder:
    """
    Dockerfile generator
    """
    head = ("FROM archlinux/base:latest\nLABEL org.thermicorp.tool=docker-makepkg\nRUN echo -e "
            "\"[multilib]\\nInclude = /etc/pacman.d/mirrorlist\" >> /etc/pacman.conf\n"
            "RUN pacman --noconfirm -Sy archlinux-keyring && pacman-key --init && "
            "pacman-key --populate archlinux\n"
            "RUN systemd-machine-id-setup")

    tail = ("ADD sudoers /etc/sudoers\n"
            """VOLUME "/src\"\n"""
            "ADD run.py /run.py\n"
            """ENTRYPOINT ["/run.py"]\n""")

    def __init__(self):
        self.pacman_cache_dir = "/var/cache/pacman/pkg"
        self.pacman_cache_ip = None
        self.pacman_cache_port = "8990"
        self.cache = True
        self.darkhttpd_process = None
        self.docker_build_process = None

    @classmethod
    def get_docker0_address(cls):
        """
        Get the first valid non-link-local IP address on docker0
        """
        try:
            addresses = netifaces.ifaddresses('docker0')
        except:
            eprint("No docker0 interface exists. Looks like you don't run docker?")
            # we could actually theoretically use an IP from any interface, but I want
            # to make sure to not make any holes into existing rule sets that protect
            # other interfaces.
            sys.exit(1)
        else:
            # check for IPv4 and IPv6 addresses. We can't use link-local ones though,
            # because the address specified for those needs to contain the name
            # of the interface that needs to be used to reach the destination address
            # and I don't know of a way to predict it in docker.
            for (family, address_list) in addresses.items():
                if family == netifaces.AF_INET:
                    for address_dict in address_list:
                        return ipaddress.ip_address(address_dict["addr"])
                elif family == netifaces.AF_INET6:
                    for address_dict in address_list:
                        ipv6_address = ipaddress.ip_address(address_dict["addr"])
                        if not ipv6_address.is_link_local():
                            return ipaddress.ip_address(address_dict["addr"])
            eprint("No suitable address found for the local cache. " +
                   "Therefore the local cache is disabled.")
            return None

    @classmethod
    def start_docker_build(cls):
        """
        Start docker build
        """
        args = ["/bin/docker", "build", "--pull", "--no-cache", "--tag=makepkg", os.path.dirname(
            os.path.realpath(__file__))]
        docker_id=None
        process=None
        try:
            process=subprocess.run(args, capture_output=True)
        except:
            pass
        if process:
            if process.returncode:
                docker_id=process.stdout.decode("utf-8")
                try:
                    subprocess.run(["/bin/docker", "container", "rm", docker_id])
                except:
                    pass

    def pacman_cache_exists(self):
        """
        Check if the pacman cache directory exists
        """
        return os.path.exists(self.pacman_cache_dir)

    def create_dockerfile(self):
        """
        Generate the Dockerfile
        """
        if self.cache:
            complete = self.head + (
                "\nRUN /bin/bash -c 'cat <(echo Server = "
                "http://{}:{}) /etc/pacman.d/mirrorlist > foobar && mv foobar "
                "/etc/pacman.d/mirrorlist && pacman -Syuq --noconfirm --needed "
                "procps-ng gcc base-devel ccache distcc python git mercurial bzr "
                "subversion openssh && rm -rf /var/cache/pacman/pkg/* && "
                "cp /etc/pacman.d/mirrorlist foo && tail -n +2 foo > "
                "/etc/pacman.d/mirrorlist'\n").format(
                    self.pacman_cache_ip.compressed,
                    self.pacman_cache_port) + self.tail
        else:
            complete = self.head + (
                """\nRUN pacman -Syuq --noconfirm "
                "--needed procps-ng  gcc base-devel distcc ccache python git mercurial "
                "bzr subversion openssh && rm -rf /var/cache/pacman/pkg/*\n"
                "COPY pump /usr/bin/pump\n""") + self.tail
        # write file
        script_location = os.path.realpath(__file__)

        with open(os.path.join(os.path.dirname(script_location), "Dockerfile"), "w") as docker_file:
            docker_file.write(complete)

    def start_local_cache(self):
        """
        Start the pacman http cache
        """
        # runs darkhttpd
        args = ["/usr/bin/darkhttpd", self.pacman_cache_dir, "--port", self.pacman_cache_port]
        self.darkhttpd_process = subprocess.Popen(args)

    def stop_local_cache(self):
        """
        Stop the darkhttpd process
        """
        self.darkhttpd_process.terminate()

    def insert_iptables_rules(self):
        """
        Install the iptables rule for the pacman http cache
        """
        comm = {
            4 : "/bin/iptables",
            6 : "/bin/ip6tables"
        }[self.pacman_cache_ip.version]
        args = "{} -w 5 -W 2000 -I INPUT -p tcp --dport 8990 -i docker0 -d {} -j ACCEPT".format(
            comm, self.pacman_cache_ip.compressed).split()
        subprocess.run(args)

    def delete_iptables_rules(self):
        """
        Remove the iptables rule for the pacman http cache
        """
        comm = {
            4 : "/bin/iptables",
            6 : "/bin/ip6tables"
        }[self.pacman_cache_ip.version]
        args = "{} -w 5 -W 2000 -D INPUT -p tcp --dport 8990 -i docker0 -d {} -j ACCEPT".format(
            comm, self.pacman_cache_ip.compressed).split()
        subprocess.run(args)

    def main(self):
        """
        Main function for dmakepkg_builder. Runs the build process
        """
        # check the docker0 address
        ip_address = self.get_docker0_address()

        if not ip_address or not self.pacman_cache_exists():
            self.cache = False
        self.pacman_cache_ip = ip_address

        # create and write Dockerfile
        self.create_dockerfile()

        # start darkhttpd
        self.start_local_cache()
        # make sure it gets stopped if the script exits
        atexit.register(self.stop_local_cache)

        # insert iptables rule
        self.insert_iptables_rules()

        # make sure it gets cleaned up if the script exits
        atexit.register(self.delete_iptables_rules)

        sys.exit(self.start_docker_build())

if __name__ == "__main__":
    BUILDER = DmakepkgBuilder()
    BUILDER.main()
