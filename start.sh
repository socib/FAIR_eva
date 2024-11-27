#!/bin/bash

CONFIG_FILE=config.ini
if [ $# -gt 0 ] && [ -f "$1" ]; then
    CONFIG_FILE=$1
else
    echo "<$CONFIG_FILE> does not exist, using default path (config.ini)"
fi

python web.py -c $CONFIG_FILE &
python fair.py &
wait -n
exit $?
