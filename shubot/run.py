import argparse
import logging

from mashumaro.codecs.yaml import yaml_decode

from shubot.bot import ShuBot
from shubot.config import Config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


def start_bot(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml_decode(f.read(), Config)

    logging.info("init bot...")
    bot = ShuBot(config)
    bot.run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="config file path", default="config.yaml"
    )
    args = parser.parse_args()
    start_bot(config_path=args.config)


if __name__ == "__main__":
    main()
