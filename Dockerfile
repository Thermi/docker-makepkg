FROM archlinux/base:latest
LABEL org.thermicorp.tool=docker-makepkg
RUN echo -e "[multilib]\nInclude = /etc/pacman.d/mirrorlist" >> /etc/pacman.conf
RUN pacman --noconfirm -Sy archlinux-keyring && pacman-key --init && pacman-key --populate archlinux

RUN /bin/bash -c 'cat <(echo Server = http://172.16.33.1:8990) /etc/pacman.d/mirrorlist > foobar && mv foobar /etc/pacman.d/mirrorlist && pacman -Syuq --noconfirm --needed procps-ng gcc base-devel distcc python git mercurial bzr subversion openssh && rm -rf /var/cache/pacman/pkg/* && cp /etc/pacman.d/mirrorlist foo && tail -n +2 foo > /etc/pacman.d/mirrorlist'
RUN useradd -m -d /build -s /bin/bash build-user
ADD sudoers /etc/sudoers
WORKDIR /build
VOLUME "/src"
ADD run.py /run.py
ADD gnupg.conf /build/.gnupg/gnupg.conf
ENTRYPOINT ["/run.py"]
