# ASR Clients
This repo contains two python clients for Emotech ASR service: Streaming client and non streaming client.
If you just need to run inference on some `wav` files, then it's recommended to use the non-streaming client for best accuracy.
However, if you need to capture your microphone input and do inference on it, then streaming client might be your choice.


# Streaming Client Documentation
## Command Line Arguments

You can run `python3 streaming_client.py --help` to see the available command line arguments. Some of them have default options.
```text
usage: streaming_client.py [-h] [--request-id REQUEST_ID] [--sample-rate SAMPLE_RATE] [--encoding {s16,s32,f32,f64}] [--language LANGUAGE] [--base64] [--keep-connection]
                           --auth-token AUTH_TOKEN [--channels {1,2}] [--rtf-threshold RTF_THRESHOLD] [--silence-threshold SILENCE_THRESHOLD]
                           [--partial-interval PARTIAL_INTERVAL]

optional arguments:
  -h, --help            show this help message and exit
  --request-id REQUEST_ID
                        Request id. [DEFAULT] empty
  --sample-rate SAMPLE_RATE
                        Audio sample rate. [DEFAULT 16000]
  --encoding {s16,s32,f32,f64}
                        Audio sample encoding. [DEFAULT] f32
  --language LANGUAGE   Inference language, [Default] auto
  --base64              Whether to transfer base64 encoded audio or just a binary stream
  --keep-connection     Whether to keep ws connected after inference finished
  --auth-token AUTH_TOKEN
                        Your Emotech authorization token, include it for every request
  --channels {1,2}      Number of channels to send to the server
  --rtf-threshold RTF_THRESHOLD
                        Threshold to cancel a Whisper inference task. [DEFAULT] 0.3
  --silence-threshold SILENCE_THRESHOLD
                        Required silence duration in ms after a speech before auto termination. [DEFAULT] 600
  --partial-interval PARTIAL_INTERVAL
                        Partial transcription will be generated every x ms. [DEFAULT] 500
```

### `--base64`
Toggle this on to transfer `base64` encoded audio data.

### `--keep-connection`
Toggle this on to prevent server from closing your websocket communication after inference finished.

### `--auth-token`
The token you get from Emotech, It's used to validate who you are.

## How To Use
The client uses three open-source library as dependencies:
- [pyaudio](https://pypi.org/project/PyAudio/), MIT license.
- [websockets](https://pypi.org/project/websockets/), BSD license.


You can install them via `pip3 install -r requirements.txt`

### Troubleshooting
`pyaudio` might failed with a single `pip` command as it relies on other libraries. Here is a detailed instruction on fixing it:

On MacOS:
```shell
# Install brew, skip if you have it already.
mkdir homebrew && curl -L https://github.com/Homebrew/brew/tarball/master | tar xz --strip 1 -C homebrew

brew install portaudio
pip3 install pyaudio
```

On Linux:
```shell
sudo apt-get install libasound-dev portaudio19-dev libportaudio2 libportaudiocpp0
sudo apt-get install ffmpeg libav-tools
pip3 install pyaudio
```

On Windows:
```shell
pip install pipwin
pipwin install pyaudio
```

## Example
```shell
python3 streaming_client.py --auth-token=<YOUR_TOKEN>
```
This will capture audio from your microphone until the server finds a whole sentence. After that, server will close the connection.

```shell
python3 streaming_client.py --auth-token=<YOUR_TOKEN> --keep_connection
```
This will capture audio from your microphone *FOREVER* until you terminate it with `Ctrl+C`.


# Non Streaming Client
## Command Line Arguments
You can run `python3 non_streaming_client.py --help` to see the available command line arguments. Some of them have default options.
```text
usage: non_streaming_client.py [-h] --auth-token AUTH_TOKEN --file FILE [--language LANGUAGE] [--version]

optional arguments:
  -h, --help            show this help message and exit
  --auth-token AUTH_TOKEN
                        Authorization token get from Emotech LTD
  --file FILE           Path to the file to be assessed
  --language LANGUAGE   Specity the language to assess. [Default] auto
  --version             Get ASR server version
```

Example:
```shell
python3 non_streaming_client.py --file=<PATH/TO/FILE> --auth-token=<YOUR_TOKEN> --language=en
```


## Test Environment
The clients are tested in MacOS, Ubuntu, Windows.

The clients are tested in Python 3.9, Python 3.11.
