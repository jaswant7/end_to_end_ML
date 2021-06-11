import logging
import logging.config
from pathlib import Path

import mlflow
import pretty_errors 
from rich.logging import RichHandler

from tagifai import utils

#Directories
BASE_DIR = Path(__file__).parent.parent.absolute()
CONFIG_DIR = Path(BASE_DIR,"config")
LOGS_DIR = Path(BASE_DIR, "logs")
ASSETS_DIR = Path(BASE_DIR, "assets")
DATA_DIR = Path(ASSETS_DIR, "data")
EXPERIMENTS_DIR = Path(ASSETS_DIR, "experiments")

# Create dirs
utils.create_dirs(dirpath=LOGS_DIR)
utils.create_dirs(dirpath=ASSETS_DIR)
utils.create_dirs(dirpath=DATA_DIR)
utils.create_dirs(dirpath=EXPERIMENTS_DIR)

# Loggers
logging.config.fileConfig(Path(CONFIG_DIR, "logging.config"))
logger = logging.getLogger()
logger.handlers[0] = RichHandler(markup=True)  # set rich handler

# MLFlow
mlflow.set_tracking_uri("file://" + str(EXPERIMENTS_DIR.absolute()))

# Exclusion criteria
EXCLUDE = [
    "machine-learning",
    "deep-learning",
    "data-science",
    "neural-networks",
    "python",
    "r",
    "visualization",
    "wandb",
]