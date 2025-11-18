# A Simple Command Line Background Changer

## install

```bash
pipx install . [--force]
```

## Run

```bash
RBG [-h|--help] [-S|-size RESOLUTION] [-L|--log-level LEVEL] [-s|--sleep SECONDS] [-n|--notify] [--version] PATH [PATH[PATH[...]]]
```

Scan directory trees in PATH for images and randomnly display them changing every SECONDS.
RESOLUTION overrides detected resolution
LEVEL set program log level (debug, info, warning)
notify uses notification on directories to indicate they should be reloaded
help gives help
version shows you version
When it exits it loads the default background (~/Documents/RSBG.*)
its working directory is ~/.bg
These settings and other settings can be found in common

```bash
SetBG [-h|--help] [-S|-size RESOLUTION] [-L|--log-level LEVEL] [--version] Image
```

SetBG sets and image on the background.
options aste as above

```bash
RBGN [-h|--help] [-S|--size SIZE] [--version] [-L {info,warning,debug}] [-x]|--exit
'''

RBGN tells RBG to change teh background now or exit if -x or --exit is provided.
Other options other than SIZE are as above
SIZE is ignored
