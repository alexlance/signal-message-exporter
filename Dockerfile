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
RUN cd signalbackup-tools && ./BUILDSCRIPT.sh
RUN mv signalbackup-tools/signalbackup-tools /usr/bin/ && chmod a+x /usr/bin/signalbackup-tools
RUN rm -rf signalbackup-tools

WORKDIR /root
