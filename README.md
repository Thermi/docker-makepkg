# Docker-Makepkg

This is a tool and docker image for building packages in a docker container. The resulting package is placed in the directory the tool was called from.

## Usage
The included dmakepkg.py script wraps calling of `docker run` and the necessary arguments.
It has several arguments that can be passed.

```
bin/dmakepkg.py -h
usage: dmakepkg [-h] [-x] [-y] [-z] [-e [E]] ...

positional arguments:
  rest        The arguments that are passed to the call to pacman in its
              executions in the container. They default to "--nosign --force
              --syncdeps --noconfirm".

optional arguments:
  -h, --help  show this help message and exit
  -x          Use host system's /etc/pacman.conf
  -y          Never use pump mode, even if pump mode capable servers are
              configured
  -z          Do not automatically download missing PGP keys
  -Z          Do not copy the sources. Work directly in the package directory.
  -e [E]      Executes the argument as a command in the container after
              copying the package source

```

Using the tool could look like this:
```
$ git clone https://example.comf/project.git
$ cd project
$ dmakepkg
```

### Description of the arguments

* rest: The rest of the arguments that are not known to the script. They are passed through to the docker container's makepkg call.

* -h, --help: Display the help message
* -x: Pass in the host's pacman.conf into the docker image.
* -y: Force disabling of pump mode. By default, distcc `pump` mode is used to accelerate the compiling of code.
* -z: Do not download missing PGP keys. By default, the downloading of missing PGP keys is _enabled_.
* -Z          Do not copy the sources. Work directly in the package directory.
* -e [E]: This executes the passed string as command in the container after copying of the package source. This can be used to, for example, install prerequired packages or perform arbitrary actions in the container.

## The docker image
The docker image that is used to build must be built prior to calling the script.
The image is built using the `containerBuilder.py` script that is started by the packaged systemd service.
The associated timer unit thus builds the image 15 minutes after the system was booted and every day.
During the building of the image, a darkhttpd based cache is used to accelerate the download of the packages. This is implemented by starting darkhttpd on the IP address of the docker0 device and installing of an iptables rule that permits connections to that address and the port of darkhttpd.
After the tool has finished building, the iptables rules are removed and darkhttpd is stopped.
