
DOCKER := docker run -e SIG_KEY -e SIG_FILE -it -v $${PWD}:/root/ workspace

run:
	docker build -t workspace .
	$(DOCKER) python3 signal-message-exporter.py

