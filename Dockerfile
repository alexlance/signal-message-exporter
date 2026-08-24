FROM debian:bookworm

RUN apt-get update
RUN apt-get install -y git
RUN apt-get install -y g++
RUN apt-get install -y libssl-dev
RUN apt-get install -y libsqlite3-dev
RUN apt-get install -y build-essential
RUN apt-get install -y python3
RUN apt-get install -y python3-setuptools

RUN git clone https://github.com/bepaald/signalbackup-tools
RUN apt install -y cmake pkg-config dbus libdbus-1-dev
RUN cd signalbackup-tools && cmake -B build -DCMAKE_BUILD_TYPE=Release
RUN cd signalbackup-tools && cmake --build build -j $(nproc)
RUN cd signalbackup-tools && ./BUILDSCRIPT.bash
RUN mv signalbackup-tools/signalbackup-tools /usr/bin/ && chmod a+x /usr/bin/signalbackup-tools
RUN rm -rf signalbackup-tools

WORKDIR /root
