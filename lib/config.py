import yaml
import sys
from box import Box


def load_config(conffile):
    try:
        with open(conffile) as f:
            data = yaml.safe_load(f)
    except Exception as ex:
        print(f"Couldn't load config file: {str(ex)}")
        sys.exit(2)

    return Box(data)
