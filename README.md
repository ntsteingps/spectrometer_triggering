# spectrometer_triggering

## Overview

This repository contains python code to connect to a Headwall Nano-Hyperspec
spectrometer over its network interface, and send commands to control it and
retrieve recorded data.

## Install

1. Clone the repository in the desired location on the target system. When
   cloning to a production system, be sure to use a revocable deploy key with
   minimum access right.
    ```bash
    git clone git@github.com:maargenton/caltech-spectrometer.git spectrometer
    cd spectrometer
    ```
2. Create a symbolic link to the main command in one of the system paths, e.g.:
    ```sh
    ln -fs $(pwd)/spectrometer/spectrometerctl /usr/local/bin/spectrometerctl
    ```
3. Verify the installation
    ```sh
    spectrmeterctl status
    ```
    With the spectrometer powered on and connected, this command should connect
    to the spectrometer and get its current status. In case of an issue the
    command or one of its dependencies, an error should be reported immediately.
    If everything is setup correctly by the spectrometer is unreachable or
    unresponsive, the command should be continuously attempting to connect.

## Usage

1. Copy `sample_config.json` or create the desired configuration file as e.g.
   `config.json` file.
2. To configure the spectrometer and start the capture session:
    ```
    spectrometerctl capture sample_config.json
    ```
    Note the path to capture folder displayed by the command
3. When the capture session is complete:
    ```
    spectrometerctl stop
    ```
4. To download the files into your local data folder
    ```
    spectrometerctl cp -R /imgs/100009 data
    ```
5. To delete the files on the instrument that have been copied over:
    ```
    spectrometerctl rm -R /imgs/100009
    ```



## Code layout

### connection.py

Defines a `Connection` class that manages the connection with the spectrometer
instrument. It provides a non-blocking IO interface, with the ability to read
the input stream up to a specific sequence of characters, typically the command
prompt that follows the instrument response.

Because the instrument is sometimes unresponsive, all read operations are
controlled by both an operation timeout and a minimal timeout for each
individual read operation.

### spectrometer.py

Defines a `Spectrometer` class that exposes a single `call()` function to
perform all RPC-like operations. The actual underlying socket connection is
established automatically as needed, allowing simple retires in case of
connection loss.

Each call starts by sending the command with its optional parameters, followed
by a response phase. The response is composed of 3 parts:
- An optional binary payload
- A JSON payload
- A command prompt to signal that the instrument is ready for the next command.

To handle all cases properly, the call() function gathers all the response data
up to and including the next command prompt, then splits it into the
corresponding parts.

Unlike http that has a clearly defined payload size for all types of response
(including binary data), the spectrometer protocol contains no preamble
indicating the size of the binary part of the data, and this size does not
always match the requested size. The logic to locate the end of the binary data
looks for the last occurrence of the binary sequence `\r\n{`, which marks the
beginning of the JSON response, usually. This method appears to work reliably
during testing, because the JSON payload contains `\n` line endings.


### spectrometerctl

This is a python binary intended as the primary entry point to interface with
the instrument. It provides a command-line interface for all spectrometer
operations.
